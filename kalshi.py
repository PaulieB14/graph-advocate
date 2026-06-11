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
"""
from __future__ import annotations
import asyncio
import json
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


# ===========================================================================
# 1. Event consensus trend
# ===========================================================================

async def kalshi_event_consensus_trend(event_ticker: str) -> dict:
    """Slope + acceleration of Kalshi's published consensus probability.

    Pulls /events/{ticker}/forecast_history (Kalshi exposes pre-computed
    forecast percentiles — no other PM does). Derives the recent trajectory
    so an agent can see WHERE the market is converging without re-doing
    the regression.
    """
    event_ticker = event_ticker.strip().upper()
    async with httpx.AsyncClient(timeout=10.0, headers=_UA) as c:
        try:
            r = await c.get(f"{KALSHI_BASE}/events/{event_ticker}")
            if r.status_code != 200:
                return {"error": "event_not_found", "event_ticker": event_ticker,
                        "kalshi_status": r.status_code}
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

    return {
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
        "agent_note": (
            "Forecast history is Kalshi's published consensus probability over time. "
            "Use slope+acceleration to detect regime changes before they're priced in. "
            "Pair with /kalshi-polymarket-spread for cross-source arbitrage."
        ),
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
    limit = max(1, min(int(limit), 10))

    headers_pinax = dict(_UA)
    if PINAX_JWT:
        headers_pinax["Authorization"] = f"Bearer {PINAX_JWT}"

    async with httpx.AsyncClient(timeout=12.0) as c:
        # Kalshi side — search markets matching keyword
        try:
            r_k = await c.get(f"{KALSHI_BASE}/markets",
                              params={"limit": 100, "status": "open"}, headers=_UA)
            kalshi_markets = (r_k.json().get("markets") or []) if r_k.status_code == 200 else []
        except Exception as exc:
            return {"error": "kalshi_unreachable", "detail": str(exc)[:200]}

        # Polymarket side — via Pinax Token API
        try:
            r_p = await c.get(f"{PINAX_BASE}/polymarket/markets",
                              params={"sort_by": "volume"}, headers=headers_pinax)
            poly_markets = (r_p.json().get("data") or []) if r_p.status_code == 200 else []
        except Exception as exc:
            poly_markets = []

    kw_lower = keyword.lower()

    def _match(text: str) -> bool:
        return kw_lower in (text or "").lower()

    kalshi_hits = [
        m for m in kalshi_markets
        if _match(m.get("subtitle") or "") or _match(m.get("title") or "")
        or _match(m.get("event_ticker") or "")
    ][:limit]
    poly_hits = [
        m for m in poly_markets
        if _match(m.get("market_slug") or "") or _match(m.get("event_slug") or "")
        or _match(m.get("question") or "")
    ][:limit]

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

    def _poly_mid(m: dict) -> Optional[float]:
        for k in ("last_price_yes", "last_price", "yes_price", "price"):
            v = m.get(k)
            if v is not None:
                try:
                    p = float(v)
                    if p > 1.5: p = p / 100.0
                    return round(p, 4)
                except Exception:
                    pass
        return None

    # Naive pair-up: assume best-volume matched pair per source for now;
    # callers can refine by sending a tighter keyword.
    pairs = []
    for k_mkt in kalshi_hits:
        k_mid = _kalshi_mid(k_mkt)
        if k_mid is None: continue
        best_poly = None
        best_score = -1
        for p_mkt in poly_hits:
            p_mid = _poly_mid(p_mkt)
            if p_mid is None: continue
            # Score = inverse abs difference + keyword overlap (simple)
            score = 1.0 - abs(p_mid - k_mid)
            if score > best_score:
                best_score = score
                best_poly = (p_mkt, p_mid)
        if best_poly is None: continue
        p_mkt, p_mid = best_poly
        spread = round(k_mid - p_mid, 4)
        pairs.append({
            "kalshi_ticker": k_mkt.get("ticker"),
            "kalshi_title": k_mkt.get("subtitle") or k_mkt.get("title"),
            "kalshi_yes_mid": k_mid,
            "polymarket_market_slug": p_mkt.get("market_slug"),
            "polymarket_yes_mid": p_mid,
            "spread_yes_kalshi_minus_poly": spread,
            "spread_bps": int(spread * 10000),
            "arbitrage_direction": (
                "long-kalshi-short-poly" if spread < -0.02
                else "long-poly-short-kalshi" if spread > 0.02
                else "tight"
            ),
        })

    pairs.sort(key=lambda p: abs(p["spread_yes_kalshi_minus_poly"]), reverse=True)

    return {
        "topic_keyword": keyword,
        "kalshi_candidates": len(kalshi_hits),
        "polymarket_candidates": len(poly_hits),
        "pairs": pairs,
        "agent_note": (
            "Spread > 200bps in either direction is a candidate arbitrage; verify the "
            "two markets actually resolve on the same condition before sizing. "
            "Cross-source data Pinax can't return in one call."
        ),
        "sources": {"kalshi": KALSHI_BASE, "polymarket_via": "pinax-token-api"},
    }


# ===========================================================================
# 3. Sports live-edge — combine play-by-play + market candlesticks
# ===========================================================================

async def kalshi_sports_live_edge(milestone_id: str, market_ticker: Optional[str] = None) -> dict:
    """Live-mispricing signal for Kalshi sports markets.

    Pulls game_stats (play-by-play) + recent market candlesticks to detect
    cases where the market hasn't fully reacted to in-game momentum.
    """
    milestone_id = milestone_id.strip()
    if not milestone_id:
        return {"error": "milestone_id_required"}

    async with httpx.AsyncClient(timeout=10.0, headers=_UA) as c:
        try:
            r_stats = await c.get(f"{KALSHI_BASE}/live_data/milestone/{milestone_id}/game_stats")
            stats = r_stats.json() if r_stats.status_code == 200 else {}
        except Exception as exc:
            return {"error": "kalshi_unreachable", "detail": str(exc)[:200]}

        r_md = await c.get(f"{KALSHI_BASE}/live_data/milestone/{milestone_id}")
        ms_md = r_md.json() if r_md.status_code == 200 else {}

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

    last_5_events = []
    momentum_score = None
    if stats:
        plays = (stats.get("plays") or stats.get("events") or stats.get("game_stats") or [])
        last_5_events = plays[-5:] if isinstance(plays, list) else []
        # Simple momentum: count beneficial vs harmful in last 5
        good = sum(1 for p in last_5_events if isinstance(p, dict) and
                   any(k in str(p).lower() for k in ("touchdown", "goal", "homer", "score", "made")))
        momentum_score = good / max(len(last_5_events), 1)

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
        # If momentum is strongly one-way but market hasn't reacted, flag the lag
        if momentum_score >= 0.6 and abs(market_reaction_pct) < 1.0:
            latency_arb_signal = "upside-lag-likely"
        elif momentum_score <= 0.2 and abs(market_reaction_pct) < 1.0:
            latency_arb_signal = "downside-lag-likely"
        else:
            latency_arb_signal = "market-tracking-stats"

    return {
        "milestone_id": milestone_id,
        "milestone_meta": ms_md.get("milestone") if isinstance(ms_md, dict) else None,
        "market_ticker": market_ticker,
        "momentum_score_last_5_events": momentum_score,
        "market_reaction_pct_last_hour": market_reaction_pct,
        "latency_arbitrage_signal": latency_arb_signal,
        "last_5_events": last_5_events,
        "candles_returned": len(candles),
        "agent_note": (
            "Latency-arb signal flags when game momentum and market price diverge "
            "for >1 minute. Verify with /markets/{ticker}/orderbook before sizing — "
            "low liquidity will eat the edge."
        ),
        "sources": {
            "play_by_play": f"{KALSHI_BASE}/live_data/milestone/{milestone_id}/game_stats",
            "market_candles": (
                f"{KALSHI_BASE}/markets/{market_ticker}/candlesticks"
                if market_ticker else None
            ),
        },
    }
