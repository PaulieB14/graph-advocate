# Graph Advocate — Onchain Data Routing Agent

## What can I ask?

Ask about any blockchain protocol or onchain data. Graph Advocate finds the right subgraph and writes the query for you.

**Find a subgraph:** "I need [protocol] data on [chain]"
**Get a query:** "GraphQL query for [what you need]"
**Live data:** "Show me [token/wallet/swap] data"

Examples:
- "I need Curve pool data on Ethereum — which subgraph has the highest query volume?"
- "Write me a GraphQL query for all Aave V3 liquidations above $50K"
- "What subgraphs exist for tracking NFT sales on Base?"
- "How do I query Lido withdrawal requests from The Graph?"
- "Compare lending rates across Aave, Compound, and Morpho"

## For LLM tools and agents

Machine-readable discovery surfaces (auto-fetched by Cursor, Claude Code, etc.):

- **llms.txt:** https://graph-advocate-production.up.railway.app/llms.txt
- **Capabilities (JSON):** https://graph-advocate-production.up.railway.app/agents/capabilities.json
- **Agent card (A2A):** https://graph-advocate-production.up.railway.app/.well-known/agent-card.json

## Overview

Graph Advocate helps AI agents find the right subgraph and get a ready-to-run GraphQL query for any blockchain data need. It searches 15,500+ subgraphs across 20+ chains indexed by The Graph Protocol, returning the best match with a working query, subgraph ID, and playground link.

No SDK required. Any agent that can make an HTTP POST can query The Graph — free API key at thegraph.com/studio (100K queries/month, 2 minute signup).

## Key Features

- **Subgraph Discovery** — Search 15,500+ classified subgraphs by protocol, chain, or keyword. Returns subgraph ID, query volume (reliability signal), and playground link.
- **Query Building** — Returns ready-to-execute GraphQL queries with correct entity names and field selections for any protocol (Uniswap, Aave, ENS, Compound, Curve, Lido, and more).
- **Live Token Data** — Wallet balances, DEX swaps, NFT sales, holder rankings via Token API across EVM (Ethereum, Base, Polygon, Arbitrum), Solana, and TON.
- **Live Bazaar Discovery** — `GET /bazaar/active` joins x402 Base subgraph + agent0 ERC-8004 + 8004scan + CDP Bazaar to surface services *actually being paid* right now (not just listed).
- **Protocol-Specific MCP Packages** — Pre-built tools for Aave (32 tools, V2/V3/V4), Polymarket (31 tools), Limitless, and cross-protocol lending.
- **Agent Authentication** — Integrates mcp8004 for ERC-8004 identity-verified MCP tool access.
- **x402 Payments** — 10 free queries/day, then $0.01 USDC on Base per query. **Indexed on the CDP x402 Bazaar** so any x402-aware agent (incl. Fetch.ai uAgents now) can discover and pay automatically.
- **Dispatch RPC Provider** — Same agent identity (graphadvocate.eth) is also a registered provider on Lodestar Dispatch (Arbitrum One JSON-RPC, GRT-paid, on-chain settled via TAP receipts). 10k GRT staked on Horizon.

## Usage Instructions

### Input
Send a plain-English data question as a text message. Examples:
- "Best subgraph for Uniswap V3 on Arbitrum?"
- "GraphQL query for top 10 Aave markets by TVL"
- "Top 20 USDC holders on Ethereum"
- "Which subgraph tracks ENS domain registrations?"

### Output
Returns structured JSON with:
- `recommendation` — which Graph service to use
- `query_ready` — a working GraphQL query with subgraph ID
- `get_started` — how to get a free API key
- `install` — npx command for protocol-specific MCP package (when available)
- `cache_for_seconds` — how long the response is valid

### Example Interaction

**Input:** "Best subgraph for Curve pool TVL?"

**Output:**
```json
{
  "recommendation": "subgraph-registry",
  "reason": "Curve Finance subgraph indexes Pool entities with TVL, volume, and fee data.",
  "confidence": "high",
  "query_ready": {
    "tool": "execute_query_by_subgraph_id",
    "args": {
      "subgraph_id": "...",
      "gql": "{ pools(first: 10, orderBy: totalValueLockedUSD, orderDirection: desc) { name totalValueLockedUSD } }"
    }
  },
  "get_started": "Free API key: https://thegraph.com/studio/",
  "cache_for_seconds": 86400
}
```

## Use Cases

- **Trading agents** needing real-time DEX pool data (liquidity, fee tiers, swap history)
- **Yield optimizers** comparing lending rates across Aave, Compound, Morpho, Curve
- **Prediction market agents** accessing Polymarket orderbooks, trader P&L, and resolution data
- **Portfolio trackers** querying wallet balances and token transfers across multiple chains
- **Analytics dashboards** finding the right subgraph for any DeFi protocol
- **Agent developers** who want blockchain data without building custom indexers

## Supported Services

| Service | Best For |
|---------|---------|
| Subgraph Registry | Find the right subgraph from 15,500+ indexed |
| Token API | Wallet balances, swaps, NFTs, holders (EVM/Solana/TON) |
| Substreams | Raw block data, traces, streaming |
| graph-aave-mcp | Aave V2/V3/V4 — 32 tools |
| graph-polymarket-mcp | Polymarket — 31 tools |
| graph-lending-mcp | Cross-protocol lending |
| graph-limitless-mcp | Limitless prediction markets |
| 8004scan | ERC-8004 agent discovery |

## Limitations

- Responses are routing recommendations + queries, not raw data execution (except Token API which returns live data inline)
- Subgraph data depends on indexer availability on The Graph's decentralized network
- Free tier: 10 queries/day per sender, then x402 payment required
- Best for structured onchain data — not suited for off-chain data, social media, or general knowledge questions

## Discoverable on

- **CDP x402 Bazaar:** [discovery/merchant?payTo=0x0FF5A6e...](https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86)
- **Agentic Market:** [agentic.market/?service=graph-advocate-production-up-railway-app](https://agentic.market/?service=graph-advocate-production-up-railway-app)
- **8004scan (Base):** [agents/base/41034](https://www.8004scan.io/agents/base/41034)
- **8004scan (Arbitrum):** [agents/arbitrum/734](https://www.8004scan.io/agents/arbitrum/734)
- **x402scan:** [www.x402scan.com](https://www.x402scan.com)
- **Lodestar Dispatch (RPC provider):** Active on Arbitrum One, score 1.0 in `/providers/42161`
- **Mintlify Docs:** [graphadvocate-31.mintlify.app](https://graphadvocate-31.mintlify.app)

## Metadata

- **Author:** PaulieB14
- **Version:** 2.1
- **ERC-8004:** Agent #734 on Arbitrum (Base #41034)
- **ENS:** graphadvocate.eth
- **License:** MIT
- **Source:** https://github.com/PaulieB14/graph-advocate
