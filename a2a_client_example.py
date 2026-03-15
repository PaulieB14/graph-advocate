"""
Example: another agent calling the Graph Advocate via A2A.
Run a2a_server.py first, then run this.
"""

import httpx
import json

BASE = "http://localhost:8765"


def discover():
    """Step 1 — any A2A client discovers the agent card first."""
    r = httpx.get(f"{BASE}/.well-known/agent.json")
    card = r.json()
    print("Agent:", card["name"])
    print("Skills:", [s["id"] for s in card["skills"]])
    return card


def ask(text: str, task_id: str = "task-001") -> dict:
    """Step 2 — send a task via JSON-RPC 2.0."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "id": task_id,
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            },
        },
    }
    r = httpx.post(BASE, json=payload, timeout=60)
    result = r.json()

    # Extract the agent's text response
    try:
        parts = result["result"]["status"]["message"]["parts"]
        raw = parts[0]["text"]
        return json.loads(raw)
    except Exception:
        return result


if __name__ == "__main__":
    print("=== Discovering agent ===")
    discover()

    print("\n=== Routing request ===")
    rec = ask("Top 20 USDC holders on Ethereum with 30-day balance history")
    print(json.dumps(rec, indent=2))

    print("\n=== Protocol-specific package recommendation ===")
    rec2 = ask("Which npm package should I use for Aave V3 liquidation data?", task_id="task-002")
    print(json.dumps(rec2, indent=2))
