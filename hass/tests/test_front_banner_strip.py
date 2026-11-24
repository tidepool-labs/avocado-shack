"""AVB-19: unit pin for sitegen.front_banner(), the home top strip and the banner swap.

Contract: with no saved banner the shop's default strip is rendered byte for byte (and no script); with one, both
lines are rendered, only the line for the build day is visible, and BANNER_JS is added. Synthetic stores only; the
real templates are read from hass/templates. Run: python3 -B -m unittest hass.tests.test_front_banner_strip -v
"""
import unittest
from datetime import date

from hass import sitegen
from hass.content_model import REPO_ROOT

TEMPLATES = REPO_ROOT / "hass" / "templates"
DAY = date(2026, 11, 24)
TEXT = "Closed Thursday"
BANNER = {"text": TEXT, "start": "2026-11-24", "end": "2026-11-26"}


def strip(href):
    return ('<div class="preview"><span>GOOD FOOD. CLOSE TO HOME.</span>'
            '<a href="%s">Come visit the Shack \u2197</a></div>' % href)


def render(store, rel="index.html"):
    return sitegen.front_banner(store, TEMPLATES, rel, DAY)


def banner_div(html_text):
    """The saved-banner <div> (the one carrying data-banner), without the default strip before it."""
    return html_text[html_text.index('<div class="preview" data-banner data-start'):]


class FrontBannerStripTests(unittest.TestCase):
    # Protects: the no-banner strip stays byte for byte. Fails if the copy, arrow or #visit vs /#visit changes.
    def test_default_strip_exact_both_pages(self):
        for rel, href in (("index.html", "#visit"), ("hike/index.html", "/#visit")):
            with self.subTest(rel=rel):
                self.assertEqual(render({}, rel), {"front.bannerHtml": strip(href), "front.bannerScript": ""})

    # Protects: the live banner shows and the default hides. Fails if the hidden flag lands on the wrong line.
    def test_live_banner_swaps_visibility(self):
        for day in ("2026-11-24", "2026-11-26"):  # first and last day are both live
            with self.subTest(end=day):
                html = render({"banner": {**BANNER, "start": "2026-11-23", "end": day}})["front.bannerHtml"]
                self.assertTrue(html.startswith(strip("#visit").replace('"preview"', '"preview" data-banner-default hidden', 1)))
                self.assertIn('data-start="2026-11-23" data-end="%s">' % day, banner_div(html))
                self.assertNotIn("hidden", banner_div(html))
        html = render({"banner": BANNER})["front.bannerHtml"]
        self.assertEqual(banner_div(html), '<div class="preview" data-banner data-start="2026-11-24" '
                         'data-end="2026-11-26"><span>Closed Thursday</span></div>')

    # Protects: a banner that is not live today leaves the default visible. Fails if hidden flips for those days.
    def test_future_and_past_banner_keep_default_visible(self):
        for name, start, end in (("future", "2026-11-30", "2026-12-02"), ("past", "2026-11-01", "2026-11-23")):
            with self.subTest(name):
                html = render({"banner": {**BANNER, "start": start, "end": end}}, "hike/index.html")["front.bannerHtml"]
                self.assertTrue(html.startswith(strip("/#visit").replace('"preview"', '"preview" data-banner-default', 1)))
                self.assertEqual(banner_div(html), '<div class="preview" data-banner data-start="%s" data-end="%s" hidden>'
                                 '<span>Closed Thursday</span></div>' % (start, end))

    # Protects: owner text cannot inject markup. Fails if html.escape is dropped; quotes stay literal in text.
    def test_banner_text_is_escaped(self):
        html = render({"banner": {**BANNER, "text": 'Fish <b> & "chips"'}})["front.bannerHtml"]
        self.assertIn('<span>Fish &lt;b&gt; &amp; "chips"</span>', html)
        self.assertNotIn("<b>", html)

    # Protects: the swap script ships only with a banner. Fails if it is added to (or dropped from) either case.
    def test_banner_script_only_with_banner(self):
        self.assertEqual(render({})["front.bannerScript"], "")
        for banner in (BANNER, {**BANNER, "start": "2026-11-30", "end": "2026-12-02"}):
            self.assertEqual(render({"banner": banner})["front.bannerScript"], sitegen.BANNER_JS)

    # Protects: the optional link is rendered only when banner_link returns one (a hidden page gives none).
    def test_banner_link_only_when_banner_link_returns_one(self):
        link = '<a href="/about/">Find out more \u2197</a></div>'
        for name, banner, store, want in (
                ("no link key", BANNER, {}, False), ("unknown key", {**BANNER, "link": "nope"}, {}, False),
                ("page hidden", {**BANNER, "link": "about"}, {"pageAbout": {"shown": False}}, False),
                ("page shown", {**BANNER, "link": "about"}, {"pageAbout": {"shown": True}}, True)):
            with self.subTest(name):
                html = banner_div(render({**store, "banner": banner})["front.bannerHtml"])
                self.assertEqual(html.endswith("</span>" + link), want)
                self.assertEqual("Find out more" in html, want)


if __name__ == "__main__":
    unittest.main()
