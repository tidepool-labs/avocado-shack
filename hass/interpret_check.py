"""Interpreter output checked against the ops registry (NB-AV-01) before anything reaches the editor.

check() is pure: an op, argument name or value type the registry does not allow, or a ``revises`` code that is not
waiting, becomes one owner question naming the field. An enum value that is not one of the op's choices is asked about
in site words (shelf, availability) before the editor (AV0222-02). Other value checks (real dates, makers, files) stay in the editor.
Names shown to the owner contain only visible characters (no controls, zero-width, direction or line-separator marks).
SKILLS-FW-2 adds check_skill for the skill reply shapes (see below).
The same change listed twice (same op, equal args in any key order, spacing ignored) becomes one question naming the first repeated
pair; it is checked after the shape check and before op/field checks, so a repeated unknown op is reported as a repeat.
AV1104-06: a sole-key {"lookup": "<command>"} result passes only when the real parse_command reads the string as one of the read-only
LOOKUP_VERBS (find, listing and shelf also need an argument); every other lookup becomes the fixed LOOKUP_REFUSED reply.
"""

import json
import unicodedata

from hass import voice
from hass.content_model import AVAILABILITY, CATEGORIES, FORBIDDEN_TEXT, SHELF_LABELS, valid_selling_price
from hass.editor import MAX_OPS
from hass.ops import INTAKE_PRICE

HIDDEN = {"Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"}
STRING_KINDS = ("id", "maker_key", "text", "url", "enum", "date", "time", "image", "deal")  # deal: the owner's special deal line (AVO-SPECIALS-1)
NAME_CUT = 40
AGAIN = "Could you say it another way?"
UNREADABLE_CHANGE = f"I couldn't read part of that message. {AGAIN}"
UNDO_GUIDANCE = "To undo the last change, say " + voice.quote("undo") + ". To see what we changed lately, say " + voice.quote("history") + "."
PRICE_REPLY = "The website doesn't show prices, so I haven't made any change. Could you send it without the price?"  # AV0222-03
PLAIN_TEXT_REPLY = ("The website only takes plain words, so I haven't made any change. "
                    "Could you send it again without special marks?")
LOOKUP_VERBS = frozenset({"status", "report", "history", "find", "listing", "shelf", "hidden"})  # AV1104-06: the read-only commands a question may ask for
LOOKUP_NEEDS_ARG = frozenset({"find", "listing", "shelf"})
LOOKUP_REFUSED = "Nothing changed. To look something up, say status, report, or find and a few words."
CANT_DO_YET = "I can't do that kind of change from chat yet, so nothing changed. Say help to see what I can change."
WANTS = {"bool": "yes or no", "int": "a whole number", "text_list": "a list of words"}


def _clean(value) -> str:
    """A name safe to show the owner: invisible characters removed, cut to NAME_CUT characters, "(unnamed)" if empty."""
    text = "".join(c for c in str(value) if unicodedata.category(c) not in HIDDEN) or "(unnamed)"
    return text if len(text) <= NAME_CUT else text[:NAME_CUT - 3] + "..."


def _spaced(v):  # RF1050-7: spacing folded for the repeat key only (case kept); never written back to the result
    return " ".join(v.split()) if isinstance(v, str) else [_spaced(x) for x in v] if isinstance(v, list) else v


def _kind_ok(kind: str, value) -> bool:
    if kind in STRING_KINDS: return isinstance(value, str)
    if kind == "text_list": return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if kind == "bool": return isinstance(value, bool)
    if kind == "int": return isinstance(value, int) and not isinstance(value, bool)
    return False  # a kind this check does not know is never passed through


def _forbidden_reply(kind: str, value):
    """AV0222-03: PRICE_REPLY for '$', PLAIN_TEXT_REPLY for the other FORBIDDEN_TEXT marks, in a text or text_list value."""
    for text in ([value] if kind == "text" else value if kind == "text_list" else []):
        if "$" in text: return PRICE_REPLY
        if any(bad in text for bad in FORBIDDEN_TEXT): return PLAIN_TEXT_REPLY
    return None


def _enum_question(op_name: str, arg_name: str, value, choices) -> str:
    """One question for an enum value outside the op's choices; site words only for the canonical shelf/availability args."""
    choices = tuple(choices or ())
    if op_name in ("product.add", "product.edit") and arg_name == "category" and choices == CATEGORIES:
        shelves = [SHELF_LABELS[c] for c in CATEGORIES]
        return f"There is no {_clean(value)} shelf. Which shelf: {', '.join(shelves[:-1])} or {shelves[-1]}?"
    if op_name == "product.set_availability" and arg_name == "available" and choices == AVAILABILITY:
        return "Should it say Available today, Limited or Sold out?"
    if not choices: return f"I can't pick {voice.field_phrase(arg_name)} from a list. {AGAIN}"
    return f"For {voice.field_phrase(arg_name)}, I can use: {', '.join(_clean(voice.value_words(c, arg_name)) for c in choices)}. {AGAIN}"


def _problem(result: dict, registry, pending_codes, from_intake):
    calls = result["ops"]
    if not calls: return "I couldn't find a change in that message. What would you like to change?"
    if len(calls) > MAX_OPS:  # RF2030-7: counted before call shapes, repeats and waiting-code checks
        return "That's a lot of changes at once. Could you send them a few at a time?"
    for n, call in enumerate(calls, 1):
        if not (isinstance(call, dict) and set(call) == {"op", "args"} and isinstance(call["op"], str)
                and isinstance(call["args"], dict)):
            return UNREADABLE_CHANGE
    if any(call["op"] == "history.revert" for call in calls): return UNDO_GUIDANCE  # AV0007-02: whole result refused
    seen = {}
    for i, call in enumerate(calls, 1):
        try: key = (call["op"], json.dumps({k: _spaced(v) for k, v in call["args"].items()}, sort_keys=True, ensure_ascii=False))
        except (TypeError, ValueError, RecursionError): continue  # args that cannot be compared are never called the same
        if key in seen:
            return "Two of those changes are the same. Did you mean to change something else?"
        seen[key] = i
    for call in calls:
        op = registry.get(call["op"])
        if op is None:
            return CANT_DO_YET
        for name, value in call["args"].items():
            label = f"{_clean(call['op'])}.{_clean(name)}"
            arg = op.args.get(name)
            if arg is None:
                return CANT_DO_YET
            if call["op"] == "product.add" and name == "supplier" and not from_intake:
                return CANT_DO_YET
            if arg.kind == INTAKE_PRICE:
                if not from_intake: return CANT_DO_YET
                if not valid_selling_price(value): return f"I couldn't read the selling price. {AGAIN}"
                continue
            if not _kind_ok(arg.kind, value):
                return f"I need {voice.field_phrase(name)} as {WANTS.get(arg.kind, 'words')}. {AGAIN}"
            reply = _forbidden_reply(arg.kind, value)
            if reply: return reply
            if arg.kind == "enum" and value not in (arg.choices or ()):
                return _enum_question(call["op"], name, value, arg.choices)
    code = result["revises"]
    if code is not None and code not in pending_codes:
        return "I can't find that change any more. Could you tell me the change again?"
    return None


def lookup_command(text):
    """AV1104-06: the parsed (verb, argument) when ``text`` is one read-only command the owner could send (the real parse_command
    decides, so aliases, punctuation and the argument's own case are the command's); otherwise None. A line break or other control
    character, a blank argument for find/listing/shelf, and any verb outside LOOKUP_VERBS give None."""
    from hass.chat.commands import parse_command  # function-local: hass.conversation imports this module
    if not isinstance(text, str) or any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in text): return None
    found = parse_command(text)
    if not found or found[0] not in LOOKUP_VERBS: return None
    if found[0] in LOOKUP_NEEDS_ARG and not (found[1] or "").strip(): return None
    return found


def check(result: dict, registry, pending_codes, *, from_intake=False) -> dict:
    """``result`` unchanged when it is fine (or is already a question/unsupported reply), else {"question": text}.
    AV1104-06: a lookup is unchanged when it names an allowed read-only command, else {"unsupported": LOOKUP_REFUSED}."""
    if "ops" in result and (not isinstance(result["ops"], list) or "revises" not in result
                            or (result["revises"] is not None and not isinstance(result["revises"], str))):
        return {"question": UNREADABLE_CHANGE}
    if "lookup" in result: return result if lookup_command(result["lookup"]) else {"unsupported": LOOKUP_REFUSED}
    if "ops" not in result: return result
    problem = _problem(result, registry, set(pending_codes), from_intake)
    return result if problem is None else {"question": problem}


# -- SKILLS-FW-2: a skill reply ({"skill", "slots"}, {"calls"}, {"skill": "none"}) ---------------------------------------
SKILL_KEYS = {"skill", "slots", "revises"}
REF_KINDS = ("product_ref", "maker_ref", "hike_ref", "route_ref", "shelf")  # one name, or several in one message
SKILL_TEXT_KINDS = STRING_KINDS + REF_KINDS + ("availability", "day", "clock", "attachment")


def is_skill_reply(result) -> bool:
    return isinstance(result, dict) and ("skill" in result or "calls" in result)


def _slot_ok(kind: str, value) -> bool:
    if kind in REF_KINDS and isinstance(value, list): return bool(value) and all(isinstance(v, str) for v in value)
    if kind in SKILL_TEXT_KINDS: return isinstance(value, str)
    return _kind_ok(kind, value)


def _skill_problem(call, skills):
    """One owner question for a skill call that is malformed, or None. ``skills`` has ``get(name)`` (a Registry)."""
    if not (isinstance(call, dict) and set(call) <= SKILL_KEYS and isinstance(call.get("skill"), str)
            and isinstance(call.get("slots", {}), dict)):
        return f"I could not read that message as a change. {AGAIN}"
    skill = skills.get(call["skill"])
    if skill is None:
        return None  # an unknown name is not a question: skill_check turns it into the catch-all
    schema = {s.name: s for s in skill.slots}
    for name, value in call.get("slots", {}).items():
        slot = schema.get(name)
        if slot is None or not _slot_ok(slot.kind, value):
            return f"I could not read the details for {_clean(skill.label)}. {AGAIN}"
        reply = _forbidden_reply(slot.kind, value)
        if reply: return reply
    return None


def check_skill(result: dict, skills, pending_codes=()) -> dict:
    """SKILLS-FW-2: ``result`` unchanged when a skill reply is well formed; a malformed one (wrong shape, a slot name or
    value type the skill does not have, too many calls, the same call twice, a ``revises`` code not waiting, a price) becomes
    {"question": text}. A skill name that does not exist becomes {"skill": "none", "unknown": True}: the router writes
    it to the backlog and never guesses. Replies that are not skill replies pass through untouched."""
    if not is_skill_reply(result): return result
    if "skill" in result and "calls" in result:
        return {"question": f"I could not read that message as one change. {AGAIN}"}
    if "calls" in result and not set(result) <= {"calls", "revises"}:  # closed envelope: refuse the whole reply, never strip
        return {"question": f"I could not read that message as a change. {AGAIN}"}
    if result.get("skill") == "none":  # the catch-all has its own closed shape: only skill and an optional text summary
        if not set(result) <= {"skill", "summary"} or not isinstance(result.get("summary", ""), str):
            return {"question": f"I could not read that message as a change. {AGAIN}"}
        return {"skill": "none", "summary": result.get("summary", "")}
    code = result.get("revises")
    if code is not None and (not isinstance(code, str) or code not in set(pending_codes)):
        return {"question": f"I could not find draft {_clean(code)} waiting; reply with the change again."}
    calls = result["calls"] if "calls" in result else [result]
    if not isinstance(calls, list) or not calls:
        return {"question": "I did not find a change in that message. What would you like to change?"}
    if len(calls) > MAX_OPS:
        return {"question": (f"That is {len(calls)} changes in one message; I can take at most {MAX_OPS} at a time. "
                             "Please send them in smaller groups.")}
    seen = {}
    for i, call in enumerate(calls, 1):
        if "calls" in result and isinstance(call, dict) and "revises" in call:  # the code lives on the envelope, never per call
            return {"question": f"I could not read that message as a change. {AGAIN}"}
        problem = _skill_problem(call, skills)
        if problem: return {"question": problem}
        try: key = (call["skill"], json.dumps({k: _spaced(v) for k, v in call.get("slots", {}).items()}, sort_keys=True, ensure_ascii=False))
        except (TypeError, ValueError, RecursionError): continue
        if key in seen:
            return {"question": f"Changes {seen[key]} and {i} in that message are the same. Did you mean to change something else? {AGAIN}"}
        seen[key] = i
    if any(skills.get(c["skill"]) is None for c in calls):
        return {"skill": "none", "summary": "", "unknown": True}
    return result
