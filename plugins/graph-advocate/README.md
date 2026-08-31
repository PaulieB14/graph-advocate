# Graph Advocate (Grok Build plugin)

Onchain data routing for [The Graph](https://thegraph.com). Grok talks to Graph Advocate over MCP; Graph Advocate routes the question to the right subgraph, Token API, Polymarket, Hyperliquid, x402, or ERC-8004 service.

Homepage: https://graphadvocate.com  
Repo: https://github.com/PaulieB14/graph-advocate  
License: MIT-0

## Install

```bash
grok plugin install PaulieB14/graph-advocate --path plugins/graph-advocate
```

Once listed on the [Grok plugin marketplace](https://github.com/xai-org/plugin-marketplace):

```bash
grok plugin install graph-advocate --trust
```

## What this plugin does

- Starts the public MCP package `graph-advocate-mcp` over stdio (`npx -y graph-advocate-mcp@2.11.1`).
- Ships a routing skill so Grok picks the right Graph Advocate tool.
- Does **not** hold a wallet or private key. Paid tools return a structured HTTP 402 (price, asset, network, `payTo`) so *your* wallet can settle x402.

### Tools

| Tool | Paid | What it does |
| --- | --- | --- |
| `route_data_request` | $0.01 | Route a natural-language onchain question |
| `polymarket_trader_score` | $0.01 | Polymarket trader reputation |
| `hyperliquid_trader_score` | $0.02 | Hyperliquid trader reputation |
| `preflight_price` | free | Quote a paid call before you pay |
| `check_quota` | free | Remaining quota for a wallet |

## Network endpoints

Default MCP target:

- `https://graphadvocate.com` (override with `GRAPH_ADVOCATE_URL`)

No other hosts are contacted by this plugin. The MCP process talks only to that URL.

## Credentials

None required.

Optional env (public values, not secrets):

- `GRAPH_ADVOCATE_URL` — MCP HTTP target. Default `https://graphadvocate.com`.
- `GRAPH_ADVOCATE_SENDER` — public `0x` wallet used as the x402 payer identity. Not a private key.
- `GRAPH_ADVOCATE_TIMEOUT_MS` — request timeout.

This package never ships, reads, or uses a private key, and it will not sign x402 payments.