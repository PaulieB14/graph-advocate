"""Limitless + Polymarket cross-market spread.

Limitless (limitless.exchange) is a Base-native prediction market on the CTF
Conditional Tokens Framework. Two subgraphs index it (simple-markets and
negrisk-markets) plus a public REST API at api.limitless.exchange exposes
market titles and prices (titles are off-chain, not in the subgraph).

The single agent-facing endpoint here is the JOIN: given a topic keyword,
find candidate markets on both Polymarket (via Pinax Token API) and
Limitless (via Limitless REST), pair them by closest-price match, and
return per-pair spread + arbitrage direction. Single-source passthroughs
structurally can't answer this — that's the value.

Exposed via one x402-paid endpoint on graphadvocate.com:
    POST /predmarket/spread  $0.05  Polymarket ↔ Limitless spread on a topic
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

LIMITLESS_API_BASE = "https://api.limitless.exchange"
# Polymarket's public Gamma API returns markets with `outcomePrices` and
# `lastTradePrice` inline — single request, no auth, no N+1. The Pinax
# `/polymarket/markets` endpoint returns metadata only (no prices), which
# would force a per-market OHLC call to derive a yes-mid. Gamma is simpler.
POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com"

_HTTP_TIMEOUT = httpx.Timeout(12.0, connect=5.0)

_UA = {"User-Agent": "graph-advocate/1.0 (+https://graphadvocate.com)"}


def _limitless_headers() -> dict:
    h = dict(_UA)
    key = os.environ.get("LIMITLESS_API_KEY")
    if key:
        h["X-API-Key"] = key
    return h


def _pinax_headers() -> dict:
    h = dict(_UA)
    key = (
        os.environ.get("TOKEN_API_JWT", "")
        or os.environ.get("TOKEN_API_ACCESS_TOKEN", "")
        or os.environ.get("JWT", "")
        or os.environ.get("PINAX_API_KEY", "")
    )
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


async def search_limitless(keyword: str, limit: int = 5) -> list[dict]:
    """Search Limitless markets by keyword. Public endpoint, no key required."""
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as c:
        r = await c.get(
            f"{LIMITLESS_API_BASE}/markets/search",
            params={"query": keyword},
            headers=_limitless_headers(),
        )
    if r.status_code != 200:
        return []
    body = r.json() or {}
    rows = body.get("markets") or body.get("data") or []
    return rows[:limit]


async def search_polymarket(keyword: str, limit: int = 5) -> list[dict]:
    """Search Polymarket markets via public Gamma API.

    Gamma's `/markets` accepts a free-text search-style filter and returns
    prices inline (no per-market OHLC follow-up). Public, no auth.
    """
    kw = (keyword or "").strip().lower()
    if not kw:
        return []
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as c:
        # Gamma supports server-side filtering via `q`, but to be robust to
        # rolling API changes (Polymarket has changed Gamma param names
        # several times) we pull a wider page and client-side filter.
        r = await c.get(
            f"{POLYMARKET_GAMMA_BASE}/markets",
            params={"closed": "false", "active": "true", "limit": 200, "order": "volume", "ascending": "false"},
            headers=_UA,
        )
    if r.status_code != 200:
        return []
    rows = r.json() or []
    out = []
    for m in rows:
        hay = " ".join(
            str(m.get(k) or "")
            for k in ("slug", "question", "groupItemTitle", "description")
        ).lower()
        if kw in hay:
            out.append(m)
        if len(out) >= limit:
            break
    return out


def _limitless_yes_mid(m: dict) -> Optional[float]:
    """Yes-side mid price from Limitless market record.

    Limitless returns `prices: [yes, no]` as 0-1 floats. Also accepts
    `tradePrices.buy.limit[0]` (yes-buy limit price) as a fallback.
    """
    prices = m.get("prices")
    if isinstance(prices, list) and len(prices) >= 2:
        try:
            yes = float(prices[0])
            if 0 < yes < 1:
                return round(yes, 4)
        except (TypeError, ValueError):
            pass
    tp = m.get("tradePrices") or {}
    try:
        buy_limit = (tp.get("buy") or {}).get("limit") or []
        if buy_limit:
            yes = float(buy_limit[0])
            if 0 < yes < 1:
                return round(yes, 4)
    except (TypeError, ValueError, IndexError):
        pass
    return None


def _polymarket_yes_mid(m: dict) -> Optional[float]:
    """Yes-side mid price from a Polymarket Gamma API market record.

    Gamma returns `outcomePrices` as a JSON-encoded string like
    `'["0.515", "0.485"]'` (yes, no). Falls back to `lastTradePrice`.
    """
    raw = m.get("outcomePrices")
    if isinstance(raw, str):
        try:
            arr = json.loads(raw)
            if isinstance(arr, list) and len(arr) >= 2:
                yes = float(arr[0])
                if 0 < yes < 1:
                    return round(yes, 4)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    if isinstance(raw, list) and len(raw) >= 2:
        try:
            yes = float(raw[0])
            if 0 < yes < 1:
                return round(yes, 4)
        except (TypeError, ValueError):
            pass
    last = m.get("lastTradePrice")
    if last is not None:
        try:
            p = float(last)
            if 0 < p < 1:
                return round(p, 4)
        except (TypeError, ValueError):
            pass
    return None


def _arb_direction(spread: float) -> str:
    if spread < -0.02:
        return "long-limitless-short-polymarket"
    if spread > 0.02:
        return "long-polymarket-short-limitless"
    return "tight"


async def polymarket_limitless_spread(topic_keyword: str, limit: int = 5) -> dict:
    """Cross-source spread between Polymarket and Limitless on a topic.

    Returns paired markets ranked by absolute spread (largest first), so an
    agent can scan for arbitrage opportunities. Status field is set so the
    caller knows whether the empty case means "no Limitless data" vs.
    "topic too generic" vs. "both venues uncovered".
    """
    keyword = (topic_keyword or "").strip()
    if not keyword:
        return {"error": "topic_keyword_required"}
    if len(keyword) < 3:
        return {
            "error": "topic_keyword_too_short",
            "topic_tried": keyword,
            "expected": "Use a 3+ character topic (e.g. 'trump', 'fed rate', 'btc', 'super bowl').",
        }

    limit = max(1, min(int(limit), 10))

    try:
        poly_hits = await search_polymarket(keyword, limit=limit)
    except Exception as exc:
        return {"error": "polymarket_unreachable", "detail": str(exc)[:200]}

    try:
        lim_hits = await search_limitless(keyword, limit=limit)
    except Exception as exc:
        return {"error": "limitless_unreachable", "detail": str(exc)[:200]}

    pairs = []
    used_lim_ids: set = set()
    for p_mkt in poly_hits:
        p_mid = _polymarket_yes_mid(p_mkt)
        if p_mid is None:
            continue
        best = None
        best_score = -1.0
        for l_mkt in lim_hits:
            l_id = l_mkt.get("conditionId") or l_mkt.get("id")
            if l_id in used_lim_ids:
                continue
            l_mid = _limitless_yes_mid(l_mkt)
            if l_mid is None:
                continue
            # Closest-price match — Polymarket and Limitless rarely use the
            # exact same wording for the same event, so price proximity is
            # the most reliable cross-venue alignment signal.
            score = 1.0 - abs(p_mid - l_mid)
            if score > best_score:
                best_score = score
                best = (l_mkt, l_mid, l_id)
        if best is None:
            continue
        l_mkt, l_mid, l_id = best
        used_lim_ids.add(l_id)
        spread = round(p_mid - l_mid, 4)
        pairs.append(
            {
                "polymarket_slug": p_mkt.get("slug"),
                "polymarket_question": p_mkt.get("question"),
                "polymarket_yes_mid": p_mid,
                "limitless_condition_id": l_mkt.get("conditionId"),
                "limitless_slug": l_mkt.get("slug"),
                "limitless_title": l_mkt.get("title"),
                "limitless_yes_mid": l_mid,
                "spread_yes_polymarket_minus_limitless": spread,
                "spread_bps": int(spread * 10000),
                "arbitrage_direction": _arb_direction(spread),
            }
        )

    pairs.sort(
        key=lambda p: abs(p["spread_yes_polymarket_minus_limitless"]),
        reverse=True,
    )

    if pairs:
        status = "ok"
        agent_note = (
            "Spread > 200bps in either direction is a candidate arbitrage; "
            "verify the two markets actually resolve on the same condition "
            "(same end date, same resolution source) before sizing. Naive "
            "title-overlap pair-up — confirm semantically before trading."
        )
    elif poly_hits and not lim_hits:
        status = "polymarket_only"
        agent_note = (
            "Polymarket has markets matching this topic; Limitless does not. "
            "Limitless is Base-native and skews crypto/AI/tech topics — try "
            "those keywords for higher cross-venue match rate."
        )
    elif lim_hits and not poly_hits:
        status = "limitless_only"
        agent_note = (
            "Limitless has markets matching this topic; Polymarket does not. "
            "Polymarket is broader (politics, sports, current events) — try "
            "a more mainstream topic keyword for cross-venue overlap."
        )
    else:
        status = "no_matches"
        agent_note = (
            "Neither venue returned markets matching this topic. Try a "
            "broader keyword or a known active event (e.g. 'trump', "
            "'bitcoin', 'fed rate', 'world cup')."
        )

    return {
        "topic_keyword": keyword,
        "status": status,
        "polymarket_candidates": len(poly_hits),
        "limitless_candidates": len(lim_hits),
        "pairs": pairs,
        "agent_note": agent_note,
    }
