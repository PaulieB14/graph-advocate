# graph-advocate-mcp

Ask any blockchain data question in plain English, from inside your agent.

Graph Advocate routes a question to the right service across **15,500+ subgraphs on 20+ chains** — Token API (EVM/Solana/TON), Aave, Uniswap, ENS, Polymarket, Hyperliquid, ERC-8004 agent discovery — and returns a ready-to-run query, plus the live rows when the answer carries a runnable one.

## Install

```bash
npx graph-advocate-mcp
```

Claude Desktop / Claude Code (`claude_desktop_config.json` or `.mcp.json`):

```json
{
  "mcpServers": {
    "graph-advocate": {
      "command": "npx",
      "args": ["-y", "graph-advocate-mcp"],
      "env": { "GRAPH_ADVOCATE_SENDER": "0xYourWallet" }
    }
  }
}
```

## Tools

| Tool | Cost | What it does |
|---|---|---|
| `route_data_request` | $0.01 | Plain-English question → the right service, a runnable query, and live rows where available |
| `polymarket_trader_score` | $0.01 | Skill score + classification for a Polymarket wallet |
| `hyperliquid_trader_score` | $0.02 | Skill score for a Hyperliquid perps trader |
| `preflight_price` | free | Read any endpoint's 402 — price, asset, network, payTo — without paying |
| `check_quota` | free | Free daily quota remaining on the A2A endpoint |

## This package holds no private key

That is deliberate. A paid tool returns its 402 challenge as structured data — price, asset, network, `payTo`, and the exact body to send again — and **your** wallet settles it: Claude Code's x402 skill, any x402 SDK, or a human. Shipping a signing key inside a package people `npx` is a liability no amount of convenience pays for.

```json
{
  "status": "payment_required",
  "price_usdc": "$0.02",
  "amount_base_units": "20000",
  "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  "network": "eip155:8453",
  "pay_to": "0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86",
  "endpoint": "https://graphadvocate.com/polymarket/screen",
  "retry_body": { "condition_id": "0x…" },
  "how_to_pay": "POST retry_body to endpoint again with an x402 `X-PAYMENT` header…"
}
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GRAPH_ADVOCATE_URL` | `https://graphadvocate.com` | Override for a self-hosted instance |
| `GRAPH_ADVOCATE_SENDER` | *(unset)* | Your EVM wallet, sent as the identified sender |
| `GRAPH_ADVOCATE_TIMEOUT_MS` | `60000` | Per-request timeout |

## One thing worth knowing about the free tier

The daily free allowance applies to Graph Advocate's **A2A** endpoint, not to the HTTP `/route` path this package calls. `check_quota` reporting `remaining_today: 3` does **not** make the next `route_data_request` free — that one is charged every call. The tool descriptions say so too; this note exists because the older `/quota` response implied otherwise.

## Links

- Service: <https://graphadvocate.com>
- Skill (ClawHub): `@paulieb14/graph-advocate`
- Source: <https://github.com/PaulieB14/graph-advocate>

MIT.
