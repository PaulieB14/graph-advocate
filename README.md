# Graph Advocate Agent

**Live:** `https://graph-advocate-production.up.railway.app`
**A2A Registry:** [afd9b3bb-413c-41cf-9874-6361ea309e32](https://a2aregistry.org)
**Moltbook:** [moltbook.com/u/graphadvocate](https://www.moltbook.com/u/graphadvocate)
**MoltBridge:** `graph-advocate` — capabilities: onchain-data-routing, token-api, subgraph-query, defi-data, evm-data, solana-data
**Agent card:** `https://graph-advocate-production.up.railway.app/.well-known/agent-card.json`

A Claude-powered routing agent that intercepts plain-English data requests from other agents and routes them to the right [The Graph Protocol](https://thegraph.com) service — returning structured JSON with a ready-to-execute tool call.

Exposes itself as an **A2A (Agent-to-Agent) server** so any A2A-compatible agent can discover and call it over HTTP.

---

## What it does

- Listens to plain-English data requests from other agents
- Routes to the best Graph service: **Token API**, **Subgraph Registry**, **Substreams**, or a **protocol-specific MCP package**
- Returns structured JSON: recommendation + confidence + ready-to-run query
- Multi-turn: remembers context across a conversation
- Logs every recommendation to SQLite for performance tuning
- Exposes 3 skills over A2A protocol for agent-to-agent discovery

---

## Services it routes to

### MCP Servers
| Service | Best for |
|---|---|
| **Token API** | Wallet balances, swaps, NFT data, holder rankings — EVM / Solana / TON |
| **Subgraph Registry** | Protocol-level indexed data (Uniswap, Aave, ENS, Compound…) |
| **Substreams** | Raw block data, traces, logs, real-time streaming |

### npm Packages (`npx <name>`)
| Package | Protocol |
|---|---|
| `graph-aave-mcp` | Aave V2/V3 — 7 chains, 11 subgraphs |
| `graph-lending-mcp` | Cross-protocol lending (Messari standard) |
| `graph-polymarket-mcp` | Polymarket prediction markets |
| `predictfun-mcp` | Predict.fun on BNB Chain |
| `subgraph-registry-mcp` | 15,500+ classified subgraphs |
| `substreams-search-mcp` | Substreams package browser |
| `subgraphs-skills` | AI skills for subgraph development |
| `subgraph-mcp-skills` | AI skills for querying via MCP |
| `create-substreams-sink-sql` | Scaffold Substreams → PostgreSQL sink |

---

## Output schema

```json
{
  "recommendation": "graph-aave-mcp",
  "reason": "graph-aave-mcp is purpose-built for Aave V3 liquidation data across 7 chains.",
  "confidence": "high",
  "install": {
    "run_directly": "npx graph-aave-mcp",
    "install_globally": "npm install -g graph-aave-mcp"
  },
  "query_ready": {
    "tool": "execute_query_by_subgraph_id",
    "args": { "subgraph_id": "...", "gql": "{ ... }" }
  },
  "alternatives": [
    { "service": "subgraph-registry", "reason": "...", "confidence": "medium" }
  ]
}
```

---

## Setup

```bash
git clone git@github.com:PaulieB14/graph-advocate.git
cd graph-advocate

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Add your Anthropic API key to .env
```

---

## Usage

### CLI — single question
```bash
bash run.sh advocate.py "Top 20 USDC holders on Ethereum"
```

### Python — call from another agent
```python
from advocate import ask_graph_advocate

rec, history = ask_graph_advocate(
    "Which npm package should I use for Aave liquidation data?",
    requesting_agent="my-agent"
)
# rec["recommendation"]  → "graph-aave-mcp"
# rec["install"]         → {"run_directly": "npx graph-aave-mcp"}
```

### A2A Server — agent-to-agent protocol
```bash
bash run.sh a2a_server.py
```

**Discover the agent (any A2A client):**
```
GET http://localhost:8765/.well-known/agent.json
```

**Send a task:**
```bash
curl -X POST http://localhost:8765 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "messageId": "msg-001",
        "parts": [{"kind": "text", "text": "Aave V3 liquidation data on Ethereum"}]
      }
    }
  }'
```

### A2A skills
| Skill ID | Description |
|---|---|
| `route_data_request` | Route any onchain data request to the right service |
| `compare_services` | Compare services for a use case, ranked |
| `recommend_npm_package` | Recommend the right @paulieb npm package |

---

## Validation suite
```bash
bash run.sh test_advocate.py
```

## Performance dashboard
```bash
bash run.sh dashboard.py        # terminal
open dashboard.html             # browser (after running queries)
```

---

## Files

| File | Purpose |
|---|---|
| `advocate.py` | Core agent — routing logic, system prompt, SQLite logging |
| `a2a_server.py` | A2A HTTP server (JSON-RPC 2.0, port 8765) |
| `a2a_client_example.py` | Example: another agent calling via A2A |
| `test_advocate.py` | 7-case validation suite |
| `dashboard.py` | Terminal performance dashboard |
| `dashboard.html` | Browser performance dashboard |
| `example_usage.py` | Python usage examples |
| `run.sh` | Loads `.env` + activates venv |

---

## Deployment

Hosted on Railway. Auto-deploys on every push to `main`.

| | |
|---|---|
| **Production URL** | `https://graph-advocate-production.up.railway.app` |
| **Live Dashboard** | `https://graph-advocate-production.up.railway.app/dashboard` |
| **Live Logs (JSON)** | `https://graph-advocate-production.up.railway.app/logs` |
| **Agent card** | `https://graph-advocate-production.up.railway.app/.well-known/agent-card.json` |
| **A2A Registry ID** | `afd9b3bb-413c-41cf-9874-6361ea309e32` |
| **A2A Registry** | [a2aregistry.org](https://a2aregistry.org) |
| **Moltbook** | [moltbook.com/u/graphadvocate](https://www.moltbook.com/u/graphadvocate) |
| **MoltBridge** | Agent ID: `graph-advocate` — discoverable via `/discover-capability` |

### Required env vars (Railway Variables tab)
```
ANTHROPIC_API_KEY=sk-ant-...
ADVOCATE_PUBLIC_URL=https://graph-advocate-production.up.railway.app
```

### Call it from anywhere (no install needed)
```bash
curl -X POST https://graph-advocate-production.up.railway.app \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "messageId": "msg-001",
        "parts": [{"kind": "text", "text": "Which service should I use for Aave liquidation data?"}]
      }
    }
  }'
```

## Model

Uses **Claude Opus 4.6** with adaptive thinking.
