# agentic.market × ERC-8004 × x402 — Dune Dashboard Kit

Everything needed to publish a public Dune dashboard for the x402 ecosystem on Base, with agentic.market as the curated lens and ERC-8004 agent identity as the trust layer.

**Strategically unique:** nobody else joins x402 on-chain payments to ERC-8004 agent identity. This dashboard is the first.

---

## Data files (upload these to Dune as CSV datasets)

| File | Rows | Source | Refresh |
|---|---|---|---|
| `bazaar_merchants.csv` | 50,423 services | CDP Bazaar `/v2/x402/discovery/resources` | weekly |
| `agentic_market_services.csv` | 50 curated services | `api.agentic.market/v1/services` | weekly |
| `agent0_base_agents.csv` | 53,333 Base ERC-8004 agents | Agent0 subgraph `QmcLwgyKn3RnyhkkSwLYscP9dL1Fc6omvfC9bFRgcK1e7u` | weekly |
| `facilitators.csv` | 29 facilitators / 112 addresses | x402scan repo (`Merit-Systems/x402scan`) | as-needed |

---

## Step-by-step publish

### 1. Upload the 4 CSVs to Dune

Dune → **Datasets** → **Upload CSV**. Suggested table names (used in `queries.sql`):

```
dune.<your_handle>.dataset_bazaar
dune.<your_handle>.dataset_amarket
dune.<your_handle>.dataset_agents
dune.<your_handle>.dataset_facilitators
```

Replace `<your_handle>` with your Dune username (e.g. `paulieb`).

### 2. Find-and-replace placeholders in `queries.sql`

The SQL has `<your_handle>` placeholders. Search-and-replace once.

### 3. Set Dune Parameters on the dashboard

Create two parameters at the dashboard level (Dune → "Add parameter"):

- `cdp_facilitator` → for single-facilitator mode (default: Coinbase, see `facilitators.csv` for the address)
- `timeframe_days` → default `30`

For **multi-facilitator** mode (the full x402 economy, not just Coinbase), use the `dataset_facilitators` JOIN pattern shown in the SQL comments.

### 4. Build the dashboard panels

Recommended layout (10 panels matching `queries.sql` order):

| Position | Panel | Query |
|---|---|---|
| Top row (hero tiles) | tx_count · volume · merchants · buyers · median price | `1. HERO STATS` |
| Time series | Daily volume + tx count | `2. DAILY VOLUME` |
| Big table | Top merchants enriched | `3. TOP MERCHANTS` |
| Donut chart | Agent vs anon share | `4. AGENT SHARE OF ECONOMY` |
| Bar chart | By category | `5. CATEGORY BREAKDOWN` |
| Table | New service launches | `6. NEW SERVICE LAUNCH RADAR` |
| Bar chart | Pricing distribution | `7. PRICING DISTRIBUTION` |
| Table | Top earning agents | `8. AGENT LEADERBOARD` |
| Table | Outreach list | `9. UNLISTED EARNERS` |
| Counters | Catalog × activity matrix | `10. CATALOG vs ACTIVITY` |

### 5. Publish + share

Dune → "Publish" → toggle public → grab the URL.

---

## Key facilitator addresses (from `facilitators.csv`)

The 5 biggest by transaction volume (per x402scan, 2026-05-23):

| Facilitator | Tx count | Volume | Wallet count |
|---|---|---|---|
| **Coinbase** | 82.4M | $27.78M | 25 addresses |
| **PayAI** | 23.1M | $4.33M | 15 addresses |
| **Daydreams** | 11.8M | $2.76M | 2 addresses |
| **Heurist** | 7.96M | $30.06K | 9 addresses |
| **Virtuals Protocol** | 1.99M | $4.34M | 1 address |

**For your dashboard**: filter `from = <facilitator_address>` to catch a specific facilitator, OR JOIN `erc20_base.evt_transfer."from" IN (SELECT address FROM dataset_facilitators WHERE chains LIKE '%base%')` for the full Base x402 economy.

---

## How the ERC-8004 join works

Most agents have `agent_wallet = null` (defaulted to owner). The Agent0 subgraph indexes both. The JOIN logic:

```sql
LEFT JOIN dataset_agents ag
       ON LOWER(ag.owner)        = merchant_pay_to
       OR LOWER(ag.agent_wallet) = merchant_pay_to
```

This catches:
- Agents that left `agent_wallet` defaulted (owner == payment recipient)
- Agents that explicitly set `agent_wallet` to a separate x402 payTo (like Graph Advocate Base #41034)

---

## Refresh / regenerate the datasets

Re-run the data pulls:

```bash
cd /Users/paulbarba/graph-advocate/dune

# Bazaar (50,423 services, ~2 min)
python3 build_bazaar.py    # paginates CDP /discovery/resources

# agentic.market (50 services, instant)
python3 build_amarket.py   # GET api.agentic.market/v1/services

# Agent0 subgraph (53,333 agents, ~30s)
python3 build_agents.py    # paginates via Graph Network

# Facilitators (re-pull from Merit-Systems/x402scan)
python3 build_facilitators.py
```

For a "live" dashboard, schedule these as a daily cron + upload to Dune via their `INSERT` API (requires Dune Plus).

---

## Why this matters

| | x402scan (paid) | Your free Dune dashboard |
|---|---|---|
| Volume tracking | ✅ via paid API | ✅ free on-chain |
| Facilitator breakdown | ✅ via paid API | ✅ free |
| Pricing distribution | ✅ inferred | ✅ direct |
| **agentic.market category enrichment** | ❌ | ✅ first dashboard with this |
| **ERC-8004 agent join** | ❌ | ✅ **completely new** |
| **Public/free** | ❌ pay per query | ✅ |

The ERC-8004 join is the moat. Once published, it becomes the canonical "which x402 earners are accountable agents" view.

---

## Strategic next steps

After v1 ships:

1. **Wire as a `/x402/dashboard/data` JSON endpoint** on graphadvocate.com — agents can poll the same data live
2. **Add the "earn rank per OASF skill domain"** view — what kinds of agent skills earn the most
3. **Add a "from agentic.market to ERC-8004"** flow — show which agentic.market services have NOT yet registered as agents (outreach list, drives ERC-8004 adoption)
4. **Cross-marketplace overlap** — same services on agentic.market + ampersend + x402station, with shared on-chain identity
