# /predmarket/spread launch — status report (2026-06-14)

One-hour autonomous traction push. All commits live on `main`; Railway / Mintlify / ClawHub deployed.

## What shipped

| Surface | Status | Note |
|---|---|---|
| `/predmarket/spread` endpoint | ✅ Live | $0.05, 17th paid skill |
| 402-body enrichment shim | ✅ Live | every paid endpoint now returns `output_example` |
| Docs (`docs.graphadvocate.com/predmarket`) | ✅ Live | Mintlify auto-deployed |
| ClawHub listing | ✅ v2.7.0 published | `clawhub.ai/paulieb14/graph-advocate` |
| README endpoint table | ✅ Updated | `/predmarket/spread` row added |
| Agent-card | ✅ 17 skills | `predmarket_spread` registered |
| OpenAPI spec | ✅ /predmarket/spread in paths | machine-readable |

## Outreach run

Two scripts (`scripts/oneoff_predmarket_launch_outreach.py` + `_expanded.py`) — 16 total target endpoints. Each call carries an `X-About` HTTP header announcing the new endpoint to operator access logs.

**Results:** 14/16 returned 2xx (2 SSL/route errors). 4 confirmed on-chain settlements:
- `blockrun.ai/api/v1/pm/polymarket/markets` (direct adjacency — they index Polymarket+Limitless+Kalshi)
- `blockrun.ai/api/v1/pm/polymarket/activity`
- `orbisapi.com/proxy/hyre-agent`
- `surplusintelligence.ai/.../chat/completions` (settled higher than $0.001 — likely per-token billed)

**Operators now have GA's hot wallet in their logs with the X-About announcing `/predmarket/spread`:**
blockrun, orbisapi, surplusintelligence, x402station, ottoai (kol-sentiment / yield-markets / mega-report / hyperliquid-market / funding-rates / crypto-news), coingecko (`x402/onchain/search/pools`).

## Spend

| | |
|---|---|
| **Starting USDC** | $0.137 |
| **Ending USDC** | $0.005 |
| **Spent** | $0.132 |

Higher than the $0.05 target. The surplusintelligence inference call appears to have settled per-token rather than at the 402-challenge minimum. Recommend topping up hot wallet to ~$0.50 before next outreach batch.

**Hot wallet:** `0xe121e3a8611E1f44f7cC52892eE1117fdDC8F734`

## ERC-8004 tokenURI refresh — ready, needs your key

Current on-chain tokenURI on Arb #734 + Base #41034 points to `Qm…tWWe` (2026-05-22) which is missing kalshi + predmarket + cross-venue spread.

I baked a new registration JSON (19 a2aSkills, updated description) and pinned to Pinata:

**New CID:** `QmfKtSrPYgMvUn39bcN44Lexd3xnH69HgC7ckA4S8SeL3r`

When you're back, run (~$0.01 gas):

```bash
export PK_OWNER=<graphadvocate.eth PK>
./scripts/update_erc8004_tokenuri_2026-06-14.sh
```

That calls `setAgentURI` on both chains. 8004scan sweep refreshes 30-60 min later. Will surface the new endpoint to ERC-8004 registry consumers (Agentverse, 8004scan, AI agent discovery).

## Discovery surfaces — what auto-syncs vs manual

| Surface | Sync mode | Status |
|---|---|---|
| CDP Bazaar | auto via 402 challenges | will pick up `/predmarket/spread` on next crawl |
| x402scan | auto-crawl | will pick up |
| Agentic Market | auto via x402 bazaar | should pick up after CDP refresh |
| Agentverse | manual / on-chain ERC-8004 | refreshes after tokenURI update |
| Ampersend | manual add (E&N team) | unchanged — needs Paul to ping E&N |
| ClawHub | explicit publish | ✅ done (v2.7.0) |
| 8004scan | reads ERC-8004 tokenURI | refreshes after tokenURI update |

## Tweet — three drafts in `docs/TWEET_PREDMARKET_LAUNCH.md`

Pick one and post. Recommended: Option A (JOIN angle, concise). Option C (example-led) is best if you want the tweet itself to act as a free 402 preview.

## What's left for you

1. **Run `scripts/update_erc8004_tokenuri_2026-06-14.sh`** with `PK_OWNER` set (refreshes on-chain pointer)
2. **Post a tweet** — pick one from `docs/TWEET_PREDMARKET_LAUNCH.md`
3. **Ping Ampersend / E&N team** to add `/predmarket/spread` to their catalog (manual-add surface)
4. **Top up hot wallet** to ~$0.50 USDC if you want more outreach runs
5. **Post in HexNest "prediction-market reasoning" room** about the new endpoint (highest direct-agent audience; I didn't have an A2A endpoint to send from)

## Notable: still zero organic traffic

Dashboard recent-activity feed unchanged from earlier (last item 16:31 UTC); zero hits on `/predmarket/spread` yet. Expected — discovery surfaces refresh on their own schedules (CDP every few hours, x402scan daily). The outreach gives operators a reason to investigate; the tweet + Ampersend add will close the loop.

## Commits in this hour

- `03d879a` feat: /predmarket/spread paid endpoint
- `03a9c69` 402: enrich response body with output_example
- `ebd7418` clawhub: bump to v2.7.0
- `ea740db` docs: add /predmarket/spread Mintlify page
- `edf0425` launch: outreach scripts + README + tweet drafts
- `00389e4` erc8004: refresh registration JSON + setAgentURI runbook
