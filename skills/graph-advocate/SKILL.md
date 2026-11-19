---
name: graph-advocate
description: Answer onchain data questions with live rows from The Graph (Uniswap, Aave, Compound, ENS, Polymarket, Hyperliquid, token balances/holders/swaps, 15,500+ subgraphs). Try GET /preview free first, then pay $0.01 USDC on Base (x402) for the full answer + working GraphQL query. Use for DeFi/blockchain data lookups; not for sending transactions or general web search.
homepage: https://graphadvocate.com
---

# Graph Advocate

Plain-English onchain data question in, live rows + the exact GraphQL/REST query + its source subgraph out.
Service: `https://graphadvocate.com` (ERC-8004 agent #41034 on Base, `graphadvocate.eth`).

## When to use

- "Top Uniswap V3 pools on Base by volume", "largest Aave V3 markets on Arbitrum by TVL", "who owns vitalik.eth",
  "Compound V3 markets", Polymarket protocol stats, token balances / holders / swaps, "which subgraph indexes X".
- You need real numbers plus a query you can rerun yourself, not a guess.
- Not for: executing trades, signing anything other than the x402 payment, or non-blockchain questions.

## 1. Free first: GET /preview

No key, no wallet. Returns up to 3 live rows (when the topic has live coverage) plus the query and source.

```bash
curl -s "https://graphadvocate.com/preview?q=top%20Uniswap%20V3%20pools%20on%20Base%20by%20volume"
```

Read `live_preview.rows`, `live_preview.query`, `live_preview.source.subgraph_id`. If `live_preview` is `null`
the topic has no free live coverage; the paid call below still routes it.

## 2. Full answer: POST /route ($0.01 USDC on Base, x402)

```bash
curl -i -X POST https://graphadvocate.com/route -H 'content-type: application/json' \
  -d '{"request":"top Uniswap V3 pools on Base by volume"}'
# -> HTTP 402 with a PAYMENT-REQUIRED header (x402 v2, exact, eip155:8453 USDC, amount 10000 = $0.01)
#    plus a free live top-3 preview and copy-paste pay snippets in the body (`how_to_pay`)
```

Pay with any x402 v2 client and resend the same body. JavaScript:

```js
import { wrapFetchWithPaymentFromConfig } from "@x402/fetch";
import { ExactEvmScheme } from "@x402/evm";
import { privateKeyToAccount } from "viem/accounts";

const account = privateKeyToAccount(process.env.EVM_PRIVATE_KEY); // low-balance Base wallet with a little USDC; no ETH needed
const pay = wrapFetchWithPaymentFromConfig(fetch, {
  schemes: [{ network: "eip155:8453", client: new ExactEvmScheme(account) }],
});
const res = await pay("https://graphadvocate.com/route", {
  method: "POST", headers: { "content-type": "application/json" },
  body: JSON.stringify({ request: "top Uniswap V3 pools on Base by volume" }),
});
console.log(await res.json());
```

Python: `pip install 'x402[evm,httpx]' eth-account`, then `x402Client().register("eip155:8453", ExactEvmScheme(EthAccountSigner(Account.from_key(key))))`
and `x402HttpxClient(client).post(url, json={...})`.

The 200 response has `result` (up to 25 formatted rows, `row_count`, `query`, `source`, `indexed_block`),
`executed.data` (exact gateway values), and `query_ready` (the query to rerun on The Graph yourself).
Only sign a requirement for USDC on `eip155:8453` paid to `0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86`
with amount `10000`; refuse anything else.

## Other entry points

- **A2A** (JSON-RPC `message/send` at `https://graphadvocate.com/`, card at `/.well-known/agent-card.json`):
  a wallet address in `message.metadata.sender` gets 3 full answers/day free, then $0.01. No sender = paid from call 1.
- **MCP**: `npx -y graph-advocate-mcp` — tools `route_data_request` ($0.01 per call; returns the 402 for your wallet to settle),
  `preflight_price` and `check_quota` (free). The package holds no key.
- **/ask** ($0.05): natural-language Q&A over the x402 payments warehouse on Base (e.g. "top x402 recipients last 30 days").
  It is not a general onchain Q&A endpoint; use `/route` for protocol data.
- Specialist paid endpoints (Polymarket/Hyperliquid trader scores, Uniswap pre-trade checks, prediction-market spreads):
  listed with prices at `https://graphadvocate.com/.well-known/x402` and `https://graphadvocate.com/llms.txt`.

## Safety

Queries go to graphadvocate.com (operated by @paulieb14). Do not send secrets. Use a dedicated low-balance wallet
and cap per-call spend at $0.01 for `/route`.
