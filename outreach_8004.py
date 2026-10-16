"""ERC-8004 registry candidate source for outreach.py (Base + Arbitrum).

Pulls agents from 8004scan that declare x402 support, ranked by 8004scan's
total_score, keeps those with an A2A or MCP endpoint that actually answers,
and drops our own agent, already-contacted URLs and obvious spam.

Controlled by OUTREACH_8004_SOURCE in outreach.py:
    off      (default) - not used at all
    dry-run  - fetch + log who it WOULD contact, write outreach_8004_candidates.json;
               never sends
    on       - merge into the send list (requires explicit approval to enable)

CLI (read-only, never sends):
    python outreach_8004.py --csv /tmp/outreach-candidates.csv [--exclude urls.txt]
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from typing import Any, Iterable

import httpx

SCAN_BASE = "https://api.8004scan.io/api/v1"
CHAINS = {8453: "base", 42161: "arbitrum"}
SELF_IDS = {(8453, "41034"), (42161, "734")}
SELF_HOSTS = ("graphadvocate.com",)
UA = "GraphAdvocate-Outreach/1.0 (+https://graphadvocate.com)"
API_SLEEP = 2.1          # 8004scan anonymous cap is 30/min
PER_CHAIN_SCAN = 300     # top-N by total_score per chain
MAX_DETAILS = 200

_SPAM_NAME = re.compile(r"^(agent\s*#?\d+|test.*|untitled|my agent|new agent|\W*)$", re.I)
_SPAM_WORDS = ("ziwei", "airdrop claim", "free money", "casino", "porn", "seed phrase",
               "drainer", "guaranteed profit")

# keyword -> (suggested GA endpoint, price, why)
FIT_RULES = (
    (("polymarket", "prediction market", "kalshi", "betting", "odds"),
     ("/polymarket/pnl-quick", "$0.01", "Polymarket wallet skill/PnL before copying a trader")),
    (("hyperliquid", "perp", "perps", "futures", "leverage"),
     ("/hyperliquid/score", "$0.02", "Hyperliquid trader skill score / counterparty risk")),
    (("swap", "dex", "trade", "trading", "token risk", "honeypot", "liquidity", "uniswap", "memecoin"),
     ("/uniswap/pretrade", "$0.02", "token risk + deepest venue before a swap")),
    (("reputation", "trust", "identity", "erc-8004", "8004", "kyc", "score"),
     ("/agent/score", "$0.02", "0-100 reputation score for a counterparty wallet")),
    (("payment", "x402", "commerce", "invoice", "settlement", "merchant"),
     ("/onchain-x402/address", "$0.01", "x402 settlement history of an address")),
)
DEFAULT_FIT = ("/route", "$0.01", "route any onchain data question to a working query")


def _get(client: httpx.Client, url: str, **kw) -> tuple[int, Any]:
    try:
        r = client.get(url, timeout=15, **kw)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, None
    except Exception:
        return 0, None


def list_x402_agents(client: httpx.Client, chain_id: int, limit: int = PER_CHAIN_SCAN) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while len(out) < limit:
        st, body = _get(client, f"{SCAN_BASE}/agents", params={
            "chain_id": chain_id, "x402_supported": "true", "sort_by": "total_score",
            "limit": min(100, limit - len(out)), "offset": offset})
        items = (body or {}).get("items") if isinstance(body, dict) else None
        if st != 200 or not items:
            break
        out.extend(items)
        offset += len(items)
        if not body.get("has_more"):
            break
        time.sleep(API_SLEEP)
    return out


def is_spam(item: dict) -> bool:
    name = str(item.get("name") or "").strip()
    desc = str(item.get("description") or "").strip()
    if _SPAM_NAME.match(name) or not desc or len(desc) < 20:
        return True
    blob = f"{name} {desc}".lower()
    return any(w in blob for w in _SPAM_WORDS)


def is_self(chain_id: int, token_id: str, urls: Iterable[str]) -> bool:
    if (int(chain_id), str(token_id)) in SELF_IDS:
        return True
    return any(h in (u or "").lower() for u in urls for h in SELF_HOSTS)


def endpoints(detail: dict) -> tuple[str, str]:
    """(a2a_endpoint, mcp_endpoint) from an 8004scan detail record."""
    svc = detail.get("services") if isinstance(detail.get("services"), dict) else {}
    a2a = detail.get("a2a_endpoint") or ((svc.get("a2a") or {}).get("endpoint") if isinstance(svc.get("a2a"), dict) else "")
    mcp = detail.get("mcp_server") or ((svc.get("mcp") or {}).get("endpoint") if isinstance(svc.get("mcp"), dict) else "")
    ok = lambda u: u if isinstance(u, str) and u.startswith("https://") else ""
    return ok(a2a), ok(mcp)


def reachable_a2a(client: httpx.Client, url: str) -> str:
    """Return the JSON-RPC URL if an agent card resolves (or the URL answers), else ''."""
    card_url = url if ("agent-card" in url or url.endswith(".json")) \
        else url.rstrip("/") + "/.well-known/agent-card.json"
    st, body = _get(client, card_url)
    if st == 200 and isinstance(body, dict) and (body.get("url") or body.get("name")):
        u = body.get("url") or url
        return u if isinstance(u, str) and u.startswith("https://") else ""
    return ""


def reachable_mcp(client: httpx.Client, url: str) -> bool:
    try:
        r = client.post(url, timeout=15, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "graph-advocate-probe", "version": "1"}}},
            headers={"accept": "application/json, text/event-stream"})
        return r.status_code < 400 or r.status_code in (401, 402)
    except Exception:
        return False


def fit(name: str, desc: str, tags: Iterable[str] = ()) -> tuple[str, str, str]:
    blob = " ".join([name, desc, *tags]).lower()
    for words, out in FIT_RULES:
        if any(w in blob for w in words):
            return out
    return DEFAULT_FIT


def collect(exclude_urls: set[str] | None = None, max_details: int = MAX_DETAILS,
            per_chain: int = PER_CHAIN_SCAN, log=print) -> list[dict]:
    exclude = {u.rstrip("/").lower() for u in (exclude_urls or set())}
    cands: list[dict] = []
    seen_keys: set[str] = set()
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        pool: list[dict] = []
        for cid in CHAINS:
            rows = list_x402_agents(client, cid, per_chain)
            log(f"8004scan chain={cid} x402 agents scanned={len(rows)}")
            pool.extend(rows)
            time.sleep(API_SLEEP)
        pool = [r for r in pool if not is_spam(r)
                and any(p.upper() in ("A2A", "MCP") for p in (r.get("supported_protocols") or []))]
        log(f"after spam/protocol filter: {len(pool)}")
        details = 0
        for r in pool:
            if details >= max_details:
                break
            cid, tid = int(r["chain_id"]), str(r["token_id"])
            details += 1
            time.sleep(API_SLEEP)
            st, d = _get(client, f"{SCAN_BASE}/agents/{cid}/{tid}")
            if st != 200 or not isinstance(d, dict):
                continue
            a2a, mcp = endpoints(d)
            if is_self(cid, tid, (a2a, mcp)):
                continue
            a2a_rpc = reachable_a2a(client, a2a) if a2a else ""
            mcp_ok = bool(mcp) and reachable_mcp(client, mcp)
            endpoint = a2a_rpc or (mcp if mcp_ok else "")
            if not endpoint:
                continue
            key = endpoint.rstrip("/").lower()
            host = re.sub(r"^https://([^/]+).*", r"\1", key)
            if key in exclude or key in seen_keys:
                continue
            # one agent per host: registries are full of N copies of the same bot
            if any(c["_host"] == host for c in cands):
                continue
            seen_keys.add(key)
            name = str(d.get("name") or r.get("name") or "").strip()
            desc = re.sub(r"\s+", " ", str(d.get("description") or "")).strip()
            tags = [str(t) for t in (d.get("tags") or []) if isinstance(t, (str, int))]
            ep, price, why = fit(name, desc, tags)
            cands.append({
                "name": name, "chain": CHAINS[cid], "agent_id": f"{cid}:{tid}",
                "endpoint": endpoint, "endpoint_type": "a2a" if a2a_rpc else "mcp",
                "x402": "yes" if d.get("x402_supported") else "no",
                "what_they_do": desc[:180],
                "suggested_endpoint": ep, "price": price, "fit_reason": why,
                "score": round(float(d.get("total_score") or 0), 1),
                "wallet": d.get("agent_wallet") or d.get("owner_address") or "",
                "_host": host,
            })
    before = len(cands)
    cands = drop_farms(cands)
    log(f"reachable={before} after farm filter={len(cands)}")
    cands.sort(key=lambda c: c["score"], reverse=True)
    for c in cands:
        c.pop("_host", None)
    return cands


SHARED_HOSTS = (".vercel.app", ".hf.space", ".up.railway.app", ".onrender.com", ".workers.dev",
                ".netlify.app", ".ngrok-free.dev")


def drop_farms(cands: list[dict], window: int = 500, min_cluster: int = 3) -> list[dict]:
    """Drop registration farms: >=min_cluster agents on free shared hosting whose
    token ids sit within `window` of each other on the same chain (batch-minted)."""
    shared = [c for c in cands if any(h in c["endpoint"] for h in SHARED_HOSTS)]
    farm: set[str] = set()
    for c in shared:
        ch, tid = c["agent_id"].split(":")
        near = [x for x in shared if x["agent_id"].split(":")[0] == ch
                and abs(int(x["agent_id"].split(":")[1]) - int(tid)) <= window]
        if len(near) >= min_cluster:
            farm.add(c["agent_id"])
    return [c for c in cands if c["agent_id"] not in farm]


CSV_FIELDS = ["name", "chain", "agent_id", "endpoint", "endpoint_type", "x402", "what_they_do",
              "suggested_endpoint", "price", "fit_reason", "score", "wallet"]


def write_csv(path: str, cands: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for c in cands:
            w.writerow({k: c.get(k, "") for k in CSV_FIELDS})


if __name__ == "__main__":
    args = sys.argv[1:]
    out = args[args.index("--csv") + 1] if "--csv" in args else "outreach-candidates.csv"
    excl: set[str] = set()
    if "--exclude" in args:
        with open(args[args.index("--exclude") + 1]) as f:
            excl = {line.strip() for line in f if line.strip()}
    res = collect(excl)
    write_csv(out, res)
    print(json.dumps({"written": out, "count": len(res)}))
