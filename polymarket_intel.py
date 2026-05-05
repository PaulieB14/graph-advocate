"""Polymarket trader intelligence — agent-priced derived metrics.

Uses the Pinax-operated Token API at token-api.thegraph.com — Pinax already
returns per-position aggregate PnL (buy_cost, sell_revenue, realized_pnl,
unrealized_pnl, total_pnl), so we don't reconstruct lots from the activity
feed. We layer skill scoring + classification + ghost-fill risk on top.

Auth: TOKEN_API_JWT (canonical) → TOKEN_API_ACCESS_TOKEN (legacy fallback)
      → PINAX_API_KEY (alias). Read at request time.

Exposed via four x402-paid endpoints on graphadvocate.com:
    POST /polymarket/pnl-quick   $0.01  derived skill metrics
    POST /polymarket/pnl         $0.05  scores + per-position records
    POST /polymarket/screen      $0.02  size-the-room: top holders + skill + ghost-fill risk
    POST /polymarket/risk        $0.02  ghost-fill counterparty risk (wallet type probe)

Free-tier JWT cap on /users/positions and /markets/positions is 10 records.
A paid TOKEN_API_JWT lifts that. Code caps client-side to stay safe.
"""

from __future__ import annotations

import logging
import math
import os
import re
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEPOSIT_WALLET_FACTORY = "0x00000000000fb5c9adea0298d729a0cb3823cc07"
ERC1967_IMPL_SLOT = (
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
)

_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# Free-tier-safe caps. With a paid TOKEN_API_JWT these can be raised.
_USER_POSITIONS_LIMIT = int(os.getenv("PINAX_POSITIONS_LIMIT", "10"))
_MARKET_POSITIONS_LIMIT = int(os.getenv("PINAX_MARKET_POSITIONS_LIMIT", "10"))


# ── Config (request-time reads) ──────────────────────────────────────────────


def _pinax_base() -> str:
    return os.getenv(
        "PINAX_BASE_URL",
        "https://token-api.thegraph.com/v1/polymarket",
    )


def _pinax_key() -> str:
    """Mirrors advocate.py:1859 — request-time read of TOKEN_API_JWT.

    Falls back to TOKEN_API_ACCESS_TOKEN, then PINAX_API_KEY. If none are
    set, returns empty string and the request goes unauthenticated (will
    401 against token-api.thegraph.com).
    """
    return (
        os.environ.get("TOKEN_API_JWT", "")
        or os.environ.get("TOKEN_API_ACCESS_TOKEN", "")
        or os.environ.get("PINAX_API_KEY", "")
    )


# ── Pinax client ─────────────────────────────────────────────────────────────


async def _pinax(path: str, **params: Any) -> Any:
    key = _pinax_key()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    url = f"{_pinax_base()}{path}"
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.get(url, headers=headers, params=params)
    if r.status_code >= 400:
        key_state = "set" if key else "MISSING"
        raise RuntimeError(
            f"pinax {path} {r.status_code} (jwt={key_state}): {r.text[:200]}"
        )
    return r.json()


def _data(resp: Any) -> list:
    """Token API returns {data: [...], pagination: {...}, statistics: {...}}"""
    if isinstance(resp, dict) and isinstance(resp.get("data"), list):
        return resp["data"]
    if isinstance(resp, list):
        return resp
    return []


async def fetch_user_positions(user: str, limit: int | None = None) -> list[dict]:
    """All positions for a wallet. Each record is a per-market position with
    aggregate PnL (buy_cost, sell_revenue, realized_pnl, unrealized_pnl,
    total_pnl, pnl_pct, position_value, transactions, ...)."""
    return _data(
        await _pinax(
            "/users/positions",
            user=user,
            limit=limit or _USER_POSITIONS_LIMIT,
        )
    )


async def fetch_market_meta(condition_id: str) -> dict | None:
    """Fetch a single market by condition_id. Returns the record with
    `outcomes: [{label, token_id}, ...]` for ghost-fill / screen lookups."""
    rows = _data(await _pinax("/markets", condition_id=condition_id, limit=1))
    return rows[0] if rows else None


async def fetch_market_holders(token_id: str, limit: int | None = None) -> list[dict]:
    """Top holders of a single outcome token (one side of a market)."""
    return _data(
        await _pinax(
            "/markets/positions",
            token_id=token_id,
            limit=limit or _MARKET_POSITIONS_LIMIT,
        )
    )


# ── Score derivation ─────────────────────────────────────────────────────────
#
# Pinax returns per-position aggregate PnL. We compute wallet-level skill
# metrics by treating each position (one market the trader has been in) as
# one trial. Sharpe-like = mean(per-position return) / stdev(per-position
# return), where return = total_pnl / buy_cost.


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float], mean: float) -> float:
    if len(xs) < 2:
        return 0.0
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_scores(positions: list[dict]) -> dict:
    """Wallet-level skill metrics from a list of per-position records.

    Output fields are documented in the agent-card and the README.
    """
    closed_or_active = [p for p in positions if float(p.get("buy_cost") or 0) > 0]
    sample_size = len(closed_or_active)
    transactions_total = sum(int(p.get("transactions") or 0) for p in closed_or_active)

    realized_pnl = sum(float(p.get("realized_pnl") or 0) for p in closed_or_active)
    unrealized_pnl = sum(float(p.get("unrealized_pnl") or 0) for p in closed_or_active)
    total_pnl = realized_pnl + unrealized_pnl

    win_rate = (
        sum(1 for p in closed_or_active if float(p.get("total_pnl") or 0) > 0)
        / sample_size
        if sample_size
        else 0.0
    )

    # Per-position return = total_pnl / buy_cost. Capped to bound outliers
    # from tiny positions where pnl_pct can swing wildly.
    returns = [
        _clamp(
            float(p.get("total_pnl") or 0) / float(p.get("buy_cost") or 1),
            -5.0,
            5.0,
        )
        for p in closed_or_active
        if float(p.get("buy_cost") or 0) > 0
    ]
    mean_ret = _avg(returns)
    std_ret = _stdev(returns, mean_ret)
    sharpe_like = mean_ret / std_ret if std_ret > 0 else 0.0

    # Confidence: log10 of total trade count. Hits 1.0 around 300 trades.
    confidence = _clamp(
        math.log10(max(1, transactions_total)) / 2.5, 0.0, 1.0
    )

    # Worst single-position loss as a drawdown proxy (snapshot data — true
    # cumulative drawdown would need a time series of past valuations).
    worst_position_pnl = min(
        (float(p.get("total_pnl") or 0) for p in closed_or_active),
        default=0.0,
    )

    skill_score = _clamp(50 + sharpe_like * 25 * confidence, 0.0, 100.0)

    if sample_size < 5:
        classification = "insufficient_data"
    elif skill_score >= 65:
        classification = "sharp"
    elif skill_score <= 40:
        classification = "retail"
    else:
        classification = "neutral"

    return {
        "skill_score": round(skill_score, 1),
        "classification": classification,
        "sharpe_like": round(sharpe_like, 3),
        "win_rate": round(win_rate, 3),
        "sample_size_markets": sample_size,
        "sample_size_trades": transactions_total,
        "confidence": round(confidence, 2),
        "worst_position_pnl_usdc": round(worst_position_pnl, 2),
        "realized_pnl_usdc": round(realized_pnl, 2),
        "unrealized_pnl_usdc": round(unrealized_pnl, 2),
        "total_pnl_usdc": round(total_pnl, 2),
        "open_positions_count": sum(1 for p in positions if p.get("active")),
    }


async def score_wallet(wallet: str) -> dict:
    """Convenience: fetch + score in one call."""
    return compute_scores(await fetch_user_positions(wallet))


# ── Ghost-fill risk: wallet-type probe ───────────────────────────────────────


async def _polygon_rpc(method: str, params: list) -> Any:
    rpc = os.getenv("POLYGON_RPC_URL", "https://polygon.drpc.org")
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.post(
            rpc,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
    if r.status_code >= 400:
        raise RuntimeError(f"polygon rpc {method} {r.status_code}")
    j = r.json()
    if j.get("error"):
        raise RuntimeError(f"polygon rpc {method}: {j['error']}")
    return j.get("result")


async def detect_wallet_type(wallet: str) -> dict:
    """Classify a Polygon address by ghost-fill risk via on-chain bytecode
    probe. EOA → high risk (legacy CLOB path). ERC-1967 proxy → likely
    Polymarket deposit wallet (POLY_1271, sig type 3) → ghost-fill-immune
    by design. Other contract bytecode → legacy proxy/Safe → medium."""
    code = await _polygon_rpc("eth_getCode", [wallet, "latest"])
    if not code or code in ("0x", "0x0"):
        return {
            "type": "eoa",
            "ghost_fill_risk": "high",
            "reason": (
                "Owner EOA — legacy CLOB signing path. Highest historical "
                "ghost-fill incidence."
            ),
        }
    impl = None
    try:
        impl = await _polygon_rpc(
            "eth_getStorageAt", [wallet, ERC1967_IMPL_SLOT, "latest"]
        )
    except Exception as e:
        log.debug(f"impl slot read failed for {wallet}: {e}")
    is_erc1967 = bool(
        impl
        and impl != "0x"
        and impl
        != "0x0000000000000000000000000000000000000000000000000000000000000000"
    )
    if is_erc1967:
        return {
            "type": "smart_account_erc1967",
            "ghost_fill_risk": "low",
            "reason": (
                "ERC-1967 proxy wallet. Likely Polymarket deposit wallet "
                "(POLY_1271/signatureType=3) — ERC-1271-validated orders, "
                "ghost-fill-immune by design."
            ),
            "impl_address": "0x" + impl[-40:],
        }
    return {
        "type": "legacy_smart_account",
        "ghost_fill_risk": "medium",
        "reason": (
            "Smart contract wallet but not an ERC-1967 proxy (likely Gnosis "
            "Safe or custom). Pre-deposit-wallet path; carries legacy "
            "ghost-fill risk depending on signing setup."
        ),
    }


# ── Validation helpers ───────────────────────────────────────────────────────

_HEX_ADDR = re.compile(r"^0x[0-9a-f]{40}$")
_HEX_BYTES32 = re.compile(r"^0x[0-9a-f]{64}$", re.IGNORECASE)


def normalize_wallet(s: Any) -> str | None:
    if not isinstance(s, str):
        return None
    s = s.strip().lower()
    return s if _HEX_ADDR.match(s) else None


def normalize_condition_id(s: Any) -> str | None:
    if not isinstance(s, str):
        return None
    s = s.strip()
    return s if _HEX_BYTES32.match(s) else None


# ── Concurrency helper used by handlers ──────────────────────────────────────


async def _gather(*coros):
    import asyncio
    return await asyncio.gather(*coros)
