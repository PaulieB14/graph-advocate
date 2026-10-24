"""Free preview teaser for unpaid callers who hit the x402 paywall.

Zero-cost: pure keyword -> curated-source templates, no LLM and no gateway call.
The teaser is added as an EXTRA field (`free_preview`) next to the standard
x402 fields; it never alters `x402Version`, `accepts`, `resource` or the
`payment-required` header. GA_FREE_PREVIEW=0 disables it.

Rate limits (in-memory, per process): PER_CALLER_PER_HOUR per caller key and
GLOBAL_PER_DAY overall; over-limit callers just get the normal 402.
"""
from __future__ import annotations

import os
import re
import threading
import time

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

# (keywords-all-of-any-group, source, endpoint, what the paid answer returns)
_TOPICS: list[tuple[tuple[str, ...], str, str, str]] = [
    (("polymarket",), "Polymarket subgraphs on The Graph (main V2 FjHkLw5U…, orderbook B9mm21…, PnL 6iGihL…)",
     "/polymarket/*", "trader PnL, positions, order flow and a ready-to-run GraphQL query"),
    (("kalshi",), "Kalshi public market API + Polymarket cross-venue reconciliation",
     "/kalshi/* and /kalshi-polymarket/*", "matched markets, price gaps and trader stats"),
    (("hyperliquid", "leverage", "perp"), "Hyperliquid info API (fills, positions, vaults)",
     "/hyperliquid/*", "wallet PnL, leverage, liquidation risk and fills"),
    (("uniswap",), "Uniswap V2/V3/V4 official subgraphs (e.g. V3 Ethereum 5zvR82Qo…)",
     "/uniswap/* or /route", "ranked pools/tokens with a verified query and field-trap warnings (e.g. TVL fields)"),
    (("aave", "health factor", "liquidation"), "Aave V3 subgraphs (16 deployments across chains)",
     "/route", "position health, liquidation thresholds and the exact query"),
    (("curve",), "Curve / Messari-standard DEX subgraphs",
     "/route", "the right deployment per chain plus a working pool query"),
    (("x402",), "x402 settlement warehouse (132M+ Base EIP-3009 settlements)",
     "/onchain-x402/address or /ask", "payer/payee totals and daily volume with the SQL trace"),
    (("ens", ".eth"), "ENS subgraph (5XqPmWe6…)", "/route", "name ownership, expiries and resolver records"),
    (("balance", "holder", "transfer", "token", "erc20", "nft", "swap"),
     "The Graph Token API (EVM/SVM/TVM balances, transfers, holders, swaps, NFTs)",
     "/route", "the exact Token API endpoint + params for your chain"),
    (("lido", "compound", "morpho", "lending", "borrow"), "Messari-standard lending subgraphs",
     "/route", "the best deployment for that protocol/chain plus a ready query"),
]
_FALLBACK = ("The Graph Network (15,500+ subgraphs), Token API and Substreams",
             "/route", "the best-matching subgraph/endpoint, why, and a ready-to-run query")


def enabled() -> bool:
    return os.environ.get("GA_FREE_PREVIEW", "1").strip().lower() not in ("0", "false", "off", "no")


def is_real_question(text: str | None) -> bool:
    if not text:
        return False
    t = text.strip()
    if len(t) < 12 or len(t.split()) < 3:
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


def build(text: str | None, caller_key: str | None, pay_url: str = "https://graphadvocate.com/route",
          price: str = "$0.01") -> dict | None:
    """Return the teaser dict, or None (disabled / probe / rate-limited)."""
    if not enabled() or not is_real_question(text):
        return None
    if not _allow(caller_key or "anon"):
        return None
    low = text.lower()
    src, ep, full = _FALLBACK
    for kws, s, e, f in _TOPICS:
        if any(re.search(r"(?<![a-z0-9])" + re.escape(k), low) for k in kws):
            src, ep, full = s, e, f
            break
    return {
        "free": True,
        "teaser": f"Best source for this: {src}. Graph Advocate serves it via {ep}.",
        "full_answer_includes": full,
        "cta": f"Pay {price} USDC on Base for the full breakdown: re-POST the same body to {pay_url} "
               "with an x402 `X-PAYMENT` header (any x402 SDK, e.g. x402-fetch / x402-axios, signs and retries automatically).",
    }
