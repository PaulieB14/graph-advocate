"""
Graph Advocate — Daily Outreach
Runs once per day. Fetches A2A registry, finds relevant agents,
sends a brief introduction to ones not yet contacted.

Run manually: bash run.sh outreach.py
Railway cron:  runs automatically at 09:00 UTC daily
"""

import json
import httpx
import time
import os
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_URL = "https://a2aregistry.org/api/agents"
CONTACTED_LOG = Path("/tmp/advocate_contacted.json")  # persists within Railway session
PUBLIC_URL = os.environ.get("ADVOCATE_PUBLIC_URL", "https://graph-advocate-production.up.railway.app")

# Keywords that suggest an agent might need onchain data
RELEVANT_KEYWORDS = [
    "defi", "nft", "token", "blockchain", "crypto", "wallet",
    "trading", "swap", "uniswap", "aave", "ethereum", "solana",
    "onchain", "on-chain", "web3", "protocol", "liquidity",
    "analytics", "portfolio", "price", "market", "dex",
]

INTRO_MESSAGE = (
    "Hello! I am the Graph Advocate — a routing agent for The Graph Protocol. "
    "If your agent ever needs onchain data (token balances, NFT sales, DEX swaps, "
    "protocol entities, or raw block data), I can tell you exactly which service "
    "and query to use. I cover Token API (EVM/Solana/TON), Subgraph Registry "
    "(15,500+ subgraphs), and Substreams. Just send me a plain-English data request "
    f"at {PUBLIC_URL} and I'll return a ready-to-execute tool call. "
    "No obligation — happy to help if our paths cross."
)


def load_contacted() -> set:
    if CONTACTED_LOG.exists():
        return set(json.loads(CONTACTED_LOG.read_text()))
    return set()


def save_contacted(contacted: set):
    CONTACTED_LOG.write_text(json.dumps(list(contacted)))


def is_relevant(agent: dict) -> bool:
    text = " ".join([
        agent.get("name", ""),
        agent.get("description", ""),
        " ".join(agent.get("skills", [{}])[0].get("tags", []) if agent.get("skills") else []),
    ]).lower()
    return any(kw in text for kw in RELEVANT_KEYWORDS)


def send_intro(agent: dict) -> str | None:
    url = agent.get("url", "").rstrip("/")
    if not url or not url.startswith("http"):
        return None

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "messageId": f"advocate-intro-{int(time.time())}",
                    "parts": [{"kind": "text", "text": INTRO_MESSAGE}],
                }
            },
        }
        r = httpx.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            parts = data.get("result", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "")[:200]
            return "ok (no text response)"
        return f"http {r.status_code}"
    except Exception as e:
        return f"error: {str(e)[:80]}"


def run():
    print(f"\n{'='*60}")
    print(f"GRAPH ADVOCATE OUTREACH — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")

    # Load who we've already contacted
    contacted = load_contacted()
    print(f"Previously contacted: {len(contacted)} agents")

    # Fetch registry
    try:
        r = httpx.get(REGISTRY_URL, timeout=10)
        agents = r.json().get("agents", [])
    except Exception as e:
        print(f"Registry fetch failed: {e}")
        return

    print(f"Registry has {len(agents)} agents")

    # Filter: relevant + not yet contacted + not ourselves
    candidates = [
        a for a in agents
        if a.get("url", "").rstrip("/") not in contacted
        and "graph-advocate" not in a.get("name", "").lower()
        and is_relevant(a)
    ]

    print(f"New relevant agents to contact: {len(candidates)}")

    if not candidates:
        print("No new agents to contact today.")
        return

    sent = 0
    for agent in candidates:
        name = agent.get("name", "unknown")
        url = agent.get("url", "").rstrip("/")
        print(f"\n→ {name} ({url})")

        response = send_intro(agent)
        contacted.add(url)
        save_contacted(contacted)

        if response:
            print(f"  Response: {response}")
        else:
            print(f"  No response / not reachable")

        sent += 1
        time.sleep(2)  # be polite, don't hammer

    print(f"\n{'='*60}")
    print(f"Sent {sent} introductions. Total contacted: {len(contacted)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
