"""Free preview teaser for unpaid callers who hit the x402 paywall.

Zero-cost: pure keyword -> curated-source templates, no LLM and no gateway call.
The teaser is added as an EXTRA field (`free_preview`) next to the standard
x402 fields; it never alters `x402Version`, `accepts`, `resource` or the
`payment-required` header. GA_FREE_PREVIEW=0 disables it.

Rate limits (in-memory, per process): PER_CALLER_PER_HOUR per caller key and
GLOBAL_PER_DAY overall; over-limit callers just get the normal 402.

Each matched topic may include a static `example` (GraphQL stub or HTTP
request shape) clearly labeled as an example, not live data. Served previews
emit a structured `free_preview_served` log line (topic + path only).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

PER_CALLER_PER_HOUR = int(os.environ.get("GA_FREE_PREVIEW_PER_HOUR", "3"))
GLOBAL_PER_DAY = int(os.environ.get("GA_FREE_PREVIEW_PER_DAY", "2000"))

_lock = threading.Lock()
_hits: dict[str, list[float]] = {}
_day = {"d": "", "n": 0}

_PROBE_RE = re.compile(
    r"^\s*(ping|pong|hi|hello|hey|test|status|health|healthcheck|ok|ready)\W*$"
    r"|reply (only )?with (just |only )?(the )?(single )?word"
    r"|taifoon|agentprobe|liveness|conformance probe|capability survey"
    r"|what can you do|state your useful capabilities|who are you|list (your )?(tools|capabilities|skills)"
    r"|do not (execute tools|run a paid|make purchases)|紫薇|hermes",
    re.I,
)

# Partnership / security-swarm pitch spam — conservative; only clear pitches.
_SPAM_PITCH_RE = re.compile(
    r"security\s+swarm|autonomous\s+evm\s+security|pre-?sign\s+protection"
    r"|tx-?firewall|fast-ping\s*\(\$?|workers\.dev/api"
    r"|partner(ship)?\s+with\s+us|integrate\s+our\s+(api|service|agent)"
    r"|we\s+offer\s+(paid\s+)?(protection|security|firewall)"
    r"|list\s+(us|our\s+api)\s+on\s+your"
    r"|deterministic\s+pre-?sign",
    re.I,
)

# Example helpers — always labeled as examples, never claimed live.
def _ex_graphql(query: str, note: str = "Illustrative GraphQL shape; not live data.") -> dict:
    return {"label": "example (not live data)", "kind": "graphql", "query": query.strip(), "note": note}


def _ex_http(method: str, path: str, body: dict, note: str = "Example request the paid answer would run; not live data.") -> dict:
    return {
        "label": "example (not live data)",
        "kind": "http",
        "request": {"method": method, "path": path, "body": body},
        "note": note,
    }


_UNI_V3_POOLS_GQL = """
{
  pools(first: 5, orderBy: volumeUSD, orderDirection: desc) {
    id
    feeTier
    volumeUSD
    token0 { symbol }
    token1 { symbol }
  }
}
""".strip()

_AAVE_LIQ_GQL = """
{
  liquidations(first: 5, orderBy: timestamp, orderDirection: desc, where: { amountUSD_gt: "50000" }) {
    id
    timestamp
    amountUSD
    collateralAsset
    principalAsset
  }
}
""".strip()

_AAVE_HF_GQL = """
{
  users(first: 5, orderBy: id, where: { borrowedReservesCount_gt: 0 }) {
    id
    borrowedReservesCount
    collateralReserve: reserves(where: { currentATokenBalance_gt: "0" }, first: 3) {
      reserve { symbol }
      currentATokenBalance
    }
  }
}
""".strip()

_ENS_GQL = """
{
  domains(first: 3, where: { name_ends_with: ".eth" }, orderBy: createdAt, orderDirection: desc) {
    name
    owner { id }
    expiryDate
    resolver { address }
  }
}
""".strip()

# (keywords, topic_id, source, endpoint, full_answer_includes, example_or_None)
_TOPICS: list[tuple[tuple[str, ...], str, str, str, str, dict | None]] = [
    (("polymarket",), "polymarket",
     "Polymarket subgraphs on The Graph (main V2 FjHkLw5U…, orderbook B9mm21…, PnL 6iGihL…)",
     "/polymarket/*",
     "trader PnL, positions, order flow and a ready-to-run GraphQL query",
     _ex_http("POST", "/polymarket/pnl-quick", {"wallet": "0xYOUR_WALLET"},
              "Example paid endpoint + body; replace wallet. Not live data.")),
    (("kalshi",), "kalshi",
     "Kalshi public market API + Polymarket cross-venue reconciliation",
     "/kalshi/* and /kalshi-polymarket/*",
     "matched markets, price gaps and trader stats",
     _ex_http("POST", "/kalshi-polymarket/spread", {"query": "fed rate"},
              "Example paid endpoint + body. Not live data.")),
    (("hyperliquid", "leverage", "perp"), "hyperliquid",
     "Hyperliquid info API (fills, positions, vaults)",
     "/hyperliquid/*",
     "wallet PnL, leverage, liquidation risk and fills",
     _ex_http("POST", "/hyperliquid/risk", {"user": "0xYOUR_WALLET"},
              "Example paid endpoint + body; replace user. Not live data.")),
    (("uniswap",), "uniswap",
     "Uniswap V2/V3/V4 official subgraphs (e.g. V3 Ethereum 5zvR82Qo…)",
     "/uniswap/* or /route",
     "ranked pools/tokens with a verified query and field-trap warnings (e.g. TVL fields)",
     _ex_graphql(_UNI_V3_POOLS_GQL,
                 "Example Uniswap V3 pools-by-volume query shape. Paid /route picks the right deployment per chain. Not live data.")),
    (("aave", "health factor", "liquidation"), "aave",
     "Aave V3 subgraphs (16 deployments across chains)",
     "/route",
     "liquidation events and/or position health (thresholds, HF), plus the exact GraphQL for the matching Aave V3 deployment",
     None),  # example chosen dynamically in build()
    (("curve",), "curve",
     "Curve / Messari-standard DEX subgraphs",
     "/route",
     "the right deployment per chain plus a working pool query",
     _ex_graphql(
         '{ pools(first: 5, orderBy: totalValueLockedUSD, orderDirection: desc) { id name totalValueLockedUSD } }',
         "Illustrative Curve/Messari pool query shape. Not live data.")),
    (("x402",), "x402",
     "x402 settlement warehouse (132M+ Base EIP-3009 settlements)",
     "/onchain-x402/address or /ask",
     "payer/payee totals and daily volume with the SQL trace",
     _ex_http("POST", "/onchain-x402/address", {"address": "0xYOUR_ADDRESS"},
              "Example paid endpoint + body. Not live data.")),
    (("ens", ".eth"), "ens",
     "ENS subgraph (5XqPmWe6…)",
     "/route",
     "name ownership, expiries and resolver records",
     _ex_graphql(_ENS_GQL, "Example ENS domains query shape. Not live data.")),
    (("balance", "holder", "transfer", "token", "erc20", "nft", "swap"), "token-api",
     "The Graph Token API (EVM/SVM/TVM balances, transfers, holders, swaps, NFTs)",
     "/route",
     "the exact Token API endpoint + params for your chain",
     _ex_http("GET", "/route", {"request": "top USDC holders on Ethereum"},
              "Paid /route returns the Token API path + params. This body is an example question, not live data.")),
    (("lido", "compound", "morpho", "lending", "borrow"), "lending",
     "Messari-standard lending subgraphs",
     "/route",
     "the best deployment for that protocol/chain plus a ready query",
     _ex_graphql(
         '{ markets(first: 5, orderBy: totalValueLockedUSD, orderDirection: desc) { id inputToken { symbol } totalValueLockedUSD } }',
         "Illustrative Messari lending markets query shape. Not live data.")),
]
_FALLBACK = ("fallback", "The Graph Network (15,500+ subgraphs), Token API and Substreams",
             "/route", "the best-matching subgraph/endpoint, why, and a ready-to-run query", None)


def enabled() -> bool:
    return os.environ.get("GA_FREE_PREVIEW", "1").strip().lower() not in ("0", "false", "off", "no")


def is_spam_pitch(text: str | None) -> bool:
    """True for obvious partnership / security-swarm pitches (no preview)."""
    if not text:
        return False
    return bool(_SPAM_PITCH_RE.search(text))


def is_real_question(text: str | None) -> bool:
    if not text:
        return False
    t = text.strip()
    if len(t) < 12 or len(t.split()) < 3:
        return False
    if is_spam_pitch(t):
        return False
    return not _PROBE_RE.search(t)


def _allow(key: str) -> bool:
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    with _lock:
        if _day["d"] != today:
            _day.update(d=today, n=0)
        if _day["n"] >= GLOBAL_PER_DAY:
            return False
        h = [x for x in _hits.get(key, []) if now - x < 3600]
        if len(h) >= PER_CALLER_PER_HOUR:
            _hits[key] = h
            return False
        h.append(now)
        _hits[key] = h
        if len(_hits) > 20000:
            _hits.clear()
        _day["n"] += 1
        return True


def _match_topic(low: str) -> tuple[str, str, str, str, dict | None]:
    """Return (topic_id, source, endpoint, full_answer_includes, example)."""
    for kws, tid, s, e, f, ex in _TOPICS:
        if any(re.search(r"(?<![a-z0-9])" + re.escape(k), low) for k in kws):
            if tid == "aave":
                if "liquidation" in low:
                    f = ("recent liquidation events (amounts, collateral/principal assets, "
                         "timestamps) plus the exact GraphQL for the matching Aave V3 deployment")
                    ex = _ex_graphql(
                        _AAVE_LIQ_GQL,
                        "Example liquidation-query shape (field names vary by deployment). "
                        "Paid /route returns the verified query. Not live data.")
                else:
                    f = ("position health / health-factor style fields, liquidation thresholds, "
                         "and the exact GraphQL for the matching Aave V3 deployment")
                    ex = _ex_graphql(
                        _AAVE_HF_GQL,
                        "Example borrowed-user query shape. Paid /route returns the verified query. Not live data.")
            return tid, s, e, f, ex
    tid, s, e, f, ex = _FALLBACK
    return tid, s, e, f, ex


def _feedback_ask() -> dict | None:
    """Short ERC-8004 rating invite from feedback_invite (no invented addresses)."""
    try:
        from feedback_invite import FEEDBACK
        return FEEDBACK
    except Exception:
        return None


def build(text: str | None, caller_key: str | None, pay_url: str = "https://graphadvocate.com/route",
          price: str = "$0.01") -> dict | None:
    """Return the teaser dict, or None (disabled / probe / spam / rate-limited)."""
    if not enabled() or not is_real_question(text):
        return None
    if not _allow(caller_key or "anon"):
        return None
    low = (text or "").lower()
    topic, src, ep, full, example = _match_topic(low)
    out: dict[str, Any] = {
        "free": True,
        "teaser": f"Best source for this: {src}. Graph Advocate serves it via {ep}.",
        "full_answer_includes": full,
        "cta": f"Pay {price} USDC on Base for the full breakdown: re-POST the same body to {pay_url} "
               "with an x402 `X-PAYMENT` header (any x402 SDK, e.g. x402-fetch / x402-axios, signs and retries automatically).",
    }
    if example:
        out["example"] = example
    fb = _feedback_ask()
    if fb:
        out["feedback"] = fb
    # Structured line for daily checks — topic + path only (no question text / PII).
    log.info("free_preview_served topic=%s path=%s", topic, ep.split()[0] if ep else "/route")
    return out
