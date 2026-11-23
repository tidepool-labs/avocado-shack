"""HASS-CLOVER-1/2: the Clover settings block: the optional `clover` key of host.json (HASS-CLOVER-2 accepts it in `hass/host.py`).

Closed keys, no defaults for the three identity keys, every number range-checked. A problem is reported by field name only, never by value
(the block holds a path to the token, not the token). An absent block means "Clover not configured" and nothing else changes.

Omit `writeMode` to stay read-only. `dry-run` rehearses with the read token;
`live` requires all existing write gates, even in sandbox.
"""
from dataclasses import dataclass, field

from hass.clover.mapper import CATEGORIES, MAX_PRICE_CENTS

KEYS = {"environment", "merchantId", "tokenFile", "liveApproved", "dailyWriteCap", "priceConfirmPct", "maxPriceCents",
        "lowStockThreshold", "maxStock", "categoryMap", "writeTokenFile", "writes", "siteStock", "siteStockWords", "writeMode"}
REQUIRED = ("environment", "merchantId", "tokenFile")


class ConfigProblem(ValueError):
    """`fields` are setting names only."""

    def __init__(self, fields):
        super().__init__(",".join(fields))
        self.fields = tuple(fields)


@dataclass(frozen=True)
class CloverConfig:
    environment: str
    merchant_id: str
    token_file: str
    daily_write_cap: int = 20          # Clover changes per Pacific day; an undo does not count
    price_confirm_pct: int = 25        # legacy warning threshold only; never an extra approval
    max_price_cents: int = MAX_PRICE_CENTS
    low_stock_threshold: int = 5       # at or under this count is "low"
    max_stock: int = 100_000           # a typo guard on a typed count
    category_map: dict = field(default_factory=dict)  # Hass category word -> Clover category name
    live_approved: bool = False        # explicit write go-live gate (sandbox too)

    write_token_file: str = ""
    writes: bool = False
    site_stock: str = "off"
    site_stock_words: str = "words"
    write_mode: str | None = None

    @property
    def writes_allowed(self):
        """All three write gates are required, even on sandbox; the service also validates the separate file."""
        return self.live_approved and self.writes and bool(self.write_token_file) and self.write_token_file != self.token_file


def _int(v, low, high):
    return type(v) is int and low <= v <= high


def from_settings(raw):
    """Validate a settings dict into a CloverConfig, or raise ConfigProblem(field names)."""
    if not isinstance(raw, dict):
        raise ConfigProblem(["clover"])
    bad = sorted(set(raw) - KEYS) + [k for k in REQUIRED if k not in raw]
    cmap = raw.get("categoryMap", {})
    checks = {
        "environment": raw.get("environment") in ("sandbox", "production"),
        "merchantId": isinstance(raw.get("merchantId"), str) and 8 <= len(raw["merchantId"]) <= 20 and raw["merchantId"].isascii() and raw["merchantId"].isalnum(),
        "tokenFile": isinstance(raw.get("tokenFile"), str) and 0 < len(raw["tokenFile"]) <= 4096 and raw["tokenFile"].startswith("/"),
        "writeTokenFile": isinstance(raw.get("writeTokenFile", ""), str) and ("writeTokenFile" not in raw or (raw["writeTokenFile"].startswith("/") and raw["writeTokenFile"] != raw.get("tokenFile"))),
        "writes": type(raw.get("writes", False)) is bool,
        "writeMode": raw.get("writeMode") in ("dry-run", "live"),
        "siteStock": raw.get("siteStock", "off") in ("off", "auto", "draft"),
        "siteStockWords": raw.get("siteStockWords", "words") in ("words", "limited"),
        "liveApproved": type(raw.get("liveApproved", False)) is bool,
        "dailyWriteCap": _int(raw.get("dailyWriteCap", 20), 1, 200),
        "priceConfirmPct": _int(raw.get("priceConfirmPct", 25), 1, 1000),
        "maxPriceCents": _int(raw.get("maxPriceCents", MAX_PRICE_CENTS), 1, 10_000_000),
        "lowStockThreshold": _int(raw.get("lowStockThreshold", 5), 0, 100_000),
        "maxStock": _int(raw.get("maxStock", 100_000), 1, 10_000_000),
        "categoryMap": isinstance(cmap, dict) and all(k in CATEGORIES and isinstance(v, str) and 0 < len(v) <= 100 for k, v in cmap.items()),
    }
    bad += [k for k, ok in checks.items() if not ok and k not in bad and (k in raw or k in REQUIRED)]
    if bad:
        raise ConfigProblem(bad)
    cfg = CloverConfig(raw["environment"], raw["merchantId"], raw["tokenFile"], raw.get("dailyWriteCap", 20), raw.get("priceConfirmPct", 25),
                        raw.get("maxPriceCents", MAX_PRICE_CENTS), raw.get("lowStockThreshold", 5), raw.get("maxStock", 100_000), dict(cmap),
                        raw.get("liveApproved", False), raw.get("writeTokenFile", ""), raw.get("writes", False),
                        raw.get("siteStock", "off"), raw.get("siteStockWords", "words"), raw.get("writeMode"))
    if cfg.write_mode == "live" and not cfg.writes_allowed:
        raise ConfigProblem(["writeMode"])
    return cfg
