# An agent can now go from question to onchain data in one round-trip — no API key, no signup

Two pieces of plumbing landed in the same week, and together they change what a generic AI agent can do with The Graph.

Until now, an agent that wanted to use a subgraph had to clear two human-shaped gates:

1. **Discovery.** Out of 15,500+ deployed subgraphs, which one actually answers "Aave V3 liquidations on Arbitrum"? You had to read READMEs, compare query volumes, eyeball schemas. No agent does this well.
2. **Payment.** Every gateway URL needs `gateway.thegraph.com/api/{API_KEY}/...`. That key is bound to a human-signed-up account on a paid plan. Agents don't sign up for paid plans.

Both gates closed agents out of a 15K-subgraph dataset that should have been the most agent-friendly thing on chain.

As of 2026-05-08, both are gone.

## What landed

**The Graph's x402 gateway is live in production.** `gateway.thegraph.com/api/x402/subgraphs/id/{id}` now returns a real `HTTP 402` challenge instead of an "auth error: malformed API key" 200. Confirmed in [edgeandnode/gateway#1188](https://github.com/edgeandnode/gateway/issues/1188#issuecomment-4408459316) by tmigone, [documented officially](https://thegraph.com/docs/en/subgraphs/guides/x402-payments/), and verified by direct probe. The docs frame the use case plainly: x402 is for *"autonomous agents and short-lived processes that can't store long-term credentials"* and *"per-query workloads where pre-purchased credits don't fit the access pattern."* That's exactly the agent shape — and it's now first-class, not a hack.

**`subgraph-registry-mcp` v0.5.0 ships hash-pinned discovery.** The same MCP server that's been classifying all 15K subgraphs by domain/network/protocol-type now verifies the registry SQLite blob against a SHA-256 pinned in the npm package — refuses to load if the GitHub-hosted file was tampered or swapped. That removes the supply-chain "but how do I trust the registry?" objection.

You can use either piece on its own. Used together they collapse the agent workflow from five steps to two.

## The combined workflow

```
Agent: "Best subgraph for Uniswap V3 on Arbitrum?"

Step 1 — discovery (no key, no payment):
  call subgraph-registry-mcp.recommend_subgraph
  → returns id=HMuAwufqZ1YCRmzL2SfHTVkzZovC9VL2UAKhjvRqKiR1
    + reliability score + suggested entities

Step 2 — execute (no key, $0.01 USDC):
  POST gateway.thegraph.com/api/x402/subgraphs/id/HMuAwufqZ1...
       { query: "{ _meta { block { number } } }" }
  → 402 + payment-required header
  → client signs EIP-3009 transferWithAuthorization for $0.01 USDC on Base
  → re-POST with Payment-Signature header
  → 200 + GraphQL data
```

That's it. No API key. No signup form. No paid plan. The wallet does the auth.

## Live receipt

I ran exactly that flow against the gateway this afternoon, paying $0.01 USDC from a Base wallet, and got back:

```json
{ "_meta": { "block": { "number": 45743214, "timestamp": 1778275775 } } }
```

Real subgraph data, real onchain settlement, total wall-clock ~3 seconds. The settlement reference is in the response's `x-payment-response` header — auditable on Base.

From code, it's about as much ceremony as a normal `fetch`:

```ts
import { createGraphQuery } from '@graphprotocol/client-x402'

const query = createGraphQuery({
  endpoint: 'https://gateway.thegraph.com/api/x402/subgraphs/id/HMuAwufqZ1YCRmzL2SfHTVkzZovC9VL2UAKhjvRqKiR1',
  chain: 'base',
})
const result = await query('{ tokens(first: 5) { symbol } }')
```

The client handles the 402 → sign → resend dance. Your code only sees the data.

## Two gotchas worth knowing before you build

**Use the scoped npm name.** `@graphprotocol/client-x402`, not the old unscoped `graphclient-x402`. The old name still resolves on npm and will silently misbehave; tmigone called this out specifically.

**The gateway's auto-served SKILLS.md has a bug.** Fix is in [edgeandnode/gateway#1192](https://github.com/edgeandnode/gateway/pull/1192), not yet deployed. If your agent reads SKILLS.md from the gateway to discover capabilities, the metadata is wrong until that PR ships. Pull from the canonical source instead.

## What this actually unlocks

Pay-per-query is the foundation, not the product. The interesting layer is what you build on top of it:

- An autonomous wallet-profiling agent can query 50 protocols' subgraphs in a session for ~$0.50 — no procurement, no key rotation, no monthly minimums.
- A trading agent doing pre-trade research can pay only for the queries it actually runs, not for a 100K/month plan it doesn't use.
- Agent-priced products (mine: `/polymarket/score` at $0.02, `/hyperliquid/vault` at $0.10) become composable — the upstream subgraph cost is now itself x402, so margins are calculable end-to-end.

The pattern matters more than any single endpoint. Agents that operate on metered USDC — discovery free, execution paid — are a different shape of consumer than humans on monthly plans, and the infrastructure for them is now actually here.

## When NOT to use x402

The docs are upfront about this and so should you be: *"For sustained, high-volume application use, the existing API-key flow remains the recommended path."* If you're a hosted dapp serving millions of queries/month from a known account, an API key is still the right shape — bulk pricing, no per-call signing overhead, established billing flow. x402 is for the agent-shaped slice of the workload, not a replacement for the human-shaped slice.

## What's still missing (honest closer)

Three things to flag before someone builds against the wrong assumption:

- **Testnet endpoints.** The documented `testnet.gateway.thegraph.com` host doesn't resolve as of this writing. If you need a testnet flow, you're waiting.
- **Subscriptions and streaming.** x402 is per-request. Long-poll subgraphs and substreams aren't a fit yet.
- **Discoverability of x402-priced subgraphs vs. metered ones.** Right now the gateway accepts x402 against any subgraph ID, but there's no manifest telling agents *which* subgraphs are priced. Coming, but not yet.

None of those block the basic loop. They just constrain what you can build first.

## Further reading

- [Official x402 docs on The Graph](https://thegraph.com/docs/en/subgraphs/guides/x402-payments/) — endpoints, USDC token addresses for mainnet and testnet, three SDK options (CLI / programmatic / typed), env vars
- [`@graphprotocol/client-x402` on npm](https://www.npmjs.com/package/@graphprotocol/client-x402)
- [`subgraph-registry-mcp` on npm](https://www.npmjs.com/package/subgraph-registry-mcp)
- [x402 protocol spec](https://www.x402.org)

---

If you ship something against this — either side, registry or gateway — drop me the link. The combo is what makes both ecosystems more useful, and the more agent-builders kick the tires this week, the faster the gotchas above get fixed.

— [@PaulieB14](https://x.com/PaulieB14), operator of [graphadvocate.com](https://graphadvocate.com) (ERC-8004 #734) and [subgraph-registry-mcp](https://www.npmjs.com/package/subgraph-registry-mcp)
