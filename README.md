# Graph Advocate Agent

**Live:** `https://graph-advocate-production.up.railway.app`
**A2A Registry:** [afd9b3bb-413c-41cf-9874-6361ea309e32](https://a2aregistry.org)
**ERC-8004:** Agent #734 on Arbitrum | Agent #41,034 on Base
**Ampersend:** [app.ampersend.ai/discover/agent/8453:41034](https://app.ampersend.ai/discover/agent/8453:41034) — x402 payments via Edge & Node's agent wallet platform
**Agentverse:** 4.7 rating, 1,100+ interactions — [profile](https://agentverse.ai/agents/details/agent1qfa8f2kzanmt4zqg35gvgk5lpkjev52f75duhdyl3tj6s0nn26466yu5c7a/profile)
**ClawHub:** [graph-advocate](https://clawhub.ai/paulieb14/graph-advocate)
**Agent card:** `https://graph-advocate-production.up.railway.app/.well-known/agent-card.json`
**ENS:** `graphadvocate.eth`

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
| `graph-aave-mcp` | Aave V2/V3/V4 — 32 tools, 11 subgraphs + V4 API |
| `graph-lending-mcp` | Cross-protocol lending (Messari standard) |
| `graph-polymarket-mcp` | Polymarket prediction markets — 31 tools, stdio + SSE |
| `predictfun-mcp` | Predict.fun on BNB Chain |
| `subgraph-registry-mcp` | 15,500+ classified subgraphs |
| `substreams-search-mcp` | Substreams package browser |
| `subgraphs-skills` | AI skills for subgraph development |
| `subgraph-mcp-skills` | AI skills for querying via MCP |
| `create-substreams-sink-sql` | Scaffold Substreams → PostgreSQL sink |
| `mcp8004` | ERC-8004 agent auth middleware for MCP servers |

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

## x402 Payments & Ampersend

Graph Advocate supports autonomous agent payments via the [x402 protocol](https://www.x402.org/) on Base.

- **Free tier:** 10 queries/day per sender
- **Paid tier:** $0.01 USDC per query via x402 after free tier
- **Payment wallet:** [Ampersend](https://www.edgeandnode.com/ampersend) smart account on Base
- **Registered:** [Ampersend Discover](https://app.ampersend.ai/discover/agent/8453:41034)

Payments are settled on-chain via USDC on Base using EIP-3009 (`transferWithAuthorization`). The agent returns a standard x402 `402 Payment Required` response when the free tier is exceeded, with payment requirements that any x402-compatible client can fulfill automatically.

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
| **Chat UI** | `https://graph-advocate-production.up.railway.app/chat` |
| **Live Dashboard** | `https://graph-advocate-production.up.railway.app/dashboard` |
| **Live Logs (JSON)** | `https://graph-advocate-production.up.railway.app/logs` |
| **Agent card** | `https://graph-advocate-production.up.railway.app/.well-known/agent-card.json` |
| **A2A Registry ID** | `afd9b3bb-413c-41cf-9874-6361ea309e32` |
| **A2A Registry** | [a2aregistry.org](https://a2aregistry.org) |
| **ERC-8004 Agent ID** | 734 (Arbitrum One) |
| **8004scan** | [8004scan.io/agents/42161/734](https://www.8004scan.io/agents/42161/734) |
| **ENS** | `graphadvocate.eth` |
| **Agent Wallet** | `0x575267eED09c338FAE5716A486A7B58A5749A292` |
| **ClawHub** | [clawhub.ai/paulieb14/graph-advocate](https://clawhub.ai/paulieb14/graph-advocate) |
| **Moltbook** | [moltbook.com/u/graphadvocate](https://www.moltbook.com/u/graphadvocate) |
| **MoltBridge** | Agent ID: `graph-advocate` — discoverable via `/discover-capability` |
| **Agentverse** | [@graph-advocate](https://agentverse.ai) on Fetch.ai |
| **ASI:One** | Discoverable as `@graphadvocate` on [asi1.ai](https://asi1.ai) |

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

