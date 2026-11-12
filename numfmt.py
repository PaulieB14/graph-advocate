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


def _flatten(prefix: str, value: Any, out: dict) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}_{k}" if prefix else k, v, out)
    elif isinstance(value, list):
        out[prefix] = [humanize_data(v, prefix.rsplit("_", 1)[-1]) if isinstance(v, (dict, list)) else v for v in value]
    elif isinstance(value, str) and _USD_KEY_RE.search(prefix.rsplit("_", 1)[-1]) and _NUMERIC_RE.match(value.strip()):
        out[prefix] = format_usd(value) or value
    else:
        out[prefix] = value


def table_rows(data: dict, limit: int = 25) -> tuple[str | None, list[dict]]:
    """(list_field_name, flat formatted rows) for the biggest list in a GraphQL `data` block.

    {"pools": [{"token0": {"symbol": "USDC"}, "volumeUSD": "609167447506.18"}]}
      -> ("pools", [{"token0_symbol": "USDC", "volumeUSD": "$609.17B"}])
    A single-entity field (dict) becomes one row. `_meta` is ignored.
    """
    best_key, best = None, None
    for k, v in (data or {}).items():
        if k == "_meta":
            continue
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            if best is None or len(v) > len(best):
                best_key, best = k, v
        elif isinstance(v, dict) and best is None:
            best_key, best = k, [v]
    if best is None:
        return None, []
    rows = []
    for item in best[:limit]:
        flat: dict = {}
        _flatten("", item, flat)
        rows.append(flat)
    return best_key, rows
