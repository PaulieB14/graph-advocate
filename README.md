# Graph Advocate

<div align="center">

<img src="static/graphadvocate.png" alt="Graph Advocate" width="160" />

**Onchain Data Routing Agent for [The Graph Protocol](https://thegraph.com)**

Ask a question about blockchain data. Get back the right subgraph, a ready-to-execute query, and an MCP install hint.

[![CDP Bazaar](https://img.shields.io/badge/CDP%20Bazaar-indexed-00D4AA)](https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86)
[![x402scan](https://img.shields.io/badge/x402scan-listed-blue)](https://www.x402scan.com)
[![ERC-8004](https://img.shields.io/badge/ERC--8004-%23734-purple)](https://www.8004scan.io/agents/arbitrum/734)

**[📚 Docs](https://docs.graphadvocate.com)** · [Live Dashboard](https://graphadvocate.com/dashboard) · [Chat](https://graphadvocate.com/chat) · [Agent Card](https://graphadvocate.com/.well-known/agent-card.json) · [llms.txt](https://graphadvocate.com/llms.txt) · [capabilities.json](https://graphadvocate.com/agents/capabilities.json)

**Discoverable on:** [Agentic Market](https://agentic.market/?service=graphadvocate-com) · [CDP Bazaar](https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86) · [Ampersend](https://app.ampersend.ai/discover/agent/8453:41034) · [Agentverse](https://agentverse.ai/agents/details/agent1qfa8f2kzanmt4zqg35gvgk5lpkjev52f75duhdyl3tj6s0nn26466yu5c7a/profile) · [x402scan](https://www.x402scan.com) · [ClawHub](https://clawhub.ai/paulieb14/graph-advocate) · [8004scan](https://www.8004scan.io/agents/base/41034)

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
| **Free tier** | 3 queries/day per agent (`POST /`, `POST /chat`, `POST /route`) |
| **Network** | Base (`eip155:8453`) |
| **Facilitator** | Coinbase CDP |
| **Verification** | `POST /admin/self-test-paid {"all": true}` — exercises every paid handler |

### Paid endpoint pricing

| Endpoint | Price | Returns |
|---|---|---|
| `POST /route` | $0.01 | Routed query + ready-to-run GraphQL |
| `POST /hyperliquid/score` | $0.02 | Derived skill metrics for an HL trader |
| `POST /hyperliquid/pnl` | $0.05 | Scores + open positions + recent activity |
| `POST /hyperliquid/screen` | $0.05 | Top N traders of a coin with per-trader skill scores (N capped at 10) |
| `POST /hyperliquid/vault` | $0.10 | Vault evaluator: leader skill + depositor concentration + redemption pressure |
| `POST /hyperliquid/risk` | $0.02 | Counterparty risk: liquidation rate + funding burn + outflow flag |
| `POST /hyperliquid/fills` | $0.02 | Recent fill stream for a coin with bid/ask flow summary (N capped at 10) |
| `POST /polymarket/pnl-quick` | $0.02 | Skill score + classification for a wallet |
| `POST /polymarket/pnl` | $0.05 | Full PnL: scores + per-position records |
| `POST /polymarket/screen` | $0.05 | Top wagerers on a market with ghost-fill risk (N capped at 10) |
| `POST /polymarket/risk` | $0.02 | Wallet-type detection + ghost-fill risk classification |
| `POST /kalshi/consensus-trend` | $0.05 | Kalshi consensus-probability slope + acceleration (uses Kalshi-unique forecast_history) |
| `POST /kalshi-polymarket/spread` | $0.05 | Cross-source arbitrage spread between Kalshi and Polymarket on a topic — JOIN passthrough APIs can't return |
| `POST /kalshi/sports-live-edge` | $0.05 | Live sports mispricing: play-by-play momentum vs market reaction; flags latency-arb windows |
| `POST /predmarket/spread` | $0.05 | **Polymarket ↔ Limitless cross-venue spread** on a topic — paired markets, per-pair yes-mid spread (bps), arbitrage direction. JOIN single-venue passthroughs can't return |

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

## Project structure

Flat module layout, grouped here by role. Web entrypoint is [`a2a_server.py`](a2a_server.py) (`python a2a_server.py`).

**Server & routing**
- [`a2a_server.py`](a2a_server.py) — A2A/x402 HTTP server: JSON-RPC 2.0, payments, dashboard, paid-endpoint wiring
- [`advocate.py`](advocate.py) — Core routing: keyword auto-search, Claude call, response parsing, SQLite logging
- [`mcp_server.py`](mcp_server.py) — MCP server (SSE transport)

**Paid intelligence endpoints** — derived signals, the x402 revenue surface
- [`hyperliquid_intel.py`](hyperliquid_intel.py) — Hyperliquid trader skill / risk / vault metrics
- [`polymarket_intel.py`](polymarket_intel.py) — Polymarket trader skill + ghost-fill risk
- [`kalshi.py`](kalshi.py) — Kalshi consensus-trend, sports-live-edge, Kalshi↔Polymarket spread
- [`limitless_intel.py`](limitless_intel.py) — Polymarket↔Limitless cross-venue spread
- [`uniswap_intel.py`](uniswap_intel.py) — Uniswap pre-trade / DeFi-spot intelligence
- [`agent_score.py`](agent_score.py) — 0–100 agent reputation score (ERC-8004 + on-chain + feedback)
- [`b20.py`](b20.py) — B20 native token-standard helpers (Base)

**Outreach** — outbound agent-to-agent
- [`outreach.py`](outreach.py) — Daily outbound outreach run
- [`x402_outreach.py`](x402_outreach.py) — Outbound x402 client (GA pays other agents)

**Dashboards & monitoring**
- [`dashboard.py`](dashboard.py) — Terminal dashboard (recommendation-log stats)
- [`generate_dashboard.py`](generate_dashboard.py) — Renders `dashboard.html` from the SQLite log
- [`x402_dashboard.py`](x402_dashboard.py) — x402 ecosystem dashboard data pipeline

**Examples & tests**
- [`a2a_client_example.py`](a2a_client_example.py) · [`example_usage.py`](example_usage.py) — Sample agents calling GA over A2A
- [`test_advocate_routing.py`](test_advocate_routing.py) — Routing test suite (`python3 test_advocate_routing.py`, 90 tests)

**Directories** — [`docs/`](docs/) Mintlify docs site · [`static/`](static/) assets · [`dune/`](dune/) Dune analysis exports & queries

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
