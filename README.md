# Graph Advocate

<div align="center">

<img src="static/graphadvocate.png" alt="Graph Advocate" width="160" />

**Onchain Data Routing Agent for [The Graph Protocol](https://thegraph.com)**

Ask a question about blockchain data. Get back the right subgraph, a ready-to-execute query, and an MCP install hint.

[![CDP Bazaar](https://img.shields.io/badge/CDP%20Bazaar-indexed-00D4AA)](https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86)
[![x402scan](https://img.shields.io/badge/x402scan-listed-blue)](https://www.x402scan.com)
[![ERC-8004](https://img.shields.io/badge/ERC--8004-%23734-purple)](https://www.8004scan.io/agents/arbitrum/734)

**[📚 Docs](https://docs.graphadvocate.com)** · [Live Dashboard](https://graphadvocate.com/dashboard) · [Chat](https://graphadvocate.com/chat) · [Agent Card](https://graphadvocate.com/.well-known/agent-card.json) · [llms.txt](https://graphadvocate.com/llms.txt) · [capabilities.json](https://graphadvocate.com/agents/capabilities.json)

**Discoverable on:** [Agentic Market](https://agentic.market/?service=graphadvocate-com) · [CDP Bazaar](https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86) · [Ampersend](https://app.ampersend.ai/discover/agent/8453:41034) · [Agentverse](https://agentverse.ai) · [x402scan](https://www.x402scan.com) · [ClawHub](https://clawhub.ai/paulieb14/graph-advocate) · [8004scan](https://www.8004scan.io/agents/base/41034)

> **For LLM tools (Cursor, Claude Code, etc.):** point at `https://graphadvocate.com/llms.txt` for auto-discovery of routing services and capabilities.

</div>

---

## What it does

Routes plain-English data requests to the right Graph Protocol service — Token API, Subgraph Registry, Substreams, or one of 8+ protocol-specific MCP packages (Aave, Polymarket, Uniswap, etc.). Every response includes a working query you can execute immediately.

Searches 15,500+ indexed subgraphs in real-time. Powered by Claude.

## x402 Payments

Accepts autonomous agent payments on **Base mainnet** via [x402](https://www.x402.org/). Verified and settled by the Coinbase CDP facilitator.

| | |
|---|---|
| **Free tier** | 10 queries/day per agent (`POST /`) |
| **Paid** | $0.01 USDC per query (`POST /route` with x402 payment) |
| **Network** | Base (`eip155:8453`) |
| **Facilitator** | Coinbase CDP |

```bash
# Try it
npx agentcash try https://graphadvocate.com
```

## Protocols

| Protocol | Identity |
|----------|----------|
| **A2A** | `POST /` — JSON-RPC 2.0 |
| **x402** | `POST /route` — pay-per-query on Base |
| **MCP** | `/mcp/sse` — SSE transport |
| **ERC-8004** | Agent #734 (Arbitrum) |
| **ENS** | `graphadvocate.eth` |

## Services

Routes to: **Token API** (balances, swaps, NFTs), **Subgraph Registry** (15,500+ protocols), **Substreams** (raw blocks), **graph-aave-mcp** (40 tools), **graph-polymarket-mcp** (31 tools), **graph-lending-mcp**, **graph-limitless-mcp**, **predictfun-mcp**, **8004scan** (agent discovery).

## Quick start

```bash
curl -X POST https://graphadvocate.com \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"role":"user","messageId":"1","parts":[{"kind":"text","text":"Top Aave V3 markets by TVL"}]}}}'
```

## Development

```bash
git clone git@github.com:PaulieB14/graph-advocate.git && cd graph-advocate
pip install -r requirements.txt
cp .env.example .env  # add ANTHROPIC_API_KEY
python3 a2a_server.py
```

## Deployment

Railway (auto-deploy on push). Requires: `ANTHROPIC_API_KEY`, `CDP_API_KEY_ID`, `CDP_API_KEY_SECRET`, `GRAPH_API_KEY`.

**Live:** https://graphadvocate.com

## License

MIT
