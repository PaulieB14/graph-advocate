"""Grounded answers for caller-dictated JSON data lookups.

A caller that writes "Reply with only a JSON object {...}" used to get that
object composed by the model from memory (Haiku, no subgraph call, logged as
`ROUTED unknown`). On 2026-10-11..14 that returned wrong tokens for Base
Uniswap V3 pools to a paying caller (Taifoon). This module runs a real query
and builds the reply from its result. When no query can be run it returns
the caller's shape with nulls and an explicit `could_not_determine` status —
never invented values, and `query_used` only when that query was executed.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

log = logging.getLogger("graph-advocate")

GATEWAY = "https://gateway.thegraph.com/api/subgraphs/id"

# Same verified map as uniswap_intel.UNISWAP_SUBGRAPHS.
from uniswap_intel import UNISWAP_SUBGRAPHS  # noqa: E402

_CHAIN_IDS = {"1": "ethereum", "8453": "base", "42161": "arbitrum", "137": "polygon",
              "10": "optimism", "56": "bsc"}
_CHAIN_WORDS = (("arbitrum", "arbitrum"), ("base", "base"), ("polygon", "polygon"),
                ("optimism", "optimism"), ("bsc", "bsc"), ("bnb", "bsc"),
                ("ethereum", "ethereum"), ("mainnet", "ethereum"))

_ADDR_RE = re.compile(r"0x[0-9a-fA-F]{40}\b")
_POOL_ADDR_RE = re.compile(r"\bpool\s+(0x[0-9a-fA-F]{40})\b", re.I)
_UNISWAP_RE = re.compile(r"\buniswap\s*(v[234])?\b", re.I)
_LOOKUP_RE = re.compile(
    r"\b(which|what|return|get|fetch|read|look\s*up|show)\b.*\b(tokens?|pool|fee|balance|"
    r"holders?|price|address|liquidity|reserves?|tvl|volume)\b", re.I | re.S)


def _gateway_key() -> str:
    return (os.environ.get("GRAPH_API_KEY") or os.environ.get("GATEWAY_API_KEY")
            or os.environ.get("GRAPH_GATEWAY_API_KEY") or "")


def run_gql(subgraph_id: str, query: str) -> dict:
    """Execute against The Graph gateway. Returns the `data` dict or raises."""
    import httpx
    key = _gateway_key()
    if not key:
        raise RuntimeError("no gateway API key configured")
    r = httpx.post(f"{GATEWAY}/{subgraph_id}", json={"query": query},
                   headers={"Authorization": f"Bearer {key}"}, timeout=15)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(f"gateway errors: {json.dumps(body['errors'])[:300]}")
    return body.get("data") or {}


def detect_chain(text: str) -> str | None:
    m = re.search(r"\bchain(?:\s*id)?\s*[:=]?\s*(\d{1,6})\b", text, re.I)
    if m and m.group(1) in _CHAIN_IDS:
        return _CHAIN_IDS[m.group(1)]
    low = text.lower()
    for word, chain in _CHAIN_WORDS:
        if re.search(rf"\b{word}\b", low):
            return chain
    return None


def is_data_lookup(text: str) -> bool:
    return bool(_ADDR_RE.search(text) and _LOOKUP_RE.search(text))


def requested_keys(text: str) -> list[str]:
    """Keys of the JSON object template the caller dictated, in order."""
    m = re.search(r"json(?:\s+object)?[^{]{0,80}(\{.*\})", text, re.I | re.S)
    if not m:
        return []
    keys: list[str] = []
    for k in re.findall(r'"([A-Za-z_][\w\-]*)"\s*:', m.group(1)) or re.findall(
            r"([A-Za-z_][\w]*)\s*:", m.group(1)):
        if k not in keys:
            keys.append(k)
    return keys


def _pool_query(pool: str) -> str:
    return (f'{{ pool(id: "{pool.lower()}") {{ id feeTier '
            f'token0 {{ id symbol decimals }} token1 {{ id symbol decimals }} }} }}')


_FIELD_ALIASES = {
    "token0": ("token0", "id"), "token0_address": ("token0", "id"), "token0address": ("token0", "id"),
    "token0_symbol": ("token0", "symbol"), "token0symbol": ("token0", "symbol"),
    "token1": ("token1", "id"), "token1_address": ("token1", "id"), "token1address": ("token1", "id"),
    "token1_symbol": ("token1", "symbol"), "token1symbol": ("token1", "symbol"),
    "fee_tier": ("feeTier",), "feetier": ("feeTier",), "fee": ("feeTier",),
    "pool": ("id",), "pool_address": ("id",), "pool_id": ("id",), "address": ("id",),
}


def _get(d: dict, path: tuple) -> Any:
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def _pool_reply(keys: list[str], pool: dict, chain: str, query: str, sid: str) -> dict:
    fee = pool.get("feeTier")
    try:
        fee = int(fee)
    except (TypeError, ValueError):
        pass
    if not keys:
        keys = ["token0", "token1", "fee_tier"]
    out: dict = {}
    for k in keys:
        norm = k.lower()
        if norm in ("query_used", "query", "source_query"):
            out[k] = query
        elif norm in ("chain", "network"):
            out[k] = chain
        elif norm in ("source", "data_source"):
            out[k] = f"uniswap-v3 subgraph {sid} on {chain}"
        elif norm in _FIELD_ALIASES:
            v = _get(pool, _FIELD_ALIASES[norm])
            out[k] = fee if _FIELD_ALIASES[norm] == ("feeTier",) else v
        else:
            out[k] = None
    out.setdefault("token0_symbol", _get(pool, ("token0", "symbol")))
    out.setdefault("token1_symbol", _get(pool, ("token1", "symbol")))
    # Executed, so these are safe to state.
    out.setdefault("query_used", query)
    out["_grounding"] = {"executed": True, "subgraph_id": sid, "chain": chain}
    return out


def could_not_determine(keys: list[str], reason: str) -> dict:
    out = {k: None for k in keys if k.lower() not in ("query_used", "query", "source_query")}
    out["status"] = "could_not_determine"
    out["reason"] = reason
    out["_grounding"] = {"executed": False}
    return out


def answer(request: str, gql: Callable[[str, str], dict] | None = None) -> dict | None:
    """Grounded caller-JSON answer, or None if this isn't a lookup we can route.

    Returns a dict in the caller's shape: real values from an executed query,
    or nulls + status=could_not_determine. Never model-composed values.
    """
    gql = gql or run_gql
    text = request or ""
    keys = requested_keys(text)
    pool_m = _POOL_ADDR_RE.search(text)
    uni = _UNISWAP_RE.search(text)
    if not (pool_m and uni):
        return None
    pool = pool_m.group(1)
    chain = detect_chain(text)
    version = (uni.group(1) or "v3").lower()
    sid = UNISWAP_SUBGRAPHS.get((version, chain or ""))
    if not sid:
        return could_not_determine(
            keys, f"no verified Uniswap {version} subgraph for chain {chain or 'unspecified'}")
    query = _pool_query(pool)
    try:
        data = gql(sid, query)
    except Exception as e:  # network / gateway error: say so, don't guess
        log.warning(f"GROUNDED query failed sid={sid[:10]} pool={pool}: {e}")
        return could_not_determine(keys, f"subgraph query failed: {str(e)[:160]}")
    row = (data or {}).get("pool")
    if not row:
        return could_not_determine(
            keys, f"pool {pool} not found in the Uniswap {version} subgraph on {chain}")
    log.info(f"GROUNDED uniswap-{version} {chain} pool={pool} → "
             f"{_get(row, ('token0', 'symbol'))}/{_get(row, ('token1', 'symbol'))} {row.get('feeTier')}")
    return _pool_reply(keys, row, chain, query, sid)
