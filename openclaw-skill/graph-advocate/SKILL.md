---
name: graph-advocate
description: "Route any blockchain data question to the right Graph Protocol service. Returns live data from 15,500+ subgraphs, Token API (EVM/Solana/TON + Polymarket), x402 payment analytics, and protocol-specific MCP packages. Trigger keywords: subgraph, token, balance, holder, swap, pool, TVL, DeFi, NFT, Aave, Uniswap, Polymarket, ENS, governance, x402, prediction market, onchain data, blockchain."
version: 2.1.0
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
| **Polymarket markets, OHLCV, P&L, positions** | token-api | [token-api.md](references/token-api.md) | REST endpoints under `/v1/polymarket/*` — no npm install |
| **Find a subgraph for a protocol** | subgraph-registry | [subgraph-registry.md](references/subgraph-registry.md) | Search 15,500+ subgraphs by protocol/chain |
| **Aave lending data** | graph-aave-mcp | [aave.md](references/aave.md) | 40 tools — V2/V3/V4, liquidations, rates |
| **Polymarket advanced (orderbook, disputes, trader winrate/drawdown)** | graph-polymarket-mcp | [polymarket.md](references/polymarket.md) | 31 tools — live CLOB, UMA resolution, subgraph-specific P&L stats |
| **Cross-protocol lending** | graph-lending-mcp | — | Messari standardized — 40+ protocols on 15 chains |
| **Limitless prediction markets** | graph-limitless-mcp | — | Markets on Base |
| **Predict.fun prediction markets** | predictfun-mcp | — | BNB Chain prediction markets |
| **x402 payment analytics** | x402-analytics | [x402.md](references/x402.md) | Payment volume, facilitators, daily stats on Base |
| **Raw block data, streaming** | substreams | — | Traces, logs, custom transformations |
| **Agent discovery (ERC-8004)** | 8004scan | — | Find AI agents by capability |
| **MCP server auth** | mcp8004 | — | ERC-8004 identity verification |

**Polymarket routing rule:** Prefer `token-api` for common queries (markets, OHLCV, activity, user positions, P&L, platform stats). Only route to `graph-polymarket-mcp` for advanced queries: live orderbook depth, live spreads, disputed markets, UMA resolution, trader winrate/drawdown/profit factor, CTF splits/merges/redemptions.

If the request spans two services, use both and combine results.

## Quick Examples

```
"Top 10 USDC holders on Ethereum"           → token-api
"Best subgraph for Uniswap V3 on Arbitrum?" → subgraph-registry
"Aave V3 liquidations above $50K"           → graph-aave-mcp
"Hottest Polymarket markets"                → token-api (/v1/polymarket/markets)
"Polymarket OHLCV for Bitcoin market"       → token-api (/v1/polymarket/markets/ohlc)
"Polymarket trader P&L for 0x..."           → token-api (/v1/polymarket/users/positions)
"Polymarket live orderbook depth"           → graph-polymarket-mcp (advanced)
"Polymarket trader winrate/drawdown"        → graph-polymarket-mcp (subgraph P&L stats)
"Compare Aave vs Compound TVL"              → graph-lending-mcp
"x402 payment volume on Base today"         → x402-analytics
"Find agents that do trading"               → 8004scan
```

## How It Works

1. Agent sends plain-English question
2. Graph Advocate identifies the best service
3. Searches the subgraph registry (15,500+ subgraphs with query hints)
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
| POST | `https://graphadvocate.com/` | A2A JSON-RPC 2.0 |
| POST | `https://graphadvocate.com/chat` | Simple HTTP chat |
| GET | `https://graphadvocate.com/.well-known/agent-card.json` | Agent card |
| GET | `https://graphadvocate.com/agents/capabilities.json` | Machine-readable capability list |
| GET | `https://graphadvocate.com/mcp/catalog` | List of installable MCP servers |
| GET | `https://graphadvocate.com/llms.txt` | LLM-friendly discovery file |
| GET | `https://graphadvocate.com/dashboard` | Live monitoring |
| POST | `https://graphadvocate.com/feedback` | Agent feedback |

## x402 Payments — Spend Controls (READ BEFORE INSTALLING)

**Pricing:**
- `/route` — 3 free queries/sender/day, then **$0.01 USDC** per call (Base mainnet)
- `/polymarket/*` — paid from call 1 ($0.01 - $0.05 per call)
- `/hyperliquid/*` — paid from call 1 ($0.02 - $0.10 per call)

**This skill can trigger automatic USDC payments from a wallet-enabled agent.** If
your agent runtime exposes an x402-capable wallet (e.g. Ampersend, x402-fetch with
a private key, awal, CDP delegated wallet), each call past the free tier and every
call to a paid endpoint will settle USDC on Base **without a per-call confirmation
prompt** — that's the design of x402.

**Required spend controls before autonomous use:**

1. **Use a dedicated low-balance wallet.** Top up only what you're willing to spend
   in a session — e.g. fund with $5 USDC, never your main treasury wallet.
2. **Set a spend cap in your agent runtime.** Most x402 clients accept
   `maxAmountPerCall` and `maxTotalSpend` parameters. If yours does not, wrap calls
   to this skill in a counter that breaks after N invocations.
3. **Stop conditions.** Add at least one of:
   - Hard cap on call count per task (e.g. `max_calls_per_run = 5`)
   - Time bound on the task (e.g. abort after 5 minutes)
   - Cost ceiling check before each call (read wallet USDC balance; halt if below threshold)
4. **Manual approval mode for the first run.** Treat the first agent execution as a
   probe — log every call, inspect spend, then enable autonomous mode only after
   confirming the per-task cost matches expectations.

**Receipt trail:** every paid call returns an `x-payment-response` header with the
on-chain settlement reference. Log it. If a call doesn't return that header but
charged your wallet, file an issue — the contract is "no settlement, no charge."

**No-charge endpoints:** `/.well-known/agent-card.json`, `/agents/capabilities.json`,
`/mcp/catalog`, `/llms.txt`, `/dashboard`, `/chat`, `GET /` — these are free metadata/UI
surfaces and never trigger payment.

Payments are received by Ampersend smart account `0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86`.

## External Endpoints

| Endpoint | Data sent | Purpose |
|----------|-----------|---------|
| `graphadvocate.com` | Your plain-English query | Routes to the right Graph service |
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

By using this skill, your plain-English data queries are sent to `graphadvocate.com` (hosted on Railway, operated by @paulieb14). The service returns structured JSON with live data. Queries may include wallet addresses and protocol/trading intent — do not send sensitive private context (private keys, seed phrases, internal strategy details) and only install if you trust this endpoint operator.

**Wallet authority disclaimer:** if your agent runtime has an attached x402 wallet,
this skill *can* spend USDC from that wallet for any paid endpoint (see "Spend
Controls" above). The skill does not need any credentials *from* you — but if your
runtime auto-pays x402 challenges, paid calls will settle silently. Use a
spend-limited wallet, not your main one.

## Links

- GitHub: https://github.com/PaulieB14/graph-advocate
- The Graph: https://thegraph.com
- Subgraph Studio: https://thegraph.com/studio
