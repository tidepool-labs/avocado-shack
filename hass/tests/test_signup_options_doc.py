"""AV2137-10 (H25-forms): docs/hass/SIGNUP-OPTIONS.md explains the open signup-destination choice without making it.
Stdlib, offline: it reads the page and repository sources only; no database, browser, service, network or participant
data is opened. The tests prove the document contract, not a mailing integration.
Run: python3 -m unittest hass.tests.test_signup_options_doc -v
"""
import re
import unittest
from pathlib import Path

from hass.tests.test_trial_handover_doc import ANCHORS as HANDOVER_ANCHORS, h25_forms_problems, handover_rows

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "hass"
PAGE = DOCS / "SIGNUP-OPTIONS.md"
HANDOVER = DOCS / "HANDOVER.md"
SERVER = "storefront-mockup/community-server.py"
JS = "storefront-mockup/community.js"

FORMS = ("Home-page newsletter", "Hiking updates", "Real hike RSVP", "Sample RSVP")
FORM_HEADER = ["Form", "Where", "What the visitor enters or ticks", "Separate choices", "What the local service saves"]
# form -> (column, phrase that cell must say). Each phrase is written here from the sources, not from the page.
FORM_FACTS = {
    "Home-page newsletter": ((2, "starts unticked"), (3, "pressing the button is the newsletter choice"),
                             (3, "hiking updates yes only if the box is ticked"), (4, "consent version label")),
    "Hiking updates": ((2, "no tick boxes"), (3, "it sends newsletter no and hiking yes"), (3, "never joins the newsletter")),
    "Real hike RSVP": ((2, "up to 120 characters"), (2, "from 1 to 6"), (3, "no consent box"),
                       (3, "does not join either list"), (4, "internal row number")),
    "Sample RSVP": ((3, "none"), (4, "nothing"), (4, "no details were saved or sent")),
}
OPTIONS = ("Keep them closed", "Run the existing club service on the chosen host", "A mailto link to the shop",
           "An outside mailing-list service (unnamed)")
OPTION_HEADER = ["Option", "What it would do", "Needed before launch", "Still open"]
PREREQ_HEADER = ["Option", "Sender mailbox and domain", "Unsubscribe handling", "Matching privacy text",
                 "Who reads the signups", "F08"]
# Each caveat is (name, a phrase the page must say, lower case, apostrophes straight).
CAVEATS = {
    "no decision": "records no decision", "no contact": "contacts no one", "no form change": "changes no form",
    "no launch": "authorizes no launch", "email disconnected": "email delivery is not connected",
    "closed message": "online signup isn't open yet", "static refuses before posting": "refused before anything is posted",
    "pending probe": "a submit in that moment waits for the answer and is then refused",
    "static sends nothing": "they send and save nothing", "sample browser only": "stays in the browser",
    "local only": "listens on the loopback address", "nothing is sent": "has no code that sends email",
    "no unsubscribe": "there is no unsubscribe", "merge adds choices": "repeat signups add choices",
    "rsvp is not a list signup": "an rsvp is not a mailing-list signup",
    "privacy dialog is closed text": "the local service does save",
    "closed needs no mail setup": "nothing to set up for sending, delivery or a mailbox merely to stay closed",
    "service not production": "not production-ready and not email-enabled", "no reader today": "there is no reader today",
    "sender is only proposed": "only proposed and is not an active mailbox",
    "mailto has no capacity-safe rsvp": "no capacity-safe rsvp", "mailto has no managed list": "no managed list",
    "list does not replace rsvp": "does not replace the rsvp service", "f08 is future": "f08 is future work",
    "saving is not sending": "saving a signup does not send one", "consents stay separate": "keeping the two consents separate",
    "no rank": "they are not ranked",
}
QUESTION_WORDS = ("destination", "mailbox", "reads", "unsubscribe", "data live", "kept", "consent", "rsvp", "launch")
POLICY = (r"\bwe recommend\b", r"\brecommended\b", r"\bour (?:pick|choice)\b", r"\bbest option\b", r"\bpreferred\b",
          r"\bwe chose\b", r"\bis hereby\b", r"\bdecided on\b", r"\bthe decision is\b", r"\blaunch date\s*:",
          r"\bsigned off by\b", r"\b(?:chosen|selected|agreed|approved) (?:option|destination|host) (?:is|will be|of)\b",
          r"\bretention period (?:is|of) \d", r"\banswers?\s*:")
VENDORS = (r"mailchimp", r"constant contact", r"sendgrid", r"mailgun", r"substack", r"buttondown", r"convertkit",
           r"klaviyo", r"brevo", r"sendinblue", r"postmark", r"\bgmail\b", r"\bgoogle\b", r"\boutlook\b", r"\bshopify\b",
           r"\bcloudflare\b", r"\bnetlify\b", r"\bamazon\b", r"\bgithub pages\b")
RECIPES = (r"\bcurl\b", r"\bsendmail\b", r"\bsmtp\b", r"\bsystemctl\b", r"\bsudo\b", r"\bpip install\b", r"\bpython3?\b",
           r"\bgit (?:push|commit)\b", r"\bmailto:", r"\bsubscribe (?:at|to) \w+\.\w+")
DELIVERED = (r"\b(?:confirmation|welcome) (?:email|message)s? (?:is|are|was|will be) sent\b",
             r"\bsends? (?:you |visitors )?(?:a |an )?(?:confirmation|welcome)\b", r"\bemail (?:is|has been|was) (?:sent|delivered)\b",
             r"\bmails? (?:is|are) delivered\b")
PRIVATE = (r"[\w.+-]+@[\w-]+\.[\w.]+", r"https?://", r"\bwww\.", r"\b[\w-]+\.(?:com|org|net|io|co)\b", r"\+?\d[\d ().-]{8,}\d",
           r"\b[0-9a-f]{12,}\b", r"(?<![\w-])/(?:home|Users|var|tmp|etc)/", r"~/", r"community\.sqlite3", r"community-data")
# (file the page links to, line) -> text that line must contain, so a moved anchor fails here.
ANCHORS = {
    (JS, 136): "No details were saved or sent", (JS, 144): "club-service", (JS, 165): "async function send(",
    (JS, 173): "newsletter:false,hikes:true", (JS, 174): "newsletter:true,hikes:e.currentTarget.hikes.checked",
    (JS, 177): "aria-disabled", (JS, 178): "/api/community/rsvps",
    (SERVER, 89): "emailConnected", (SERVER, 90): "def do_POST", (SERVER, 103): "/api/community/subscriptions",
    (SERVER, 108): "ON CONFLICT(email)", (SERVER, 112): "/api/community/rsvps",
    ("storefront-mockup/script.js", 14): "data-policy", ("hass/templates/home/newsletter.html", 1): "community-newsletter",
    ("hass/templates/hike/index.html", 24): "hike-updates",
    ("storefront-mockup/README.md", 47): "no email delivery", ("storefront-mockup/README.md", 49): "unsubscribe",
    ("docs/hass/FEATURES.md", 68): "| F08 |",
}
LINKED = (SERVER, JS, "storefront-mockup/script.js", "hass/templates/home/newsletter.html", "hass/templates/hike/index.html",
          "storefront-mockup/README.md", "docs/hass/FEATURES.md", "docs/hass/HANDOVER.md", "docs/hass/RETENTION-OPTIONS.md")


def source(rel: str) -> str:
    return (ROOT / rel).read_text("utf-8")


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u2019", "'").replace("**", "")).lower()


def tables(doc: str) -> dict:
    """{first header cell: [rows]} for each markdown table; the header row is rows[0]."""
    out, current = {}, None
    for line in doc.splitlines():
        if line.startswith("| ") and not line.startswith("| ---"):
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if current is None:
                current = out.setdefault(cells[0], [])
            current.append(cells)
        elif not line.startswith("| "):
            current = None
    return out


def form_problems(doc: str) -> list:
    rows = tables(doc).get("Form")
    if not rows or rows[0] != FORM_HEADER:
        return ["form table header is not the five expected columns"]
    if [r[0] for r in rows[1:]] != list(FORMS):
        return [f"forms are {[r[0] for r in rows[1:]]}"]
    problems = []
    for row in rows[1:]:
        if len(row) != 5:
            problems.append(f"{row[0]}: {len(row)} cells")
            continue
        for col, phrase in FORM_FACTS[row[0]]:
            if phrase not in squash(row[col]):
                problems.append(f"{row[0]}: {FORM_HEADER[col]} does not say '{phrase}'")
    return problems


def option_problems(doc: str) -> list:
    # Two tables start with "Option": the comparison and the one-by-one prerequisites.
    blocks, current, problems = [], None, []
    for line in doc.splitlines():
        if line.startswith("| ") and not line.startswith("| ---"):
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if cells[0] == "Option":
                current = [cells]
                blocks.append(current)
            elif current is not None:
                current.append(cells)
        elif not line.startswith("| "):
            current = None
    by_header = {tuple(b[0]): b for b in blocks}
    for header in (OPTION_HEADER, PREREQ_HEADER):
        rows = by_header.get(tuple(header))
        if rows is None:
            problems.append(f"no table with columns {header}")
            continue
        if [r[0] for r in rows[1:]] != list(OPTIONS):
            problems.append(f"{header[1]} table options are {[r[0] for r in rows[1:]]}")
        for row in rows[1:]:
            if len(row) != len(header):
                problems.append(f"{row[0]}: {len(row)} cells")
                continue
            for col in range(1, len(header)):
                if len(row[col]) < 20:
                    problems.append(f"{row[0]}: {header[col]} cell is thin")
    return problems


def caveat_problems(doc: str) -> list:
    text = squash(doc)
    return [name for name, phrase in CAVEATS.items() if phrase not in text]


def hits(patterns, text: str, flags=re.I) -> list:
    return [p for p in patterns if re.search(p, text, flags)]


def delivered_problems(doc: str) -> list:
    """Claims that mail goes out; a plain denial such as 'no confirmation email is sent' is removed first."""
    return hits(DELIVERED, re.sub(r"\bno (?:confirmation |welcome )?(?:email|mail)\b", "", doc, flags=re.I))


def policy_problems(doc: str) -> list:
    return hits(POLICY, doc) + hits(VENDORS, doc) + hits(RECIPES, doc)


def private_problems(doc: str) -> list:
    return hits(PRIVATE, doc, 0)


def question_problems(doc: str) -> list:
    if "## Questions Michael and G must answer" not in doc:
        return ["no questions section"]
    block = doc.split("## Questions Michael and G must answer", 1)[1].split("\n## ", 1)[0]
    items = re.findall(r"^(\d+)\. (.+)$", block, re.M)
    problems = [] if [n for n, _ in items] == [str(i) for i in range(1, 10)] else ["questions are not numbered 1-9"]
    problems += [f"question {n} is not a question" for n, text in items if "?" not in text]
    return problems + [f"nobody is asked about {w}" for w in QUESTION_WORDS if w not in block.lower()]


def link_problems(doc: str) -> list:
    problems, seen = [], set()
    for path, anchor in re.findall(r"\]\(([^)#\s]+)(?:#([\w-]+))?\)", doc):
        if path.startswith(("http", "mailto")):
            continue
        target = (DOCS / path).resolve()
        rel = target.relative_to(ROOT).as_posix()
        seen.add(rel)
        if not target.is_file():
            problems.append(f"{path} is not a file")
        elif anchor:
            if not re.fullmatch(r"L\d+", anchor):
                problems.append(f"{path}#{anchor} is not a line anchor")
                continue
            line = int(anchor[1:])
            lines = target.read_text("utf-8").splitlines()
            if not 1 <= line <= len(lines):
                problems.append(f"{path}#{anchor} is past the end")
            elif (rel, line) not in ANCHORS:
                problems.append(f"{path}#{anchor} is not a checked anchor")
            elif ANCHORS[rel, line].lower() not in lines[line - 1].lower():
                problems.append(f"{path}#{anchor} moved")
    return problems + [f"{need} is not linked" for need in LINKED if need not in seen]


class SignupOptionsDocTests(unittest.TestCase):
    def setUp(self):
        self.doc = PAGE.read_text("utf-8")

    def test_signup_forms_field_kinds_and_separate_consents(self):
        self.assertEqual(form_problems(self.doc), [])
        js, server = source(JS), source(SERVER)
        newsletter, hike = source("hass/templates/home/newsletter.html"), source("hass/templates/hike/index.html")
        # What the page script and the templates really do, so the table is checked against the code.
        self.assertIn("newsletter:false,hikes:true", js)
        self.assertIn("newsletter:true,hikes:e.currentTarget.hikes.checked", js)
        self.assertIn('<input type="checkbox" name="hikes">', newsletter)  # one tick box, not pre-ticked
        self.assertNotIn("checked", newsletter.replace("hikes.checked", ""))
        hike_form = re.search(r'<form id="hike-updates">.*?</form>', hike, re.S).group(0)
        self.assertEqual(hike_form.count("<input"), 1)
        self.assertNotIn("checkbox", hike_form)
        rsvp_body = re.search(r"send\(f,'/api/community/rsvps',\{([^}]*)\}\)", js).group(1)
        self.assertEqual(sorted(re.findall(r"(\w+):", rsvp_body)), ["email", "eventId", "name", "partySize"])
        self.assertIn("Math.min(6,event.remaining??6)", js)
        self.assertIn('maxlength="120"', js)
        self.assertIn("data.get('newsletter') is True", server)
        self.assertIn("MAX(subscriptions.newsletter,excluded.newsletter)", server)
        self.assertIn("CHECK(party_size BETWEEN 1 AND 6)", server)
        self.assertIn("len(name)>120", server)
        rsvp_handler = server.split("path=='/api/community/rsvps'", 1)[1].split("return self.reply(404", 1)[0]
        self.assertNotIn("subscriptions", rsvp_handler)  # an RSVP never touches either list
        for word in ("unsubscribe", "smtplib", "sendmail", "mailto"):
            self.assertNotIn(word, (server + js).lower())  # no way to leave a list, and nothing that mails
        for phrase in ("bookkeeping is not extra fields", "the consent version label is a stored word",
                       "pressing the button is the newsletter choice", "repeat signups add choices"):
            self.assertIn(phrase, squash(self.doc))
        # Mutations: hiking-only joins the newsletter; an RSVP becomes a subscription; a consent box appears.
        mutated = self.doc.replace("so it never joins the newsletter", "so it also joins the newsletter")
        self.assertIn("Hiking updates: Separate choices does not say 'never joins the newsletter'", form_problems(mutated))
        mutated = self.doc.replace("it does not join either list", "it joins the newsletter list")
        self.assertIn("Real hike RSVP: Separate choices does not say 'does not join either list'", form_problems(mutated))
        mutated = self.doc.replace("It has no consent box and ", "It has a consent box and ")
        self.assertIn("Real hike RSVP: Separate choices does not say 'no consent box'", form_problems(mutated))
        mutated = self.doc.replace("that starts unticked", "that starts ticked")
        self.assertIn("Home-page newsletter: What the visitor enters or ticks does not say 'starts unticked'", form_problems(mutated))
        no_sample = "\n".join(ln for ln in self.doc.splitlines() if not ln.startswith("| Sample RSVP |"))
        self.assertNotEqual(form_problems(no_sample), [])
        self.assertEqual(form_problems(""), ["form table header is not the five expected columns"])

    def test_static_closed_local_saved_sample_unsent(self):
        js, script = source(JS), source("storefront-mockup/script.js")
        self.assertIn("Online signup isn’t open yet, so nothing was sent or saved.", js)
        self.assertIn("Online signup isn’t open yet. Please say hello at the Shack instead.", js)
        self.assertLess(js.index("if(!await liveService()){status.textContent=SIGNUP_CLOSED;return false}"),
                        js.index("fetch(path,{method:'POST'"))  # the refusal comes before any post
        self.assertIn("x.disabled=true", js)  # the closed forms are disabled once no service answers
        self.assertIn("acceptsSubmissions===true", js)
        self.assertIn("No details were saved or sent.", js)
        self.assertIn("isn’t open yet", script)
        self.assertIn("don’t send or save", script)
        self.assertIn("'emailSent':False", source(SERVER))
        self.assertIn("ThreadingHTTPServer(('127.0.0.1'", source(SERVER))
        self.assertEqual(caveat_problems(self.doc), [])
        text = squash(self.doc)
        for phrase in ("no club service. the page does not even ask for one", "a plain static host without the marker",
                       "a visible form does not mean it works", "no active sender mailbox", "nothing is sent."):
            self.assertIn(phrase, text)
        self.assertEqual(delivered_problems(self.doc), [])
        for bad in ("A confirmation email is sent after each signup.", "The service sends a welcome message.",
                    "An email has been sent to the address.", "Mail is delivered each week."):
            with self.subTest(bad):
                self.assertNotEqual(delivered_problems(self.doc + "\n" + bad), [])
        for name, old, new in (("static sends nothing", "they send and save nothing", "they save signups"),
                               ("sample browser only", "stays in the browser", "is saved by the service"),
                               ("closed message", "Online signup isn't open yet. Please", "Signups are open. Please"),
                               ("nothing is sent", "has no code that sends email", "sends a confirmation")):
            with self.subTest(name):
                self.assertEqual(caveat_problems(self.doc.replace(old, new)), [name])

    def test_four_options_prerequisites_and_open_questions(self):
        self.assertEqual(option_problems(self.doc), [])
        self.assertEqual(question_problems(self.doc), [])
        self.assertNotRegex(self.doc.split("## The four options", 1)[1].split("\n## ", 1)[0].split("### ")[0].lower(),
                            r"\|\s*(?:recommended|default|selected|chosen)\s*\|")  # no ranking or selection column
        for option in OPTIONS:
            with self.subTest(option):
                gone = "\n".join(ln for ln in self.doc.splitlines() if not ln.startswith(f"| {option} |"))
                self.assertEqual(len(option_problems(gone)), 2)  # missing from both tables
        thin = re.sub(r"(?m)^(\| A mailto link to the shop \| )[^|]*", r"\1x ", self.doc, count=1)
        self.assertIn("A mailto link to the shop: What it would do cell is thin", option_problems(thin))
        # A mailto link cannot become a capacity, consent or list solution; an outside list cannot become the RSVP backend;
        # staying closed does not require enabling mail.
        for name, old, new in (("mailto has no capacity-safe rsvp", "no capacity-safe RSVP", "a capacity-safe RSVP"),
                               ("mailto has no managed list", "no managed list", "a managed list"),
                               ("list does not replace rsvp", "does not replace the RSVP service", "replaces the RSVP service"),
                               ("closed needs no mail setup", "Nothing to set up for sending, delivery or a mailbox merely to stay closed",
                                "A sender mailbox must be set up first"),
                               ("service not production", "not production-ready and not email-enabled", "ready for production"),
                               ("f08 is future", "F08 is future work", "F08 is installed"),
                               ("saving is not sending", "Saving a signup does not send one", "Saving a signup sends one"),
                               ("consents stay separate", "Keeping the two consents separate", "Merging the two consents")):
            with self.subTest(name):
                self.assertEqual(caveat_problems(self.doc.replace(old, new)), [name])
        for need in ("sender mailbox and domain", "unsubscribe", "privacy text", "who reads", "f08"):
            self.assertIn(need, " ".join(PREREQ_HEADER).lower())
        mailto = next(r for r in tables(self.doc)["Option"] if r[0] == "A mailto link to the shop")
        self.assertIn("no form", mailto[3].lower())
        self.assertNotEqual(question_problems(re.sub(r"(?m)^6\. .*\n", "", self.doc)), [])
        self.assertNotEqual(question_problems(self.doc.replace("\n9. ", "\n")), [])
        head, tail = self.doc.split("## Questions Michael and G must answer", 1)
        self.assertIn("nobody is asked about unsubscribe",
                      question_problems(head + "## Questions Michael and G must answer" + tail.replace("unsubscribe", "opt out")))
        self.assertIn("RETENTION-OPTIONS.md", self.doc.split("## Questions Michael and G must answer", 1)[1])
        self.assertIn("this page does not choose periods", self.doc)
        self.assertIn("F08", self.doc.split("## Questions Michael and G must answer", 1)[1])

    def test_signup_aid_no_choice_no_contact_no_private_examples(self):
        self.assertEqual(policy_problems(self.doc), [])
        self.assertEqual(private_problems(self.doc), [])
        self.assertEqual(delivered_problems(self.doc), [])
        self.assertTrue(self.doc.startswith("# Signup options — an open decision\n"))
        for phrase in ("Nobody has chosen where the signup forms send what visitors type", "names no service",
                       "none is the default", "Nothing on this page is a decision, a recommendation, a selected host, a launch date or a sign-off"):
            self.assertIn(phrase, self.doc.replace("**", ""))
        # The rejected strings live only here, never in the page; each must be caught by its checker.
        for bad in ("We recommend the club service.", "Recommended: a mailing list.", "The chosen option is the shop link.",
                    "Use Mailchimp for this.", "Sign in to Gmail first.", "Run curl against the service.",
                    "Run python3 community-server.py.", "Open mailto:someone for the shop.", "Answer: the shop link."):
            with self.subTest(bad):
                self.assertNotEqual(policy_problems(self.doc + "\n" + bad), [])
        for sample in ("write to someone@example.org", "see https://example.org/x", "visit www.example.net",
                       "call +1 555 010 0199", "id 0123456789abcdef", "/home/someone/state", "the shop site.com",
                       "community-data/community.sqlite3"):
            with self.subTest(sample):
                self.assertNotEqual(private_problems(sample), [])
        self.assertNotIn("](http", self.doc)

    def test_signup_source_links_and_h25_forms_anchor(self):
        self.assertEqual(link_problems(self.doc), [])
        self.assertNotEqual(link_problems(self.doc + "\n[x](../../hass/no_such_file.py)"), [])
        self.assertNotEqual(link_problems(self.doc.replace("community.js#L174", "community.js#L99999")), [])
        self.assertNotEqual(link_problems(self.doc.replace("community.js#L174", "community.js#L175")), [])
        self.assertNotEqual(link_problems(self.doc.replace("community.js#L174", "community.js#L2")), [])
        self.assertNotEqual(link_problems(self.doc.replace("community.js#L174", "community.js#intro")), [])
        self.assertNotEqual(link_problems(self.doc.replace("FEATURES.md#L68", "FEATURES.md#L67")), [])
        self.assertNotEqual(link_problems(self.doc.replace("script.js#L14", "script.js#L15")), [])
        self.assertNotEqual(link_problems(self.doc.replace("(RETENTION-OPTIONS.md)", "(RETENTION.md)")), [])
        handover = HANDOVER.read_text("utf-8")
        self.assertEqual(h25_forms_problems(handover), [])
        row = handover_rows(handover)["H25-forms"]
        self.assertEqual(row[2], "Owner / G")
        self.assertTrue(row[3].endswith("[Signup options](SIGNUP-OPTIONS.md#L1)"))
        self.assertEqual(handover.count("](SIGNUP-OPTIONS.md"), 1)  # linked from the one row only
        self.assertIn("[Retention options](RETENTION-OPTIONS.md)", handover_rows(handover)["H21"][3])  # H21 link unchanged
        self.assertIn(("docs/hass/SIGNUP-OPTIONS.md", 1), HANDOVER_ANCHORS)
        first = self.doc.splitlines()[0]
        self.assertIn(HANDOVER_ANCHORS[("docs/hass/SIGNUP-OPTIONS.md", 1)].lower(), first.lower())
        shifted = "Intro\n" + self.doc  # a shifted heading no longer sits on line 1
        self.assertNotIn(HANDOVER_ANCHORS[("docs/hass/SIGNUP-OPTIONS.md", 1)].lower(), shifted.splitlines()[0].lower())
        wrong_row = handover.replace(", [Signup options](SIGNUP-OPTIONS.md#L1)", "").replace(
            "| H25-domain | ", "| H25-domain | ").replace("[line 129](../../HERMES_HANDOFF.txt#L129) |",
                                                          "[line 129](../../HERMES_HANDOFF.txt#L129), [Signup options](SIGNUP-OPTIONS.md#L1) |")
        self.assertEqual(h25_forms_problems(wrong_row), ["H25-forms source lacks [Signup options](SIGNUP-OPTIONS.md#L1)",
                                                         "H25-domain links the signup options page"])


if __name__ == "__main__":
    unittest.main()
