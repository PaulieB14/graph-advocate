# Graph Advocate — Cowork Project

## What this project is

Graph Advocate is a Claude-powered A2A (Agent-to-Agent) routing agent. It listens to plain-English data requests from other AI agents and routes them to the right [The Graph Protocol](https://thegraph.com) service — returning structured JSON with a ready-to-execute tool call.

**Live URL:** `https://graph-advocate-production.up.railway.app`  
**Deploys via:** Railway — every push to `main` auto-deploys.  
**Stack:** Python, FastAPI/uvicorn, SQLite, Anthropic API (Claude Opus 4.6)

---

## Key files

| File | Purpose |
|---|---|
| `advocate.py` | Core routing logic, system prompt, Claude calls, SQLite logging |
| `a2a_server.py` | A2A HTTP server (JSON-RPC 2.0). This is what Railway runs. |
| `dashboard.html` | Browser monitoring dashboard (currently static, needs live data) |
| `generate_dashboard.py` | Regenerates dashboard.html from SQLite data |
| `test_advocate.py` | 7-case validation suite — always run after changing advocate.py |
| `requirements.txt` | Python dependencies |
| `railway.toml` | Railway deployment config |
| `.env.example` | Required env vars — copy to .env and fill in locally |

---

## Environment variables

For local dev, copy `.env.example` to `.env` and set:
```
ANTHROPIC_API_KEY=sk-ant-...
ADVOCATE_PUBLIC_URL=https://graph-advocate-production.up.railway.app
```

On Railway, set these in the Variables tab.

---

## How to run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
bash run.sh a2a_server.py
```

Server starts on port 8765. Test with:
```bash
curl -X POST http://localhost:8765 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"role":"user","messageId":"test-1","parts":[{"kind":"text","text":"Aave V3 liquidation data on Ethereum"}]}}}'
```

---

## Current priorities

### 1. Fix unknown routing (HIGH)
In `advocate.py`, some requests return `"recommendation": "unknown"` — these are routing failures. The system prompt needs to be improved to handle edge cases like:
- Aave liquidation data via protocol-specific subgraphs
- Requests that mix on-chain and off-chain data
- Vague or ambiguous queries

After any change to `advocate.py`, run the test suite:
```bash
bash run.sh test_advocate.py
```

### 2. Live monitoring dashboard (HIGH)
The dashboard at `/dashboard` currently shows static data. The goal is:
- Add a `/dashboard/data` JSON endpoint to `a2a_server.py` that returns live stats from SQLite
- Update `dashboard.html` to poll `/dashboard/data` every 30 seconds
- Show: total calls, unique agents, top requestors, confidence breakdown, recent requests

### 3. Working GQL examples in every response (MEDIUM)
Every response from `advocate.py` should include a ready-to-run GraphQL query or curl example so agents get immediate value without needing to look anything up.

---

## Routing services

The agent routes to these Graph Protocol services:

| Service | Best for |
|---|---|
| **token-api** | Wallet balances, swaps, NFT data, holder rankings |
| **subgraph-registry** | Protocol-level indexed data (Uniswap, Aave, ENS…) |
| **substreams** | Raw block data, traces, real-time streaming |
| **graph-aave-mcp** | Aave V2/V3/V4 specifically — 32 tools |
| **graph-lending-mcp** | Cross-protocol lending (Messari standard) |
| **graph-polymarket-mcp** | Polymarket prediction markets |

---

## Deploy workflow

1. Make changes locally
2. Run `bash run.sh test_advocate.py` — all tests must pass
3. `git add . && git commit -m "..." && git push origin main`
4. Railway auto-deploys in ~60 seconds
5. Check live at `https://graph-advocate-production.up.railway.app`

---

## Agent identity

- **A2A Registry ID:** `afd9b3bb-413c-41cf-9874-6361ea309e32`
- **ERC-8004 Agent ID:** 734 on Arbitrum
- **ENS:** `graphadvocate.eth`
- **Agent wallet:** `0x575267eED09c338FAE5716A486A7B58A5749A292`
- **MoltBridge ID:** `graph-advocate`
- **ClawHub:** [clawhub.ai/paulieb14/graph-advocate](https://clawhub.ai/paulieb14/graph-advocate)
