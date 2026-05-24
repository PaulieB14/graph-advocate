"""x402 ecosystem dashboard data pipeline.

Once-daily background worker that pulls from:
  - PaulieB14/x402-omnigraph subgraph (canonical X402Payment, Facilitator,
    X402DailyStat entities — pre-indexed by The Graph Network on Base)
  - Agent0 ERC-8004 Base subgraph (53k registered agents with owner +
    agent_wallet — for the agent identity JOIN)
  - agentic.market /v1/services (curated catalog + name/category enrichment
    via per-endpoint x402 challenge probing)

Aggregates into a single JSON blob cached in /tmp (or Railway volume).
Served at GET /x402/data — read by /x402 dashboard page.

Why once-daily: Paul's "don't spend crazy money" directive. x402 ecosystem
metrics don't change minute-by-minute meaningfully.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import Counter, defaultdict

log = logging.getLogger("x402_dash")

# Public, free Graph Network deployment IDs
SUB_OMNIGRAPH = "QmPtuuoU9nu9VJyodiVohf21y8RsR2fx8BpxuVBRHhP29D"  # Paul's x402-omnigraph
SUB_AGENT0    = "QmcLwgyKn3RnyhkkSwLYscP9dL1Fc6omvfC9bFRgcK1e7u"  # Agent0 ERC-8004 Base

CACHE_PATH = os.getenv("X402_DASH_CACHE", "/tmp/x402_dashboard.json")
REFRESH_INTERVAL_SECONDS = int(os.getenv("X402_DASH_INTERVAL", str(24 * 3600)))

_state: dict = {
    "status": "not_started",
    "last_refresh_ts": 0,
    "last_error": "",
    "data": None,
}


def snapshot() -> dict:
    """Read the latest cached blob from disk (or in-memory). Never raises."""
    if _state["data"]:
        return _state["data"]
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH) as f:
                _state["data"] = json.load(f)
                return _state["data"]
    except Exception as e:
        log.warning(f"snapshot read failed: {e}")
    return {
        "status": _state["status"],
        "last_refresh_ts": _state["last_refresh_ts"],
        "last_error": _state["last_error"],
        "note": "no data yet — first refresh runs in background on server start",
    }


# ── Data fetching ─────────────────────────────────────────────────────────


def _graph_key() -> str | None:
    return os.environ.get("GRAPH_API_KEY") or os.environ.get("GATEWAY_API_KEY")


async def _query_subgraph(deployment_id: str, query: str) -> dict:
    import httpx
    key = _graph_key()
    if not key:
        raise RuntimeError("GRAPH_API_KEY not set")
    url = f"https://gateway.thegraph.com/api/deployments/id/{deployment_id}"
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(url, json={"query": query},
                         headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        d = r.json()
        if d.get("errors"):
            raise RuntimeError(f"subgraph errors: {d['errors']}")
        return d.get("data", {})


async def fetch_omnigraph_data() -> dict:
    """Pull canonical x402 data from Paul's omnigraph subgraph.

    Coverage notes (verified via curl-test):
      - facilitators: 105 total → bumped to first:200 to catch them all
      - daily stats: ~400 days available; 90d sufficient for the dashboard
      - recipients: top 200 by volume captures 98.4% of the top-1000 value;
        no pagination needed for the merchants table
      - role enum is RECIPIENT (uppercase, unquoted)
    """
    data = await _query_subgraph(SUB_OMNIGRAPH, """
    {
      facilitators(first: 200, orderBy: totalSettlements, orderDirection: desc) {
        id address name totalSettlements isActive
      }
      x402DailyStats(first: 90, orderBy: date, orderDirection: desc) {
        date totalPayments totalVolumeDecimal eip3009Payments permit2Payments
      }
      x402AddressSummaries(first: 200, where: {role: RECIPIENT}, orderBy: totalVolume, orderDirection: desc) {
        id address role totalPayments totalVolumeDecimal firstPaymentTimestamp lastPaymentTimestamp
      }
    }
    """)
    return data


async def fetch_agent0_agents(limit: int = 100000) -> list:
    """Pull ALL Base agents from Agent0 subgraph via cursor pagination.

    There are ~53k Base agents; capping below that broke the merchant↔agent
    JOIN coverage (3.7% hit rate at 2k cap). With a 100k cap, all current
    agents are pulled in ~55 pages = ~55 free-tier queries per daily
    refresh. Bumped from prior 2k cap after Paul flagged the coverage gap.
    """
    agents = []
    last_id = 0
    page_count = 0
    MAX_PAGES = 100  # safety stop (~100k agents = far above current 53k)
    while len(agents) < limit and page_count < MAX_PAGES:
        q = (
            "{ agents(first:1000, where:{agentId_gt:" + str(last_id) +
            "}, orderBy:agentId, orderDirection:asc)"
            "{ id chainId agentId owner agentWallet } }"
        )
        try:
            data = await _query_subgraph(SUB_AGENT0, q)
            page = data.get("agents") or []
            if not page:
                break
            agents.extend(page)
            last_id = int(page[-1]["agentId"])
            page_count += 1
            if len(page) < 1000:
                break
        except Exception as e:
            log.warning(f"agent0 page {page_count} failed: {e}")
            break
    log.info(f"agent0: pulled {len(agents)} agents in {page_count} pages")
    return agents[:limit]


async def fetch_agentic_market() -> list:
    """Pull current agentic.market service catalog."""
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get("https://api.agentic.market/v1/services",
                        headers={"user-agent": "graph-advocate/1.0"})
        r.raise_for_status()
        return (r.json() or {}).get("services") or []


# ── Aggregation ───────────────────────────────────────────────────────────


def build_dashboard_payload(omnigraph: dict, agents: list, services: list) -> dict:
    """Combine sources into the dashboard data shape."""
    facs = omnigraph.get("facilitators") or []
    daily = omnigraph.get("x402DailyStats") or []
    receivers = omnigraph.get("x402AddressSummaries") or []

    # Normalize daily stats (newest last for line charts)
    daily_clean = []
    for d in reversed(daily):
        daily_clean.append({
            "date": d.get("date"),
            "tx_count": int(d.get("totalPayments") or 0),
            "volume_usdc": float(d.get("totalVolumeDecimal") or 0),
            "eip3009_count": int(d.get("eip3009Payments") or 0),
            "permit2_count": int(d.get("permit2Payments") or 0),
        })

    # Facilitator rollup: address → name (Paul's subgraph indexes per-address)
    addr_to_fac = {}
    fac_totals = defaultdict(lambda: {
        "tx_count": 0, "addresses": [], "is_active": False, "first_seen": None,
    })
    for f in facs:
        addr = (f.get("address") or "").lower()
        name = f.get("name") or "Unknown"
        addr_to_fac[addr] = name
        fac_totals[name]["tx_count"] += int(f.get("totalSettlements") or 0)
        fac_totals[name]["addresses"].append(addr)
        fac_totals[name]["is_active"] = fac_totals[name]["is_active"] or bool(f.get("isActive"))

    fac_leaderboard = sorted([
        {"facilitator": k, **v} for k, v in fac_totals.items()
    ], key=lambda x: x["tx_count"], reverse=True)

    # Build owner-address → agent metadata map (ERC-8004 join key)
    agent_index: dict[str, dict] = {}
    for a in agents:
        for k in ("owner", "agentWallet"):
            addr = (a.get(k) or "").lower()
            if addr and addr.startswith("0x"):
                agent_index[addr] = {
                    "agent_id": a.get("agentId"),
                    "chain_id": a.get("chainId"),
                    "owner": (a.get("owner") or "").lower(),
                }

    # Build service payTo → metadata map
    svc_index: dict[str, dict] = {}
    cats: Counter = Counter()
    for s in services:
        for e in (s.get("endpoints") or []):
            pt = (e.get("payTo") or "").lower()
            if pt and pt.startswith("0x"):
                svc_index[pt] = {
                    "name": s.get("name"),
                    "category": s.get("category"),
                    "domain": s.get("domain"),
                    "integration_type": s.get("integrationType"),
                }
                cats[s.get("category") or "Uncategorized"] += 1

    # Top merchants enriched (from omnigraph receivers)
    top_merchants = []
    for r in receivers[:50]:
        addr = (r.get("address") or "").lower()
        svc = svc_index.get(addr) or {}
        agent = agent_index.get(addr)
        top_merchants.append({
            "address": addr,
            "tx_count": int(r.get("totalPayments") or 0),
            "volume_usdc": float(r.get("totalVolumeDecimal") or 0),
            "first_seen_ts": int(r.get("firstPaymentTimestamp") or 0) or None,
            "last_seen_ts": int(r.get("lastPaymentTimestamp") or 0) or None,
            "service_name": svc.get("name"),
            "category": svc.get("category"),
            "integration_type": svc.get("integration_type"),
            "is_registered_agent": bool(agent),
            "agent_id": agent.get("agent_id") if agent else None,
        })

    # Ecosystem hero totals
    total_payments = sum(d["tx_count"] for d in daily_clean[-30:])
    total_volume = sum(d["volume_usdc"] for d in daily_clean[-30:])
    eip3009 = sum(d["eip3009_count"] for d in daily_clean[-30:])
    permit2 = sum(d["permit2_count"] for d in daily_clean[-30:])

    # Agent share of x402 economy
    agent_volume = sum(m["volume_usdc"] for m in top_merchants if m["is_registered_agent"])
    anon_volume = sum(m["volume_usdc"] for m in top_merchants if not m["is_registered_agent"])
    agent_count = sum(1 for m in top_merchants if m["is_registered_agent"])

    return {
        "status": "ok",
        "refreshed_at": int(time.time()),
        "sources": {
            "x402_omnigraph_subgraph": SUB_OMNIGRAPH,
            "agent0_base_subgraph": SUB_AGENT0,
            "agentic_market_catalog": "https://api.agentic.market/v1/services",
        },
        "hero_30d": {
            "tx_count": total_payments,
            "volume_usdc": round(total_volume, 2),
            "active_facilitators": sum(1 for f in fac_leaderboard if f["is_active"]),
            "eip3009_count": eip3009,
            "permit2_count": permit2,
            "eip3009_share_pct": round(100 * eip3009 / total_payments, 1) if total_payments else 0,
            "registered_agents_indexed": len(agents),
            "agentic_market_services": len(services),
        },
        "facilitators": fac_leaderboard[:25],
        "daily_stats": daily_clean[-90:],
        "top_merchants": top_merchants,
        "category_breakdown": [
            {"category": c, "service_count": n}
            for c, n in cats.most_common()
        ],
        "agent_vs_anon": {
            "agent_count": agent_count,
            "anon_count": len(top_merchants) - agent_count,
            "agent_volume_usdc": round(agent_volume, 2),
            "anon_volume_usdc": round(anon_volume, 2),
        },
    }


# ── Background refresh loop ────────────────────────────────────────────────


async def refresh_once() -> bool:
    """Fetch all sources + write cache. Returns True on success."""
    global _state
    _state["status"] = "fetching"
    try:
        omnigraph, agents, services = await asyncio.gather(
            fetch_omnigraph_data(),
            fetch_agent0_agents(),  # full pagination — ~53k agents
            fetch_agentic_market(),
            return_exceptions=False,
        )
        payload = build_dashboard_payload(omnigraph, agents, services)
        os.makedirs(os.path.dirname(CACHE_PATH) or ".", exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(payload, f)
        _state["data"] = payload
        _state["last_refresh_ts"] = int(time.time())
        _state["status"] = "ok"
        _state["last_error"] = ""
        log.info(f"x402 dashboard: refreshed — "
                 f"{payload['hero_30d']['tx_count']:,} txs, "
                 f"${payload['hero_30d']['volume_usdc']:,.2f}, "
                 f"{len(payload['facilitators'])} facilitators")
        return True
    except Exception as e:
        _state["status"] = "error"
        _state["last_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        log.warning(f"x402 dashboard refresh failed: {_state['last_error']}")
        return False


async def run() -> None:
    """Background task — refresh once on startup, then every REFRESH_INTERVAL_SECONDS.
    Never raises. Self-isolates from the rest of GA."""
    # Initial refresh (warm cache on cold start)
    try:
        await asyncio.sleep(5)  # small delay so other startup tasks settle
        await refresh_once()
    except Exception as e:
        log.warning(f"x402 initial refresh failed: {e}")

    # Loop forever at the configured interval
    while True:
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
        try:
            await refresh_once()
        except Exception as e:
            log.warning(f"x402 scheduled refresh failed: {e}")
