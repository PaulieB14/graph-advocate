"""
Search Agentverse for agents that might need onchain/blockchain data.
Prints their addresses so you can target the intro blast.
"""
import os
import httpx

API_KEY = os.environ.get("AGENTVERSE_API_KEY", "")
BASE = "https://agentverse.ai/v1"

KEYWORDS = ["blockchain", "defi", "crypto", "onchain", "data", "web3", "ethereum", "solana"]

def search_agents(keyword: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        r = httpx.get(
            f"{BASE}/search/agents",
            params={"search": keyword, "limit": 20},
            headers=headers,
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("agents", [])
        # Try alternate endpoint format
        r2 = httpx.get(
            f"{BASE}/agents",
            params={"query": keyword, "limit": 20},
            headers=headers,
            timeout=10,
        )
        if r2.status_code == 200:
            return r2.json().get("agents", [])
        print(f"  [{keyword}] HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  [{keyword}] Error: {e}")
    return []

seen = set()
results = []

for kw in KEYWORDS:
    agents = search_agents(kw)
    for a in agents:
        addr = a.get("address") or a.get("agent_address", "")
        name = a.get("name", "unknown")
        if addr and addr not in seen:
            seen.add(addr)
            results.append({"name": name, "address": addr, "keyword": kw})
            print(f"  [{kw}] {name} — {addr}")

print(f"\nFound {len(results)} unique agents")
print("\nAddresses for intro blast:")
for r in results:
    print(f'    "{r["address"]}",  # {r["name"]}')
