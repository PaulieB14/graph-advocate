"""Examples showing how other agents call the Graph Advocate."""
import json
from advocate import ask_graph_advocate

# ── Single request ──────────────────────────────────────────────────────────
print("Example 1: single request")
rec, history = ask_graph_advocate(
    "I need the top 20 USDC holders on Ethereum with 30-day balance history",
    requesting_agent="portfolio-agent",
)
print(json.dumps(rec, indent=2))

# Pass rec["query_ready"] straight to the MCP:
# tool = rec["query_ready"]["tool"]   →  "getV1EvmHolders"
# args = rec["query_ready"]["args"]   →  {"network_id": "mainnet", ...}

print("\n" + "="*60)

# ── Multi-turn: refine the request ──────────────────────────────────────────
print("Example 2: multi-turn refinement")
rec1, history = ask_graph_advocate(
    "I need Ethereum wallet balances",
    requesting_agent="defi-agent",
)
print("Turn 1:", rec1.get("recommendation"), "→", rec1.get("query_ready", {}).get("tool"))

rec2, history = ask_graph_advocate(
    "Actually I need Solana too",
    history=history,
    requesting_agent="defi-agent",
)
print("Turn 2:", rec2.get("recommendation"), "→", rec2.get("query_ready", {}).get("tool"))
# Advocate now recommends Token API (multi-chain) combining both chains
