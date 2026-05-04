# Graph Advocate

**Onchain data router for AI agents.** Ask in plain English, get back the right
subgraph + a ready-to-run GraphQL query. **ERC-8004 verified** · **x402-paid on Base**.

- 🌐 **[graphadvocate.com](https://graphadvocate.com)**
- 📚 **[docs.graphadvocate.com](https://docs.graphadvocate.com)**
- 🪪 **ERC-8004:** Agent #734 (Arbitrum) · #41034 (Base) · ENS `graphadvocate.eth`
- 💸 **x402 payTo:** `0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86` (Ampersend smart account)

## Try it (30 sec, free)

```bash
curl -X POST https://graphadvocate.com/route \
  -H "Content-Type: application/json" \
  -d '{"question":"Top 20 USDC holders on Ethereum"}'
```

Returns JSON with `subgraph_id`, a working GraphQL `query`, MCP install hint,
and playground link. First **10 queries/day per sender** are free — no payment
header needed. After that: $0.01 USDC via x402 on Base.

## Why agents pay for this

Without Graph Advocate, an agent that wants Aave liquidations on Base has to:
(1) discover candidate subgraphs, (2) compare query volumes for reliability,
(3) read schemas, (4) write GraphQL, (5) test against the indexer. That's
5–10 minutes of model + tool time per data question.

Graph Advocate returns the working query in **one HTTP round trip for $0.01**.

**Real traction:** an automated wallet-profiling agent (`0xac5a07c4…`) has
paid for **21+ queries across 3 sessions over 3 days** since first paying —
the recurring-traffic shape of agents that scale into sustained use.

## What it knows

| Surface | Coverage |
|---|---|
| **Subgraph Registry** | 15,500+ subgraphs across 20+ chains, ranked by query volume (reliability signal) |
| **Token API** | Wallet balances, DEX swaps, NFTs, holder rankings — EVM (ETH, Base, Arbitrum, Polygon), Solana, TON |
| **Substreams** | Raw block data, traces, streaming |
| **MCP packages** | Aave V2/V3/V4 (40 tools, incl. cross-chain liquidation risk), Polymarket (31 tools), cross-protocol lending, Limitless, Predict.fun |
| **Live Bazaar** | `GET /bazaar/active` joins x402 Base subgraph + agent0 ERC-8004 + 8004scan + CDP Bazaar — surfaces services *actually being paid right now*, not just listed |
| **8004 directory** | ERC-8004 agent discovery + auth via `mcp8004` |

## ERC-8004 + x402 stack details

This is what makes Graph Advocate **agent-native** rather than a generic API.

### ERC-8004 identity (verifiable on-chain)

- **Agent #41034 on Base** ([8004scan](https://www.8004scan.io/agents/base/41034)) and **#734 on Arbitrum** ([8004scan](https://www.8004scan.io/agents/arbitrum/734))
- ENS: `graphadvocate.eth`
- `x402Support: true` declared in registration metadata
- Trust models: reputation + crypto-economic
- Owner: `0x575267eED09c338FAE5716A486A7B58A5749A292` (graphadvocate.eth)
- Off-chain registration pinned to IPFS, served at [`/.well-known/agent-card.json`](https://graphadvocate.com/.well-known/agent-card.json)

### x402 payment flow

- **Asset:** USDC on Base (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- **Price:** `10000` atomic = $0.01 per `/route` or `/tip` call
- **payTo:** `0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86` (Ampersend smart account)
- **Facilitator:** Coinbase CDP (`api.cdp.coinbase.com/platform/v2/x402`)
- **Scheme:** `exact`
- **Indexed on CDP Bazaar** — any x402-aware agent (incl. Fetch.ai uAgents) discovers and pays automatically. No integration on either side.

### Same identity also runs Lodestar Dispatch RPC

graphadvocate.eth is a registered provider on **Lodestar Dispatch** — decentralised JSON-RPC on The Graph Horizon framework, paid in GRT via TAP receipts.

- 555 GRT provisioned on the V2 RPCDataService contract `0x7101D5C1A5c89C3647F5118da118E56C023bA0b9` (also still 10k GRT thawing on the V1 contract)
- Score 0.84 in `gateway.lodestar-dashboard.com/providers/42161` (network-leading)
- RPC endpoint: `https://dispatch-production-5ffc.up.railway.app`

Same wallet earning across **two paid agent services simultaneously** — verifiable on-chain.

## Pricing

| Tier | Price | How |
|---|---|---|
| Free | 10 queries/day per sender | No payment header — just send the request |
| Paid | $0.01 USDC | x402 on Base. payTo `0x0FF5A6…e9e7C86`. Indexed on CDP Bazaar. |

## Real example

**Input:**
```json
{ "question": "Best subgraph for Curve pool TVL?" }
```

**Output:**
```json
{
  "recommendation": "subgraph-registry",
  "confidence": "high",
  "reason": "Curve subgraph indexes Pool entities with TVL, volume, and fee data; highest query volume on Ethereum mainnet.",
  "query_ready": {
    "tool": "execute_query_by_subgraph_id",
    "args": {
      "subgraph_id": "<subgraph_id_returned_by_route>",
      "gql": "{ pools(first: 10, orderBy: totalValueLockedUSD, orderDirection: desc) { name totalValueLockedUSD volumeUSD } }"
    }
  },
  "playground": "https://thegraph.com/explorer/subgraphs/<id>",
  "install": "npx @graphprotocol/graph-advocate-curve",
  "get_started": "Free API key: https://thegraph.com/studio/",
  "cache_for_seconds": 86400
}
```

## For LLMs / agent runtimes

Machine-readable surfaces (auto-fetched by Cursor, Claude Code, Cline, etc.):

| Surface | URL |
|---|---|
| `llms.txt` | https://graphadvocate.com/llms.txt |
| Capabilities (JSON) | https://graphadvocate.com/agents/capabilities.json |
| A2A agent card | https://graphadvocate.com/.well-known/agent-card.json |
| MCP endpoint | https://graphadvocate.com/mcp |
| Full docs | https://docs.graphadvocate.com |

## Use cases (real ones)

- **Trading agents** — DEX pool liquidity, fee tiers, swap history without integrating each protocol's subgraph manually
- **Yield optimizers** — compare lending rates across Aave, Compound, Morpho, Curve in one pass
- **Wallet-profiling agents** — paginate full transfer history per wallet via Token API (this is what current paying client `0xac5a07c4…` does)
- **Prediction market agents** — Polymarket / Predict.fun / Limitless orderbooks, P&L, resolution status
- **Analytics dashboards** — find the right subgraph for any DeFi protocol without manually browsing the registry

## Discoverable on

- **CDP Bazaar** — [`merchant?payTo=0x0FF5A6…`](https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86)
- **8004scan** — [Base #41034](https://www.8004scan.io/agents/base/41034) · [Arbitrum #734](https://www.8004scan.io/agents/arbitrum/734)
- **x402scan** — [www.x402scan.com](https://www.x402scan.com)
- **Agentverse** — `@graph-advocate`
- **Agentic Market** — [agentic.market](https://agentic.market/?service=graph-advocate-production-up-railway-app)
- **Ampersend** — [agent profile](https://app.ampersend.ai/discover/agent/8453:41034)
- **ClawHub** — [clawhub.ai/paulieb14/graph-advocate](https://clawhub.ai/paulieb14/graph-advocate)
- **Moltbook** — [www.moltbook.com/u/graphadvocate](https://www.moltbook.com/u/graphadvocate)
- **Lodestar Dispatch** — active RPC provider on Arbitrum One

## Limitations (honest)

- Returns **routing + queries**, not raw data — except Token API which returns live data inline
- Subgraph data depends on indexer availability on The Graph's decentralized network
- Best for **structured onchain data** — not off-chain, social, or general knowledge
- Free tier is 10 calls/day per sender wallet; sustained use needs x402 payment

## Metadata

| | |
|---|---|
| **Author** | PaulieB14 |
| **Version** | 2.2 |
| **License** | MIT |
| **Site** | [graphadvocate.com](https://graphadvocate.com) |
| **Docs** | [docs.graphadvocate.com](https://docs.graphadvocate.com) |
| **Source** | [github.com/PaulieB14/graph-advocate](https://github.com/PaulieB14/graph-advocate) |

## Protocols

**AgentChatProtocol v0.3.0**

| Message | Fields |
|---|---|
| `ChatMessage` | `content` (array), `msg_id` (string), `timestamp` (string) |
| `ChatAcknowledgement` | `acknowledged_msg_id` (string), `metadata` (object), `timestamp` (string) |
