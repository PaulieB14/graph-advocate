# Graph Advocate — Full Reference

Complete reference for all endpoints, identity, integrations, and architecture. See [README.md](README.md) for the quick overview.

---

## Live Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | POST | A2A JSON-RPC 2.0 routing (free tier, 10/day) |
| `/` | GET | Landing page (HTML with OG meta tags) |
| `/route` | POST | x402 paid endpoint ($0.01 USDC on Base) |
| `/route` | GET | x402 v2 challenge (HTTP 402) |
| `/dashboard` | GET | Live monitoring dashboard (4 tabs) |
| `/dashboard/data` | GET | Dashboard JSON API (15s poll) |
| `/chat` | GET/POST | Web chat UI (Haiku-powered) |
| `/.well-known/agent-card.json` | GET | A2A agent discovery card |
| `/.well-known/x402` | GET | x402scan discovery document |
| `/openapi.json` | GET | OpenAPI 3.1 spec with x-payment-info |
| `/quality` | GET | Response quality metrics (auto-scored 0-5) |
| `/feedback` | POST | Agent feedback (was_useful, tool_executed) |
| `/feedback/stats` | GET | Feedback summary |
| `/export/json` | GET | Full activity history |
| `/export/csv` | GET | Activity CSV export |
| `/export/stats` | GET | Summary stats (grant reporting) |
| `/logs` | GET | Last 200 requests as JSON |
| `/mcp/sse` | GET | MCP server (SSE transport) |
| `/graphadvocate.png` | GET | Bot logo (1024x1024 PNG) |
| `/favicon.ico` | GET | Favicon |

---

## Identity & Registrations

| Platform | ID / Link |
|----------|-----------|
| **Production URL** | https://graphadvocate.com |
| **ENS** | `graphadvocate.eth` |
| **ERC-8004 (Arbitrum)** | Agent #734 — [8004scan](https://www.8004scan.io/agents/arbitrum/734) |
| **ERC-8004 (Base)** | Agent #41,034 — [8004scan](https://www.8004scan.io/agents/base/41034) |
| **A2A Registry** | [afd9b3bb-413c-41cf-9874-6361ea309e32](https://a2aregistry.org) |
| **x402scan** | [Listed](https://www.x402scan.com) — v2, Utility tag |
| **Agentverse** | [@graph-advocate](https://agentverse.ai) — 4.7 rating, 2,300+ interactions |
| **Ampersend** | [Discover](https://app.ampersend.ai/discover/agent/8453:41034) |
| **ClawHub** | [graph-advocate](https://clawhub.ai/paulieb14/graph-advocate) |
| **Agent Wallet** | `0x575267eED09c338FAE5716A486A7B58A5749A292` |
| **x402 Pay-To Wallet** | `0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86` (Ampersend) |

---

## x402 Payment Details

| Field | Value |
|-------|-------|
| **Protocol** | x402 v2 |
| **Network** | Base mainnet (`eip155:8453`) |
| **Asset** | USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`) |
| **Amount** | 10000 atomic = $0.01 |
| **Pay-to** | `0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86` |
| **Facilitator** | Coinbase CDP (`api.cdp.coinbase.com/platform/v2/x402`) |
| **Scheme** | `exact` |
| **Max timeout** | 300 seconds |
| **Free tier** | 10 queries/day per requesting agent (POST / only) |
| **Discovery** | `/.well-known/x402` + `/openapi.json` |

---

## Services & Routing

### Data Services

| Service | Best for | Auth |
|---------|---------|------|
| **Token API** | Wallet balances, swaps, NFTs, holders (EVM/Solana/TON) | JWT from thegraph.market |
| **Subgraph Registry** | Protocol-level indexed data (15,500+ subgraphs) | API key from thegraph.com/studio |
| **Substreams** | Raw block data, traces, streaming | JWT from thegraph.market |
| **8004scan** | AI agent discovery & reputation | None (public API) |

### MCP Packages

| Package | Protocol | Tools | Install |
|---------|----------|-------|---------|
| `graph-aave-mcp` | Aave V2/V3/V4 | 40 tools, 16 subgraphs + V4 API + liquidation risk | `npx graph-aave-mcp` |
| `graph-polymarket-mcp` | Polymarket | 31 tools, 8 subgraphs + REST APIs | `npx graph-polymarket-mcp` |
| `graph-lending-mcp` | Multi-protocol lending | Messari standardized | `npx graph-lending-mcp` |
| `graph-limitless-mcp` | Limitless (Base) | Prediction markets | `npx graph-limitless-mcp` |
| `predictfun-mcp` | Predict.fun (BNB) | Prediction markets | `npx predictfun-mcp` |
| `subgraph-registry-mcp` | Subgraph search | 15,500+ classified | `npx subgraph-registry-mcp` |
| `substreams-search-mcp` | Substreams browser | Package registry | `npx substreams-search-mcp` |
| `mcp8004` | ERC-8004 auth | Agent identity middleware | `npm install mcp8004` |

### Graph Ecosystem Dashboards (graphtools.pro)

| Dashboard | URL |
|-----------|-----|
| Delegators Activity Log | https://graphtools.pro/delegators-activity |
| Indexer Score | https://graphtools.pro/indexer-score |
| Top 10 Indexers by Query Fees | https://graphtools.pro/top-indexers |
| Elite Subgraph Dashboard | https://graphtools.pro/elite-subgraphs |
| Subgraph Search by Contract | https://graphtools.pro/subgraph-search |
| GRT Vesting Dashboard | https://graphtools.pro/vesting |
| Curation Earnings Tracker | https://graphtools.pro/curation |
| Graph Dispute Dashboard | https://graphtools.pro/disputes |
| Subgraphs Network Dashboard | https://graphtools.pro/subgraphs-network |

---

## Dashboard Features

The live dashboard at `/dashboard` has 4 tabs:

- **Overview** — Hero metrics (total requests, 24h activity, quality score) + 24h stacked bar chart
- **Live Activity** — Full-width feed with text filter + service dropdown, click to expand details
- **Analytics** — Routing breakdown donut (side-by-side with legend) + top querying agents leaderboard
- **Services** — Per-service health grid with request count, quality score, and last-seen timestamp

Auto-refreshes every 15 seconds. Selected tab persists via localStorage.

---

## Output Schema

```json
{
  "recommendation": "graph-aave-mcp",
  "reason": "Aave V3 liquidation data is indexed by...",
  "confidence": "high",
  "query_ready": {
    "tool": "execute_query_by_subgraph_id",
    "args": { "subgraph_id": "...", "query": "{ ... }" }
  },
  "curl_example": "curl -X POST ...",
  "install": "npx graph-aave-mcp",
  "get_started": "Free API key: https://thegraph.com/studio/",
  "alternatives": [
    { "service": "subgraph-registry", "reason": "...", "confidence": "medium" }
  ],
  "cache_for_seconds": 3600
}
```

---

## Architecture

```
Agent request → A2A / x402 → Graph Advocate
                                  ↓
                          Claude (routing + auto-search)
                                  ↓
                    ┌─────────────┼─────────────┐
                    ↓             ↓             ↓
              Token API    Subgraph Registry  MCP Package
              (REST)       (GraphQL)          (npx install)
```

**Routing layers:**
1. `_auto_search` — keyword matching + live subgraph/substreams/token-api/8004scan searches
2. Claude API call with system prompt + search context
3. `_extract_json` → `_fallback_route` → `_inject_missing_fields` → `_normalize_service_name`

**Caching:** Static benchmark responses (saves ~120 Claude calls/day) + SQLite persistent cache (24h TTL) + in-memory cache

**Quality scoring:** Every response auto-scored 0-5 on: parse success, query readiness, subgraph ID presence, curl example, install command. Service-aware — REST APIs not penalized for missing subgraph IDs.

**x402:** PaymentMiddlewareASGI from x402 SDK wraps `/route`. CDP facilitator handles verification + on-chain settlement. Free tier on `POST /` uses a per-sender daily counter.

---

## Files

| File | Purpose |
|------|---------|
| `advocate.py` | Core routing logic, system prompt, Claude calls, auto-search, SQLite logging |
| `a2a_server.py` | A2A HTTP server, x402 payments, dashboard, feedback, quality scoring, chat |
| `test_advocate_routing.py` | 34-case test suite |
| `erc8004-registration.json` | On-chain agent metadata (IPFS + Arbitrum) |
| `static/graphadvocate.png` | Bot logo (1024x1024) |
| `.env.example` | All env vars documented |

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Claude API access |
| `CDP_API_KEY_ID` | Yes (for x402) | CDP facilitator auth |
| `CDP_API_KEY_SECRET` | Yes (for x402) | CDP facilitator auth |
| `GRAPH_API_KEY` | Yes | Subgraph gateway queries |
| `TOKEN_API_JWT` | Yes | Token API access |
| `AGENTVERSE_API_KEY` | Optional | Fetch.ai Agentverse connection |
| `ADVOCATE_PUBLIC_URL` | Set by Railway | Public URL for agent card |

---

## Deployment

Hosted on **Railway**. Auto-deploys on push to `main`. SQLite on Railway volume (`/data/`).

| | |
|---|---|
| **Production** | https://graphadvocate.com |
| **Platform** | Railway (Docker, auto-deploy) |
| **Model** | Claude Opus 4.6 with adaptive thinking |
| **Storage** | SQLite on `/data/` volume (activity, quality scores, feedback, cache) |
| **Payments** | x402 via CDP facilitator on Base mainnet |
| **Fetch.ai** | Proxy mode on Agentverse |
