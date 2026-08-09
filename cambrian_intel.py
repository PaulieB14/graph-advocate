"""Narrative-vs-flow divergence: Cambrian social momentum JOINed with on-chain flow from The Graph.

The question this answers is one neither source can answer alone. Cambrian's deep42 feed says what
is being *talked about* — tweet velocity, unique authors, engagement, sentiment. The Graph says what
is actually being *traded*. The interesting number is the gap:

  - **Overhyped**: loud on social, quiet on-chain. Narrative running ahead of money.
  - **Under the radar**: real on-chain flow, nobody tweeting. Arguably the more valuable direction,
    and the one a purely-social feed structurally cannot see.

Every call still resolves and queries a subgraph, so the endpoint drives Graph usage rather than
substituting for it.

## The two constraints that shaped this

**Cambrian free tier is 1,000 requests per MONTH.** That is ~33/day, so Cambrian cannot be called
per user request — one hot hour would exhaust a week's budget. The social cohort is therefore
fetched on a timer (`_MOMENTUM_TTL`) and shared by every caller. At a 2h TTL that is 12 calls/day,
~360/month, leaving headroom for retries and development. Momentum over hours is exactly the
resolution this signal wants anyway; a per-request fetch would buy nothing.

**Cambrian returns `tokenSymbol` only — no contract address.** Symbols are not unique and are
actively squatted: querying Uniswap V3 mainnet for `symbol: "MORPHO"` returns five tokens all named
"Morpho Token", of which one has $623M volume and 212k transactions and four have ~$0.15 and two
transactions each; LINK has about fifteen claimants. Resolving by symbol without a guard picks an
impostor most of the time, so the whole cohort is resolved in ONE query ordered by `txCount`
descending — the first row seen for a symbol is its most-transacted claimant — and an activity floor
is applied on top. A wrong token is worse than no token, so a symbol whose best claimant is still
below the floor is reported unresolved rather than guessed at.
"""

from __future__ import annotations

import json
import logging
import os
import statistics
import time
import urllib.parse
import urllib.request

log = logging.getLogger("graph-advocate")

CAMBRIAN_BASE = "https://api.cambrian.org"

# 2h. Chosen against a 1,000/month ceiling: 12 calls/day ≈ 360/month, leaving room for retries and
# for a second cohort endpoint later. Raise this before adding another Cambrian-backed endpoint.
_MOMENTUM_TTL = 2 * 60 * 60

# A token needs real on-chain activity before we will believe a symbol match. Tuned against the
# MORPHO impostors, which sit at ~2 transactions; a genuine token clears this by orders of magnitude.
_MIN_TX_COUNT = 500

# Assets whose ticker is NOT theirs on an EVM chain. Symbol resolution is refused outright for
# these — no activity threshold can save it, which is the whole point.
#
# Measured on Uniswap V3 mainnet 2026-08-08: "DOGE" resolves to `0x1121acc1…` **"Department Of
# Government Efficiency"** with 101,264 transactions — it clears the activity floor below by 200x
# and is a genuinely liquid token that is genuinely not Dogecoin. "XLM" resolves to
# "BenjaminNetanyahuGazaHamasIronDome". These are not squatters that a liquidity bar filters out;
# they are real markets that happen to own the ticker. Refusing by identity is the only correct
# move, and reporting the symbol as non-EVM is more honest than reporting a confident wrong answer.
#
# Bridged wrappers (Wormhole wSOL and friends) are deliberately NOT auto-resolved here either: an
# agent handed wSOL as "SOL" computes wrong supply and wrong holders. Pinning them is worthwhile
# later, but it needs an explicit address map and a `bridged` label, not a symbol lookup.
_NON_EVM_MAJORS = {
    "BTC", "DOGE", "XRP", "ADA", "DOT", "ATOM", "NEAR", "TON",
    "SUI", "APT", "SEI", "TRX", "XLM", "SOL", "AVAX", "LTC", "BCH", "ALGO",
}

# Cambrian's cohort includes tokens with 3 tweets from 3 authors. Ranking those against a token with
# 130 tweets is noise pretending to be signal, so they are carried but flagged, not silently ranked.
_MIN_TWEETS = 5
_MIN_AUTHORS = 4

_momentum_cache: dict[str, tuple[float, list]] = {}


def _api_key() -> str:
    return os.getenv("CAMBRIAN_API_KEY", "").strip()


def _fetch_momentum(limit: int = 40) -> tuple[list, str]:
    """Cambrian's trending-momentum cohort. Cached hard — see the module docstring on the budget.

    Returns `(rows, source)` where source is "live" or "cache", so the caller can tell an agent how
    fresh the social half is. On failure a stale cohort is served rather than nothing: an hours-old
    momentum reading is still informative, and the alternative is a dead endpoint.
    """
    key = f"momentum:{limit}"
    cached = _momentum_cache.get(key)
    if cached and time.time() - cached[0] < _MOMENTUM_TTL:
        return cached[1], "cache"

    api_key = _api_key()
    if not api_key:
        return (cached[1] if cached else []), "unconfigured"

    url = f"{CAMBRIAN_BASE}/deep42/social-data/trending-momentum?{urllib.parse.urlencode({'limit': limit})}"
    req = urllib.request.Request(url, headers={"X-API-KEY": api_key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            rows = json.loads(r.read())
        if not isinstance(rows, list):
            raise ValueError(f"unexpected payload type {type(rows).__name__}")
        _momentum_cache[key] = (time.time(), rows)
        log.info(f"cambrian: refreshed momentum cohort ({len(rows)} tokens)")
        return rows, "live"
    except Exception as e:
        # Serving stale beats serving nothing, but say which it is.
        log.warning(f"cambrian: momentum fetch failed — {e}")
        return (cached[1] if cached else []), "stale" if cached else "unavailable"


def _percentile_ranks(values: list[float]) -> list[float]:
    """Rank each value 0-100 within its own cohort.

    Percentile rank rather than a ratio or z-score, because the two inputs are not commensurable:
    momentumScore lives around 200-300 while volumeUSD runs to 1e8. Any ratio between them is
    arbitrary, and a z-score assumes a normality that on-chain volume (heavily long-tailed) does not
    have. Ranking within the fetched cohort is scale-free and survives both distributions.
    """
    n = len(values)
    if n <= 1:
        return [50.0] * n
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        # Ties share the midpoint of the span they occupy, so equal inputs cannot be ordered by
        # accident of position.
        mid = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = round(100.0 * mid / (n - 1), 1)
        i = j + 1
    return ranks


_DAY = 86400
# Recent window vs the token's own prior baseline. Two days smooths a single quiet Sunday without
# blurring a genuine move; eight days of baseline is long enough to be a norm and short enough to
# still be *this* market regime.
_RECENT_DAYS = 2
_BASELINE_DAYS = 8
# Day rows older than this mean the token has effectively stopped trading; its "flow" is not low,
# it is absent, which is a different statement and must not rank as merely quiet.
_STALE_AFTER_DAYS = 3


def _flow_acceleration(day_rows: list[dict], now: float) -> tuple[float | None, str]:
    """Recent daily volume against the token's own baseline. Returns (ratio, note).

    A ratio, not an absolute, because absolute USD volume measures how *big* a token is, not whether
    something is happening to it — rank by absolute and LINK beats every small token forever, which
    says nothing. Dividing by the token's own baseline asks the question that actually parallels
    social momentum: is this more active than usual for itself?
    """
    if not day_rows:
        return None, "no_day_data"
    fresh = [r for r in day_rows if now - float(r.get("date") or 0) <= _STALE_AFTER_DAYS * _DAY]
    if not fresh:
        return None, "stale_day_data"

    rows = sorted(day_rows, key=lambda r: float(r.get("date") or 0), reverse=True)
    recent = [float(r.get("volumeUSD") or 0) for r in rows[:_RECENT_DAYS]]
    baseline = [float(r.get("volumeUSD") or 0) for r in rows[_RECENT_DAYS:_RECENT_DAYS + _BASELINE_DAYS]]
    if not recent or not baseline:
        return None, "insufficient_history"

    r_mean = statistics.fmean(recent)
    b_mean = statistics.fmean(baseline)
    if b_mean <= 0:
        # No baseline to divide by. Any recent volume is new activity, but the ratio is undefined
        # rather than infinite, so say so instead of inventing a number.
        return (None, "no_baseline") if r_mean <= 0 else (None, "new_activity_no_baseline")
    return r_mean / b_mean, "ok"


async def narrative_vs_flow(chain: str = "ethereum", limit: int = 10, cohort: int = 40) -> dict:
    """Rank trending tokens by the gap between social momentum and on-chain flow acceleration.

    `chain` selects which Uniswap deployment supplies the flow side. `limit` caps returned rows;
    `cohort` is how many social rows to rank within — a wider cohort makes percentiles more
    meaningful and costs nothing extra, since the social half is cached and the on-chain half is a
    single batched query regardless of cohort size.
    """
    import httpx

    import uniswap_intel as uni

    try:
        limit = max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        limit = 10
    try:
        cohort = max(limit, min(int(cohort), 100))
    except (TypeError, ValueError):
        cohort = 40

    rows, freshness = _fetch_momentum(cohort)
    if not rows:
        return {
            "error": "cambrian_unavailable" if freshness != "unconfigured" else "cambrian_unconfigured",
            "detail": (
                "CAMBRIAN_API_KEY is not set on this deployment."
                if freshness == "unconfigured"
                else "Cambrian returned no social cohort and no cached cohort was available."
            ),
            "social_source": freshness,
        }

    chain_key = uni.CHAIN_ALIASES.get(chain.lower(), chain.lower())
    sid = uni.UNISWAP_SUBGRAPHS.get(("v3", chain_key))
    if not sid:
        return {
            "error": "unsupported_chain",
            "chain_tried": chain,
            "supported": sorted({c for v, c in uni.UNISWAP_SUBGRAPHS if v == "v3"}),
        }

    by_symbol = {}
    for r in rows:
        sym = (r.get("tokenSymbol") or "").strip()
        if sym:
            by_symbol.setdefault(sym.upper(), r)
    symbols = list(by_symbol)
    if not symbols:
        return {"error": "empty_cohort", "social_source": freshness}

    # One query for the whole cohort. Ordered by txCount descending so the first row seen for a
    # symbol is its most-transacted claimant — the squatter guard, applied in bulk. Querying
    # per-symbol would be 40 gateway calls to learn the same thing.
    query = """
    query($syms:[String!]){
      tokens(where:{symbol_in:$syms}, first:500, orderBy:txCount, orderDirection:desc){
        id symbol name txCount
        tokenDayData(first:12, orderBy:date, orderDirection:desc){ date volumeUSD }
      }
    }"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            data = await uni._gql(client, sid, query, {"syms": symbols})
    except Exception as e:
        return {"error": "subgraph_unreachable", "detail": str(e)[:200], "chain": chain}

    best: dict[str, dict] = {}
    for tok in data.get("tokens") or []:
        sym = (tok.get("symbol") or "").upper()
        if sym not in best:  # first == highest txCount, by the query's ordering
            best[sym] = tok

    now = time.time()
    resolved, unresolved = [], []
    for sym, social in by_symbol.items():
        if sym in _NON_EVM_MAJORS:
            # Refused by identity, before any liquidity test — see _NON_EVM_MAJORS.
            unresolved.append({
                "symbol": sym,
                "reason": "non_evm_asset",
                "detail": (
                    "This ticker belongs to a non-EVM asset; the tokens carrying it on this chain "
                    "are unrelated (e.g. DOGE resolves to 'Department Of Government Efficiency', "
                    "101k txs). Refused rather than guessed."
                ),
            })
            continue
        tok = best.get(sym)
        if not tok:
            # Expected: Cambrian's cohort is chain-agnostic and includes SOL, XLM, ADA and other
            # non-EVM assets. Reported, never dropped — a caller comparing counts would otherwise
            # believe the endpoint lost tokens.
            unresolved.append({"symbol": sym, "reason": "no_token_on_chain"})
            continue
        tx = int(tok.get("txCount") or 0)
        if tx < _MIN_TX_COUNT:
            unresolved.append({
                "symbol": sym,
                "reason": "below_activity_floor",
                "detail": f"best claimant has {tx} txs (<{_MIN_TX_COUNT}); a ticker squatter, not the real token",
                "candidate": tok.get("id"),
            })
            continue
        accel, note = _flow_acceleration(tok.get("tokenDayData") or [], now)
        if accel is None:
            unresolved.append({"symbol": sym, "reason": note, "candidate": tok.get("id")})
            continue
        resolved.append((social, tok, accel))

    if not resolved:
        return {
            "error": "no_overlap",
            "detail": (
                f"None of the {len(by_symbol)} trending tokens resolved to a token with recent "
                f"on-chain activity on {chain}. Cambrian's cohort is chain-agnostic; try another chain."
            ),
            "chain": chain,
            "social_source": freshness,
            "unresolved": unresolved[:30],
            "unresolved_count": len(unresolved),
        }

    social_ranks = _percentile_ranks([float(s.get("momentumScore") or 0) for s, _, _ in resolved])
    flow_ranks = _percentile_ranks([a for _, _, a in resolved])

    out = []
    for i, (social, tok, accel) in enumerate(resolved):
        tweets = int(social.get("recentTweets") or 0)
        authors = int(social.get("uniqueAuthors") or 0)
        divergence = round(social_ranks[i] - flow_ranks[i], 1)
        out.append({
            "symbol": social.get("tokenSymbol"),
            "token_address": tok.get("id"),
            "token_name": tok.get("name"),
            "divergence": divergence,
            "reading": "overhyped" if divergence > 20 else "under_the_radar" if divergence < -20 else "aligned",
            "social_rank": social_ranks[i],
            "flow_rank": flow_ranks[i],
            "flow_acceleration": round(accel, 3),
            "social": {
                "momentum_score": social.get("momentumScore"),
                "sentiment": social.get("sentiment"),
                "recent_tweets": tweets,
                "unique_authors": authors,
                "total_reach": social.get("totalReach"),
                "tweet_velocity": social.get("tweetVelocity"),
            },
            "onchain": {"tx_count_lifetime": int(tok.get("txCount") or 0), "chain": chain},
            "thin_sample": tweets < _MIN_TWEETS or authors < _MIN_AUTHORS,
        })

    out.sort(key=lambda r: abs(r["divergence"]), reverse=True)

    return {
        "chain": chain,
        "cohort_size": len(resolved),
        "social_source": freshness,
        "social_cache_ttl_seconds": _MOMENTUM_TTL,
        "ranked": out[:limit],
        "unresolved": unresolved[:30],
        "unresolved_count": len(unresolved),
        "how_to_read": (
            "divergence = social percentile − on-chain percentile, both ranked within this cohort. "
            "The on-chain side is flow ACCELERATION — the last "
            f"{_RECENT_DAYS} days of volume against the token's own prior {_BASELINE_DAYS}-day "
            "baseline — not absolute volume, which would just rank tokens by size and say nothing. "
            "Positive divergence = talk running ahead of money (overhyped). Negative = on-chain "
            "activity picking up with little social attention (under the radar), which a social feed "
            "alone structurally cannot see. `thin_sample` marks tokens whose social side rests on "
            "very few tweets."
        ),
        "sources": {
            "social": "Cambrian deep42 trending-momentum",
            "onchain": f"Uniswap V3 subgraph on {chain} via The Graph (one batched query)",
        },
    }
