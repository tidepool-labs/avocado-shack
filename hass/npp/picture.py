"""S6: settle the install choice, check raw privacy, and freeze the exact picture identity.

The job runner owns when to start/wait for polish. Call this at picture decision time
(including a deadline fallback), not just to poll: it may settle the existing
write-once decision. This stage never starts an edit, drafts a card, or sends anything.
"""
from __future__ import annotations

import hashlib
import io
import re
import subprocess
import time
from dataclasses import dataclass

from hass import house_style, media, newitem_render, publish_live
from hass.ops import Refused, photos

# The fidelity reader strips punctuation and short words. It cannot screen the
# actual picture read for prices, contact info or private one-digit values.
_MONEY = re.compile(r"[$¢]|\d\s*[.,]\s*\d{2}(?!\d)|\b(?:cents?|dollars?|bucks?)\b", re.I)
_NOTES = {"raw": "picture: your own photo", "house": "picture: house style"}


@dataclass(frozen=True)
class FrozenPicture:
    variant: str
    image_path: str
    image_sha256: str

    @property
    def note(self) -> str:
        """Text inside the job runner's single fallback bracket."""
        return _NOTES.get(self.variant, "")

    def matches_draft(self, draft: object) -> bool:
        """Use before S8 capture: a path alone does not identify the picture bytes."""
        if not isinstance(draft, dict):
            return False
        assets = draft.get("assets")
        return isinstance(assets, dict) and assets.get(self.image_path) == "sha256:" + self.image_sha256


def read_text(data: bytes, *, timeout: float = 30) -> str | None:
    """Local OCR of the exact selected bytes. Empty successful read differs from failure."""
    deadline = time.monotonic() + timeout
    reads = []
    try:
        # The normal page read can miss dark text on colored stickers. A red-channel
        # read lifts yellow paper away from black ink without cropping any pixels.
        Image, *_ = newitem_render._modules()
        with Image.open(io.BytesIO(data)) as img, io.BytesIO() as channel:
            img.convert("RGB").getchannel("R").save(channel, "PNG")
            passes = (data, channel.getvalue())
        for view in passes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            result = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "11"], input=view,
                                    capture_output=True, timeout=remaining, check=False)
            if result.returncode != 0:
                return None
            reads.append(result.stdout.decode("utf-8"))
        return "\n\n".join(reads).strip()
    except (house_style.PillowMissing, OSError, subprocess.TimeoutExpired, UnicodeError, MemoryError):
        return None


def choose(settings, sha, *, has_person_or_screen, private_numbers_clear,
           label_words=(), source_label_words=(), ocr=read_text) -> FrozenPicture | photos.Retake:
    """Select an initial listing picture, or return an owner-facing retake with no image.

    ``private_numbers_clear(text, allowed_label_tokens)`` is the local S7 number
    checker bound to the job's typed private values; only explicit True passes.
    ``label_words`` is the S2 evidence for this photo and ``source_label_words``
    an independent read of its printed label, not the back photo or whole-scene OCR.
    Neither OCR nor the private number check runs on the legacy install path.
    """
    if not isinstance(sha, str) or not media.SHA_RE.fullmatch(sha):
        return photos.Retake(photos.RETAKE["style"], ("style",))
    selected, _, _ = photos._installation_picture(settings, sha, style=True,
                                                     owner_fallback=settings.get("itemIntake") is True)
    if isinstance(selected, photos.Retake):
        return selected
    if isinstance(selected, Refused):
        return photos.Retake(photos.RETAKE["style"], ("style",))
    if selected.variant == "raw":
        reason = _raw_problem(selected.data, has_person_or_screen, private_numbers_clear,
                              label_words, source_label_words, ocr)
        if reason:
            return photos.Retake(photos.RETAKE[reason], (reason,))
    return FrozenPicture(selected.variant, selected.path, hashlib.sha256(selected.data).hexdigest())


def _raw_problem(data, has_person_or_screen, private_numbers_clear, label_words, source_label_words, ocr):
    if has_person_or_screen is not False:
        return "style"
    try:
        img, alpha, _ = newitem_render._upright(data)
        sharp = photos._sharpness(img, alpha)
    except (media.Refused, newitem_render.Refused, house_style.PillowMissing, OSError, MemoryError):
        return "style"
    if sharp is None or sharp < photos.SHARP_MIN:
        return "blurry"
    text = ocr(data)
    if (not isinstance(text, str) or _MONEY.search(text) or "/home/" in text.casefold()
            or any(pattern.search(text) for pattern in publish_live.PATTERNS.values())):
        return "style"
    allowed = frozenset(word.casefold() for word in label_words).intersection(
        word.casefold() for word in source_label_words)
    if private_numbers_clear(text, allowed) is not True:
        return "style"
    return None
