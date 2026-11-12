"""Shared number formatting for subgraph values.

The Graph returns BigDecimal fields (volumeUSD, totalValueLockedUSD, amountUSD…)
as strings with up to ~30 decimal digits, e.g. "609167447506.1830892627042412837456".
Dropped raw into an answer they read as garbage, and a model asked to
paraphrase them mangles digits. Everything user-facing goes through here:

    format_usd("609167447506.18308926")  -> "$609.17B"
    round_decimal("609167447506.1830892627", 2) -> "609167447506.18"

`humanize_data` mirrors a GraphQL `data` block and replaces USD-valued string
fields with display strings; the raw `data` is always kept alongside.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

_SUFFIXES = ((Decimal("1e12"), "T"), (Decimal("1e9"), "B"), (Decimal("1e6"), "M"))
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")
_USD_KEY_RE = re.compile(r"(usd|amountusd)$", re.I)


def to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def round_decimal(value: Any, places: int = 2) -> str | None:
    """Plain-string rounding (no float, no exponent). None if not numeric."""
    d = to_decimal(value)
    if d is None:
        return None
    q = Decimal(1).scaleb(-places)
    return format(d.quantize(q, rounding=ROUND_HALF_UP), "f")


def format_usd(value: Any) -> str | None:
    """'$609.17B' / '$363.10M' / '$12,345.68' / '$0.0042'. None if not numeric."""
    d = to_decimal(value)
    if d is None:
        return None
    sign = "-" if d < 0 else ""
    a = abs(d)
    for threshold, suffix in _SUFFIXES:
        if a >= threshold:
            return f"{sign}${(a / threshold).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}{suffix}"
    if a >= 1000:
        return f"{sign}${a.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"
    if a >= 1 or a == 0:
        return f"{sign}${a.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
    return f"{sign}${a.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)}"


def format_count(value: Any) -> str | None:
    d = to_decimal(value)
    if d is None:
        return None
    return f"{d.quantize(Decimal(1), rounding=ROUND_HALF_UP):,}"


def format_fee_tier(value: Any) -> str | None:
    """Uniswap feeTier is hundredths of a bip: '500' -> '0.05%'."""
    d = to_decimal(value)
    if d is None:
        return None
    pct = (d / Decimal(10000)).normalize()
    return f"{format(pct, 'f')}%"


def humanize_data(value: Any, _key: str = "") -> Any:
    """Copy of a GraphQL `data` block with *USD string fields turned into '$1.23B'."""
    if isinstance(value, dict):
        return {k: humanize_data(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [humanize_data(v, _key) for v in value]
    if isinstance(value, str) and _USD_KEY_RE.search(_key) and _NUMERIC_RE.match(value.strip()):
        return format_usd(value) or value
    return value
