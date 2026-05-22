"""Hyperliquid trader intelligence — agent-priced derived metrics.

Wraps Pinax Token API `/v1/hyperliquid/*` (production as of v3.17.0,
2026-05-07) with skill scoring, vault evaluation, and counterparty risk
metrics designed for autonomous trading agents on HyperCore.

Auth: TOKEN_API_JWT (canonical) → TOKEN_API_ACCESS_TOKEN (legacy fallback)
      → PINAX_API_KEY (alias) → hardcoded free-tier fallback.

Five paid endpoints exposed via graphadvocate.com:
    POST /hyperliquid/score/:user   $0.02  derived skill, sharpe-like, liquidation rate, funding burn
    POST /hyperliquid/pnl/:user     $0.05  full report: scores + open positions + recent activity
    POST /hyperliquid/screen/:coin  $0.05  top traders of a coin with per-trader skill scores
    POST /hyperliquid/vault/:vault  $0.10  vault evaluator: leader skill + depositor concentration + redemption pressure
    POST /hyperliquid/risk/:user    $0.02  counterparty risk: liquidation rate + funding burn + recent flow

Unique vs polymarket-token-api: liquidation tracking + vault evaluator
(no Polymarket equivalent — binary outcomes don't have these mechanics).
"""

from __future__ import annotations

import logging
import math
import os
import re
from typing import Any

import httpx

log = logging.getLogger(__name__)

_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# Free-tier-safe limits. Hyperliquid endpoints generally allow more rows than
# Polymarket's per-page caps, but stay conservative.
# Pinax free-tier hard caps: most /v1/hyperliquid/* endpoints reject
# limit > 10 with HTTP 403 "Parameter 'limit' exceeds maximum of 10 items."
# Verified 2026-05-11 — /hyperliquid/pnl and /hyperliquid/risk were 502ing on
# self-pay validation because _ACTIVITY_LIMIT=20 and _POSITIONS_LIMIT=50
# exceeded the free-tier cap. Both defaulted down to 10. Override via env if
# you upgrade to Pinax Pro.
_USERS_LIMIT = int(os.getenv("PINAX_HL_USERS_LIMIT", "10"))
_POSITIONS_LIMIT = int(os.getenv("PINAX_HL_POSITIONS_LIMIT", "10"))
_ACTIVITY_LIMIT = int(os.getenv("PINAX_HL_ACTIVITY_LIMIT", "10"))
_DEPOSITORS_LIMIT = int(os.getenv("PINAX_HL_DEPOSITORS_LIMIT", "10"))


# ── Config (request-time reads, mirror polymarket_intel) ────────────────────


def _pinax_base() -> str:
    return os.getenv(
        "PINAX_HL_BASE_URL",
        "https://token-api.thegraph.com/v1/hyperliquid",
    )


# Free-tier fallback JWT — same as polymarket_intel + advocate.py:1862.
# Public, already in committed source. Ensures requests work without env config.
_FALLBACK_JWT = (
    "eyJhbGciOiJLTVNFUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJleHAiOjE4MDUyMTk1MzQsImp0aSI6IjE4ZTU3Mjk2LTcyYTktNDVlYi1iNDlhLWY0MWFlMzIzYTUzOCIsImlhdCI6MTc2OTIxOTUzNCwiaXNzIjoiZGZ1c2UuaW8iLCJzdWIiOiIwYm9qaTQ5NTUyMjg5MjIwYzVkYjciLCJ2IjoyLCJha2kiOiIzNjJiNDU5NGI1NmFkYWE0YzIxZWNhYzE3M2M4MTEyZDM3OGMyMWY1MjM1MDUzZWYwYmJkYjVlZjJkZWY2NDViIiwidWlkIjoiMGJvamk0OTU1MjI4OTIyMGM1ZGI3Iiwic3Vic3RyZWFtc19wbGFuX3RpZXIiOiJGUkVFIiwiY2ZnIjp7IlNVQlNUUkVBTVNfTUFYX1JFUVVFU1RTIjoiMiIsIlNVQlNUUkVBTVNfUEFSQUxMRUxfSk9CUyI6IjUiLCJTVUJTVFJFQU1TX1BBUkFMTEVMX1dPUktFUlMiOiI1In0sInRva2VuX2FwaV9wbGFuX3RpZXIiOiJGUkVFIiwidG9rZW5fYXBpX2ZlYXR1cmVfY29uZmlncyI6eyJUT0tFTl9BUElfQkFUQ0hfU0laRSI6IjEiLCJUT0tFTl9BUElfSVRFTVNfUkVUVVJORUQiOiIxMCIsIlRPS0VOX0FQSV9NQVhJTVVNX0FMTE9XRURfRU5EUE9JTlRfR1JPVVAiOiJuZnQiLCJUT0tFTl9BUElfUExBTl9DUkVESVRTX0NFTlRTIjoiMjUwMCIsIlRPS0VOX0FQSV9SQVRFX0xJTUlUX1BFUl9NSU5VVEUiOiIyMDAiLCJUT0tFTl9BUElfUkVBTF9USU1FX0RBVEEiOiJ0cnVlIn19."
    "pXh91NO328L1rs9AinFazARJSqEq6dSBeTjxrrDM-pO2BN71VUHBXwJVgH8kNxxw33BgI8SkhZL6cCDjgxwkVw"
)


def _pinax_key() -> str:
    return (
        os.environ.get("TOKEN_API_JWT", "")
        or os.environ.get("TOKEN_API_ACCESS_TOKEN", "")
        or os.environ.get("JWT", "")
        or os.environ.get("PINAX_API_KEY", "")
        or _FALLBACK_JWT
    )


# ── Pinax client ─────────────────────────────────────────────────────────────


async def _pinax(path: str, **params: Any) -> Any:
    key = _pinax_key()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    url = f"{_pinax_base()}{path}"
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.get(url, headers=headers, params=params)
    if r.status_code >= 400:
        if os.environ.get("TOKEN_API_JWT"):
            ks = "env:TOKEN_API_JWT"
        elif os.environ.get("TOKEN_API_ACCESS_TOKEN"):
            ks = "env:TOKEN_API_ACCESS_TOKEN"
        elif os.environ.get("JWT"):
            ks = "env:JWT"
        elif os.environ.get("PINAX_API_KEY"):
            ks = "env:PINAX_API_KEY"
        else:
            ks = "free-tier-fallback"
        raise RuntimeError(
            f"pinax/hyperliquid {path} {r.status_code} (jwt={ks}): {r.text[:200]}"
        )
    return r.json()


def _data(resp: Any) -> list:
    if isinstance(resp, dict) and isinstance(resp.get("data"), list):
        return resp["data"]
    if isinstance(resp, list):
        return resp
    return []


async def fetch_user(user: str, coin: str | None = None, dex: str | None = None) -> dict | None:
    """Aggregate stats for a trader. Filterable by coin/dex (None = all)."""
    params: dict[str, Any] = {"user": user, "limit": 1}
    if coin: params["coin"] = coin
    if dex: params["dex"] = dex
    rows = _data(await _pinax("/users", **params))
    return rows[0] if rows else None


async def fetch_user_positions(user: str) -> list[dict]:
    return _data(
        await _pinax("/users/positions", user=user, limit=_POSITIONS_LIMIT)
    )


async def fetch_user_activity(user: str, limit: int | None = None) -> list[dict]:
    return _data(
        await _pinax("/users/activity", user=user, limit=limit or _ACTIVITY_LIMIT)
    )


async def fetch_top_traders_by_coin(coin: str, n: int = 10) -> list[dict]:
    """Top traders on a specific coin/market, sorted by total_volume desc."""
    return _data(
        await _pinax("/users", coin=coin, limit=n, sort="total_volume", order="desc")
    )


async def fetch_vault(vault: str) -> dict | None:
    rows = _data(await _pinax("/vaults", vault=vault, limit=1))
    return rows[0] if rows else None


async def fetch_vault_depositors(vault: str, limit: int | None = None) -> list[dict]:
    return _data(
        await _pinax(
            "/vaults/depositors",
            vault=vault,
            limit=limit or _DEPOSITORS_LIMIT,
            sort="deposits",
            order="desc",
        )
    )


# ── Score derivation ─────────────────────────────────────────────────────────
#
# Hyperliquid users have richer signals than Polymarket because perps trading
# tracks liquidations, funding paid/received, and per-coin breakdowns. Skill
# score weights: profitability (40%), risk control (40%), efficiency (20%).


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _safe_div(a: float, b: float) -> float:
    return a / b if b not in (0, 0.0) else 0.0


def compute_user_score(user_stats: dict) -> dict:
    """Wallet-level skill metrics from a single Hyperliquid /users record.

    The user_stats arg is one row from /v1/hyperliquid/users with fields:
    transactions, buys, sells, volume_bought, volume_sold, total_volume,
    total_fees, realized_pnl, total_funding, liquidation_fills, coins_traded,
    first_trade, last_trade.
    """
    if not user_stats:
        return {
            "skill_score": 0.0,
            "classification": "no_data",
            "reason": "no Hyperliquid trading history found for this address",
        }

    txs = float(user_stats.get("transactions") or 0)
    volume = float(user_stats.get("total_volume") or 0)
    fees = float(user_stats.get("total_fees") or 0)
    pnl = float(user_stats.get("realized_pnl") or 0)
    funding = float(user_stats.get("total_funding") or 0)
    liqs = float(user_stats.get("liquidation_fills") or 0)
    coins = int(user_stats.get("coins_traded") or 0)

    # Profitability: PnL / total_volume (basis-points-of-edge proxy).
    # Cap at +/- 100 bps because anything beyond is noise from tiny denominators.
    pnl_bps = _clamp(_safe_div(pnl, volume) * 10_000, -100, 100)

    # Risk control: liquidation rate (fills / total trades). Lower is better.
    # 0 liquidations = perfect; 1% liquidation rate = catastrophic.
    liq_rate = _safe_div(liqs, txs)
    risk_penalty = _clamp(liq_rate * 10_000, 0, 100)  # 0-100 bps as penalty

    # Funding burn: negative if trader pays funding consistently. Normalize to volume.
    funding_per_volume_bps = _clamp(_safe_div(funding, volume) * 10_000, -50, 50)

    # Efficiency: profit factor proxy (PnL / fees paid).
    profit_factor = _safe_div(pnl, fees) if fees > 0 else 0
    pf_normalized = _clamp(profit_factor / 10, -5, 5)  # 10x fees = max edge

    # Sample-size confidence (logarithmic, hits 1.0 at ~1M txs).
    confidence = _clamp(math.log10(max(1, txs)) / 6.0, 0.0, 1.0)

    # Composite skill_score (0-100). Weight: profitability 40, risk 40, efficiency 20.
    raw = (
        0.40 * (50 + pnl_bps * 0.5)          # 0-100 from -100..100 bps
        + 0.40 * (50 - risk_penalty * 0.5)   # full credit for zero liquidations
        + 0.20 * (50 + pf_normalized * 10)    # profit factor
    )
    # Confidence-weight: shrink score toward 50 when sample size is small.
    skill_score = _clamp(50 + (raw - 50) * confidence, 0.0, 100.0)

    if txs < 100:
        classification = "insufficient_data"
    elif skill_score >= 70:
        classification = "sharp"
    elif skill_score <= 35:
        classification = "retail"
    else:
        classification = "neutral"

    return {
        "skill_score": round(skill_score, 1),
        "classification": classification,
        "sharpe_like": round(_safe_div(pnl, max(1, math.sqrt(volume))), 4),
        "pnl_bps_of_volume": round(pnl_bps, 2),
        "liquidation_count": int(liqs),
        "liquidation_rate_bps": round(liq_rate * 10_000, 2),
        "funding_paid_per_volume_bps": round(-funding_per_volume_bps, 2),  # negative funding = paid
        "profit_factor": round(profit_factor, 3),
        "sample_size_trades": int(txs),
        "coins_traded": coins,
        "confidence": round(confidence, 2),
        "realized_pnl_usdc": round(pnl, 2),
        "total_volume_usdc": round(volume, 2),
        "total_fees_usdc": round(fees, 2),
        "first_trade": user_stats.get("first_trade"),
        "last_trade": user_stats.get("last_trade"),
    }


# ── Vault evaluator ─────────────────────────────────────────────────────────
#
# Vaults on Hyperliquid are native copy-trading vehicles. A vault has a leader
# (whose strategy depositors mirror) and a pool of depositors. Quality signals:
#   1. Leader's own trading skill (their /users score)
#   2. Depositor concentration (top-1 share = whale-dependent vs. distributed)
#   3. Redemption pressure (withdrawals / deposits ratio over lifetime)
#   4. Distribution rate (commissions paid out / lifetime deposits — too high
#      means leader is taking too much; too low means strategy isn't earning)


def compute_vault_score(
    vault_data: dict,
    depositors: list[dict],
    leader_score: dict | None,
) -> dict:
    """Composite quality score for a Hyperliquid vault."""
    if not vault_data:
        return {"vault_quality_score": 0, "classification": "vault_not_found"}

    deposits = float(vault_data.get("lifetime_deposits") or 0)
    withdrawals = float(vault_data.get("lifetime_withdrawals") or 0)
    distributions = float(vault_data.get("lifetime_distributions") or 0)
    leader_commissions = float(vault_data.get("lifetime_leader_commissions") or 0)
    n_depositors = int(vault_data.get("depositor_count") or 0)

    # Redemption pressure: withdrawal/deposit ratio. <0.3 healthy, >0.8 concerning.
    redemption_pressure = _clamp(_safe_div(withdrawals, deposits), 0.0, 1.0)

    # Concentration: top depositor's share of total deposits.
    # depositors list is sorted desc by deposits.
    top_share = 0.0
    if depositors and deposits > 0:
        top_share = _clamp(
            _safe_div(float(depositors[0].get("deposits") or 0), deposits),
            0.0,
            1.0,
        )

    # Distribution health: commissions/deposits ratio. Sane: 1-5%. Greedy: >10%.
    commission_rate = _clamp(_safe_div(leader_commissions, deposits), 0.0, 1.0)

    # Leader's own skill (from /users score, if available).
    leader_skill = (leader_score or {}).get("skill_score", 50.0)

    # Composite (0-100): leader skill 40%, low redemption 25%,
    # diversified depositors 20%, healthy commission 15%.
    score = (
        0.40 * float(leader_skill)
        + 0.25 * (100 - redemption_pressure * 100)
        + 0.20 * (100 - top_share * 100)
        + 0.15 * (100 - abs(commission_rate * 100 - 3) * 5)  # peak at ~3% commission
    )
    score = _clamp(score, 0.0, 100.0)

    if n_depositors < 5:
        classification = "insufficient_data"
    elif score >= 70:
        classification = "high_quality"
    elif score <= 35:
        classification = "low_quality"
    else:
        classification = "neutral"

    return {
        "vault_quality_score": round(score, 1),
        "classification": classification,
        "leader_skill_score": float(leader_skill),
        "redemption_pressure": round(redemption_pressure, 3),
        "top_depositor_share": round(top_share, 3),
        "depositor_count": n_depositors,
        "commission_rate_of_deposits": round(commission_rate, 4),
        "lifetime_deposits_usdc": round(deposits, 2),
        "lifetime_withdrawals_usdc": round(withdrawals, 2),
        "lifetime_distributions_usdc": round(distributions, 2),
        "lifetime_leader_commissions_usdc": round(leader_commissions, 2),
        "vault_address": vault_data.get("vault"),
        "leader_address": vault_data.get("leader"),
    }


# ── Counterparty risk (liquidation + leverage pattern) ──────────────────────


_OUTFLOW_EVENT_TYPES = {"withdrawal", "withdraw", "transfer_out"}


def compute_risk(user_stats: dict, recent_activity: list[dict]) -> dict:
    """Pre-trade counterparty risk for a Hyperliquid user.

    Flags:
      - liquidation_count + rate
      - funding burn pattern (consistent paying = leveraged)
      - recent withdrawal flag (drained collateral within last 24h)
    """
    base = compute_user_score(user_stats)

    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_outflows = []
    for ev in recent_activity:
        ts = ev.get("timestamp") or ""
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if t < cutoff:
            continue
        et = str(ev.get("event_type") or "").lower()
        if et in _OUTFLOW_EVENT_TYPES:
            recent_outflows.append(ev)

    liq_count = int(base.get("liquidation_count", 0))
    if liq_count == 0 and base.get("classification") == "sharp":
        risk_level = "low"
    elif liq_count > 10 or base.get("classification") == "retail":
        risk_level = "high"
    else:
        risk_level = "medium"

    return {
        "user": user_stats.get("user") if user_stats else None,
        "risk_level": risk_level,
        "liquidation_count": liq_count,
        "liquidation_rate_bps": base.get("liquidation_rate_bps"),
        "funding_paid_per_volume_bps": base.get("funding_paid_per_volume_bps"),
        "skill_score": base.get("skill_score"),
        "classification": base.get("classification"),
        "recent_24h_outflows": len(recent_outflows),
        "recent_24h_outflow_flag": len(recent_outflows) > 0,
        "sample_size_trades": base.get("sample_size_trades"),
    }


# ── Validation helpers ───────────────────────────────────────────────────────

_HEX_ADDR = re.compile(r"^0x[0-9a-f]{40}$")
# Hyperliquid coin formats: BTC, ETH, @107 (spot), xyz:SILVER (builder)
_COIN_PATTERN = re.compile(r"^(@\d+|[A-Za-z][A-Za-z0-9]*(?::[A-Za-z][A-Za-z0-9]*)?)$")


def normalize_user(s: Any) -> str | None:
    if not isinstance(s, str):
        return None
    s = s.strip().lower()
    return s if _HEX_ADDR.match(s) else None


def normalize_vault(s: Any) -> str | None:
    return normalize_user(s)  # vault addresses are EVM-format


def normalize_coin(s: Any) -> str | None:
    if not isinstance(s, str):
        return None
    s = s.strip()
    return s if _COIN_PATTERN.match(s) else None


# ── Concurrency helper ───────────────────────────────────────────────────────


async def _gather(*coros):
    import asyncio
    return await asyncio.gather(*coros)
