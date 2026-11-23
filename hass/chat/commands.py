"""The owner's command words: the parsers hass/conversation.py tries before the interpreter, and the help text.

AVB-12: moved verbatim out of hass/conversation.py, which imports every name back (hass.conversation.<name> is
unchanged). Pure functions; no state.
"""
import re
import unicodedata

from hass import memory as memory_mod
from hass.content_model import SHELF_LABELS
from hass.chat.shared import ALIAS_NAME_MAX, q
from hass.ops import catalog

APPROVE, REJECT = ("yes", "approve", "approved"), ("no", "cancel", "reject")
UNDO_PHRASES = ("undo that", "undo it", "undo last", "undo the last change", "please undo")  # AV0222-07 (H06/H17): whole message only
CANCEL_PHRASES = ("cancel that", "cancel it", "never mind", "nevermind")
KEYWORD_RE = re.compile(r"(yes|approved|approve|no|cancel|reject)(?: ([0-9a-f]{4,12}))?")
NEAR_RE = re.compile(r"(ok|okay|yes please|yep|yeah|sure|go ahead|do it|sounds good|looks good)(?: ([0-9a-f]{4,12}))?")  # H05
COMMAND_RE = re.compile(r"(history)(?:\s+(?s:.*))?|(undo)(?: ([0-9a-f]{4,12}))?"  # H06, same normalisation as KEYWORD_RE
                        r"|(status|did (?:it|that|my change) work\??)|(pause|stop)(?: changes)?"  # H17; SHOP-4 phrases
                        r"|(resume)(?: changes)?|(help|commands|\?|what can you do\??|what do you do\??|what can i say\??)"  # AV2007-04: capability questions are help; no new group
                        r"|(find)(?:\s+(.*))?"  # AV1537-04; the query is re-read from the original text to keep its case
                        r"|(show)(?:\s+(.*))?"  # AV0022-08 (H17): groups 10/11, earlier indices unchanged
                        r"|((?:morning )?report)"  # AV1322-05 (F04): group 12; groups 1-11 keep their indices
                        r"|(post)(?:\s+((?s:.*)))?"  # AV1322-07 (F07): groups 13/14; AV1052-07: the id, name or alias is the whole rest (_post checks it), re-read from the original text to keep its case
                        r"|(margin)(?:\s+((?s:.*)))?"  # AV1102-12 (F03): groups 15/16; the rest is checked by MARGIN_RE
                        r"|(hidden)"  # AV1222-13 (H03): group 17
                        r"|(listing)(?:\s+((?s:.*)))?"  # AV1622-09 (H17): groups 18/19; AV1052-07: the whole rest; _listing checks it
                        r"|(photos to take)"  # AV0222-04 (H10/H17): group 20
                        r"|(backlog)"  # SKILLS-FW-3: group 21 (what I could not do yet; read-only)
                        r"|(again)(?:\s+((?s:.*)))?"  # AV2152-03 (H05/H16): groups 22/23; the code is checked by _again, never guessed
                        r"|(shelf)(?:\s+(.*))?"  # AV1052-05 (H17): groups 24/25; one line, the shelf is checked by _shelf
                        r"|(costs)"  # AV2137-06 (F03/H15): group 26; the whole message only, so `costs are up` stays an ordinary message
                        r"|(held)")  # AV2137-07 (H03/H17): group 27; the whole message only, so `held products` and `unheld` stay ordinary messages

SHELF_NOT_A_NAME = frozenset("report specials special check chek checked done finished in out then stock sold".split())  # AV1052-05: words that make "shelf ..." a stock update or report

# AV1052-12 (H17/H25): one entry per command - (name, group, other words that reach it, full lines each ending in a quoted
# example). `help` replies a short grouped index of the names; `help <name>` replies that entry's lines. Every line is
# at most 70 plain characters (test_help). The examples parse back to the entry's own verb (test_help).
HELP_GROUPS = ("Drafts", "Look up", "Notes", "Control")
# HRM-13 (M5): `help listing` first tells how to list a new product by photo, in the owner guide's words
# (docs/hass/NPP-OWNER-GUIDE.md). The example tag is prompts.ready's `yes {code}-{n}` with the guide's 4ed1. These lines
# carry no marked example: the photo flow has no command verb of its own (test_help's one-entry-per-verb rule).
LISTING_PHOTO_LINES = ("New product: send a photo with the selling price, each or per lb",
                       "I reply with the website card and a code; change it in your own words",
                       "yes 4ed1-2 (the code on the latest card) posts it; undo takes it down")
HELP_LISTING = "To list a new product by photo: " + q("help listing")  # HRM-13: the index line that points to it
HELP_ENTRIES = (
    ("yes", "Drafts", ("approve", "approved"), (q("yes") + " - go ahead with the change waiting for you",
                                                 q("yes a1b2") + " - go ahead with the one with that code")),
    ("no", "Drafts", ("cancel", "reject"), (q("no") + " - cancel the change waiting for you", q("no a1b2") + " - cancel the one with that code")),
    ("undo", "Drafts", (), (q("undo") + " - take back the last change", q("undo a1b2") + " - take back that one")),
    ("show", "Drafts", (), (q("show a1b2") + " - repeat a waiting change (its code or a word from it)",)),
    ("again", "Drafts", (), (q("again a1b2") + " - re-draft an expired or undone change (within 7 days)",)),  # AV2152-03
    ("find", "Look up", (), (q("find lion's mane") + " - look something up",)),
    ("listing", "Look up", (), (*LISTING_PHOTO_LINES, q("listing Etto") + " - what's shown for one thing",
                                q("listing store") + " - the hours and home page words")),  # AV1052-06
    ("shelf", "Look up", (), (q("shelf vegetables") + " - read a shelf",)),  # AV1052-05
    ("hidden", "Look up", (), (q("hidden") + " - lists what's hidden",)),
    ("held", "Look up", (), (q("held") + " - why some products are on hold",)),  # AV2137-07
    ("report", "Look up", ("morning report",), (q("report") + " - the morning shelf report",)),
    ("post", "Look up", (), (q("post Hass avocado") + " - a caption to copy for a product",  # AV1937-10: nothing is posted
                              q("post maker fixture-farm") + " - a caption to copy for a maker",
                              q("post notice") + " - a caption for the home page notice",  # AV1104-07
                              q("post today") + " - a caption for what you checked today")),  # AV1104-08
    ("look", "Look up", (), (q("look") + " - a fresh picture of the website", q("look hike") + " - or of the hike page; add a product")),  # AV1922-01
    ("photos to take", "Look up", (), (q("photos to take") + " - the products that still need a photo",)),
    ("margin", "Look up", (), (q("margin Hass avocado at 35%") + " - a price idea or a price check",)),
    ("remember", "Notes", (), (q("remember parking: back lot") + " - I'll keep a note",)),
    ("forget", "Notes", (), (q("forget parking") + " - removes a note", q("forget backlog.3") + " - takes one off the backlog")),
    ("notes", "Notes", ("memory",), (q("notes") + " - lists your notes",)),
    ("alias", "Notes", (), (q("alias jam: Linn's preserves") + " - a nickname for a product or maker",)),
    ("cost", "Notes", (), (q("cost Hass avocado: 24 for 12") + " - the price you pay, kept private",)),
    ("backlog", "Notes", (), (q("backlog") + " - what I couldn't do yet",)),  # SKILLS-FW-3
    ("costs", "Notes", (), (q("costs") + " - the purchase costs you've saved",)),  # AV2137-06
    ("history", "Control", (), (q("history") + " - what we changed lately", q("history hours") + " - look for one change")),
    ("status", "Control", ("did it work", "did that work", "did my change work"),
     (q("status") + " - what I did last and what is waiting for you",)),
    ("stop changes", "Control", ("stop", "pause", "pause changes"), (q("stop changes") + " - I won't change anything until you resume",)),
    ("resume changes", "Control", ("resume",), (q("resume changes") + " - changes are allowed again",)),
    ("help", "Control", ("commands", "?", "what can you do", "what do you do", "what can i say"),
     (q("help") + " - the list of commands", q("help undo") + " - one command with its example")),
)
HELP_WORDS = {w: e[0] for e in HELP_ENTRIES for w in (e[0], *e[2])}  # every word `help <word>` knows -> the entry's own name
HELP_LIMIT = 70


def _help_names() -> list:
    """One line per group: `Group: name, name`, each name marked as a command word; names wrap at a comma (70 plain
    characters), the next line indented two spaces."""
    out = []
    for group in HELP_GROUPS:
        names = [e[0] for e in HELP_ENTRIES if e[1] == group]
        line, width = group + ":", len(group) + 1
        for i, name in enumerate(names):
            tail = "," if i + 1 < len(names) else ""
            if width + 1 + len(name) + len(tail) > HELP_LIMIT:
                out.append(line)
                line, width = " ", 1
            line, width = line + " " + q(name) + tail, width + 1 + len(name) + len(tail)
        out.append(line)
    return out


HELP_TEXT = "\n".join(("Tell me what to change, e.g. " + q('"Stop showing the eggs as sold out"'),  # AV1537-03, test_help
                       *_help_names(), HELP_LISTING, "Send " + q("help <command>") + " for an example: " + q("help undo")))


def help_detail(name: str) -> str:
    """The full lines of one command (any of its words), or the unknown-name reply with the same grouped names and the
    `help listing` line (HRM-13). The unknown word is never echoed."""
    entry = next((e for e in HELP_ENTRIES if e[0] == HELP_WORDS.get(name)), None)
    return "\n".join(entry[3]) if entry else "\n".join(("Unknown command. Send help with one of:", *_help_names(), HELP_LISTING))


def _help_word(norm: str):
    """AV1052-12: ("help", word) when the whole (already lower-cased) message is `help <one word>` or `help <known name>`."""
    found = re.fullmatch(r"help (\S+(?: \S+){0,3})", norm)
    return ("help", found[1]) if found and (found[1] in HELP_WORDS or " " not in found[1]) else None


# H15 owner memory. Verb and key are case-insensitive (the key is stored lower-cased); the text keeps its case.
MEMORY_RE = re.compile(r"(remember)(?:\s+(.*))?|(forget)\s+(\S.*)|(memory|notes)|(alias)(?:\s+(.*))?"
                       r"|(cost)(?:\s+(.*))?", re.IGNORECASE | re.DOTALL)  # AV1222-10: groups 8/9


BULK_PHRASES = {"no all": "reject", "cancel all": "reject", "cancel everything": "reject", "yes all": "approve", "approve all": "approve"}


def parse_keyword(text: str):
    """(verb, code or None) when the whole message is an approval keyword; otherwise None. AV1052-08: the five whole-message
    bulk phrases (`no all`, `cancel all`, `cancel everything`, `yes all`, `approve all`) give code \"all\" (never a real code)."""
    norm = re.sub(r"[.!]+$", "", text.strip().lower())
    if norm in CANCEL_PHRASES: return "reject", None  # AV0222-07: the same as a bare no
    if norm in BULK_PHRASES: return BULK_PHRASES[norm], "all"
    match = KEYWORD_RE.fullmatch(norm)
    if not match: return None
    return ("approve" if match[1] in APPROVE else "reject"), match[2]


UNKNOWN_CODE_RE = re.compile(r"(yes|approved|approve|no|cancel|reject) ([0-9a-z]{4,12})")


def parse_unknown_code(text: str):
    """AV2007-13: the code when the whole message is an approve/cancel word and one 4-12 character token that is not a
    valid (hex) code, such as `yes 9z9z`; otherwise None. Refusal only: never an approval or a cancel. The token needs a
    digit, so `yes please` or `no thanks` stay plain words. A ? or a trailing clause never qualifies."""
    match = UNKNOWN_CODE_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()))
    if not match or KEYWORD_RE.fullmatch(match[0]) or not any(c.isdigit() for c in match[2]): return None
    return match[2]


COURTESY = {"please", "thanks", "ok", "okay"}


def parse_phone(text: str):
    """AV1352-04 (H05): (verb or None, code or None, question) when, after dropping punctuation other than ?, emoji and
    the courtesy words (please, thanks, thank you, ok, okay), the whole message is one approve/cancel word and one code in
    either order, or one code alone, or (with a ?) one such word alone; otherwise None. `question` is True when the
    original text held a ?. Only the candidate is normalised, never the message; a ? is never stripped into an answer."""
    question = "?" in text
    words = "".join(c if c.isalnum() else " " for c in text.lower()).split()
    kept, i = [], 0
    while i < len(words):
        if words[i] == "thank" and words[i + 1:i + 2] == ["you"]: i += 2
        else:
            if words[i] not in COURTESY: kept.append(words[i])
            i += 1
    verbs = [w for w in kept if w in APPROVE or w in REJECT]
    codes = [w for w in kept if re.fullmatch(r"[0-9a-f]{4,12}", w)]
    if not kept or len(verbs) + len(codes) != len(kept) or len(verbs) > 1 or len(codes) > 1: return None
    if not verbs: return None, codes[0], question  # a lone code is only ever a hint
    if not codes and not question: return None  # courtesy never makes a new bare yes/no
    return ("approve" if verbs[0] in APPROVE else "reject"), (codes[0] if codes else None), question


def parse_near(text: str):
    """AV2022-07 (H05): code or "" when the whole message is a casual yes (ok, go ahead, ...); otherwise None.
    It never approves anything; Hass only answers with the exact `yes <code>` to send."""
    match = NEAR_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()).removesuffix(","))
    return None if not match else match[2] or ""


POST_MAKER_RE = re.compile(r"post\s+maker(?:(\s+)(.*))?", re.IGNORECASE | re.DOTALL)  # AV1937-10: whole words only


def _post_maker(text: str):
    """AV1937-10 (F07): ("post", "maker <key>") when the message is `post maker <key>`, else None. The key is the whole rest
    of the message with outer white space trimmed, in its own case with its spaces, apostrophes and a final . or !; it is
    read from the original text, before any punctuation is removed. No key, or a line break or control character
    anywhere after `maker`, gives ("post", "maker"): the usage reply."""
    found = POST_MAKER_RE.fullmatch(text.strip())
    if not found: return None
    rest = (found[1] or "") + (found[2] or "")
    key = (found[2] or "").strip()
    if not key or any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in rest): return "post", "maker"
    return "post", "maker " + key


LOOK_RE = re.compile(r"look(?:\s+(.*))?", re.IGNORECASE | re.DOTALL)  # AV1922-01: whole words only
LOOK_MAX = 60  # = FIND_TEXT_MAX: longest product query


def _look(text: str):
    """AV1922-01 (H06/H17): ("look", "") for a bare look, ("look", "<rest>") with the rest in its own case (outer white space and a
    final . or ! trimmed), or ("look", None) for a malformed rest (a line break, control character or more than 60 characters):
    the usage reply, never the model. Anything else (looks, look-alike words) is None."""
    found = LOOK_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip()))
    if not found: return None
    rest = (found[1] or "").strip()
    if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in rest) or len(rest) > LOOK_MAX: return "look", None
    return "look", rest


def parse_command(text: str, *, listing_names=False):
    """("undo", code or None) or (history|status|pause|resume|help, None) when the whole message is that command;
    otherwise None."""
    if maker := _post_maker(text): return maker  # AV1937-10: before the general punctuation rule, which would cut a key's . or !
    if look := _look(text): return look
    norm = re.sub(r"[.!]+$", "", text.strip().lower())
    if found := _help_word(norm): return found  # AV1052-12: help <command>; the numbered groups below are unchanged
    if norm in UNDO_PHRASES: return "undo", None  # AV0222-07: the same as a bare undo
    match = COMMAND_RE.fullmatch(norm)
    if not match: return None
    if match[27]: return "held", None  # AV2137-07
    if match[26]: return "costs", None  # AV2137-06
    if match[24]:  # AV1052-05: a shelf name or an unknown shelf gets the read-only chooser; a stock update or report ("shelf chek done. milk in, cheese out", "shelf report then specials") stays with the interpreter
        rest = (match[25] or "").strip()
        if re.search(r"[,.;:?!]", rest) or set(rest.split()) & SHELF_NOT_A_NAME: return None
        return "shelf", rest  # _shelf resolves it
    if match[22]: return "again", (match[23] or "").strip()  # AV2152-03: the rest as sent (lower-cased); _again accepts only a code
    if match[21]: return "backlog", None  # SKILLS-FW-3
    if match[20]: return "photos", None  # AV0222-04
    if match[1]:  # AV2152-02: bare history stays (history, None); history <words> keeps the words in their own case
        stripped = re.sub(r"[.!]+$", "", text.strip())
        if stripped.lower() != "history": return "history", stripped[7:].strip()
    if match[18]:
        ident = re.sub(r"[.!]+$", "", text.strip())[7:].strip() if match[19] else ""
        # Several words need a catalog check in the message flow, not just a syntax match.
        return ("listing", ident) if listing_names or len(ident.split()) <= 1 else None
    if match[17]: return "hidden", None  # AV1222-13
    if match[15]: return "margin", match[16] or ""  # AV1102-12 (F03)
    if match[13]:  # AV1322-07: the id in its own case
        ident = re.sub(r"[.!]+$", "", text.strip())[4:].strip() if match[14] else ""
        # AV1052-07: the whole rest is a name only for the conversation (listing_names, which then checks it names a product); the plain parser keeps its six-word window
        return ("post", ident) if listing_names or not ident or re.fullmatch(r"(?:hike\s+)?\S+(?:\s+\S+){0,5}", ident, re.IGNORECASE) else None
    if match[12]: return "report", None  # AV1322-05 (F04)
    if match[10]: return "show", match[11] or ""  # AV0022-08: the code is checked by _show, never guessed
    if match[7]: return "help", None
    if match[8]: return "find", re.sub(r"[.!]+$", "", text.strip())[4:].strip()  # ("find", query in its own case)
    if match[2]: return "undo", match[3]
    found = next(v for v in (match[1], match[4], match[5], match[6]) if v)  # SHOP-4: did it work = status, stop = pause
    return ("status" if found.startswith("did ") else "pause" if found == "stop" else found), None


def _note_key(name: str) -> str:
    """AV1352-07: a note name as typed: trimmed, lower-cased, runs of spaces become one \"-\" (KEY_RE still decides)."""
    return re.sub(" +", "-", name.strip().lower())


def parse_memory(text: str):
    """("remember", key, text), ("forget", key, None) or ("memory", None, None) when the whole message is an H15
    memory command; otherwise None. `remember …` without `key:` still parses (as an empty text) so it is refused."""
    match = MEMORY_RE.fullmatch(text.strip())
    if match and match[1]:
        key, colon, value = (match[2] or "").partition(":")
        return "remember", _note_key(key), value.strip() if colon else ""
    if match and match[6]:  # ("alias", name, product id or maker key); a missing part is refused, not guessed
        name, colon, ident = (match[7] or "").partition(":")
        return "alias", name.strip(), ident.strip() if colon else ""
    if match and match[8]:  # AV1222-10 ("cost", product id, "<pack> for <units>"); a bad part is refused, not guessed
        ident, colon, rest = (match[9] or "").partition(":")
        return "cost", ident.strip().lower(), rest.strip() if colon else ""
    match = MEMORY_RE.fullmatch(re.sub(r"!+$", "", text.strip()))  # a key may end in "." (KEY_RE), never "!"
    if match and match[3]:  # AV1352-07: spaces in a note name become "-"; `forget alias <name>` removes alias.<name>
        operand = match[4].strip()
        if re.search(r"[^\S ]", operand) or re.fullmatch(r"it +all", operand, re.IGNORECASE): return None  # old routing
        if re.match(r"alias +\S", operand, re.IGNORECASE):
            name = operand[5:].strip()
            ok = memory_mod._clean(name) and len(name) <= ALIAS_NAME_MAX
            if not ok: return "forget", "alias. " + name.lower(), None
            return "forget", "alias." + catalog._fold(name).replace(" ", "-"), "spaced"  # may also be the note alias-<name>
        return "forget", _note_key(operand), None
    match = MEMORY_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip()))
    return ("memory", None, None) if match and match[5] else None


READ_ONLY = {"history", "status", "help", "find", "show", "report", "post", "margin", "hidden", "listing", "backlog", "look", "shelf", "costs", "held"}


def _asked(text: str):
    """AV1352-05 (H17): the message without its closing run of . ! ? when that run holds a ?, else None."""
    cut = re.sub(r"[.!?]+$", "", text.strip())
    return cut if cut != text.strip() and "?" in text.strip()[len(cut):] else None


def read_command(text: str, *, listing_names=False):
    """AV1352-05 (H17): parse_command, but a closing ? is dropped for a read-only command only (never yes/no, undo, stop,
    resume); anything else keeps today's reading of the original text."""
    if maker := _post_maker(text): return maker  # AV1937-10: a key keeps even a closing ?
    cut = _asked(text)
    found = parse_command(cut, listing_names=listing_names) if cut else None
    return found if found and found[0] in READ_ONLY else parse_command(text, listing_names=listing_names)


def read_memory(text: str):
    """AV1352-05 (H17): `memory?` lists notes; remember, forget and alias never see a stripped text."""
    cut = _asked(text)
    found = parse_memory(cut) if cut else None
    return found if found and found[0] == "memory" else parse_memory(text)
