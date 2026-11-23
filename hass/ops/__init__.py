"""Typed Hass editing operations (H02): registry, argument kinds and result types.

Closed argument kinds only: no path, command, SQL, URL-fetch, dict or "any" kind. Unit modules in this
package (A3/A4/A6) export ``OPS = (Op(...), ...)``; ``load_registry()`` collects them without editing this file.
"""

from __future__ import annotations

import importlib, json, os, pkgutil, re, stat  # noqa: E401
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from hass.content_model import (ID_RE, IMAGE_RE, SELLING_PRICE_ERROR, SITE_DIR, _https, _text,
                                special_text_problem, valid_selling_price)

KINDS = ("id", "maker_key", "text", "text_list", "url", "enum", "bool", "int", "date", "time", "image", "deal")  # deal: AVO-SPECIALS-1 owner deal line
# Only the checked intake planner sets this kind in chat, not the legacy ops interpreter.
INTAKE_PRICE = "intake_price"
KINDS += (INTAKE_PRICE,)
# clocks are ASCII HH:MM (consumed by time.fromisoformat); \d would also match Unicode digits
TIME_RE = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
COLLECTIONS = ("products", "makers", "events", "routeIdeas", "store", "club")
CHANGE_ID_RE = re.compile(r"chg-[0-9a-f]{12}")


@dataclass(frozen=True)
class Arg:
    kind: str
    required: bool = True
    choices: tuple | None = None
    minimum: int | None = None

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown argument kind {self.kind!r}")


@dataclass(frozen=True)
class Op:
    name: str
    args: Mapping[str, Arg]
    apply: Callable[..., Any]


@dataclass
class OpContext:
    now: datetime
    site_dir: Path
    settings: Mapping[str, Any]
    warnings: list = field(default_factory=list)
    state_dir: Path | None = None
    assets: dict = field(default_factory=dict)  # site-relative assets/products path -> bytes the editor writes (H10)

    def change(self, change_id):
        """Read-only: the recorded change ``<state>/changes/<id>.json`` as a dict, or None (H06 undo); regular, non-link
        file only: a link, FIFO, socket or folder there raises OSError and is never followed or opened. The
        ``changes`` parent must itself be a real folder (a link, dangling link or file raises OSError); absent is None."""
        if self.state_dir is None or not CHANGE_ID_RE.fullmatch(str(change_id)):
            return None
        parent = Path(self.state_dir) / "changes"
        try:
            if not stat.S_ISDIR(os.lstat(parent).st_mode):
                raise OSError("changes parent is not a folder")
        except FileNotFoundError:
            return None
        path = parent / f"{change_id}.json"
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(st.st_mode):
            raise OSError("not a regular file")
        return json.loads(path.read_text("utf-8"))


@dataclass
class Touched:
    collection: str
    key: str
    before: Any
    after: Any

    def __post_init__(self):
        if self.collection not in COLLECTIONS:
            raise ValueError(f"unknown collection {self.collection!r}")


@dataclass
class NeedsDetails:
    missing: list
    question: str


@dataclass
class NotFound:
    key: str


@dataclass
class Refused:
    reason: str


def load_registry() -> dict[str, Op]:
    """Import every module in hass.ops and merge their OPS; duplicate names raise."""
    registry: dict[str, Op] = {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        for op in getattr(module, "OPS", ()):
            if op.name in registry:
                raise ValueError(f"duplicate op name {op.name!r}")
            registry[op.name] = op
    return registry


def has_control_chars(value) -> bool:
    if isinstance(value, str):
        return any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value)
    if isinstance(value, dict):
        return any(has_control_chars(k) or has_control_chars(v) for k, v in value.items())
    if isinstance(value, list):
        return any(has_control_chars(v) for v in value)
    return False


def _check_value(problems, where, arg: Arg, value, makers, site_dir):
    kind = arg.kind
    if kind in ("id", "maker_key", "text", "deal", "url", "enum", "date", "time", "image") and not isinstance(value, str):
        problems.append(f"{where}: must be a string ({kind})")
        return
    if kind == "id" and not ID_RE.fullmatch(value):
        problems.append(f"{where}: not a valid id")
    elif kind == "maker_key" and value not in makers:
        problems.append(f"{where}: not a maker in makers.json")
    elif kind == "text":
        _text(problems, where, value)
    elif kind == INTAKE_PRICE and not valid_selling_price(value):
        problems.append(f"{where}: {SELLING_PRICE_ERROR}")
    elif kind == "deal":  # the one text that may carry a price ($); markup, links and contact details stay out
        if (why := special_text_problem(value, deal=True)):
            problems.append(f"{where}: {why}")
    elif kind == "text_list":
        if not isinstance(value, list) or not value:
            problems.append(f"{where}: must be a non-empty list of text")
        else:
            for i, item in enumerate(value):
                _text(problems, f"{where}[{i}]", item)
    elif kind == "url":
        _https(problems, where, value)
    elif kind == "enum" and value not in (arg.choices or ()):
        problems.append(f"{where}: must be one of {tuple(arg.choices or ())}")
    elif kind == "bool" and not isinstance(value, bool):
        problems.append(f"{where}: must be true or false")
    elif kind == "int" and (isinstance(value, bool) or not isinstance(value, int)
                            or (arg.minimum is not None and value < arg.minimum)):
        problems.append(f"{where}: must be an integer" + (f" >= {arg.minimum}" if arg.minimum is not None else ""))
    elif kind == "date":
        try:
            date.fromisoformat(value if DATE_RE.fullmatch(value) else "")
        except ValueError:
            problems.append(f"{where}: must be a real date YYYY-MM-DD")
    elif kind == "time" and not TIME_RE.fullmatch(value):
        problems.append(f"{where}: must be HH:MM (24 h)")
    elif kind == "image":
        if not IMAGE_RE.fullmatch(value) or ".." in value:
            problems.append(f"{where}: must be assets/products/<file>")
        elif (problem := _image_file_problem(site_dir, value)) is not None:
            problems.append(f"{where}: {problem}")


def _image_file_problem(site_dir, value) -> str | None:
    """The file must be regular, not a link, and resolve inside the site folder when supplied."""
    if site_dir is None:  # Offline replay checks only the syntax validated by the caller.
        return None
    path = Path(site_dir) / value
    if path.is_symlink():
        return "image file must not be a link"
    if not path.is_file():
        return "image file does not exist"
    roots, repo_assets = [Path(site_dir).resolve()], (SITE_DIR / "assets").resolve()
    # The one allowed linked folder: <site>/assets resolving to this checkout's own tracked assets (editor test harness).
    if (Path(site_dir) / "assets").resolve() == repo_assets:
        roots.append(repo_assets)
    if not any(path.resolve().is_relative_to(root) for root in roots):
        return "image file is outside the site folder"
    return None


def check_args(op: Op, args, makers, site_dir) -> tuple[list[str], list[str]]:
    """Return (problems, missing required argument names) for one op call."""
    if not isinstance(args, dict):
        return [f"{op.name}: args must be an object"], []
    problems = [f"{op.name}: unknown argument {name!r}" for name in args if name not in op.args]
    missing = [name for name, arg in op.args.items() if arg.required and name not in args]
    for name, value in args.items():
        if name in op.args:
            _check_value(problems, f"{op.name}.{name}", op.args[name], value, makers, site_dir)
    return problems, missing
