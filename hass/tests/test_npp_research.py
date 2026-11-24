"""S4 contracts. Reuse NPP-A's case data; drive the real stage and HTTP/model adapters offline."""
from datetime import date
from html import escape
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from hass import maker_site
from hass.npp import assets, research_hermes as adapter

CASES = Path(__file__).with_name("npp") / "cases"
HOME = "https://minersfigs.example/"
ABOUT = HOME + "about"
DAY = date(2026, 11, 18)


def fixture(number, variant=0):
    case = json.loads(next(CASES.glob(f"case-{number:02}-*.json")).read_text())
    inputs = case.get("inputs", {})
    return inputs | (case["variants"][variant]["inputs"] if "variants" in case else {})


class World:
    def __init__(self, inputs=None, *, verdicts=None):
        inputs = inputs or {}
        self.urls, self.requests, self.now = [], [], 0.0
        self.p = assets()
        web = inputs.get("web", {})
        self.searches = web.get("search", {})
        self.pages: dict[str, tuple] = {
            u: (200, p["content_type"], (CASES / p["file"]).read_bytes()) for u, p in web.get("pages", {}).items()
        }
        self.forbidden = web.get("forbid_fetch", [])
        self.stubs = inputs.get("stubs", {})
        self.verdicts = verdicts or {}
        self.web = adapter.Web(get=self.get, clock=lambda: self.now, sleep=self.sleep, today=lambda: DAY)

    def sleep(self, seconds):
        self.now += seconds

    def get(self, url, headers, timeout):
        self.urls.append(url)
        if url in self.forbidden:
            raise AssertionError(f"forbidden fetch: {url}")
        if url.endswith("/robots.txt"):
            return self.pages.get(url, (200, "text/plain", b"User-agent: *\nDisallow:"))
        if url.startswith(adapter.SEARCH):
            query = parse_qs(urlsplit(url).query)["q"][0]
            links = ''
            for result in self.searches[query]:
                href = "//duckduckgo.com/l/?" + urlencode({"uddg": result["url"]})
                links += f'<a class="result__a" href="{escape(href)}">{escape(result["title"])}</a>'
            return 200, "text/html", (links + "<p>Untrusted Search Snippet</p>").encode()
        return self.pages.get(url, (404, "text/plain", b""))

    def model(self, req):
        _, payload, _ = req["text"].splitlines()
        data = json.loads(payload)
        self.requests.append((req, data))
        if "pages" in data:
            if "extract" not in self.stubs:
                raise AssertionError("unexpected extraction")
            out = {"facts": self.stubs["extract"]}
        else:
            default = self.stubs.get("verify", "supports")
            if isinstance(default, dict):
                default = next((verdict for prefix, verdict in default.items() if data["quote"].startswith(prefix)),
                               default["default"])
            out = {"verdict": self.verdicts.get(data["value"], default)}
        return {"ok": True, "text": json.dumps(out), "model": req["model"], "ms": 4}

    def run(self, **kwargs):
        with patch.object(maker_site, "_LAST", {}):
            return adapter.run(self.p, web=self.web, runner=self.model, clock=lambda: self.now, **kwargs)

    def maker(self, **kwargs):
        return self.run(owner_maker="Miners", owner_town="Paso Robles", **kwargs)


class ResearchTests(unittest.TestCase):
    def test_discovery_uses_only_addresses_and_visible_cited_facts(self):
        # Case 29: a search snippet, nav, hidden DOM or metadata must not become evidence.
        world = World(fixture(29))
        world.searches.setdefault("Miners official site", [])
        status, kind, markup = world.pages[HOME]
        world.pages[HOME] = status, kind, markup.replace(b"</body>", b'''
            <script>Miners makes jam.</script>
            <p hidden>Miners makes bread.</p>
            <p style="display: none">Miners makes tea.</p>
            <footer><p>Miners makes syrup.</p></footer>
            </body>''').replace(b"</head>", b'<meta name="description" content="Miners makes nuts."></head>')
        for food in ("jam", "bread", "tea", "syrup", "nuts"):
            world.stubs["extract"].append(dict(slot="makes", value=food, url=HOME, quote=f"Miners makes {food}."))
        result = world.maker()
        self.assertFalse(result.facts)
        self.assertEqual({row["reason"] for row in result.receipt["facts"]}, {"quote-not-in-visible-body-text"})
        self.assertEqual(result.receipt["chosen_domain"], "minersfigs.example")
        self.assertEqual(result.receipt["queries"], ["Miners Paso Robles official site", "Miners official site"])
        self.assertEqual(len(world.requests), 1)
        self.assertNotIn("Untrusted Search Snippet", world.requests[0][0]["text"])

    def test_owner_url_checks_quote_then_separately_verifies_typed_fact(self):
        # Case 30: even a source explicitly given by the owner cannot authorize old or negated facts.
        world = World(fixture(30))
        status, _, body = world.pages[ABOUT]
        world.pages[ABOUT] = status, "Text/HTML; charset=utf-8", body
        result = world.maker(owner_url=ABOUT)
        self.assertEqual([(f["slot"], f["value"]) for f in result.story_facts], [("nature", "orchard"), ("makes", "dried figs")])
        self.assertEqual(result.story_facts[0], {"id": "official-nature", "slot": "nature", "value": "orchard",
                         "quote": "Miners is an orchard in Paso Robles.", "url": ABOUT, "retrieved": DAY.isoformat()})
        self.assertEqual(result.receipt["queries"], [])
        self.assertEqual([f["reason"] for f in result.receipt["facts"]].count("negation-past-or-hedge-marker"), 2)
        extract, *verifiers = world.requests
        self.assertEqual(len(verifiers), 2)
        for request, data in verifiers:
            self.assertNotEqual(extract[0]["instructions"], request["instructions"])
            self.assertEqual(set(data), {"maker", "slot", "value", "quote"})
            self.assertEqual(request["images"], [])

        # Only a declared HTML media type may supply evidence. A substring check
        # admits this non-HTML response and sends the unchanged body for extraction.
        world = World(fixture(30))
        world.pages[ABOUT] = status, "application/x-text/html", body
        result = world.maker(owner_url=ABOUT)
        self.assertIn(ABOUT, world.urls)
        self.assertFalse(result.story_facts)
        self.assertEqual(world.requests, [])

    def test_label_seed_can_supply_identity_and_founded_year_from_official_text(self):
        # Losing label-only discovery (or blocking public calendar years as owner finance) loses real sourced slots.
        world = World()
        world.searches = {"Miners official site": [{"url": HOME, "title": "Discard me"}]}
        world.pages[HOME] = (200, "text/html", b'''<title>Miners</title><h1>Miners</h1>
          <p>Miners was founded in 1984.</p><p>Miners is based in Paso Robles.</p>
          <footer>Copyright Miners.</footer>''')
        world.stubs["extract"] = [dict(slot=slot, value=value, url=HOME, quote=quote) for slot, value, quote in (
            ("name", "Miners", "Miners"), ("town", "Paso Robles", "Miners is based in Paso Robles."),
            ("founded", "1984", "Miners was founded in 1984."))]
        result = world.run(label_brand="Miners", label_confidence=0.95)
        self.assertEqual({f["slot"]: f["value"] for f in result.facts}, {"name": "Miners", "town": "Paso Robles", "founded": "1984"})
        self.assertEqual(result.receipt["queries"], ["Miners official site"])
        self.assertEqual(result.receipt["seed"]["source"], "label")

    def test_injection_does_not_license_claims_and_unsafe_seeds_never_leave_host(self):
        # Case 31: untrusted page instructions have no authority; conflicting/absent/private seeds cause no egress.
        world = World(fixture(31))
        result = world.maker()
        self.assertEqual({f["value"] for f in result.facts}, {"dried figs"})
        for fields in (dict(known=True, owner_maker="Miners"), dict(label_brand="Miners", label_confidence=0.79),
                       dict(owner_maker="Miners", label_brand="Other Farm", label_confidence=0.9),
                       dict(owner_maker="Miners cost 73"), dict(owner_maker="Miners", owner_town="Case of twelve")):
            with self.subTest(fields=fields):
                world = World()
                self.assertFalse(world.run(**fields).facts)
                self.assertEqual((world.urls, world.requests), ([], []))

    def test_wrong_town_and_multiple_official_looking_domains_do_not_get_a_story(self):
        # Case 37: no first-result or similar-name shortcut before code checks identity.
        for variant, reason in enumerate(("no-confirmed-site", "two-passing-domains")):
            with self.subTest(variant=variant):
                world = World(fixture(37, variant))
                result = world.maker()
                self.assertFalse(result.facts)
                self.assertEqual(result.receipt["outcome"], reason)
                self.assertEqual(world.requests, [])
                if not variant:
                    self.assertEqual(result.receipt["identity"][0]["reason"], "different-base-town")

    def test_directory_prefilter_and_retailer_identity_are_not_bypassed_by_owner_url(self):
        # Case 38: a denied host must never be contacted, and a third-party merchant cannot become evidence.
        world = World(fixture(38))
        world.searches.setdefault("Miners official site", [])
        result = world.maker()
        self.assertEqual([row["reason"] for row in result.receipt["identity"]], ["denied-domain", "not-the-makers-own-site"])
        vendor = next(iter(world.pages))
        self.assertIn(vendor, world.urls)
        self.assertFalse(world.maker(owner_url=vendor).facts)
        self.assertEqual(world.requests, [])

    def test_conflict_and_refused_entailment_drop_only_unsupported_slots(self):
        # An extractor's highest-ranked value must not win a disagreement or a non-supporting second verdict.
        world = World(fixture(30), verdicts={"orchard": "unclear"})
        status, kind, body = world.pages[ABOUT]
        body = body.replace(b"</body>", b"<p>Miners makes preserves.</p></body>")
        world.pages[ABOUT] = status, kind, body
        world.stubs["extract"].append(dict(slot="makes", value="preserves", url=ABOUT, quote="Miners makes preserves."))
        result = world.maker(owner_url=ABOUT)
        self.assertFalse(result.story_facts)
        self.assertEqual([row["reason"] for row in result.receipt["facts"]].count("conflicting-values"), 2)
        self.assertEqual(result.receipt["facts"][0]["verifier"], "unclear")

    def test_robots_cross_site_redirect_and_stage_deadline_fail_closed(self):
        # No alternate HTTP path, unauthorized redirect, or late result may publish a fact.
        for mode in ("robots", "redirect", "late"):
            with self.subTest(mode=mode):
                world = World(fixture(30))
                if mode == "robots":
                    world.pages[HOME + "robots.txt"] = 200, "text/plain", b"User-agent: *\nDisallow: /about"
                elif mode == "redirect":
                    world.pages[ABOUT] = 302, "", b"", "https://unrelated.example/about"
                else:
                    orig = world.model

                    def late(req):
                        if world.requests:
                            world.sleep(40)
                        return orig(req)

                    world.model = late
                self.assertFalse(world.maker(owner_url=ABOUT).facts)
                self.assertNotIn("https://unrelated.example/about", world.urls)
                self.assertNotIn("https://unrelated.example/robots.txt", world.urls)
                if mode == "robots":
                    self.assertNotIn(ABOUT, world.urls)
                if mode != "late":
                    self.assertEqual(world.requests, [])

    def test_same_site_about_link_supplies_evidence_at_final_canonical_url(self):
        # Redirect provenance must agree with the final URL; external about links must not be followed.
        world = World(fixture(30))
        world.pages[HOME] = 200, "text/html", (CASES / "pages/miners-home-clean.html").read_bytes().replace(
            b"</nav>", b'<a href="https://[broken/about">Broken</a>'
            b'<a href="https://unrelated.example/about">About</a><a href="/about">About</a></nav>')
        canonical = HOME + "our-story"
        world.pages[canonical] = world.pages[ABOUT]
        world.pages[ABOUT] = 301, "", b"", "/our-story"
        world.stubs["extract"] = [dict(world.stubs["extract"][0], url=canonical)]
        result = world.maker(owner_url=HOME)
        self.assertEqual([f["url"] for f in result.story_facts], [canonical])
        self.assertFalse(any("unrelated.example" in url for url in world.urls))

    def test_retailer_that_contains_the_makers_name_is_not_the_official_site(self):
        # Contract: official-site evidence needs the page's owner to BE the maker (name plus no seller word) and the
        # page's own text must not call itself a shop/reseller/unofficial. Bug: a substring test on "Miners Shop"
        # with a matching title and copyright accepted a third-party shop and returned its quote as an official fact.
        shop = (b"<title>%s</title><h1>%s</h1><p>%s</p><p>Miners makes jam.</p><footer>&copy; %s. All rights reserved.</footer>")
        for title, owner, line in (
            (b"Miners Shop", b"Miners Shop", b"Miners Shop is an independent shop selling Miners products."),
            (b"Miners", b"Miners", b"We are an independent shop selling Miners products."),
            (b"Miners", b"Miners", b"This site is not affiliated with the makers of Miners."),
            (b"Miners", b"Miners", b"Miners products are available from our store."),
            (b"Miners Shop", b"Miners Shop", b"Welcome."),
            # Not blacklisted by any seller word: only the affirmative owner test and the body can reject these.
            (b"Miners Delicatessen", b"Miners Delicatessen",
             b"We are an independent grocery. Miners is one of our brands."),
            (b"Miners Delicatessen", b"Miners Delicatessen", b"Welcome."),
            (b"Miners Farm Market", b"Miners Farm Market", b"Welcome."),
            (b"Miners", b"Miners", b"We are an independent grocery. Miners is one of our brands."),
            (b"Miners", b"Miners", b"We are an independent delicatessen."),
        ):
            with self.subTest(line=line):
                world = World()
                world.searches = {"Miners official site": [{"url": HOME, "title": "x"}]}
                world.pages[HOME] = 200, "text/html", shop % (title, title, line, owner)
                world.stubs["extract"] = [dict(slot="makes", value="jam", url=HOME, quote="Miners makes jam.")]
                result = world.run(owner_maker="Miners")
                self.assertFalse(result.facts)
                self.assertEqual(result.receipt["outcome"], "no-confirmed-site")
                self.assertEqual(result.receipt["identity"][0]["reason"], "not-the-makers-own-site")
                self.assertEqual(world.requests, [])

    def test_genuine_maker_owner_names_are_still_the_official_site(self):
        # Control for the affirmative-ownership test: the maker's own name, with a company form or producer word,
        # in matching title and copyright, and no third-party wording, is still accepted and its fact returned.
        page = (b"<title>%s</title><h1>%s</h1><p>We are %s.</p><p>Miners makes jam.</p>"
                b"<footer>&copy; %s. All rights reserved.</footer>")
        for owner in (b"Miners", b"Miners Orchards", b"Miners Dried Fruit", b"Miners Family Farm"):
            with self.subTest(owner=owner):
                world = World()
                world.searches = {"Miners official site": [{"url": HOME, "title": "x"}]}
                world.pages[HOME] = 200, "text/html", page % (owner, owner, owner, owner)
                world.stubs["extract"] = [dict(slot="makes", value="jam", url=HOME, quote="Miners makes jam.")]
                result = world.run(owner_maker="Miners")
                self.assertEqual(result.receipt["identity"][0]["reason"], "official")
                self.assertEqual([(f["slot"], f["value"]) for f in result.facts], [("makes", "jam")])
