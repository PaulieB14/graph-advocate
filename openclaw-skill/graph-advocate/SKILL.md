---
name: graph-advocate
description: "Route any blockchain data question to the right Graph Protocol service. Returns live data from 14,733+ subgraphs, Token API (EVM/Solana/TON), x402 payment analytics, and protocol-specific MCP packages. Trigger keywords: subgraph, token, balance, holder, swap, pool, TVL, DeFi, NFT, Aave, Uniswap, Polymarket, ENS, governance, x402, prediction market, onchain data, blockchain."
version: 2.0.0
homepage: https://github.com/PaulieB14/graph-advocate
metadata:
  clawdbot:
    emoji: "⛓️"
---

# Graph Advocate

Ask any blockchain data question in plain English. Get back **live data** — not just a recommendation.

## Routing

Match the user's intent to the right service. Load only the reference you need.

| Intent | Service | Reference | Use for |
|--------|---------|-----------|---------|
| **Token balances, holders, swaps, NFTs** | token-api | [token-api.md](references/token-api.md) | Wallet data across EVM, Solana, TON |
| **Find a subgraph for a protocol** | subgraph-registry | [subgraph-registry.md](references/subgraph-registry.md) | Search 14,733+ subgraphs by protocol/chain |
| **Aave lending data** | graph-aave-mcp | [aave.md](references/aave.md) | 40 tools — V2/V3/V4, liquidations, rates |
| **Polymarket prediction markets** | graph-polymarket-mcp | [polymarket.md](references/polymarket.md) | 31 tools — prices, P&L, open interest |
| **x402 payment analytics** | x402-analytics | [x402.md](references/x402.md) | Payment volume, facilitators, daily stats on Base |
| **Raw block data, streaming** | substreams | — | Traces, logs, custom transformations |
| **Agent discovery (ERC-8004)** | 8004scan | — | Find AI agents by capability |
| **MCP server auth** | mcp8004 | — | ERC-8004 identity verification |
| **Cross-protocol lending** | graph-lending-mcp | — | Compare Aave/Compound/Morpho rates |
| **Limitless prediction markets** | graph-limitless-mcp | — | Markets on Base |

If the request spans two services, use both and combine results.

## Quick Examples

```
"Top 10 USDC holders on Ethereum"           → token-api
"Best subgraph for Uniswap V3 on Arbitrum?" → subgraph-registry  
"Aave V3 liquidations above $50K"           → graph-aave-mcp
"x402 payment volume on Base today"         → x402-analytics
"Find agents that do trading"               → 8004scan
```

## How It Works

1. Agent sends plain-English question
2. Graph Advocate identifies the best service
3. Searches the subgraph registry (14,733 subgraphs with query hints)
4. Executes the query and returns **live data** in the response
5. Includes `get_started` link for agents to get their own free API key

## Response Format

```json
{
  "recommendation": "subgraph-registry",
  "reason": "why this service fits",
  "confidence": "high",
  "query_ready": { "tool": "...", "args": {...} },
  "execution_result": { "source": "subgraph-gateway", "data": {...} },
  "get_started": "Free API key: https://thegraph.com/studio/",
  "cache_for_seconds": 86400
}
```

## Endpoints

| Method | URL | Purpose |
|--------|-----|---------|
| POST | `https://graph-advocate-production.up.railway.app/` | A2A JSON-RPC 2.0 |
| POST | `https://graph-advocate-production.up.railway.app/chat` | Simple HTTP chat |
| GET | `https://graph-advocate-production.up.railway.app/.well-known/agent-card.json` | Agent card |
| GET | `https://graph-advocate-production.up.railway.app/dashboard` | Live monitoring |
| POST | `https://graph-advocate-production.up.railway.app/feedback` | Agent feedback |

## x402 Payments

10 free queries/day per sender. After that, $0.01 USDC on Base per query.
Payments go to Ampersend smart account. Agents with x402 wallets pay automatically.

## External Endpoints

| Endpoint | Data sent | Purpose |
|----------|-----------|---------|
| `graph-advocate-production.up.railway.app` | Your plain-English query | Routes to the right Graph service |
| `gateway.thegraph.com/api/` | GraphQL queries | Executes subgraph queries for live data |
| `token-api.thegraph.com/` | REST requests | Fetches token/NFT/swap data |
| `api.studio.thegraph.com` | GraphQL queries | x402 payment analytics |

## Security & Privacy

- **Instruction-only skill** — no code is downloaded or executed on your machine
- **No credentials required** — Graph Advocate does not need API keys from you
- **No local file access** — reads nothing from your filesystem
- **Stateless** — no session data persists between requests

## Identity

- **ERC-8004:** Agent #734 (Arbitrum), #41,034 (Base)
- **ENS:** graphadvocate.eth
- **Ampersend:** [app.ampersend.ai/discover/agent/8453:41034](https://app.ampersend.ai/discover/agent/8453:41034)

## Trust Statement

By using this skill, your plain-English data queries are sent to `graph-advocate-production.up.railway.app` (hosted on Railway, operated by @paulieb14). The service returns structured JSON with live data. Only install if you trust this endpoint with your query text.

## Links

- GitHub: https://github.com/PaulieB14/graph-advocate
- The Graph: https://thegraph.com
- Subgraph Studio: https://thegraph.com/studio
