"""Live top-3 rows for the free preview (the 402 body shown to unpaid callers).

Until now a free reply only said WHERE the data lives plus an "example (not
live data)" query. Buyers on x402 pay for data they can use immediately, so
for topics with a known, runnable subgraph query we execute it and return the
top 3 real rows, formatted (`numfmt`), under `live_preview`.

Cost / safety rules (most traffic is bots):
  * 3.5s hard timeout; any failure / GraphQL error / empty result -> None, and
    the caller silently keeps the static example.
  * Results cached in memory per (subgraph, query) for GA_LIVE_PREVIEW_TTL_S
    (default 600s); failures are negative-cached for 60s so a dead subgraph is
    not hammered.
  * At most GA_LIVE_PREVIEW_MAX_INFLIGHT (default 4) concurrent gateway calls;
    beyond that we fall back instead of queueing.
  * Never runs for the generic fallback topic, for user-specific questions
    (wallet / pool addresses, health factors), or when another chain / protocol
    version than the one we have a verified subgraph for is named.
  * GA_LIVE_PREVIEW=0 disables it.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Callable

import numfmt
from subgraph_exec import GATEWAY_URL, _api_key

log = logging.getLogger(__name__)

TOP_N = 3
TIMEOUT_S = 3.5
TTL_S = float(os.environ.get("GA_LIVE_PREVIEW_TTL_S", "600"))
NEG_TTL_S = 120.0
PAID_TOP_N = 25
PAID_TIMEOUT_S = 8.0
MAX_INFLIGHT = int(os.environ.get("GA_LIVE_PREVIEW_MAX_INFLIGHT", "4"))
_MAX_CACHE = 200

_cache: dict[tuple[str, str], tuple[float, Any]] = {}  # key -> (expires_at, payload | None)
_cache_lock = threading.Lock()
_inflight = threading.BoundedSemaphore(MAX_INFLIGHT)

# Gateway spend guard: cache hits are free, so this only bounds UNCACHED fetches
# (new questions/topics). ~600/hour is far above real demand and far below a flood.
UNCACHED_PER_HOUR = int(os.environ.get("GA_LIVE_PREVIEW_UNCACHED_PER_HOUR", "600"))
_spend = {"h": "", "n": 0}


def _spend_ok() -> bool:
    hour = time.strftime("%Y-%m-%d-%H", time.gmtime())
    with _cache_lock:
        if _spend["h"] != hour:
            _spend.update(h=hour, n=0)
        if _spend["n"] >= UNCACHED_PER_HOUR:
            return False
        _spend["n"] += 1
        return True

UNI_V3_ETH = "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV"
AAVE_V3_ETH = "JCNWRypm7FYwV8fx5HhzZPSFaMxgkPuw4TnR3Gpi81zk"
COMPOUND_V3_ETH = "AwoxEZbiWLvv6e3QdvdMZw4WDURdGbvPfHmZRc8Dpfz9"
ENS_SUBGRAPH = "5XqPmWe6gjyrJtFn9cLy237i4cWw2j9HcUJEXsP5qGtH"
POLYMARKET_MAIN = "81Dm16JjuFSrqz813HysXoUPvzTwE7fsfPk2RTf66nyC"  # fresh; polymarket-v2-main (FjHkLw5U…) stopped indexing in May 2026

# Verified 2026-11-11: sane rows, fresh index, sub-second. (Uniswap V3 Arbitrum/Polygon timed out
# or lacked `pools`; Aave V3 Base/Optimism errored/empty; Curve ranks spam pools by TVL; polymarket-v2-main stale.)
UNI_V3 = {"ethereum": (UNI_V3_ETH, "Uniswap V3 Ethereum"),
          "base": ("43Hwfi3dJSoGpyas9VwNoDAv55yjgGrPpNSmbQZArzMG", "Uniswap V3 Base"),
          "optimism": ("Cghf4LfVqPiFw6fp6Y5X5Ubc8UpmUhSfJL82zwiBFLaj", "Uniswap V3 Optimism")}
AAVE_V3 = {"ethereum": (AAVE_V3_ETH, "Aave V3 Ethereum"),
           "polygon": ("6yuf1C49aWEscgk5n9D1DekeG1BCk5Z9imJYJT3sVmAT", "Aave V3 Polygon"),
           "arbitrum": ("4xyasjQeREe7PxnF6wVdobZvCw5mhoHZq3T7guRpuNPf", "Aave V3 Arbitrum"),
           "avalanche": ("72Cez54APnySAn6h8MswzYkwaL9KjvuuKnKArnPJ8yxb", "Aave V3 Avalanche"),
           "gnosis": ("GiNMLDxT1Bdn2dQZxjQLmW24uwpc3geKUBW8RP6oEdg", "Aave V3 Gnosis")}

_CHAIN_WORDS = {
    "ethereum": r"ethereum|mainnet|\beth\b",
    "base": r"\bbase\b",
    "arbitrum": r"arbitrum",
    "optimism": r"optimism|op mainnet",
    "polygon": r"polygon|matic",
    "avalanche": r"avalanche|avax",
    "gnosis": r"gnosis",
}
_OTHER_CHAIN_RE = re.compile(
    r"\b(arbitrum|base|polygon|matic|optimism|op mainnet|avalanche|avax|bsc|bnb|gnosis|celo|linea|scroll"
    r"|zksync|solana|blast|unichain|fantom|sonic|mantle|berachain|tron)\b")


def _chain_of(low: str, supported: dict[str, Any]) -> str | None:
    """Chain the question asks about: 'ethereum' by default, or one of `supported`.
    None when it names a chain we have no verified subgraph for (or several)."""
    named = [c for c, rx in _CHAIN_WORDS.items() if c != "ethereum" and re.search(r"\b(?:%s)\b" % rx, low)]
    other = _OTHER_CHAIN_RE.findall(low)
    if len(named) > 1:
        return None
    if named:
        return named[0] if named[0] in supported else None
    if other:  # a chain outside _CHAIN_WORDS (bsc, linea, solana...)
        return None
    return "ethereum" if "ethereum" in supported else None


_ADDRESS_RE = re.compile(r"0x[0-9a-f]{2,}")
_UNI_INTENT_RE = re.compile(r"\b(top|biggest|largest|most|best|highest|rank\w*|volume|pools?|liquid\w*)\b")
_UNI_OTHER_VERSION_RE = re.compile(r"\bv(2|4)\b|\buniswap\s*(2|4)\b")
_AAVE_INTENT_RE = re.compile(r"\b(top|biggest|largest|markets?|reserves?|tvl|supply|deposits?|borrow\w*|total value|rank\w*)\b")
_AAVE_USER_RE = re.compile(r"health factor|\bhf\b|my (position|wallet)")
_COMPOUND_INTENT_RE = _AAVE_INTENT_RE
_ENS_NAME_RE = re.compile(r"(?<![a-z0-9.-])((?:[a-z0-9-]{1,63}\.){1,3}eth)\b")
_ENS_RECENT_RE = re.compile(r"\b(recent\w*|latest|newest|new(ly)?\s+regist\w*|just regist\w*)\b")
# A subgraph that stopped indexing serves frozen numbers that look live (Polymarket V2-main
# was 192 days behind when this guard was added). Anything older than this falls back.
MAX_INDEX_AGE_S = int(os.environ.get("GA_LIVE_PREVIEW_MAX_AGE_S", str(6 * 3600)))


def enabled() -> bool:
    return os.environ.get("GA_LIVE_PREVIEW", "1").strip().lower() not in ("0", "false", "off", "no")


# --------------------------------------------------------------------------
# row formatters: (gql `data`) -> list[dict]
# --------------------------------------------------------------------------

def _iso(ts: Any) -> str | None:
    try:
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(ts)))
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _raw(value: Any, places: int = 2) -> str | None:
    return numfmt.round_decimal(value, places)


def _rows_uniswap_pools(data: dict) -> list[dict]:
    out = []
    for i, p in enumerate(data.get("pools") or [], 1):
        t0 = (p.get("token0") or {}).get("symbol") or "?"
        t1 = (p.get("token1") or {}).get("symbol") or "?"
        out.append({
            "rank": i, "pool": f"{t0}/{t1}", "fee": numfmt.format_fee_tier(p.get("feeTier")),
            "volume_usd_lifetime": numfmt.format_usd(p.get("volumeUSD")),
            "tvl_usd": numfmt.format_usd(p.get("totalValueLockedUSD")),
            "pool_id": p.get("id"),
            "raw": {"volumeUSD": _raw(p.get("volumeUSD")), "totalValueLockedUSD": _raw(p.get("totalValueLockedUSD"))},
        })
    return out


def _rows_lending_markets(data: dict) -> list[dict]:
    out = []
    for i, m in enumerate(data.get("markets") or [], 1):
        out.append({
            "rank": i, "market": m.get("name"), "asset": (m.get("inputToken") or {}).get("symbol"),
            "tvl_usd": numfmt.format_usd(m.get("totalValueLockedUSD")),
            "deposits_usd": numfmt.format_usd(m.get("totalDepositBalanceUSD")),
            "borrows_usd": numfmt.format_usd(m.get("totalBorrowBalanceUSD")),
            "raw": {"totalValueLockedUSD": _raw(m.get("totalValueLockedUSD")),
                    "totalBorrowBalanceUSD": _raw(m.get("totalBorrowBalanceUSD"))},
        })
    return out


def _rows_aave_liquidations(data: dict) -> list[dict]:
    out = []
    for i, x in enumerate(data.get("liquidates") or [], 1):
        out.append({
            "rank": i, "time": _iso(x.get("timestamp")), "market": (x.get("market") or {}).get("name"),
            "collateral_asset": (x.get("asset") or {}).get("symbol"),
            "amount_usd": numfmt.format_usd(x.get("amountUSD")), "tx": x.get("hash"),
            "raw": {"amountUSD": _raw(x.get("amountUSD"))},
        })
    return out


def _rows_ens_domains(data: dict) -> list[dict]:
    out = []
    for i, d in enumerate(data.get("domains") or [], 1):
        out.append({
            "rank": i, "name": d.get("name"),
            "owner": (d.get("owner") or {}).get("id"),
            "resolved_address": (d.get("resolvedAddress") or {}).get("id"),
            "registered": _iso(d.get("createdAt")), "expires": _iso(d.get("expiryDate")),
        })
    return out


def _rows_polymarket_global(data: dict) -> list[dict]:
    out = []
    for g in data.get("globals") or []:
        out.append({
            "scope": "Polymarket protocol totals (cumulative)",
            "traders": numfmt.format_count(g.get("numTraders")),
            "markets_total": numfmt.format_count(g.get("numConditions")),
            "markets_open": numfmt.format_count(g.get("numOpenConditions")),
        })
    return out


# --------------------------------------------------------------------------
# specs: topic -> fn(lowercased question) -> spec | None
# --------------------------------------------------------------------------

def _spec(sid: str, name: str, network: str, query: str, rows: Callable[[dict], list[dict]],
          scope: str, note_extra: str = "") -> dict:
    return {"subgraph_id": sid, "name": name, "network": network, "query": query,
            "rows": rows, "scope": scope, "note_extra": note_extra}


def _uniswap(low: str, n: int = TOP_N) -> dict | None:
    if _UNI_OTHER_VERSION_RE.search(low) or _ADDRESS_RE.search(low) or not _UNI_INTENT_RE.search(low):
        return None
    chain = _chain_of(low, UNI_V3)
    if chain is None:
        return None
    sid, name = UNI_V3[chain]
    return _spec(
        sid, name, chain,
        "{ _meta { block { number timestamp } } pools(first: %d, orderBy: volumeUSD, orderDirection: desc) "
        "{ id feeTier volumeUSD totalValueLockedUSD token0 { symbol } token1 { symbol } } }" % n,
        _rows_uniswap_pools, f"Top Uniswap V3 pools on {chain.capitalize()} by lifetime volume (USD)",
        "Volume is cumulative since pool creation, not 24h.")


def _aave(low: str, n: int = TOP_N) -> dict | None:
    if _ADDRESS_RE.search(low) or _AAVE_USER_RE.search(low) or re.search(r"\baave\s*v?[24]\b", low):
        return None
    chain = _chain_of(low, AAVE_V3)
    if chain is None:
        return None
    sid, name = AAVE_V3[chain]
    if "liquidation" in low:
        if chain != "ethereum":
            return None  # liquidations verified on Ethereum only
        return _spec(
            sid, name, chain,
            "{ _meta { block { number timestamp } } liquidates(first: %d, orderBy: timestamp, orderDirection: desc, "
            "where: { amountUSD_gt: \"50000\" }) { hash timestamp amountUSD asset { symbol } market { name } } }" % n,
            _rows_aave_liquidations, "Most recent Aave V3 Ethereum liquidations above $50K")
    if not _AAVE_INTENT_RE.search(low):
        return None
    return _spec(
        sid, name, chain,
        "{ _meta { block { number timestamp } } markets(first: %d, orderBy: totalValueLockedUSD, orderDirection: desc) "
        "{ name inputToken { symbol } totalValueLockedUSD totalDepositBalanceUSD totalBorrowBalanceUSD } }" % n,
        _rows_lending_markets, f"Largest {name} markets by TVL")


def _compound(low: str, n: int = TOP_N) -> dict | None:
    if "compound" not in low or _ADDRESS_RE.search(low) or re.search(r"\bv2\b", low):
        return None
    if _chain_of(low, {"ethereum": 1}) is None or not _COMPOUND_INTENT_RE.search(low):
        return None
    return _spec(
        COMPOUND_V3_ETH, "Compound V3 Ethereum", "ethereum",
        "{ _meta { block { number timestamp } } markets(first: %d, orderBy: totalValueLockedUSD, orderDirection: desc) "
        "{ name inputToken { symbol } totalValueLockedUSD totalDepositBalanceUSD totalBorrowBalanceUSD } }" % n,
        _rows_lending_markets, "Largest Compound V3 Ethereum markets by TVL")


def _ens(low: str, n: int = TOP_N) -> dict | None:
    m = _ENS_NAME_RE.search(low)
    if m:
        name = m.group(1)
        if len(name) > 100:
            return None
        return _spec(
            ENS_SUBGRAPH, "ENS", "ethereum",
            "{ _meta { block { number timestamp } } domains(first: %d, where: { name: \"%s\" }) "
            "{ name createdAt expiryDate owner { id } resolvedAddress { id } } }" % (n, name),
            _rows_ens_domains, f"ENS record for {name}")
    if _ENS_RECENT_RE.search(low) and re.search(r"\bens\b|\.eth\b|ethereum name service", low):
        return _spec(
            ENS_SUBGRAPH, "ENS", "ethereum",
            "{ _meta { block { number timestamp } } domains(first: %d, where: { name_ends_with: \".eth\" }, "
            "orderBy: createdAt, orderDirection: desc) { name createdAt expiryDate owner { id } } }" % n,
            _rows_ens_domains, "Most recently registered .eth names")
    return None


_POLY_STATS_RE = re.compile(r"\b(overall|total|how (big|many)|traders|stats|statistics|size of|protocol)\b")


def _polymarket(low: str, n: int = TOP_N) -> dict | None:
    if _ADDRESS_RE.search(low) or "kalshi" in low or not _POLY_STATS_RE.search(low):
        return None  # wallet-specific / cross-venue / not a protocol-size question
    return _spec(
        POLYMARKET_MAIN, "Polymarket", "polygon",
        "{ _meta { block { number timestamp } } globals(first: 1) { numTraders numConditions numOpenConditions } }",
        _rows_polymarket_global, "Polymarket protocol-wide totals (cumulative)")


_SPECS: dict[str, Callable[..., dict | None]] = {
    "uniswap": _uniswap, "aave": _aave, "lending": _compound, "ens": _ens, "polymarket": _polymarket,
}


def topics() -> list[str]:
    return sorted(_SPECS)


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------

def _fetch(sid: str, query: str, timeout_s: float = TIMEOUT_S) -> dict | None:
    """Run `query`; return the `data` dict or None on any problem."""
    key = _api_key()
    if not key:
        return None
    if not _spend_ok():
        log.info("live_preview skipped: hourly uncached budget exhausted")
        return None
    if not _inflight.acquire(blocking=False):
        log.info("live_preview skipped: too many in-flight gateway calls")
        return None
    try:
        import httpx
        r = httpx.post(
            GATEWAY_URL.format(subgraph_id=sid),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"query": query},
            timeout=httpx.Timeout(timeout_s, connect=2.0),
        )
        r.raise_for_status()
        payload = r.json()
        if payload.get("errors"):
            log.info("live_preview graphql errors sid=%s", sid[:8])
            return None
        data = payload.get("data")
        return data if isinstance(data, dict) else None
    except Exception as exc:  # timeout, network, bad JSON, 4xx/5xx
        log.info("live_preview fetch failed sid=%s err=%s", sid[:8], type(exc).__name__)
        return None
    finally:
        _inflight.release()


def _cached_fetch(sid: str, query: str, timeout_s: float = TIMEOUT_S) -> tuple[dict | None, bool, float | None]:
    """(data, from_cache, fetched_at_epoch)."""
    ck = (sid, query)
    now = time.time()
    with _cache_lock:
        hit = _cache.get(ck)
        if hit and hit[0] > now:
            payload = hit[1]
            if payload is None:
                return None, True, None
            return payload["data"], True, payload["at"]
    data = _fetch(sid, query) if timeout_s == TIMEOUT_S else _fetch(sid, query, timeout_s)
    now = time.time()
    with _cache_lock:
        if len(_cache) >= _MAX_CACHE:
            for k in [k for k, v in _cache.items() if v[0] <= now] or list(_cache)[: _MAX_CACHE // 2]:
                _cache.pop(k, None)
        if data is None:
            _cache[ck] = (now + NEG_TTL_S, None)
        else:
            _cache[ck] = (now + TTL_S, {"data": data, "at": now})
    return data, False, (now if data is not None else None)


def build(topic: str, low_text: str, price: str = "$0.01", *, n: int = TOP_N, paid: bool = False) -> dict | None:
    """Return a `live_preview` (free, top-3) or `paid_result` (paid, up to 25 rows) dict,
    or None (disabled / no spec / failure / empty / stale index)."""
    if topic == "fallback" or not enabled():
        return None
    fn = _SPECS.get(topic)
    if fn is None:
        return None
    try:
        spec = fn(low_text, n)
        if spec is None:
            return None
        started = time.monotonic()
        data, cached, at = _cached_fetch(spec["subgraph_id"], spec["query"],
                                         PAID_TIMEOUT_S if paid else TIMEOUT_S)
        if not data:
            return None
        meta_block = ((data.get("_meta") or {}).get("block") or {})
        try:
            ts = int(meta_block.get("timestamp"))
        except (TypeError, ValueError):
            ts = None
        if ts is not None and time.time() - ts > MAX_INDEX_AGE_S:
            log.warning("live_preview stale index topic=%s sid=%s age_h=%.0f", topic,
                        spec["subgraph_id"][:8], (time.time() - ts) / 3600)
            return None
        rows = spec["rows"](data)[:n]
        if not rows:
            return None
        out: dict[str, Any] = {
            "label": ("live result (real rows from The Graph)" if paid
                      else "live data (real rows from The Graph, not an example)"),
            "scope": spec["scope"],
            "source": {"subgraph_id": spec["subgraph_id"], "name": spec["name"], "network": spec["network"]},
            "query": spec["query"],
            "rows": rows,
            "row_count": len(rows),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at or time.time())),
            "cached": cached,
        }
        if paid:
            out["note"] = (spec["note_extra"] or "").strip() or None
        else:
            out["note"] = (f"Top {n} live rows free; pay {price} for full list, other chains, and follow-ups."
                           + (f" {spec['note_extra']}" if spec["note_extra"] else ""))
        if meta_block.get("number") is not None:
            out["indexed_block"] = meta_block.get("number")
            iso = _iso(meta_block.get("timestamp"))
            if iso:
                out["indexed_at"] = iso
        log.info("live_%s_served topic=%s cached=%s ms=%d", "paid" if paid else "preview", topic, cached,
                 int((time.monotonic() - started) * 1000))
        return out
    except Exception as exc:
        log.warning("live_preview failed topic=%s err=%s", topic, type(exc).__name__)
        return None


def build_paid(text: str | None, topic: str | None = None) -> dict | None:
    """Full verified result (up to 25 rows) for a paid /route call, used when the model's own
    query_ready is missing or fails. Same safety rules; longer timeout."""
    if not text:
        return None
    import free_preview as fp
    low = text.lower()
    t = topic or fp._match_topic(low)[0]
    return build(t, low, n=PAID_TOP_N, paid=True)
