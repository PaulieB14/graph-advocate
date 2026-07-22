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

import asyncio
import json
import logging
import os
from typing import Any, Optional

import httpx

# Reuse the tested tokenized matcher from the Kalshi endpoint so multi-word
# topics ('fed rate') and aliases (btc→bitcoin) work here too — a plain
# substring test misses 'federal funds rate' just like it did on Kalshi.
from kalshi import _tokenize_topic, _topic_match_score

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
    """Search active Polymarket markets via the public Gamma API.

    Match on title/question/slug ONLY — NOT description. Descriptions contain
    resolution rules that frequently reference unrelated topics (e.g. a SHEIN
    IPO market mentions "Fed" in its resolution criteria), so matching on
    description produces semantically-irrelevant candidates that wreck
    downstream pair quality.

    Uses tokenized matching (so 'fed rate' matches 'federal funds rate') and
    paginates by volume — the old single 200-row page sorted by an invalid
    'order=volume' field missed high-volume matches entirely (bitcoin, fed
    rate and recession all returned 0 Polymarket candidates).
    """
    tokens = _tokenize_topic(keyword)
    if not tokens:
        return []
    need = len(tokens)

    async def _page(offset: int) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as c:
                r = await c.get(
                    f"{POLYMARKET_GAMMA_BASE}/markets",
                    params={"closed": "false", "active": "true",
                            "archived": "false", "order": "volumeNum",
                            "ascending": "false", "limit": 100, "offset": offset},
                    headers=_UA,
                )
            if r.status_code == 200:
                j = r.json()
                return j if isinstance(j, list) else (j.get("data") or [])
        except Exception:
            pass
        return []

    pages = await asyncio.gather(*[_page(o) for o in range(0, 500, 100)])
    rows: list[dict] = []
    for p in pages:
        rows.extend(p)

    scored = []
    for m in rows:
        hay = " ".join(str(m.get(k) or "") for k in ("question", "slug", "groupItemTitle"))
        sc = _topic_match_score(hay, tokens)
        if sc >= need:
            try:
                vol = float(m.get("volumeNum") or m.get("volume") or 0)
            except (TypeError, ValueError):
                vol = 0.0
            scored.append((sc, vol, m))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [m for _, _, m in scored[:limit]]


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


def _arb_direction(spread: float, sem: float = 1.0) -> str:
    # Only assert a concrete tradeable direction on a strong same-condition
    # match; a weak overlap (different strike/date sharing generic words) must
    # not read as a real arbitrage.
    if sem < 0.5:
        return "verify-same-condition-first"
    if spread < -0.02:
        return "long-limitless-short-polymarket"
    if spread > 0.02:
        return "long-polymarket-short-limitless"
    return "tight"


_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "before", "between", "by",
    "do", "does", "for", "from", "have", "in", "is", "it", "of", "on", "or",
    "than", "that", "the", "this", "to", "was", "what", "when", "where",
    "which", "who", "whom", "why", "will", "with",
    # Prediction-market noise words that appear in nearly every title
    "market", "markets", "yes", "no", "outcome", "outcomes", "above", "below",
    "over", "under", "more", "less", "least", "most", "any", "all",
})

_NEGATIONS = ("not ", "n't ", "no ", "never ", "without ")


def _content_words(text: str) -> set[str]:
    """Lowercase content words from a title (alphanumeric only, stopwords removed)."""
    import re
    return {
        w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if w not in _STOPWORDS and len(w) > 1
    }


def _has_negation_flip(a: str, b: str) -> bool:
    """Return True if exactly one title contains a negation marker — the markets
    almost certainly resolve oppositely and should NOT be paired."""
    a_neg = any(n in (" " + a.lower() + " ") for n in _NEGATIONS)
    b_neg = any(n in (" " + b.lower() + " ") for n in _NEGATIONS)
    return a_neg != b_neg


def _semantic_pair_score(poly_q: str, lim_t: str, kw: str) -> float:
    """Return a 0-1 semantic similarity score for the pair, or 0 if rejected.

    - Negation flips fail outright (one says X, the other says not-X)
    - Requires >=2 shared content words beyond the search keyword itself
    - Score = Jaccard similarity of content-word sets
    """
    if _has_negation_flip(poly_q or "", lim_t or ""):
        return 0.0
    a = _content_words(poly_q)
    b = _content_words(lim_t)
    if not a or not b:
        return 0.0
    shared = a & b
    # Discount the keyword itself — it's guaranteed shared by virtue of search.
    kw_tokens = _content_words(kw)
    novel_shared = shared - kw_tokens
    if len(novel_shared) < 1:
        return 0.0
    union = a | b
    return len(shared) / max(1, len(union))


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

    try:
        limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        limit = 5

    # Fetch a wider candidate pool than the number of pairs we return, so the
    # semantic pairing has real choice (the old code capped candidates at
    # `limit`, starving the pairing step).
    pool = max(limit, 12)
    try:
        poly_hits = await search_polymarket(keyword, limit=pool)
    except Exception as exc:
        return {"error": "polymarket_unreachable", "detail": str(exc)[:200]}

    try:
        lim_hits = await search_limitless(keyword, limit=pool)
    except Exception as exc:
        return {"error": "limitless_unreachable", "detail": str(exc)[:200]}

    # Pre-filter Limitless to binary-YES/NO markets only. NegRisk multi-outcome
    # markets return prices=None on the search endpoint because there's no
    # single YES mid; our binary spread metric doesn't apply.
    lim_binary = [m for m in lim_hits if _limitless_yes_mid(m) is not None]

    # Pair selection: semantic-match score is primary; price-proximity is tiebreaker.
    # An unrelated pair scoring 0.0 on semantic match is dropped entirely even if
    # the yes-mids happen to coincide. Threshold tuned to require at least one
    # novel content word beyond the search keyword.
    MIN_SEMANTIC = 0.10  # Jaccard floor; tuned via 10-topic regression test
    pairs = []
    used_lim_ids: set = set()
    rejected_count = 0
    for p_mkt in poly_hits:
        p_mid = _polymarket_yes_mid(p_mkt)
        if p_mid is None:
            continue
        p_q = p_mkt.get("question") or ""
        best = None
        best_combined = -1.0
        for l_mkt in lim_binary:
            l_id = l_mkt.get("conditionId") or l_mkt.get("id")
            if l_id in used_lim_ids:
                continue
            l_mid = _limitless_yes_mid(l_mkt)
            if l_mid is None:
                continue
            l_t = l_mkt.get("title") or ""
            sem = _semantic_pair_score(p_q, l_t, keyword)
            if sem < MIN_SEMANTIC:
                rejected_count += 1
                continue
            # Combined ranking: semantic dominates (weight 0.8), price proximity
            # is tiebreaker (weight 0.2). Keeps pairs that are semantically
            # related but priced apart — those ARE the arbitrage candidates.
            price_close = 1.0 - abs(p_mid - l_mid)
            combined = 0.8 * sem + 0.2 * price_close
            if combined > best_combined:
                best_combined = combined
                best = (l_mkt, l_mid, l_id, sem)
        if best is None:
            continue
        l_mkt, l_mid, l_id, sem_score = best
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
                "semantic_match_score": round(sem_score, 3),
                "spread_yes_polymarket_minus_limitless": spread,
                "spread_bps": int(spread * 10000),
                "arbitrage_direction": _arb_direction(spread, sem_score),
            }
        )

    # Sort by absolute spread descending — biggest mispricings first.
    pairs.sort(
        key=lambda p: abs(p["spread_yes_polymarket_minus_limitless"]),
        reverse=True,
    )
    pairs = pairs[:limit]

    if pairs:
        status = "ok"
        agent_note = (
            "Pairs filtered by semantic content-word overlap + negation "
            "consistency, then ranked by absolute spread. Each pair carries "
            "a semantic_match_score (0-1, Jaccard on content words). Spread "
            ">200bps in either direction is a candidate arbitrage; still "
            "verify the two markets resolve on the same condition (same end "
            "date, same resolution source) before sizing."
        )
    elif poly_hits and lim_binary and rejected_count > 0:
        status = "no_semantic_match"
        agent_note = (
            f"Both venues returned candidates for this topic ({len(poly_hits)} "
            f"Polymarket / {len(lim_binary)} Limitless binary markets) but no "
            f"pair passed the semantic match filter ({rejected_count} candidate "
            f"pairings rejected). The topics overlap by keyword but the markets "
            f"are about different events. Try a more specific topic keyword."
        )
    elif poly_hits and not lim_binary and lim_hits:
        status = "limitless_multi_outcome_only"
        agent_note = (
            f"Polymarket has binary markets matching this topic, but Limitless "
            f"only has multi-outcome (NegRisk) markets which don't expose a "
            f"single YES mid in the search response. Cross-venue spread is "
            f"undefined for these. Try a topic with binary markets on both sides."
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
        "limitless_binary_candidates": len(lim_binary),
        "semantic_rejections": rejected_count,
        "pairs": pairs,
        "agent_note": agent_note,
    }
