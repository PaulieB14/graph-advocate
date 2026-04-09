# Graph Advocate

## What this is

Claude-powered A2A routing agent for The Graph Protocol. Agents ask plain-English data questions, get back the right subgraph + a ready-to-run GraphQL query.

**Live:** `https://graph-advocate-production.up.railway.app`
**Deploys:** Railway auto-deploys on push to `main`
**Stack:** Python, Starlette/uvicorn, SQLite, Anthropic API

## Key files



| File | Purpose |
|---|---|
| `advocate.py` | Core routing logic, system prompt, Claude calls, auto-search, SQLite logging |
| `a2a_server.py` | A2A HTTP server (JSON-RPC 2.0), x402 payments, dashboard, feedback, quality scoring |
| `test_advocate_routing.py` | 34-case test suite — run after any advocate.py change |
| `erc8004-registration.json` | On-chain agent metadata (synced to IPFS + Arbitrum) |
| `.env.example` | All env vars documented |

## Run locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
ANTHROPIC_API_KEY=sk-ant-... python3 a2a_server.py
```

Test: `python3 test_advocate_routing.py` (34 tests must pass)

## API endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | POST | A2A JSON-RPC 2.0 (main agent endpoint) |
| `/.well-known/agent-card.json` | GET | A2A agent card |
| `/chat` | GET/POST | Web chat UI |
| `/dashboard` | GET | Live monitoring dashboard |
| `/dashboard/data` | GET | Dashboard JSON API (15s poll) |
| `/feedback` | POST | Agent feedback (was_useful, tool_executed) |
| `/feedback/stats` | GET | Feedback summary |
| `/quality` | GET | Response quality metrics (auto-scored 0-5) |
| `/export/json` | GET | Full activity history |
| `/export/csv` | GET | Activity CSV export |
| `/export/stats` | GET | Summary stats for grant reporting |
| `/logs` | GET | Last 100 requests as JSON |

## Routing services

| Service | Best for |
|---|---|
| **token-api** | Wallet balances, swaps, NFTs, holders (EVM/Solana/TON) |
| **subgraph-registry** | Find the right subgraph from 15,500+ indexed |
| **substreams** | Raw block data, traces, streaming |
| **graph-aave-mcp** | Aave V2/V3/V4 — 40 tools (incl. cross-chain liquidation risk) |
| **graph-polymarket-mcp** | Polymarket — 31 tools |
| **graph-lending-mcp** | Cross-protocol lending (Messari) |
| **graph-limitless-mcp** | Limitless prediction markets on Base |
| **predictfun-mcp** | Predict.fun on BNB Chain |
| **mcp8004** | ERC-8004 agent auth for MCP servers |
| **8004scan** | Agent discovery via ERC-8004 registry |

## Architecture

- **Layer 1:** `_auto_search` — keyword matching with word boundaries, runs live subgraph/substreams/token-api/8004scan searches
- **Layer 2:** Claude API call with system prompt + search context
- **Layer 3:** `_extract_json` → `_fallback_route` → `_inject_missing_fields` — robust response parsing
- **Caching:** Benchmark bot static responses (3 queries) + SQLite persistent cache (24h TTL) + in-memory cache
- **Scoring:** Every response auto-scored 0-5 (parse, query_ready, subgraph_id, curl, install)
- **x402:** 10 free queries/day per sender, then $0.01 USDC on Base

## What NOT to break

- Word boundary matching in `_auto_search` — prevents "compound" matching "compounded"
- Thread-local SQLite with WAL mode in `advocate.py` — no per-request connections
- Benchmark bot static responses — saves ~120 Claude calls/day
- `cache_for_seconds` field in responses — agents use this to avoid re-querying

## Agent identity

- **ERC-8004:** Agent #734 on Arbitrum
- **ENS:** `graphadvocate.eth`
- **Wallet:** `0x575267eED09c338FAE5716A486A7B58A5749A292`
- **A2A Registry:** `afd9b3bb-413c-41cf-9874-6361ea309e32`
- **ClawHub:** `clawhub.ai/paulieb14/graph-advocate`
