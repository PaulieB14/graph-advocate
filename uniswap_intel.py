"""Uniswap pre-trade intelligence — the DeFi-spot leg of Graph Advocate's
trader-intelligence line.

Settles the four questions an agent must answer BEFORE it touches a token:

  1. Is the liquidity REAL, or spam-inflated?
  2. Which venue (chain x version x fee tier) is actually deepest?
  3. Does the pool let people SELL, or is it a honeypot?
  4. Is volume rising or dying?

Everything ranks by volumeUSD, NEVER by TVL. Uniswap subgraph TVL is inflated by
illiquid spam-token pools — a single fake-priced pool can report trillions — so
TVL alone is not evidence of depth. Volume is the number that has to be paid for.

Built on The Graph's Uniswap subgraphs, addressed by SUBGRAPH ID so they always
follow the publisher's latest published version.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

GATEWAY = "https://gateway.thegraph.com/api/subgraphs/id"

# Verified subgraph IDs (mirrors the map in advocate.py::_template_query).
# Subgraph-id form => auto-follows the publisher's latest published version.
UNISWAP_SUBGRAPHS: dict[tuple[str, str], str] = {
    ("v2", "ethereum"): "GmSczqdCDZ3hJeYY9JphwsADn5rePUzUKm8EZcVuhRAm",
    ("v2", "base"):     "DbcUmZwXBYbNZvLuDEvcmFa4uAWwwjrdX8dVFg1AUVKa",
    ("v3", "ethereum"): "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV",
    ("v3", "arbitrum"): "FbCGRftH4a3yZugY7TnbYgPJVEv2LvMT6oF1fxPe9aJM",
    ("v3", "base"):     "HMuAwufqZ1YCRmzL2SfHTVkzZovC9VL2UAKhjvRqKiR1",
    ("v3", "polygon"):  "EsLGwxyeMMeJuhqWvuLmJEiDKXJ4Z6YsoJreUnyeozco",
    ("v3", "optimism"): "Cghf4LfVqPiFw6fp6Y5X5Ubc8UpmUhSfJL82zwiBFLaj",
    ("v3", "bsc"):      "7XgdLW3bts4HktCYsu9dy8bEnuiNeZuftcuK3Aj4JXYV",
    ("v4", "ethereum"): "AdA6Ax3jtct69NnXfxNjWtPTe9gMtSEZx2tTQcT4VHu",
    ("v4", "base"):     "Gqm2b5J85n1bhCyDMpGbtbVn4935EvvdyHdHrx3dibyj",
    ("v4", "arbitrum"): "D1VHPU6cXXSC8eaApWCjCnPcTZQFSYCpGoDAvt4ogDWh",
    ("v4", "optimism"): "3Tn7Y1NJAr4ySKm7KFu1dwvH2WM3mHJnXzXAxQsdBDvW",
    ("v4", "bsc"):      "EAq1nJKgjnuKH6Gj4RFjCW7LcL7E2uipbncdwV7TTWkX",
}

CHAIN_ALIASES = {
    "ethereum": "ethereum", "eth": "ethereum", "mainnet": "ethereum",
    "arbitrum": "arbitrum", "arb": "arbitrum", "arbitrum-one": "arbitrum",
    "base": "base",
    "polygon": "polygon", "matic": "polygon",
    "optimism": "optimism", "op": "optimism",
    "bsc": "bsc", "bnb": "bsc", "binance": "bsc",
}

# V3 has the widest chain coverage, so it is the default venue unless the
# caller pins a version.
_VERSION_PREFERENCE = ("v3", "v4", "v2")

_ADDR_PREFIX = "0x"
_TIMEOUT = httpx.Timeout(12.0, connect=6.0)


class UniswapIntelError(RuntimeError):
    """Raised when the request is unanswerable (bad chain/token, no market)."""


def _api_key() -> str:
    k = os.getenv("GRAPH_API_KEY") or os.getenv("GRAPH_GATEWAY_API_KEY") or ""
    if not k:
        raise UniswapIntelError("GRAPH_API_KEY is not configured on this server")
    return k


def _resolve_market(chain: str, version: str | None) -> tuple[str, str, str]:
    """Return (version, chain, subgraph_id) or raise."""
    c = CHAIN_ALIASES.get((chain or "").strip().lower())
    if not c:
        raise UniswapIntelError(
            f"unsupported chain '{chain}'. Supported: {', '.join(sorted(set(CHAIN_ALIASES.values())))}"
        )
    if version:
        v = version.strip().lower().lstrip("uniswap-").strip()
        v = v if v.startswith("v") else f"v{v}"
        sid = UNISWAP_SUBGRAPHS.get((v, c))
        if not sid:
            raise UniswapIntelError(f"Uniswap {v.upper()} is not deployed on {c}")
        return v, c, sid
    for v in _VERSION_PREFERENCE:
        sid = UNISWAP_SUBGRAPHS.get((v, c))
        if sid:
            return v, c, sid
    raise UniswapIntelError(f"no Uniswap market mapped for chain '{c}'")


async def _gql(client: httpx.AsyncClient, sid: str, query: str, variables: dict | None = None) -> dict:
    """POST a GraphQL query, retrying the gateway's transient indexer routing.

    Every attempt is time-boxed, so a lagging indexer surfaces as a fast clean
    error instead of a hang.
    """
    last = None
    for attempt in range(3):
        try:
            r = await client.post(
                f"{GATEWAY}/{sid}",
                headers={"Authorization": f"Bearer {_api_key()}", "content-type": "application/json"},
                json={"query": query, "variables": variables or {}},
            )
            r.raise_for_status()
            payload = r.json()
            errs = payload.get("errors")
            if errs:
                blob = str(errs).lower()
                transient = any(s in blob for s in ("bad indexers", "unavailable", "too far behind", "no indexer"))
                last = RuntimeError(f"subgraph error: {str(errs)[:180]}")
                if transient and attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise last
            return payload.get("data") or {}
        except Exception as exc:  # noqa: BLE001 - retry any transport hiccup
            last = exc
            if attempt < 2:
                await asyncio.sleep(0.4 * (attempt + 1))
    detail = (str(last) or type(last).__name__) if last else "no response"
    raise UniswapIntelError(f"gateway unavailable: {detail[:160]}")


async def _resolve_token(client: httpx.AsyncClient, sid: str, token: str) -> dict | None:
    """Resolve a symbol or address to its canonical token row.

    For symbols, take the most-transacted match — a scam clone sharing a ticker
    loses the txCount tiebreak by orders of magnitude.
    """
    t = (token or "").strip()
    if t.lower().startswith(_ADDR_PREFIX) and len(t) == 42:
        d = await _gql(client, sid,
                       "query($id:ID!){ tokens(where:{id:$id}){ id symbol name decimals txCount derivedETH } }",
                       {"id": t.lower()})
    else:
        d = await _gql(client, sid,
                       "query($s:String!){ tokens(first:5, where:{symbol:$s}, orderBy:txCount, orderDirection:desc)"
                       "{ id symbol name decimals txCount derivedETH } }",
                       {"s": t})
    rows = d.get("tokens") or []
    return rows[0] if rows else None


async def _native_price(client: httpx.AsyncClient, sid: str) -> float | None:
    """Bundle price of the chain's native asset, across schema variants."""
    for field in ("ethPriceUSD", "nativePriceUSD", "ethPrice"):
        try:
            d = await _gql(client, sid, "{ bundles(first:1){ %s } }" % field)
            rows = d.get("bundles") or []
            if rows and rows[0].get(field) is not None:
                return float(rows[0][field])
        except Exception:
            continue
    return None


async def _pools_for_token(client: httpx.AsyncClient, sid: str, token_id: str) -> list[dict]:
    """Pools holding this token, ranked by volumeUSD (never TVL)."""
    q = ("query($id:String!){ "
         "a: pools(first:8, where:{token0:$id}, orderBy:volumeUSD, orderDirection:desc)"
         "{ id feeTier volumeUSD totalValueLockedUSD txCount token0{id symbol} token1{id symbol} } "
         "b: pools(first:8, where:{token1:$id}, orderBy:volumeUSD, orderDirection:desc)"
         "{ id feeTier volumeUSD totalValueLockedUSD txCount token0{id symbol} token1{id symbol} } }")
    d = await _gql(client, sid, q, {"id": token_id})
    pools = (d.get("a") or []) + (d.get("b") or [])
    pools.sort(key=lambda p: float(p.get("volumeUSD") or 0), reverse=True)
    return pools


async def _flow(client: httpx.AsyncClient, sid: str, pool_id: str, token_id: str,
                token_is_0: bool) -> dict:
    """Two-way-flow check. A honeypot lets you buy but blocks selling."""
    q = ("query($p:String!){ swaps(first:25, where:{pool:$p}, orderBy:timestamp, orderDirection:desc)"
         "{ timestamp amountUSD amount0 amount1 origin } }")
    d = await _gql(client, sid, q, {"p": pool_id})
    swaps = d.get("swaps") or []
    buys = sells = 0
    for s in swaps:
        try:
            amt = float(s.get("amount0") if token_is_0 else s.get("amount1") or 0)
        except (TypeError, ValueError):
            continue
        # Amounts are signed from the pool's perspective: a positive amount means
        # the token flowed INTO the pool, i.e. someone sold it.
        if amt > 0:
            sells += 1
        elif amt < 0:
            buys += 1
    n = buys + sells
    if n < 4:
        risk = "unknown"
    elif sells == 0:
        risk = "high"          # buys clear, nothing ever sells
    elif buys == 0:
        risk = "elevated"      # only exits — dying or one-way
    else:
        risk = "low"
    return {
        "sampled_swaps": len(swaps),
        "buys": buys,
        "sells": sells,
        "two_way": bool(buys and sells),
        "honeypot_risk": risk,
        "newest_trader": (swaps[0].get("origin") if swaps else None),
    }


async def _trend(client: httpx.AsyncClient, sid: str, pool_id: str) -> dict:
    """Daily volume trend for the venue — is interest rising or dying?"""
    q = ("query($p:String!){ poolDayDatas(first:6, where:{pool:$p}, orderBy:date, orderDirection:desc)"
         "{ date volumeUSD } }")
    d = await _gql(client, sid, q, {"p": pool_id})
    days = [{"date": int(x["date"]), "volume_usd": float(x.get("volumeUSD") or 0)}
            for x in (d.get("poolDayDatas") or [])]
    direction, pct = "unknown", None
    # Skip index 0 — the current day is partial and would read as a collapse.
    if len(days) >= 4:
        latest = days[1]["volume_usd"]
        prior = [x["volume_usd"] for x in days[2:5]]
        base = sum(prior) / len(prior) if prior else 0.0
        if base > 0:
            pct = round(((latest - base) / base) * 100, 1)
            direction = "rising" if pct > 20 else "falling" if pct < -20 else "flat"
    return {"days": days, "direction": direction, "pct_vs_3day_avg": pct}


async def uniswap_pretrade(token: str, chain: str = "ethereum", version: str | None = None) -> dict:
    """Pre-trade due-diligence for one token on one chain.

    Returns real liquidity, the deepest venue, honeypot flow check, volume trend
    and a composed verdict. Degrades gracefully: if the flow or trend leg is
    unavailable the rest still returns, flagged, rather than failing the call.
    """
    t0 = time.time()
    v, c, sid = _resolve_market(chain, version)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        tok = await _resolve_token(client, sid, token)
        if not tok:
            raise UniswapIntelError(f"token '{token}' not found on Uniswap {v.upper()} {c}")

        native, pools = await asyncio.gather(
            _native_price(client, sid),
            _pools_for_token(client, sid, tok["id"]),
        )

        derived = float(tok.get("derivedETH") or 0)
        price_usd = round(derived * native, 8) if (native and derived > 0) else None

        if not pools:
            return {
                "token": {"symbol": tok.get("symbol"), "address": tok["id"], "price_usd": price_usd},
                "market": {"chain": c, "version": v, "subgraph_id": sid},
                "verdict": {"tradeable": False, "risk": "high",
                            "reasons": ["no Uniswap pool found for this token on this chain/version"]},
                "note": TVL_NOTE,
                "elapsed_ms": int((time.time() - t0) * 1000),
            }

        best = pools[0]
        token_is_0 = (best.get("token0") or {}).get("id", "").lower() == tok["id"].lower()
        tvl = float(best.get("totalValueLockedUSD") or 0)
        vol = float(best.get("volumeUSD") or 0)

        # Both legs hit the same pool and are independent — run them concurrently.
        # return_exceptions so one dead leg degrades that field instead of the call.
        flow_res, trend_res = await asyncio.gather(
            _flow(client, sid, best["id"], tok["id"], token_is_0),
            _trend(client, sid, best["id"]),
            return_exceptions=True,
        )
        flow = flow_res if isinstance(flow_res, dict) else {
            "honeypot_risk": "unknown", "error": (str(flow_res) or type(flow_res).__name__)[:120]}
        trend = trend_res if isinstance(trend_res, dict) else {
            "direction": "unknown", "error": (str(trend_res) or type(trend_res).__name__)[:120]}

    # --- verdict -------------------------------------------------------------
    real_liquidity = tvl >= 10_000 and vol > 0
    reasons: list[str] = []
    if not real_liquidity:
        reasons.append(f"thin venue: ${tvl:,.0f} liquidity on the deepest pool")
    if flow.get("honeypot_risk") == "high":
        reasons.append("no sells observed in the recent swap sample — possible sell-block")
    elif flow.get("honeypot_risk") == "elevated":
        reasons.append("only exits observed in the recent swap sample")
    if trend.get("direction") == "falling":
        reasons.append(f"volume falling ({trend.get('pct_vs_3day_avg')}% vs 3-day average)")
    if price_usd is None:
        reasons.append("no priced pool path to the native asset — USD price underivable here")

    risk = "low"
    if flow.get("honeypot_risk") == "high" or not real_liquidity or price_usd is None:
        risk = "high"
    elif reasons:
        risk = "medium"
    tradeable = risk != "high"
    if not reasons:
        reasons.append("real depth, two-way flow, and a derivable price")

    return {
        "token": {
            "symbol": tok.get("symbol"), "name": tok.get("name"),
            "address": tok["id"], "decimals": int(tok.get("decimals") or 0),
            "price_usd": price_usd,
        },
        "market": {"chain": c, "version": v, "subgraph_id": sid},
        "best_venue": {
            "pool": best["id"],
            "pair": f"{(best.get('token0') or {}).get('symbol')}/{(best.get('token1') or {}).get('symbol')}",
            "fee_tier": int(best.get("feeTier") or 0) or None,
            "volume_usd": vol,
            "tvl_usd": tvl,
            "tx_count": int(float(best.get("txCount") or 0)),
            "real_liquidity": real_liquidity,
        },
        "alternate_venues": [
            {"pool": p["id"],
             "pair": f"{(p.get('token0') or {}).get('symbol')}/{(p.get('token1') or {}).get('symbol')}",
             "fee_tier": int(p.get("feeTier") or 0) or None,
             "volume_usd": float(p.get("volumeUSD") or 0),
             "tvl_usd": float(p.get("totalValueLockedUSD") or 0)}
            for p in pools[1:5]
        ],
        "flow": flow,
        "trend": trend,
        "verdict": {"tradeable": tradeable, "risk": risk, "reasons": reasons},
        "note": TVL_NOTE,
        "elapsed_ms": int((time.time() - t0) * 1000),
    }


async def top_traders_for_token(token: str, chain: str = "ethereum",
                                version: str | None = None, limit: int = 10) -> dict:
    """Who is actually trading this token right now, and which way.

    Aggregates a recent swap sample on the token's deepest venue by trader
    wallet (`origin`, the EOA — not the router), so an agent can separate
    ACCUMULATORS from DISTRIBUTORS instead of staring at anonymous volume.
    The returned wallets are profiling input: feed them to /agent/score or a
    wallet-risk pass to find out *who* is on the other side.
    """
    limit = max(1, min(int(limit or 10), 25))
    v, c, sid = _resolve_market(chain, version)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        tok = await _resolve_token(client, sid, token)
        if not tok:
            raise UniswapIntelError(f"token '{token}' not found on Uniswap {v.upper()} {c}")
        pools = await _pools_for_token(client, sid, tok["id"])
        if not pools:
            raise UniswapIntelError(f"no Uniswap pool for '{token}' on {v.upper()} {c}")
        best = pools[0]
        token_is_0 = (best.get("token0") or {}).get("id", "").lower() == tok["id"].lower()
        d = await _gql(
            client, sid,
            "query($p:String!){ swaps(first:200, where:{pool:$p}, orderBy:timestamp, orderDirection:desc)"
            "{ timestamp amountUSD amount0 amount1 origin } }",
            {"p": best["id"]},
        )

    swaps = d.get("swaps") or []
    agg: dict[str, dict] = {}
    for s in swaps:
        who = (s.get("origin") or "").lower()
        if not who:
            continue
        try:
            amt = float(s.get("amount0") if token_is_0 else s.get("amount1") or 0)
            usd = abs(float(s.get("amountUSD") or 0))
        except (TypeError, ValueError):
            continue
        e = agg.setdefault(who, {"wallet": who, "buys": 0, "sells": 0,
                                 "volume_usd": 0.0, "net_token": 0.0, "last_seen": None})
        # Positive amount = token flowed INTO the pool = wallet SOLD it.
        if amt > 0:
            e["sells"] += 1
        elif amt < 0:
            e["buys"] += 1
        e["volume_usd"] += usd
        e["net_token"] -= amt          # net accumulation from the wallet's side
        ts = s.get("timestamp")
        if ts and (e["last_seen"] is None or int(ts) > int(e["last_seen"])):
            e["last_seen"] = int(ts)

    traders = sorted(agg.values(), key=lambda x: x["volume_usd"], reverse=True)[:limit]
    for t in traders:
        b, sl = t["buys"], t["sells"]
        if b and not sl:
            t["stance"] = "accumulator"
        elif sl and not b:
            t["stance"] = "distributor"
        elif b or sl:
            t["stance"] = "accumulating" if t["net_token"] > 0 else "distributing" if t["net_token"] < 0 else "two_way"
        else:
            t["stance"] = "unknown"
        t["volume_usd"] = round(t["volume_usd"], 2)
        t["net_token"] = round(t["net_token"], 6)

    return {
        "token": {"symbol": tok.get("symbol"), "address": tok["id"]},
        "market": {"chain": c, "version": v, "subgraph_id": sid},
        "venue": {"pool": best["id"],
                  "pair": f"{(best.get('token0') or {}).get('symbol')}/{(best.get('token1') or {}).get('symbol')}",
                  "fee_tier": int(best.get("feeTier") or 0) or None},
        "sample": {"swaps_scanned": len(swaps), "unique_wallets": len(agg)},
        "traders": traders,
        "note": (
            "Wallets are `origin` (the EOA that initiated the swap), not the router contract. "
            "Stance is derived from a recent swap sample on the deepest venue only — it is a "
            "directional read on this pool, not the wallet's whole book. Feed these wallets into "
            "/agent/score or a wallet-risk pass to profile who is on the other side."
        ),
    }


# Hyperliquid perp coin -> the Uniswap spot token that tracks it.
_PERP_TO_SPOT = {"ETH": "WETH", "BTC": "WBTC", "MATIC": "POL"}


async def spot_perp_basis(coin: str, chain: str = "ethereum", version: str | None = None) -> dict:
    """Cross-venue basis: Uniswap SPOT vs Hyperliquid PERP for the same asset.

    This is a JOIN a single-venue passthrough structurally cannot return — one
    side is an AMM subgraph, the other a perps venue.

    Positive basis => the perp trades ABOVE spot (longs crowded, longs pay funding).
    Negative basis => the perp trades BELOW spot (shorts crowded / spot bid).
    """
    from hyperliquid_intel import fetch_market_activity

    c_up = (coin or "").strip().upper()
    if not c_up:
        raise UniswapIntelError("coin is required (e.g. ETH, BTC)")
    spot_symbol = _PERP_TO_SPOT.get(c_up, c_up)
    v, c, sid = _resolve_market(chain, version)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        tok, native, fills = await asyncio.gather(
            _resolve_token(client, sid, spot_symbol),
            _native_price(client, sid),
            # Pinax caps /markets/activity at 10 items — asking for more 403s.
            fetch_market_activity(c_up, limit=10),
            return_exceptions=True,
        )

    if isinstance(tok, Exception) or not tok:
        raise UniswapIntelError(f"spot token '{spot_symbol}' not found on Uniswap {v.upper()} {c}")
    if isinstance(native, Exception):
        native = None
    derived = float(tok.get("derivedETH") or 0)
    spot = round(derived * native, 8) if (native and derived > 0) else None

    perp = None
    perp_ts = None
    if not isinstance(fills, Exception) and fills:
        try:
            rows = [f for f in fills if f.get("price") is not None]
            # Pinax returns timestamp as a "YYYY-MM-DD HH:MM:SS" string, which
            # sorts correctly lexicographically — do NOT int() it.
            rows.sort(key=lambda f: str(f.get("timestamp") or ""), reverse=True)
            if rows:
                perp = float(rows[0]["price"])
                perp_ts = rows[0].get("timestamp") or None
        except (TypeError, ValueError):
            perp = None

    basis_pct = None
    signal = "unknown"
    if spot and perp:
        basis_pct = round(((perp - spot) / spot) * 100, 4)
        if basis_pct > 0.25:
            signal = "perp_premium"      # longs crowded, funding likely positive
        elif basis_pct < -0.25:
            signal = "perp_discount"     # shorts crowded / spot bid
        else:
            signal = "aligned"

    return {
        "coin": c_up,
        "spot": {"venue": f"uniswap-{v}", "chain": c, "symbol": tok.get("symbol"),
                 "address": tok["id"], "price_usd": spot, "subgraph_id": sid},
        "perp": {"venue": "hyperliquid", "coin": c_up, "price_usd": perp,
                 "last_fill_time": perp_ts},
        "basis_pct": basis_pct,
        "signal": signal,
        "interpretation": {
            "perp_premium": "Perp trades above spot — longs crowded; longs typically pay funding.",
            "perp_discount": "Perp trades below spot — shorts crowded or spot is bid.",
            "aligned": "Perp and spot within 0.25% — no meaningful basis.",
            "unknown": "One leg unavailable; basis not computable.",
        }[signal],
        "note": (
            "Spot is derived on-chain from Uniswap subgraph reserves; perp is the most recent "
            "Hyperliquid fill price, not an oracle mark. Treat basis as a directional signal, "
            "not a settlement price. Legs are independent — if one is unavailable the other still returns."
        ),
    }


TVL_NOTE = (
    "Venues are ranked by volumeUSD, never TVL: Uniswap subgraph TVL is inflated by illiquid "
    "spam-token pools, so treat tvl_usd as a weak signal and volume as the strong one. "
    "honeypot_risk is a flow heuristic over a recent swap sample, not a bytecode audit."
)
