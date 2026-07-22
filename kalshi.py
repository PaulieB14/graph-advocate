"""
Kalshi derived-signal endpoints — three high-leverage tools that survive
Pinax adding raw Kalshi data because they're cross-source JOINs or
derived scores that passthrough APIs structurally can't replicate.

1. kalshi_event_consensus_trend(event_ticker)
   Wraps the UNIQUE /events/{ticker}/forecast_history endpoint that no
   other prediction market exposes. Returns slope, acceleration, and
   confidence band around the current consensus probability.

2. kalshi_polymarket_spread(topic_keyword)
   Cross-source JOIN — Politics/Elections series overlap heavily between
   Kalshi and Polymarket. Returns price spread + arbitrage direction.

3. kalshi_sports_live_edge(milestone_id)
   Combines live game_stats (play-by-play) + market candlesticks for
   live-mispricing detection on sports markets — unique to Kalshi.

All Kalshi calls are public (no auth). Uses httpx async.

Response-quality improvements (2026-06-11): each function now does
input-format validation and returns helpful "did_you_mean" suggestions
when the requested entity doesn't exist, so a fat-fingered caller can
retry intelligently without re-paying.
"""
from __future__ import annotations
import asyncio
import json
import re
import time
import logging
import os
from typing import Any, Optional
import httpx

log = logging.getLogger("graph-advocate")

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
PINAX_BASE = "https://api.pinax.network/v1"
PINAX_JWT = os.environ.get("TOKEN_API_JWT") or os.environ.get("TOKEN_API_ACCESS_TOKEN") or ""

_UA = {"User-Agent": "graph-advocate/1.0", "accept": "application/json"}
GAMMA_BASE = "https://gamma-api.polymarket.com"


# ===========================================================================
# Shared topic matching (tokenized) + cached Kalshi series catalog.
# Added 2026-07-21. The old cross-source matcher used a whole-phrase substring
# test (`"fed rate" in title`) against only the first 100 default-sorted
# Kalshi markets (MVE sports parlays). So "fed rate" matched 0 markets (real
# titles read "federal funds rate") and suggested nonsensical parlays. We now
# match per-token (with a small alias map), seed Kalshi from the /series
# catalog, and price Polymarket via Gamma's public API.
# ===========================================================================

_STOPWORDS = {
    "the", "a", "an", "of", "on", "in", "to", "for", "and", "or", "will",
    "be", "by", "is", "are", "at", "vs", "with", "this", "that", "what",
    "which", "who", "how", "market", "markets", "odds",
}
# token -> extra surface forms to also try (recall for tickers/abbreviations
# that markets spell out in full)
_TOKEN_ALIASES = {
    "btc": ("bitcoin",), "eth": ("ethereum",), "sol": ("solana",),
    "fed": ("federal", "fomc"), "fomc": ("fed", "federal"),
    "potus": ("president",), "prez": ("president",),
    "gop": ("republican",), "dem": ("democrat", "democratic"),
    "cpi": ("inflation",),
}


def _tokenize_topic(s: str) -> list[str]:
    toks = [t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t]
    return [t for t in toks if len(t) >= 2 and t not in _STOPWORDS]


_WORD_RE = re.compile(r"[a-z0-9]+")
_STEM_SUFFIXES = ("s", "es", "ed", "ing", "d", "n")


def _word_matches(word: str, form: str) -> bool:
    """True if `word` is `form` or a simple plural/tense inflection of it (in
    either direction). Deliberately NOT a general prefix match: 'champions'
    must not match 'championship', 'eth' must not match 'ethiopia', and 'fed'
    must not match 'federal' here (that is handled by the alias map)."""
    if word == form:
        return True
    for suf in _STEM_SUFFIXES:
        if word == form + suf or form == word + suf:
            return True
    return False


def _topic_match_score(text: str, tokens: list[str]) -> int:
    """How many query tokens (or their aliases) match a whole word in text.
    Exact-word with light plural/tense stemming, so 'rate' matches 'rates' and
    'fed' (via its 'federal' alias) matches 'federal', but 'nfl' does not match
    'inflation' and 'eth' does not match 'ethiopia'."""
    if not tokens:
        return 0
    words = _WORD_RE.findall((text or "").lower())
    if not words:
        return 0
    hits = 0
    for t in tokens:
        forms = (t,) + _TOKEN_ALIASES.get(t, ())
        if any(_word_matches(w, f) for w in words for f in forms):
            hits += 1
    return hits


def _content_overlap(a_text: str, b_text: str) -> float:
    """Jaccard overlap of significant content tokens — used to pair a Kalshi
    market with the Polymarket market on the *same* condition (not merely a
    similar price)."""
    a = set(_tokenize_topic(a_text))
    b = set(_tokenize_topic(b_text))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_SERIES_CACHE: list[dict] = []
_SERIES_CACHE_TS = 0.0
_SERIES_CACHE_TTL = 6 * 3600  # series catalog changes slowly
_SERIES_LOCK = asyncio.Lock()


async def _kalshi_series_catalog(c: httpx.AsyncClient) -> list[dict]:
    """Full Kalshi series catalog (~12k), trimmed to {ticker,title,category},
    cached in-process for 6h. Returns stale/empty on failure so callers can
    fall back to a paginated market scan."""
    global _SERIES_CACHE, _SERIES_CACHE_TS
    if _SERIES_CACHE and (time.time() - _SERIES_CACHE_TS) < _SERIES_CACHE_TTL:
        return _SERIES_CACHE
    async with _SERIES_LOCK:
        if _SERIES_CACHE and (time.time() - _SERIES_CACHE_TS) < _SERIES_CACHE_TTL:
            return _SERIES_CACHE
        try:
            r = await c.get(f"{KALSHI_BASE}/series", headers=_UA, timeout=20.0)
            if r.status_code == 200:
                raw = r.json().get("series") or []
                trimmed = [
                    {"ticker": s.get("ticker"),
                     "title": s.get("title") or "",
                     "category": s.get("category") or ""}
                    for s in raw if s.get("ticker")
                ]
                if trimmed:
                    _SERIES_CACHE = trimmed
                    _SERIES_CACHE_TS = time.time()
        except Exception:
            pass
        return _SERIES_CACHE


def _series_coverage(series_title: str, tokens: list[str]) -> float:
    """Fraction of the series title's content words that the query explains —
    favours on-topic series ('Bitcoin price' for 'btc') over long unrelated
    titles that merely contain one query token."""
    title_toks = _tokenize_topic(series_title)
    if not title_toks:
        return 0.0
    return _topic_match_score(series_title, tokens) / len(title_toks)


async def _kalshi_markets_for_topic(c: httpx.AsyncClient, tokens: list[str],
                                    max_series: int = 10, cap: int = 60) -> list[dict]:
    """Series-seeded market fetch: match the topic against the /series catalog,
    then pull open markets for the best-matching series. Falls back to a
    bounded paginated market scan if the catalog is unavailable."""
    need = len(tokens)
    series = await _kalshi_series_catalog(c)
    if series:
        scored = []
        for s in series:
            # Score on the title only. A ticker-match bonus would boost Kalshi's
            # deprecated legacy short-code series (ticker 'BTC'/'CPI' == token)
            # above the current KX-prefixed series that actually carry markets.
            sc = _topic_match_score(s["title"], tokens)
            if sc >= need:
                scored.append((sc, s))
        if not scored and need > 1:  # relax to majority of tokens
            for s in series:
                if _topic_match_score(s["title"], tokens) >= need - 1:
                    scored.append((need - 1, s))
        # Rank: raw score, then current (KX-prefixed) series over legacy ones,
        # then title coverage. Kalshi's legacy non-KX series (e.g. 'BTC', 'CPI')
        # are deprecated and carry 0 open markets — the live markets live under
        # the KX-prefixed series ('KXBTC', 'KXCPI'), so KX must win.
        scored.sort(key=lambda x: (x[0],
                                   1 if str(x[1]["ticker"] or "").startswith("KX") else 0,
                                   _series_coverage(x[1]["title"], tokens)),
                    reverse=True)
        top = [s for _, s in scored[:max_series]]
        if top:
            # Fetch series' markets sequentially with light pacing + retry on
            # 429. Kalshi rate-limits bursts, so firing every series at once
            # silently empties the result. Series are coverage-ranked (most
            # on-topic first), so stop early once we have enough markets.
            async def _fetch(ticker: str) -> list[dict]:
                for attempt in range(3):
                    try:
                        r = await c.get(f"{KALSHI_BASE}/markets",
                                        params={"series_ticker": ticker,
                                                "status": "open", "limit": 100},
                                        headers=_UA)
                        if r.status_code == 200:
                            return r.json().get("markets") or []
                        if r.status_code == 429 and attempt < 2:
                            await asyncio.sleep(0.4 * (attempt + 1))
                            continue
                    except Exception:
                        if attempt < 2:
                            await asyncio.sleep(0.3)
                            continue
                    return []
                return []

            markets: list[dict] = []
            for i, s in enumerate(top):
                if i:
                    await asyncio.sleep(0.12)  # gentle stagger between series
                markets.extend(await _fetch(s["ticker"]))
                if len(markets) >= cap:
                    break
            if markets:
                return markets[:cap * 2]
    return await _kalshi_market_scan(c, tokens, cap=cap)


async def _kalshi_market_scan(c: httpx.AsyncClient, tokens: list[str],
                              max_pages: int = 14, cap: int = 60) -> list[dict]:
    """Bounded paginated fallback: page open markets and keep token matches."""
    need = len(tokens)
    out: list[dict] = []
    cursor = ""
    for _ in range(max_pages):
        params = {"limit": 200, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        try:
            r = await c.get(f"{KALSHI_BASE}/markets", params=params, headers=_UA)
            if r.status_code != 200:
                break
            j = r.json()
        except Exception:
            break
        for m in (j.get("markets") or []):
            txt = " ".join(str(m.get(k) or "") for k in
                           ("title", "subtitle", "yes_sub_title", "event_ticker"))
            if _topic_match_score(txt, tokens) >= need:
                out.append(m)
        cursor = j.get("cursor") or ""
        if not cursor or len(out) >= cap:
            break
    return out


async def _gamma_active_markets(c: httpx.AsyncClient, pages: int = 5,
                                per: int = 100) -> list[dict]:
    """Active Polymarket markets (with inline outcomePrices) via Gamma's public
    API, ranked by volume. Paginated concurrently. Public — no auth."""
    async def _one(off: int) -> list[dict]:
        try:
            r = await c.get(f"{GAMMA_BASE}/markets", headers=_UA,
                            params={"active": "true", "closed": "false",
                                    "archived": "false", "order": "volumeNum",
                                    "ascending": "false", "limit": per, "offset": off})
            if r.status_code == 200:
                j = r.json()
                return j if isinstance(j, list) else (j.get("data") or [])
        except Exception:
            pass
        return []
    res = await asyncio.gather(*[_one(o) for o in range(0, pages * per, per)])
    out: list[dict] = []
    for r in res:
        out.extend(r)
    return out


def _gamma_yes_mid(m: dict) -> Optional[float]:
    """Current YES price (0-1) for a Gamma market. outcomes/outcomePrices are
    JSON-encoded arrays; map by the 'Yes' label, fall back to last trade."""
    prices = m.get("outcomePrices")
    outs = m.get("outcomes")
    try:
        if isinstance(prices, str):
            prices = json.loads(prices)
        if isinstance(outs, str):
            outs = json.loads(outs)
    except Exception:
        prices, outs = None, None
    idx = 0
    if isinstance(outs, list):
        for i, o in enumerate(outs):
            if str(o).strip().lower() == "yes":
                idx = i
                break
    if isinstance(prices, list) and len(prices) > idx:
        try:
            return round(float(prices[idx]), 4)
        except Exception:
            pass
    v = m.get("lastTradePrice")
    try:
        return round(float(v), 4) if v is not None else None
    except Exception:
        return None


# ===========================================================================
# 1. Event consensus trend
# ===========================================================================

_EVENT_TICKER_RE = re.compile(r"^KX[A-Z0-9][A-Z0-9_\-]*$")


async def _suggest_active_events(c: httpx.AsyncClient, limit: int = 5) -> list[dict]:
    """Fetch a handful of currently-open events to suggest to a caller
    whose lookup missed. Best-effort — failures return empty list."""
    try:
        r = await c.get(f"{KALSHI_BASE}/events",
                        params={"limit": limit, "status": "open"})
        if r.status_code != 200:
            return []
        ev = r.json().get("events", []) or []
        return [
            {"event_ticker": e.get("event_ticker"),
             "title": (e.get("title") or "")[:120],
             "category": e.get("category")}
            for e in ev[:limit] if e.get("event_ticker")
        ]
    except Exception:
        return []


async def kalshi_event_consensus_trend(event_ticker: str) -> dict:
    """Slope + acceleration of Kalshi's published consensus probability.

    Pulls /events/{ticker}/forecast_history (Kalshi exposes pre-computed
    forecast percentiles — no other PM does). Derives the recent trajectory
    so an agent can see WHERE the market is converging without re-doing
    the regression.
    """
    event_ticker = event_ticker.strip().upper()

    # Input-format validation. Kalshi tickers all start with "KX" by
    # convention. Reject obviously-garbage early with a helpful hint so
    # the caller (who already paid) at least learns the format to retry with.
    if not _EVENT_TICKER_RE.match(event_ticker):
        async with httpx.AsyncClient(timeout=8.0, headers=_UA) as c:
            suggestions = await _suggest_active_events(c, limit=5)
        return {
            "error": "invalid_event_ticker_format",
            "ticker_tried": event_ticker,
            "expected_format": "Kalshi event tickers start with KX and use uppercase A-Z, digits, hyphens, underscores. Example: KXNEWPOPE-70, KXFED-25DEC-CUT25.",
            "did_you_mean": suggestions,
            "discover": f"{KALSHI_BASE}/events?status=open — listing of currently-open events you can pick a ticker from.",
        }

    async with httpx.AsyncClient(timeout=10.0, headers=_UA) as c:
        try:
            r = await c.get(f"{KALSHI_BASE}/events/{event_ticker}")
            if r.status_code != 200:
                # Event format was valid but Kalshi has no record. Offer a
                # short list of active events as fallback. This costs ~1
                # extra Kalshi call but turns a dead end into a retry path.
                suggestions = await _suggest_active_events(c, limit=5)
                return {
                    "error": "event_not_found",
                    "event_ticker": event_ticker,
                    "kalshi_status": r.status_code,
                    "did_you_mean": suggestions,
                    "discover": f"{KALSHI_BASE}/events?status=open",
                    "note": "Ticker format was valid but Kalshi returned 404. Suggestions above are currently-open events you could pivot to.",
                }
            ev = r.json().get("event", {}) or {}
            markets = (r.json().get("markets") or [])
            r2 = await c.get(f"{KALSHI_BASE}/events/{event_ticker}/forecast_history",
                             params={"limit": 200})
            history_body = r2.json() if r2.status_code == 200 else {}
            history = history_body.get("forecast_history") or history_body.get("history") or []
        except Exception as exc:
            return {"error": "kalshi_unreachable", "detail": str(exc)[:200]}

    # Derive trajectory from history snapshots.
    points: list[tuple[float, float]] = []  # (epoch_seconds, probability)
    for h in history:
        ts_str = h.get("ts") or h.get("timestamp") or h.get("created_time")
        forecast = h.get("forecast") or h.get("formatted_forecast") or h.get("median")
        if ts_str is None or forecast is None:
            continue
        try:
            if isinstance(ts_str, str):
                from datetime import datetime, timezone
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            else:
                ts = float(ts_str)
            p = float(forecast)
        except Exception:
            continue
        if p > 1.0001:
            p = p / 100.0  # forecast given as percent 0-100
        points.append((ts, p))

    points.sort(key=lambda x: x[0])
    consensus_now = points[-1][1] if points else None

    def _slope(window_pts: list[tuple[float, float]]) -> Optional[float]:
        """Per-hour slope using ordinary least squares; None if <3 points."""
        if len(window_pts) < 3:
            return None
        n = len(window_pts)
        sum_x = sum(p[0] for p in window_pts)
        sum_y = sum(p[1] for p in window_pts)
        sum_xy = sum(p[0] * p[1] for p in window_pts)
        sum_xx = sum(p[0] * p[0] for p in window_pts)
        denom = n * sum_xx - sum_x * sum_x
        if abs(denom) < 1e-9:
            return None
        m_per_sec = (n * sum_xy - sum_x * sum_y) / denom
        return m_per_sec * 3600  # convert to per-hour

    now = points[-1][0] if points else time.time()
    last_24h = [p for p in points if p[0] >= now - 24 * 3600]
    last_3d = [p for p in points if p[0] >= now - 3 * 24 * 3600]

    slope_24h = _slope(last_24h)
    slope_3d = _slope(last_3d)

    # Acceleration = recent slope vs older slope; signed indicator
    acceleration = None
    if slope_24h is not None and slope_3d is not None:
        acceleration = slope_24h - slope_3d  # >0 = accelerating up, <0 = decelerating

    # Volatility band: rolling std-dev of last 24h
    if len(last_24h) >= 4:
        mean_p = sum(p[1] for p in last_24h) / len(last_24h)
        var = sum((p[1] - mean_p) ** 2 for p in last_24h) / len(last_24h)
        stdev_24h = var ** 0.5
    else:
        stdev_24h = None

    # Days to resolve
    close_time = ev.get("close_time") or ev.get("expected_expiration_time")
    days_to_resolve = None
    if close_time:
        try:
            from datetime import datetime
            close_ts = datetime.fromisoformat(close_time.replace("Z", "+00:00")).timestamp()
            days_to_resolve = round((close_ts - time.time()) / 86400, 2)
        except Exception:
            pass

    # Distinguish three valid-event cases: rich history, exists-but-no-history-yet,
    # and exists-but-Kalshi-hasn't-snapshotted-forecast. The middle case is the
    # frustrating one — the event exists but the trend signal is empty.
    if len(points) == 0:
        status = "no_forecast_history_yet"
        note = (
            "Event exists on Kalshi but no forecast snapshots have been recorded yet. "
            "Common for newly-listed events or markets with very thin trading. Retry "
            "in 24h or pick a more-active event in the same category."
        )
    elif len(points) < 5:
        status = "thin_forecast_history"
        note = (
            f"Only {len(points)} forecast snapshots available. Slope/acceleration are "
            "computed but treat as low-confidence — wait until 24h of data accrues."
        )
    else:
        status = "ok"
        note = (
            "Forecast history is Kalshi's published consensus probability over time. "
            "Use slope+acceleration to detect regime changes before they're priced in. "
            "Pair with /kalshi-polymarket-spread for cross-source arbitrage."
        )

    return {
        "status": status,
        "kalshi_event_ticker": event_ticker,
        "event_title": ev.get("title"),
        "category": ev.get("category"),
        "consensus_probability_now": consensus_now,
        "slope_per_hour_24h": slope_24h,
        "slope_per_hour_3d": slope_3d,
        "acceleration_signal": acceleration,
        "interpretation": (
            "accelerating-up" if (acceleration or 0) > 0.001
            else "accelerating-down" if (acceleration or 0) < -0.001
            else "stable" if acceleration is not None
            else "insufficient-history"
        ),
        "volatility_24h_stdev": stdev_24h,
        "days_to_resolve": days_to_resolve,
        "markets_in_event": len(markets),
        "history_points_analyzed": len(points),
        "kalshi_source": f"{KALSHI_BASE}/events/{event_ticker}/forecast_history",
        "agent_note": note,
    }


# ===========================================================================
# 2. Kalshi vs Polymarket cross-source spread
# ===========================================================================

async def kalshi_polymarket_spread(topic_keyword: str, limit: int = 5) -> dict:
    """Cross-source arbitrage: spread between Kalshi + Polymarket on same topic.

    Survives Pinax adding raw Kalshi data because Pinax exposes one source
    at a time; the JOIN is the value-add.
    """
    keyword = topic_keyword.strip()
    if not keyword:
        return {"error": "topic_keyword_required"}
    # Validate keyword length — single-char garbage like "X" matches too
    # much noise and is almost certainly a probe. Return guidance instead.
    if len(keyword) < 3:
        return {
            "error": "topic_keyword_too_short",
            "topic_tried": keyword,
            "expected": "Use a 3+ character topic (e.g. 'fed rate', 'super bowl', 'election', 'btc price').",
            "example_topics": [
                "fed rate", "super bowl", "presidential", "btc",
                "world cup", "pope", "oscars", "inflation"
            ],
        }
    try:
        limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        limit = 5

    tokens = _tokenize_topic(keyword)
    if not tokens:
        return {
            "error": "topic_keyword_unusable",
            "topic_tried": keyword,
            "expected": "Include a distinctive word, e.g. 'fed', 'super bowl', 'bitcoin', 'election'.",
        }
    need = len(tokens)

    async with httpx.AsyncClient(timeout=15.0) as c:
        # Kalshi — seed from the /series catalog (precise), pull matching series'
        # open markets. Polymarket — Gamma public API (active, prices inline).
        try:
            kalshi_markets, poly_markets = await asyncio.gather(
                _kalshi_markets_for_topic(c, tokens),
                _gamma_active_markets(c),
            )
        except Exception as exc:
            return {"error": "upstream_unreachable", "detail": str(exc)[:200]}

    def _k_text(m: dict) -> str:
        return " ".join(str(m.get(k) or "") for k in
                        ("title", "subtitle", "yes_sub_title", "event_ticker", "ticker"))

    def _p_text(m: dict) -> str:
        return " ".join(str(m.get(k) or "") for k in
                        ("question", "slug", "groupItemTitle"))

    def _vol(m: dict, *keys: str) -> float:
        for k in keys:
            v = m.get(k)
            if v not in (None, ""):
                try:
                    return float(v)
                except Exception:
                    pass
        return 0.0

    # Kalshi markets are already series-filtered to the topic; rank by volume.
    kalshi_hits = sorted(kalshi_markets,
                         key=lambda m: _vol(m, "volume_fp", "volume_24h_fp"),
                         reverse=True)[:limit]
    # Polymarket: keep token matches (all tokens; relax to majority if empty),
    # rank by volume.
    # Require ALL query tokens on the Polymarket side. Relaxing to a subset let
    # a single generic token ('champion', 'cup', 'taylor') pull in wildly
    # off-topic markets (F1 championships for 'nba champion', MLS Cup for
    # 'world cup', Marjorie Taylor Greene for 'taylor swift').
    poly_scored = sorted(
        ((_topic_match_score(_p_text(m), tokens), _vol(m, "volumeNum", "volume"), m)
         for m in poly_markets),
        key=lambda x: (x[0], x[1]), reverse=True)
    poly_hits = [m for s, _, m in poly_scored if s >= need][:limit]

    def _kalshi_mid(m: dict) -> Optional[float]:
        yb = m.get("yes_bid_dollars") or m.get("yes_bid")
        ya = m.get("yes_ask_dollars") or m.get("yes_ask")
        try:
            if yb is None or ya is None: return None
            yb, ya = float(yb), float(ya)
            # if in cents, normalize to 0-1
            if max(yb, ya) > 1.5: yb, ya = yb / 100.0, ya / 100.0
            return round((yb + ya) / 2.0, 4)
        except Exception:
            return None

    # Pair each Kalshi market with the Polymarket market that shares the most
    # content words (same underlying condition), not merely the closest price.
    pairs = []
    for k_mkt in kalshi_hits:
        k_mid = _kalshi_mid(k_mkt)
        if k_mid is None:
            continue
        # Overlap on the human titles only — including ticker/slug tokens
        # dilutes the Jaccard and hides genuinely same-condition pairs.
        k_title = str(k_mkt.get("title") or k_mkt.get("subtitle") or "")
        best = None
        best_ov = 0.0
        for p_mkt in poly_hits:
            p_mid = _gamma_yes_mid(p_mkt)
            if p_mid is None:
                continue
            ov = _content_overlap(k_title, str(p_mkt.get("question") or ""))
            if ov > best_ov:
                best_ov = ov
                best = (p_mkt, p_mid)
        if best is None or best_ov < 0.25:
            continue
        p_mkt, p_mid = best
        spread = round(k_mid - p_mid, 4)
        pairs.append({
            "kalshi_ticker": k_mkt.get("ticker"),
            "kalshi_title": k_mkt.get("title") or k_mkt.get("subtitle"),
            "kalshi_yes_mid": k_mid,
            "polymarket_slug": p_mkt.get("slug"),
            "polymarket_question": p_mkt.get("question"),
            "polymarket_yes_mid": p_mid,
            "pair_semantic_overlap": round(best_ov, 3),
            "spread_yes_kalshi_minus_poly": spread,
            "spread_bps": int(spread * 10000),
            "arbitrage_direction": (
                # Only assert a concrete direction on a strong same-condition
                # match. Weak overlaps (different sport/strike/date that merely
                # share generic words) must not read as a tradeable arbitrage.
                "verify-same-condition-first" if best_ov < 0.5
                else "long-kalshi-short-poly" if spread < -0.02
                else "long-poly-short-kalshi" if spread > 0.02
                else "tight"
            ),
        })

    pairs.sort(key=lambda p: abs(p["spread_yes_kalshi_minus_poly"]), reverse=True)

    # Always surface the top priced markets on each side so the caller has the
    # raw data even when no confident cross-venue pair exists.
    kalshi_top = [
        {"ticker": m.get("ticker"),
         "title": (m.get("title") or m.get("subtitle") or "")[:90],
         "yes_mid": _kalshi_mid(m)}
        for m in kalshi_hits
    ]
    poly_top = [
        {"slug": m.get("slug"),
         "question": (m.get("question") or "")[:90],
         "yes_mid": _gamma_yes_mid(m)}
        for m in poly_hits
    ]

    # Classify the result so the caller knows what to do next.
    if pairs:
        status = "ok"
        agent_note = (
            "Pairs matched by shared content words + price. spread > 200bps is a "
            "candidate arbitrage, but VERIFY both markets resolve on the same "
            "condition, strike and date before sizing — Kalshi (e.g. 'upper bound "
            "above 4.25%') and Polymarket (e.g. 'cut by 25 bps') often frame the same "
            "topic as different conditions. pair_semantic_overlap is Jaccard on content "
            "words (0-1); treat < 0.3 as loosely related."
        )
    elif kalshi_hits and poly_hits:
        status = "matched_no_common_condition"
        agent_note = (
            f"Both venues list '{keyword}' markets ({len(kalshi_hits)} Kalshi / "
            f"{len(poly_hits)} Polymarket) but none share enough content to be the same "
            "resolvable condition, so no trustworthy spread. Compare kalshi_top vs "
            "polymarket_top yourself, or send a more specific topic (add the threshold "
            "or date) to align them."
        )
    elif kalshi_hits:
        status = "kalshi_only"
        agent_note = (
            f"Topic '{keyword}' matched {len(kalshi_hits)} Kalshi markets but 0 active "
            "Polymarket markets. No cross-source spread; kalshi_top shown."
        )
    elif poly_hits:
        status = "polymarket_only"
        agent_note = (
            f"Topic '{keyword}' matched {len(poly_hits)} Polymarket markets but 0 on "
            "Kalshi. No cross-source spread; polymarket_top shown."
        )
    else:
        status = "no_matches"

    if status == "no_matches":
        # Sensible fallbacks: real popular markets, NOT the default-sorted MVE
        # sports-parlay junk the old code surfaced.
        poly_sample = [
            {"slug": m.get("slug"), "question": (m.get("question") or "")[:80]}
            for m in sorted(poly_markets, key=lambda m: _vol(m, "volumeNum", "volume"),
                            reverse=True)[:5]
            if m.get("slug") and m.get("question")
        ]
        popular_cats = {"Politics", "Economics", "Crypto", "Financials", "World"}
        cat_series = [s for s in (_SERIES_CACHE or [])
                      if s.get("category") in popular_cats
                      and str(s.get("ticker") or "").startswith("KX")
                      and not str(s.get("ticker") or "").startswith("KXMVE")
                      and 12 <= len((s.get("title") or "").strip()) <= 70
                      and " " in (s.get("title") or "").strip()]
        cat_series.sort(key=lambda s: len(s["title"]))
        kalshi_sample = [{"series": s["ticker"], "title": s["title"].strip()[:80]}
                         for s in cat_series[:5]]
        return {
            "status": "no_matches",
            "topic_keyword": keyword,
            "tokens_used": tokens,
            "kalshi_candidates": 0,
            "polymarket_candidates": 0,
            "pairs": [],
            "did_you_mean": {
                "kalshi_series": kalshi_sample,
                "polymarket_active": poly_sample,
            },
            "agent_note": (
                f"No active markets matched '{keyword}' on either venue. Topics that "
                "resolve on both include: fed rate, presidential election, bitcoin "
                "price, government shutdown, super bowl."
            ),
            "sources": {"kalshi": KALSHI_BASE, "polymarket": "gamma-api.polymarket.com"},
        }

    return {
        "status": status,
        "topic_keyword": keyword,
        "tokens_used": tokens,
        "kalshi_candidates": len(kalshi_hits),
        "polymarket_candidates": len(poly_hits),
        "pairs": pairs,
        "kalshi_top": kalshi_top,
        "polymarket_top": poly_top,
        "agent_note": agent_note,
        "sources": {"kalshi": KALSHI_BASE, "polymarket": "gamma-api.polymarket.com"},
    }


# ===========================================================================
# 3. Sports live-edge — combine play-by-play + market candlesticks
# ===========================================================================

async def _suggest_active_milestones(c: httpx.AsyncClient, limit: int = 5) -> list[dict]:
    """Fetch a handful of currently-active sports milestones for the
    not-found fallback. Best-effort — failures return empty list."""
    try:
        r = await c.get(f"{KALSHI_BASE}/milestones", params={"limit": limit})
        if r.status_code != 200:
            return []
        ms = r.json().get("milestones", []) or []
        return [
            {"milestone_id": m.get("id"),
             "category": m.get("category"),
             "title": (m.get("name") or m.get("title") or "")[:120]}
            for m in ms[:limit] if m.get("id")
        ]
    except Exception:
        return []


_MILESTONE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{2,}$")


async def kalshi_sports_live_edge(milestone_id: str, market_ticker: Optional[str] = None) -> dict:
    """Live-mispricing signal for Kalshi sports markets.

    Pulls game_stats (play-by-play) + recent market candlesticks to detect
    cases where the market hasn't fully reacted to in-game momentum.
    """
    milestone_id = milestone_id.strip()
    if not milestone_id:
        return {"error": "milestone_id_required"}

    # Format validation. Milestone IDs are at least a few chars of alphanumerics
    # + dashes/underscores; single-char placeholder like "X" fails this.
    if not _MILESTONE_ID_RE.match(milestone_id):
        async with httpx.AsyncClient(timeout=8.0, headers=_UA) as c:
            suggestions = await _suggest_active_milestones(c, limit=5)
        return {
            "error": "invalid_milestone_id_format",
            "milestone_tried": milestone_id,
            "expected_format": "Milestone IDs are 3+ chars of letters/digits/dashes/underscores. Discover live ones via GET /milestones on api.elections.kalshi.com.",
            "did_you_mean": suggestions,
            "discover": f"{KALSHI_BASE}/milestones",
        }

    async with httpx.AsyncClient(timeout=10.0, headers=_UA) as c:
        # Probe milestone existence first via the metadata endpoint. That
        # lets us distinguish "milestone doesn't exist" from "milestone
        # exists but has no game_stats yet" — the latter is normal for
        # pre-game or just-started games.
        try:
            r_md = await c.get(f"{KALSHI_BASE}/live_data/milestone/{milestone_id}")
        except Exception as exc:
            return {"error": "kalshi_unreachable", "detail": str(exc)[:200]}

        if r_md.status_code != 200:
            suggestions = await _suggest_active_milestones(c, limit=5)
            return {
                "error": "milestone_not_found",
                "milestone_id": milestone_id,
                "kalshi_status": r_md.status_code,
                "did_you_mean": suggestions,
                "discover": f"{KALSHI_BASE}/milestones",
                "note": "Format was valid but Kalshi returned 404 on the metadata lookup. Suggestions above are currently-active milestones.",
            }
        ms_md = r_md.json() if isinstance(r_md.json(), dict) else {}

        try:
            r_stats = await c.get(f"{KALSHI_BASE}/live_data/milestone/{milestone_id}/game_stats")
            stats = r_stats.json() if r_stats.status_code == 200 else {}
        except Exception as exc:
            stats = {}

        candles = []
        if market_ticker:
            now = int(time.time())
            try:
                r_c = await c.get(
                    f"{KALSHI_BASE}/markets/{market_ticker}/candlesticks",
                    params={"start_ts": now - 3600, "end_ts": now,
                            "period_interval": 1},
                )
                if r_c.status_code == 200:
                    candles = r_c.json().get("candlesticks", []) or []
            except Exception:
                pass

    # Kalshi nests plays under pbp.periods[].events[]. Flatten across all
    # periods (most-recent-first; first item in events is the latest play).
    last_5_events: list = []
    score_now: dict | None = None
    momentum: dict | None = None
    if stats:
        pbp = stats.get("pbp") or {}
        periods = pbp.get("periods") or []
        all_events: list = []
        for prd in periods:
            evts = prd.get("events") or []
            if isinstance(evts, list):
                all_events.extend(evts)
        # Most-recent-first ordering — Kalshi returns latest play at index 0
        last_5_events = all_events[:5]

        # Pull current score from the most-recent event (it carries the
        # post-play score on both sides).
        if all_events:
            ev0 = all_events[0] if isinstance(all_events[0], dict) else {}
            h_now = ev0.get("home_points")
            a_now = ev0.get("away_points")
            if isinstance(h_now, (int, float)) and isinstance(a_now, (int, float)):
                score_now = {"home": int(h_now), "away": int(a_now)}

        # Momentum from score delta across the last 5 events. More robust
        # than keyword-matching ("makes" vs "goal" vs "touchdown") because
        # every sport encodes scoring the same way in points fields.
        last_pts_home = None
        last_pts_away = None
        first_pts_home = None
        first_pts_away = None
        for e in last_5_events:
            if not isinstance(e, dict): continue
            h = e.get("home_points"); a = e.get("away_points")
            if not (isinstance(h, (int, float)) and isinstance(a, (int, float))): continue
            if last_pts_home is None:
                last_pts_home, last_pts_away = h, a
            first_pts_home, first_pts_away = h, a
        if last_pts_home is not None and first_pts_home is not None:
            # events[0] is latest, events[-1] is oldest of the last-5 window —
            # delta = latest - oldest (positive = team scored over window)
            home_delta = max(0, last_pts_home - first_pts_home)
            away_delta = max(0, last_pts_away - first_pts_away)
            total = home_delta + away_delta
            if total > 0:
                home_share = home_delta / total
                direction = ("home" if home_share >= 0.7
                             else "away" if home_share <= 0.3
                             else "balanced")
            else:
                home_share = 0.5
                direction = "no_scoring"
            momentum = {
                "home_delta_pts": home_delta,
                "away_delta_pts": away_delta,
                "home_share": round(home_share, 3),
                "direction": direction,
            }

    # Back-compat: keep momentum_score_last_5_events as the home_share value
    # since v1 callers may already be reading that field name.
    momentum_score = momentum.get("home_share") if momentum else None

    # Market reaction: price delta over last 5 candles
    market_reaction_pct = None
    if candles and len(candles) >= 2:
        try:
            first_close = candles[0].get("close") or candles[0].get("yes_price")
            last_close = candles[-1].get("close") or candles[-1].get("yes_price")
            if first_close and last_close:
                f = float(first_close); l = float(last_close)
                if max(f, l) > 1.5: f, l = f / 100.0, l / 100.0
                market_reaction_pct = round((l - f) * 100, 2)
        except Exception:
            pass

    latency_arb_signal = None
    if momentum_score is not None and market_reaction_pct is not None:
        # If momentum is strongly one-way (home or away dominant) but market
        # hasn't reacted, flag the lag. home_share >= 0.7 = home on a run,
        # home_share <= 0.3 = away on a run.
        if momentum_score >= 0.7 and abs(market_reaction_pct) < 1.0:
            latency_arb_signal = "home-momentum-not-priced"
        elif momentum_score <= 0.3 and abs(market_reaction_pct) < 1.0:
            latency_arb_signal = "away-momentum-not-priced"
        else:
            latency_arb_signal = "market-tracking-stats"

    # Classify the result so the caller doesn't have to look at every null.
    has_plays = len(last_5_events) > 0
    has_candles = len(candles) > 0
    if has_plays and has_candles:
        status = "ok"
        agent_note = (
            "Latency-arb signal flags when game momentum and market price diverge "
            "for >1 minute. Verify with /markets/{ticker}/orderbook before sizing — "
            "low liquidity will eat the edge."
        )
    elif has_plays and not has_candles and market_ticker:
        status = "no_market_candles"
        agent_note = (
            f"Play-by-play data is available for milestone {milestone_id}, but no "
            f"candlestick history was returned for market_ticker '{market_ticker}'. "
            "Check the ticker matches the milestone — they have to be a paired "
            "(game, market) combo. Use GET /markets?event_ticker=<event> to find the "
            "right market ticker."
        )
    elif has_plays and not market_ticker:
        status = "no_market_ticker_supplied"
        agent_note = (
            "Play-by-play available but you didn't pass a `market` ticker, so I "
            "can't compute market_reaction_pct or the latency-arb signal. Pass the "
            "Kalshi market ticker for the game outcome (e.g. KXNFLGAME-…-WINNER-AWAY)."
        )
    else:
        status = "milestone_exists_but_no_plays_yet"
        agent_note = (
            "Milestone exists on Kalshi but no play-by-play events have been "
            "recorded yet. Common for: (a) game hasn't started, (b) milestone is "
            "pre-game only, or (c) Kalshi's live-data feed lags by a few seconds. "
            "Retry in 30-60s."
        )

    return {
        "status": status,
        "milestone_id": milestone_id,
        "milestone_meta": ms_md.get("milestone") if isinstance(ms_md, dict) else None,
        "market_ticker": market_ticker,
        "score_now": score_now,
        "momentum": momentum,
        "momentum_score_last_5_events": momentum_score,
        "market_reaction_pct_last_hour": market_reaction_pct,
        "latency_arbitrage_signal": latency_arb_signal,
        "last_5_events": last_5_events,
        "candles_returned": len(candles),
        "agent_note": agent_note,
        "sources": {
            "play_by_play": f"{KALSHI_BASE}/live_data/milestone/{milestone_id}/game_stats",
            "market_candles": (
                f"{KALSHI_BASE}/markets/{market_ticker}/candlesticks"
                if market_ticker else None
            ),
        },
    }
