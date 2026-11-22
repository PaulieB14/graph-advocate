# Graph Advocate

<div align="center">

<img src="static/graphadvocate.png" alt="Graph Advocate" width="160" />

**Onchain data router for [The Graph](https://thegraph.com)**

Ask a blockchain data question in plain English. Get live rows and the working GraphQL or REST query.

[![CDP Bazaar](https://img.shields.io/badge/CDP%20Bazaar-indexed-00D4AA)](https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86)
[![x402scan](https://img.shields.io/badge/x402scan-listed-blue)](https://www.x402scan.com)
[![ERC-8004](https://img.shields.io/badge/ERC--8004-%2341034-purple)](https://www.8004scan.io/agents/base/41034)

**[Docs](https://docs.graphadvocate.com)** · [Live site](https://graphadvocate.com) · [Dashboard](https://graphadvocate.com/dashboard) · [Chat](https://graphadvocate.com/chat) · [Agent card](https://graphadvocate.com/.well-known/agent-card.json) · [llms.txt](https://graphadvocate.com/llms.txt)

`npx skills add PaulieB14/graph-advocate` · `npx -y graph-advocate-mcp`

</div>

## Try it

Start with the free live preview — no key, no wallet, no signup:

```bash
curl -s "https://graphadvocate.com/preview?q=top+uniswap+v3+pools+by+volume"
```

That returns the top 3 live rows. For the full list, other chains, filters, or a follow-up, `POST /route` is **$0.01 USDC on Base** via [x402](https://www.x402.org/). Unpaid calls return HTTP 402 with the same free top-3 plus `how_to_pay` snippets (x402-fetch, Python, curl, MCP). A browser opening `/route` shows those snippets; the status stays 402 so agents still see a payment challenge.

```bash
# Unpaid call — 402 + free preview + how_to_pay
curl -s -X POST https://graphadvocate.com/route \
  -H "Content-Type: application/json" \
  -d '{"request":"top Uniswap V3 pools on Base"}'
```

A paid response includes `result` (formatted rows), `executed.data`, and `query_ready`.

## Pricing

All paid calls settle in USDC on Base (`eip155:8453`) through the Coinbase CDP facilitator. No API key and no signup.

| Path | Price | What you get |
|------|-------|----------------|
| `GET /preview?q=...` | Free | Live top-3 rows (plain 200) |
| `POST /` (A2A, `metadata.sender` = your 0x wallet) | 3 full answers/day, then $0.01 | Routed answer + live rows |
| `POST /route` | $0.01 every call | Live rows + the query that produced them |
| `POST /ask` | $0.05 | Natural-language Q&A over x402 settlements on Base |
| `/chat` | Free | The subgraph and GraphQL to run yourself (not the data) |
| Other paid endpoints | $0.01–$0.10 | Hyperliquid, Polymarket, Kalshi, Uniswap, and agent-score APIs — see [docs](https://docs.graphadvocate.com) or `/llms.txt` |

Pay with any x402 client (`x402-fetch`, `x402` for Python). The 402 body includes copy-paste snippets.

## Protocols

| Protocol | How to call |
|----------|-------------|
| **HTTP** | `GET /preview`, `POST /route` |
| **A2A** | `POST /` — JSON-RPC 2.0 `message/send` |
| **MCP** | `POST /mcp` (streamable HTTP) or `npx -y graph-advocate-mcp` |
| **Skill** | `npx skills add PaulieB14/graph-advocate` |
| **x402** | USDC on Base; payTo is in the 402 `payTo` field, not the identity wallet |
| **ERC-8004** | Agent #41034 on Base, #734 on Arbitrum · `graphadvocate.eth` |

Identity wallet (ERC-8004 / ENS): `0x575267eED09c338FAE5716A486A7B58A5749A292`. Payments go to the `payTo` in the 402 challenge, never to that identity address.

## What it routes

Plain-English questions across 15,500+ subgraphs and Token API / Substreams: Uniswap, Aave, Compound, ENS, Polymarket, Hyperliquid, wallet balances, holders, swaps, and more. Also protocol MCP packages (Aave, Uniswap, Polymarket, lending, Limitless, Predict.fun).

## Repo layout

Runtime stays at the repo root — Railway starts `python a2a_server.py` (site) and `python outreach.py` (daily outreach cron). Do not move those entrypoints.

| Path | Role |
|------|------|
| `a2a_server.py`, `advocate.py` | HTTP / A2A / x402 server and router |
| `*_intel.py`, `kalshi.py`, `agent_score.py` | Paid intelligence endpoints |
| `mcp_server.py`, `mcp/` | Python MCP server and the `graph-advocate-mcp` npm package |
| `outreach.py`, `x402_outreach.py` | Inbound conversion cron and outbound x402 client |
| `docs/` | Mintlify docs (published to [docs.graphadvocate.com](https://docs.graphadvocate.com) on push to `main`) |
| `skills/`, `plugins/`, `openclaw-skill/` | Skill listings (`npx skills add`) |
| `scripts/` | Operator tools (self-pay, preflight, audits) — not imported by the server |
| `notes/` | Internal launch logs and drafts, not the public docs site |
| `test_*.py` | Test suite: `python -m pytest -q test_*.py` |

## Development

```bash
git clone git@github.com:PaulieB14/graph-advocate.git && cd graph-advocate
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY for local routing
python3 a2a_server.py
python -m pytest -q test_*.py
```

Production is Railway (auto-deploy on push to `main`). Required env: `ANTHROPIC_API_KEY`, `CDP_API_KEY_ID`, `CDP_API_KEY_SECRET`, `GRAPH_API_KEY`.

## License

MIT
