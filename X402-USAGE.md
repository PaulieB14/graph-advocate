# Graph Advocate — x402 Paying Customers

A live record of agents that have **paid Graph Advocate in USDC** via x402 to use its routing service. Updated as patterns emerge.

**Pricing:**
- `/route` — $0.01 per query (subgraph + Token API + MCP routing)
- `/tip` — $0.01 per call (free-form support)
- 10 free queries / sender / day before x402 gates kick in

**payTo:** `0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86` (Ampersend smart account)
**Network:** Base mainnet, USDC

---

## Active recurring customer

### Wallet A — `0xac5a07c4…2142d`

A loyal automated agent that uses Graph Advocate as part of a multi-service x402 pipeline. **Confirmed recurring across three sessions over ~27 days.**

| Metric | Value |
|--------|-------|
| First seen | 2026-04-02 |
| Last seen | 2026-04-29 |
| GA queries to date | 21 (3 sessions × 5–11 queries) |
| Cumulative spend on GA | $0.21 USDC |
| Lifetime x402 payments (all services) | 265 |
| Lifetime x402 spend (all services) | $3.40 USDC |
| Tx count on Base | 1 (uses smart-account / EIP-3009) |
| ENS / 8004 | none |

**Their x402 stack** — top services they pay (last 200 calls):

| Rank | Service | Calls | Spend |
|----:|---------|------:|------:|
| 1 | x402.twit.sh (Twitter API) | 95 | $0.92 |
| 2 | blockrun.ai (Polymarket / onchain activity) | 30 | $0.30 |
| **3** | **Graph Advocate** | **21** | **$0.21** |
| 4 | 0x2bb72231… | 16 | $0.04 |
| 5 | 0x66d7c2f9… | 10 | $0.05 |
| 6+ | 12 other services | ~28 total | ~$0.50 |

**Inferred use case: automated wallet profiling.** The pipeline pulls Twitter context (twit.sh) + onchain activity (blockrun.ai) + subgraph routing (GA), then queries the recommended subgraph for deeper data. Pattern repeats roughly weekly.

**Session log:**
- **2026-04-02 (first session):** Discovery — found GA via CDP Bazaar alongside Nansen, OneSource, Strale, Orbis (5 sellers in one morning).
- **2026-04-27 (second session):** 11 paid queries across morning + afternoon batches (`token-api` routing, paginated `eth_getTransfers` for target wallets, offsets 0/10/20/30/40).
- **2026-04-29 (third session):** 10 paid queries spread across ~3 hours (blocks 45322500–45324922).

**Why this profile matters:** Wallet A is the canonical "killer customer" persona for Graph Advocate. They use GA as a routing layer — not the end consumer of data, but a step in a larger automated workflow. Build/market around this pattern.

---

## Newly discovered (1 trial call)

### Wallet B — `0x15c3cdd6…bc2b`

A high-volume x402 aggregator that just discovered Graph Advocate today.

| Metric | Value |
|--------|-------|
| First x402 use ever | 2026-04-17 (12 days ago) |
| First GA call | 2026-04-29 17:22 UTC |
| GA queries to date | 1 ($0.01) |
| Lifetime x402 payments (all services) | **4,637** |
| Lifetime x402 spend (all services) | **$71.82 USDC** |
| Average | ~387 calls / day across 27 services |
| ENS / 8004 | none |

**Behavior pattern:** Their last 200 calls hit 27 distinct recipients with mostly ~11 calls each — looks like systematic crawling of x402 services rather than targeted use. Heavy users of `0x29322ea7…` (32 calls / $0.32, top recipient) and a long tail.

**Why this matters:** If GA converts B into a recurring user even at their own moderate per-service cadence (~10 calls/week), it'd more than double GA's organic revenue. They tried GA exactly once today — that's the moment a returning-customer hook would convert them.

---

## Aggregate stats

As of 2026-04-29:

- **Lifetime organic GA queries (excluding self-pays):** 22
- **Distinct paying wallets:** 2 (one recurring, one new today)
- **Cumulative organic revenue:** $0.22 USDC
- **Recurring rate:** 1 of 2 wallets has ≥3 sessions (50% return rate among first-time payers)
- **Self-pays / test wallets excluded:** `0xe121e3a8…F734` (GA hot wallet, 2× $0.001 bazaar-intel test) and `0xda664bc1…1bd0` (Paul's test wallet, ~4 historical calls)

---

## What this dataset is good for

1. **Persona research.** Wallet A's stack (twit.sh + blockrun.ai + GA + 14 others) is a real working composition — useful for anyone designing similar agent architectures.
2. **Routing heuristics.** GA's response logic could optimize for "wallet-profiling intent" (the pattern Wallet A repeats) vs "exploratory single-shot" (Wallet B's first-call shape).
3. **Bazaar / discovery validation.** Both wallets discovered GA without a tweet, without manual outreach — purely via CDP Bazaar indexing. The discovery layer works, slowly.

---

## Caveats

- All wallets here are anonymous EOAs. We have no off-chain identity. The patterns are inferred from their on-chain x402 traffic.
- Per-query content (the actual data questions they ask) is not stored long-term — only routing decisions and aggregate metrics. So we know *what* services they use, not *why*.
- Wallet B's "trial call" interpretation is speculative — could equally be a one-shot they don't need to repeat.

---

*Last updated: 2026-04-29 (after 3rd recurring session from Wallet A + first call from Wallet B).*
