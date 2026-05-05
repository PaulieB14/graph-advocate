"""Polymarket trader intelligence — agent-priced derived metrics.

Pure-JSON computations on top of the free Pinax Polymarket REST API
(`/v1/polymarket/*`). Designed for autonomous agents in their decision loops
(trading bots sizing the room, copy-trade vetting, MM adverse-selection
pricing, ERC-8004 reputation graphs) — not humans.

Exposed via four new x402-paid endpoints on graphadvocate.com:

    POST /polymarket/pnl-quick   $0.01  derived skill metrics, no lot reconstruction
    POST /polymarket/pnl         $0.05  scores + per-lot FIFO/LIFO/HIFO + open positions
    POST /polymarket/screen      $0.02  size-the-room: top holders + skill + ghost-fill risk
    POST /polymarket/risk        $0.02  ghost-fill counterparty risk (wallet type + outflows)

The ghost-fill risk endpoint classifies wallets via Polygon eth_getCode +
ERC-1967 implementation slot probe. Polymarket's new POLY_1271 / sig type 3
deposit wallets (factory 0x0000…3Cc07) are ghost-fill-immune by design;
legacy EOAs / Safes carry the historical risk that LPs have been getting
burned by.
"""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────

PINAX_BASE = os.getenv(
    "PINAX_BASE_URL",
    # Pinax-operated Token API hosted at token-api.thegraph.com.
    # Confirmed in advocate.py:485-488 and the Polymarket section of the
    # routing system prompt — the endpoints live under /v1/polymarket/*.
    "https://token-api.thegraph.com/v1/polymarket",
)
# Pinax / Token API JWT — mirrors advocate.py:1859 convention exactly.
# TOKEN_API_JWT is the canonical name; TOKEN_API_ACCESS_TOKEN is the legacy
# fallback. PINAX_API_KEY supported as a third-tier alias for clarity.
PINAX_KEY = (
    os.getenv("TOKEN_API_JWT", "")
    or os.getenv("TOKEN_API_ACCESS_TOKEN", "")
    or os.getenv("PINAX_API_KEY", "")
)
POLYGON_RPC = os.getenv("POLYGON_RPC_URL", "https://polygon.drpc.org")

# Polymarket deposit-wallet factory on Polygon mainnet (chainId 137).
# Source: https://docs.polymarket.com — Deposit Wallet Migration.
DEPOSIT_WALLET_FACTORY = "0x00000000000fb5c9adea0298d729a0cb3823cc07"

# ERC-1967 implementation slot per EIP-1967.
ERC1967_IMPL_SLOT = (
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
)

_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


# ── Pinax client ─────────────────────────────────────────────────────────────


async def _pinax(path: str, **params: Any) -> Any:
    """GET against Pinax Polymarket API. Returns parsed JSON."""
    headers = {"Authorization": f"Bearer {PINAX_KEY}"} if PINAX_KEY else {}
    url = f"{PINAX_BASE}{path}"
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.get(url, headers=headers, params=params)
    if r.status_code >= 400:
        raise RuntimeError(f"pinax {path} {r.status_code}: {r.text[:200]}")
    return r.json()


def _as_array(x: Any) -> list:
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        for k in ("data", "results", "items"):
            if isinstance(x.get(k), list):
                return x[k]
    return []


async def fetch_user_positions(user: str) -> list[dict]:
    return _as_array(await _pinax("/users/positions", user=user, limit=1000))


async def fetch_user_activity(user: str) -> list[dict]:
    return _as_array(
        await _pinax("/markets/activity", user=user, event_type="trade", limit=10000)
    )


async def fetch_user_recent_activity(user: str) -> list[dict]:
    return _as_array(await _pinax("/markets/activity", user=user, limit=100))


async def fetch_market_positions(condition_id: str) -> list[dict]:
    return _as_array(
        await _pinax("/markets/positions", condition_id=condition_id, limit=100)
    )


# ── Lot accounting ───────────────────────────────────────────────────────────
#
# Replays trades per token_id to produce closed lots (realized PnL) and
# remaining open lots. Method picks how sells match buys:
#   fifo — oldest first  (default; conservative)
#   lifo — newest first  (defers gains)
#   hifo — highest-cost first  (minimizes realized PnL)


def _parse_ts(s: str | None) -> float:
    if not s:
        return 0.0
    try:
        # Pinax uses "YYYY-MM-DD HH:MM:SS" (UTC, no tz suffix)
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(
            tzinfo=timezone.utc if "T" not in s and "+" not in s else None
        ).timestamp()
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            ).timestamp()
        except Exception:
            return 0.0


def build_lots(activity: list[dict], method: str = "fifo") -> dict:
    by_token: dict[str, list[dict]] = {}
    for ev in activity:
        if ev.get("event_type") != "trade":
            continue
        market = ev.get("market") or {}
        token_id = market.get("token_id")
        if not token_id:
            continue
        by_token.setdefault(token_id, []).append(ev)

    closed: list[dict] = []
    open_lots_out: list[dict] = []

    for token_id, trades in by_token.items():
        trades.sort(key=lambda t: _parse_ts(t.get("timestamp")))
        lots: list[dict] = []  # open buy lots

        for t in trades:
            # Pinax exposes side as "buy" | "sell"; if absent, infer from value sign
            side = t.get("side") or (
                "buy" if float(t.get("value") or 0) >= 0 else "sell"
            )
            try:
                qty = abs(float(t.get("amount") or 0)) / 1e6
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue
            gross_value = abs(float(t.get("value") or 0))
            fee = abs(float(t.get("fee_value") or 0))
            price = gross_value / qty if qty else 0.0
            market = t.get("market") or {}

            if side == "buy":
                lots.append(
                    {
                        "qty": qty,
                        "price": price,
                        "fee_total": fee,
                        "opened_at": t.get("timestamp"),
                        "opened_block": t.get("block_num"),
                        "opened_tx": t.get("tx_hash"),
                        "market": market,
                    }
                )
                continue

            # sell — match against open lots per chosen accounting method
            if method == "lifo":
                order = sorted(
                    lots, key=lambda l: _parse_ts(l["opened_at"]), reverse=True
                )
            elif method == "hifo":
                order = sorted(lots, key=lambda l: l["price"], reverse=True)
            else:  # fifo
                order = list(lots)

            remaining = qty
            remaining_fee = fee
            for lot in order:
                if remaining <= 0:
                    break
                if lot["qty"] <= 0:
                    continue
                used = min(remaining, lot["qty"])
                portion = used / qty
                sell_fee = remaining_fee * portion
                buy_fee_share = lot["fee_total"] * (used / (lot["qty"] + 1e-12))
                pnl = used * (price - lot["price"]) - sell_fee - buy_fee_share
                closed.append(
                    {
                        "token_id": token_id,
                        "market_slug": lot["market"].get("market_slug"),
                        "outcome": lot["market"].get("outcome_label"),
                        "qty": round(used, 6),
                        "buy_price": round(lot["price"], 4),
                        "sell_price": round(price, 4),
                        "pnl_usdc": round(pnl, 2),
                        "opened_at": lot["opened_at"],
                        "closed_at": t.get("timestamp"),
                        "opened_tx": lot["opened_tx"],
                        "closed_tx": t.get("tx_hash"),
                        "method": method,
                    }
                )
                lot["qty"] -= used
                lot["fee_total"] -= buy_fee_share
                remaining -= used
                remaining_fee -= sell_fee

            lots = [l for l in lots if l["qty"] > 1e-9]

        for lot in lots:
            open_lots_out.append(
                {
                    "token_id": token_id,
                    "market_slug": lot["market"].get("market_slug"),
                    "outcome": lot["market"].get("outcome_label"),
                    "qty": round(lot["qty"], 6),
                    "avg_buy_price": round(lot["price"], 4),
                    "opened_at": lot["opened_at"],
                }
            )

    return {"closed": closed, "open": open_lots_out}


# ── Score derivation ─────────────────────────────────────────────────────────


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float], mean: float) -> float:
    if len(xs) < 2:
        return 0.0
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_scores(
    closed: list[dict],
    open_positions_from_pinax: list[dict] | None = None,
) -> dict:
    """Derived metrics so the calling agent doesn't have to compute them.

    All fields documented in the agent-card and the README.
    """
    open_positions_from_pinax = open_positions_from_pinax or []
    sample_size = len(closed)
    realized_pnl = sum(c["pnl_usdc"] for c in closed)
    win_rate = (
        sum(1 for c in closed if c["pnl_usdc"] > 0) / sample_size
        if sample_size
        else 0.0
    )

    returns = [
        _clamp((c["sell_price"] - c["buy_price"]) / c["buy_price"], -5.0, 5.0)
        for c in closed
        if c["buy_price"] > 0
    ]
    mean_ret = _avg(returns)
    std_ret = _stdev(returns, mean_ret)
    sharpe_like = mean_ret / std_ret if std_ret > 0 else 0.0

    confidence = _clamp(
        math.log10(max(1, sample_size)) / 2.5, 0.0, 1.0
    )  # 1.0 around 300 lots

    chrono = sorted(closed, key=lambda c: _parse_ts(c.get("closed_at")))
    cum = peak = max_dd = 0.0
    for c in chrono:
        cum += c["pnl_usdc"]
        if cum > peak:
            peak = cum
        if peak - cum > max_dd:
            max_dd = peak - cum

    unrealized_pnl = sum(
        float(p.get("unrealized_pnl") or 0) for p in open_positions_from_pinax
    )

    skill_score = _clamp(50 + sharpe_like * 25 * confidence, 0.0, 100.0)

    if sample_size < 20:
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
        "sample_size": sample_size,
        "confidence": round(confidence, 2),
        "max_drawdown_usdc": round(max_dd, 2),
        "realized_pnl_usdc": round(realized_pnl, 2),
        "unrealized_pnl_usdc": round(unrealized_pnl, 2),
        "total_pnl_usdc": round(realized_pnl + unrealized_pnl, 2),
        "open_positions_count": len(open_positions_from_pinax),
    }


# ── Ghost-fill risk: wallet type + recent outflow ────────────────────────────


async def _polygon_rpc(method: str, params: list) -> Any:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.post(
            POLYGON_RPC,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
    if r.status_code >= 400:
        raise RuntimeError(f"polygon rpc {method} {r.status_code}")
    j = r.json()
    if j.get("error"):
        raise RuntimeError(f"polygon rpc {method}: {j['error']}")
    return j.get("result")


async def detect_wallet_type(wallet: str) -> dict:
    """Classify a Polygon address by ghost-fill risk via on-chain bytecode probe.

    EOA → no bytecode → high risk (legacy CLOB path)
    ERC-1967 proxy → likely Polymarket deposit wallet (POLY_1271/sig type 3) → low risk
    Other contract bytecode → legacy proxy/Safe → medium risk
    """
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

    is_erc1967_proxy = bool(
        impl
        and impl != "0x"
        and impl
        != "0x0000000000000000000000000000000000000000000000000000000000000000"
    )

    if is_erc1967_proxy:
        # TODO: tighten by tracing CREATE2 deployer == DEPOSIT_WALLET_FACTORY.
        return {
            "type": "smart_account_erc1967",
            "ghost_fill_risk": "low",
            "reason": (
                "ERC-1967 proxy wallet. Likely Polymarket deposit wallet "
                "(POLY_1271/signatureType=3) — ERC-1271-validated orders, "
                "ghost-fill-immune by design. Verify by checking the "
                "implementation address against deposit wallet factory "
                "deployments."
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


_OUTFLOW_EVENT_TYPES = {
    "withdrawal",
    "withdraw",
    "transfer_out",
    "redemption",
    "merge",
}


async def recent_outflow_flag(wallet: str) -> dict:
    """Flag if the wallet has drained collateral in the last 24h.

    Combined with wallet_type, this is the classic ghost-fill setup:
    fill arrives, balance is gone.
    """
    try:
        recent = await fetch_user_recent_activity(wallet)
    except Exception as e:
        return {"flag": None, "error": str(e)}

    cutoff = datetime.now(timezone.utc).timestamp() - 24 * 3600
    outflows = [
        ev
        for ev in recent
        if _parse_ts(ev.get("timestamp")) >= cutoff
        and str(ev.get("event_type") or "").lower() in _OUTFLOW_EVENT_TYPES
    ]
    return {"flag": len(outflows) > 0, "events_24h": len(outflows)}


# ── Composed scoring (used by /pnl/quick and /screen) ────────────────────────


async def score_wallet(wallet: str) -> dict:
    activity, positions = await _gather(
        fetch_user_activity(wallet),
        fetch_user_positions(wallet),
    )
    lots = build_lots(activity, "fifo")
    return compute_scores(lots["closed"], positions)


async def _gather(*coros):
    """Run coros concurrently, returning their results in order."""
    import asyncio

    return await asyncio.gather(*coros)


# ── Validation helpers ───────────────────────────────────────────────────────

import re

_HEX_ADDR = re.compile(r"^0x[0-9a-f]{40}$")
_HEX_BYTES32 = re.compile(r"^0x[0-9a-f]{64}$", re.IGNORECASE)


def normalize_wallet(s: str | None) -> str | None:
    if not isinstance(s, str):
        return None
    s = s.strip().lower()
    return s if _HEX_ADDR.match(s) else None


def normalize_condition_id(s: str | None) -> str | None:
    if not isinstance(s, str):
        return None
    s = s.strip()
    return s if _HEX_BYTES32.match(s) else None
