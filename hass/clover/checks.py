"""Offline post-change checks. A verdict carries only fixed finding words."""
from dataclasses import dataclass
from decimal import Decimal
from typing import NotRequired, TypedDict

from hass.clover import mapper, reads
from hass.content_model import valid_selling_price


@dataclass(frozen=True)
class Verdict:
    ok: bool
    findings: tuple[str, ...]


class RegisterExpected(TypedDict):
    """Approved item facts: integer cents, a Clover price type/unit, and a numeric count."""

    name: str
    price_cents: int
    price_type: str
    unit_name: str  # empty for FIXED
    sku: str
    count: int | Decimal
    category_id: NotRequired[str | None]


def register_check(raw_item: dict, snapshot: reads.Snapshot, expected: RegisterExpected) -> Verdict:
    """Check the raw read-back and its name in a caller-supplied fresh snapshot."""
    try:
        item = mapper.parse_item(raw_item)
    except mapper.MapError:
        return Verdict(False, ("not-found",))

    findings = []
    if item.hidden:
        findings.append("hidden")
    name = expected["name"]
    if raw_item.get("name") != name:
        findings.append("name")
    if (item.price_cents, raw_item.get("priceType"), raw_item.get("unitName", "")) != (
        expected["price_cents"], expected["price_type"], expected["unit_name"]
    ):
        findings.append("price")
    if raw_item.get("sku", "") != expected["sku"]:
        findings.append("sku")
    if item.stock != expected["count"]:
        findings.append("count")
    if category_id := expected.get("category_id"):
        categories = raw_item.get("categories")
        elements = categories.get("elements") if isinstance(categories, dict) else None
        if not isinstance(elements, list) or not any(
            isinstance(row, dict) and row.get("id") == category_id for row in elements
        ):
            findings.append("category")

    hits = reads.exact(name, snapshot)
    if len(hits) > 1:
        findings.append("ambiguous-name")
    elif not hits or hits[0].id != item.id:
        findings.append("not-found")
    return Verdict(not findings, tuple(findings))


def site_check(site_record: dict, link: dict | None, item: mapper.CloverItem, low_threshold: int) -> Verdict:
    """Compare a website record and its saved link entry to the read-back item."""
    findings = []
    if not link or link.get("cloverId") != item.id:
        findings.append("unlinked")
    if mapper.norm_name(site_record.get("name")) != mapper.norm_name(item.name):
        findings.append("name")

    price = site_record.get("sellingPrice")
    if not isinstance(price, str) or not valid_selling_price(price):
        findings.append("price")
    else:
        amount, _, unit = price.partition(" ")
        if int(amount.replace(".", "")) != item.price_cents:
            findings.append("price")
        if not (unit == "each" and item.price_type == "FIXED"
                or unit == "per lb" and item.price_type == "PER_UNIT" and item.unit_name == "lb"):
            findings.append("price-unit")

    if site_record.get("status") != "active" or item.hidden:
        findings.append("hidden-vs-active")
    word = site_record.get("available")
    if word is None:
        findings.append("no-word")
    elif word != mapper.availability_hint(item, low_threshold):
        findings.append("stock-word")
    return Verdict(not findings or findings == ["no-word"], tuple(findings))
