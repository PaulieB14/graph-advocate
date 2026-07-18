# When "Six Indexers" Are One Operator: A Structural Observation from a Failed Query on The Graph

**Date:** 2026-06-11
**Author:** Paul Barba (Graph Advocate)
**Status:** Investigation, evidence-backed

---

## TL;DR

Staked Cloud is one of The Graph's largest and most transparent indexer operators. They publish their infrastructure URLs openly, and their on-chain identities are operationally legitimate — multi-identity setups are common and have legitimate reasons (key separation, blast-radius isolation, operational segmentation). This report is about a structural observation that emerges from that legitimate setup, not a critique of Staked.

Six independent operators failing identically at the same instant seemed worth a closer look. While debugging an unrelated query against the **Agent0 ERC-8004 Base Mainnet** subgraph, I noticed the gateway reported *"6 indexers at chainhead, all returning `BadResponse(400)`"*. Looking up those addresses in the Graph Network subgraph, they share a hostname pattern (`graph-indexer-{N}-arbi.prod-eks-ca-central-1.staked.cloud`) consistent with sequentially-indexed nodes inside a single AWS region / EKS cluster operated by Staked Cloud.

This exposes a gap between how the protocol counts indexer diversity and how diversity behaves operationally. When shared infrastructure has a problem, every sibling tends to exhibit the same failure simultaneously — as observed for Agent0 Base.

**By the numbers:**

- **11 distinct on-chain identities** registered under `staked.cloud` URLs (7 actively allocating, plus 4 dormant or duplicate)
- **~480M GRT self-staked** and **~136M GRT delegated** across the active 7
- **371 distinct subgraph deployments** carry at least one Staked sibling allocation
- **3 deployments** are fully covered by Staked siblings (6 of 6), and **27 deployments** by 5 siblings
- **8 of the top 25** Staked-concentrated deployments are currently returning `BadResponse(400)` from every Staked sibling (Agent0 Base + 7 others)
- **Staked is not unique**: four other operators run multi-identity fleets under shared apex hostnames (StakeSquid, P2P.org, Data Nexus, UpNode), though Staked is by far the largest

---

## A note on framing and terminology

A few words about what this is and isn't:

- This is **not a "Staked is malicious" finding.** Staked publishes their indexer URLs openly. Multi-identity operations on Ethereum mainnet and L2s are normal — operators commonly run separate addresses for key-separation, slashing blast-radius isolation, and operational segmentation. Staked's fleet currently provides the majority of chainhead coverage on 100+ deployments that would have thinner coverage otherwise.
- This is **not unique to Staked.** A URL-hostname survey across all 152 indexers with URLs registered in the Graph Network subgraph turns up four other operator clusters meeting a "3+ on-chain addresses under one apex hostname" threshold. Staked is the largest by an order of magnitude, but the pattern is industry-wide.
- I use the term **"sibling fleet" or "operator cluster"** rather than "sybil" throughout. "Sybil" in crypto carries a bad-faith connotation (an actor inflating identities to evade detection) that doesn't fit what's happening here. The on-chain count of indexers is real; it just isn't a clean proxy for operator diversity.
- The graph-node version diagnosis for the Agent0 failure is a **hypothesis** based on observation of symptoms. I have not directly confirmed the deployed graph-node version on `prod-eks-ca-central-1`. It is the most plausible explanation but remains unverified.
- I have **invited Staked Cloud and Edge & Node to respond** and will append any corrections, clarifications, or context they offer.

---

## The discovery

Querying Agent0 Base via the public gateway with the simplest possible request:

```graphql
{ _meta { block { number } } }
```

Returns:

```json
{
  "errors": [{
    "message": "bad indexers: {
      0x2b3c7d1ef5fdfc0557934019c531d3e70d6200ae: BadResponse(400),
      0x9af3fc811a66dbbca44acce94906d8743f9cf0d0: BadResponse(400),
      0xa6ff993e0f6253f1b7f55c873577a2f0f0ceb325: BadResponse(400),
      0xdc53e62df89fd07b31ed4ff886397b9e7ae4625e: BadResponse(400),
      0xe6de2325ef1aac1f058fae59d3c38a472f569846: BadResponse(400),
      0xe9e284277648fcdb09b8efc1832c73c09b5ecf59: BadResponse(400),
      0xf92f430dd8567b0d466358c79594ab58d919a6d4: Unavailable(too far behind)
    }"
  }]
}
```

**Positive control** — the same gateway, same API key, same minimal query against a different deployment (TellerV2, IPFS `Qmd1NEdWrzt5R7Kun3PLrciFB9sSsF7rkWyKBqFPy4r231`) returns:

```json
{"data":{"_meta":{"block":{"number":25298395}}}}
```

So the gateway and API key are healthy; the failure is specific to the Agent0 Base deployment.

Six indexers all returning `BadResponse(400)` on a request that should always succeed. Looking up their URLs in the Graph Network subgraph:

| Indexer address | URL |
|---|---|
| 0x2b3c…00ae | `graph-indexer-7-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0x9af3…f0d0 | `graph-indexer-12-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0xa6ff…b325 | `graph-indexer-6-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0xdc53…625e | `graph-indexer-13-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0xe6de…9846 | `graph-indexer-8-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0xe9e2…cf59 | `graph-indexer-0-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0xf92f…a6d4 | `graph-l2prod.ellipfra.com` *(separate operator, lagging — see footnote)* |

The hostname pattern is consistent: same operator domain, same region/cluster identifier (`prod-eks-ca-central-1`), numerically-indexed nodes. The `-arbi` segment indicates the L2 endpoint (these indexers operate on Arbitrum One); the load-determining subdomain is `prod-eks-ca-central-1`.

> *Footnote on Ellipfra:* Ellipfra is a separate operator currently flagged "too far behind" by the gateway. If Ellipfra catches up, this deployment would have one non-Staked chainhead indexer. Whether the lag is transient or structural is not investigated here.

The next question I asked was: *how many `staked.cloud` addresses are there in total?*

---

## Scale of the pattern

Searching the Graph Network subgraph for all indexers with `staked.cloud` URLs (not just the 6 from the error) returns **11 distinct on-chain addresses**.

For the purposes of this report, "active" means an address with nonzero stake and at least one Active allocation; "standby" means effectively zero stake and zero allocations; "duplicate" means a second on-chain address pointing at a URL slot already occupied by another address.

| URL slot | Status | On-chain address | Self-staked GRT | Delegated GRT |
|---|---|---|---:|---:|
| indexer-0 | active | 0xe9e2…cf59 | 8.9M | 133M |
| indexer-6 | active | 0xa6ff…b325 | 9.0M | 0 |
| indexer-6 | duplicate (0 stake) | 0x0df8…a2af | 0 | 0 |
| indexer-7 | active | 0x2b3c…00ae | 123.6M | 2.8K |
| indexer-8 | active | 0xe6de…9846 | 15.9M | 0 |
| indexer-9 | standby | 0xe912…c5d0 | ~320 | ~254 |
| indexer-10 | standby | 0xe48b…4720 | ~660 | 0 |
| indexer-11 | standby | 0xd981…77c6 | ~393 | 0 |
| indexer-12 | active | 0x9af3…f0d0 | 102.2M | 0 |
| indexer-13 | active | 0xdc53…625e | 100.7M | 0 |
| indexer-14 | active | 0x090f…3ed3 | 120.5M | 0 |

**11 distinct on-chain identities total, 7 of them actively allocating.** Total active self-stake: ~480M GRT. Total delegated: ~136M GRT.

The protocol's accounting treats these as 11 (or 7 active) separate stake-weighted identities. Operationally they share a domain, a region, and (by hostname inference) a Kubernetes cluster. The standbys and the indexer-6 duplicate carry effectively zero stake and contribute no meaningful routing weight; the active 7 are the load-bearing fleet.

> Gaps in the slot numbering (1–5 absent) likely indicate retired or non-Arb-region siblings — Staked may operate other regional clusters under different hostnames that didn't surface in the `staked.cloud` URL search. I haven't audited that.

---

## How many subgraphs is this concentrated on?

Pulled all Active allocations belonging to the 7 active Staked sibling addresses, using cursor-based pagination on `id_gt` to clear the 1000-row page cap.

- **2,136 total Active allocations** across the 7 active Staked addresses (across 3 pagination pages)
- **371 distinct subgraph deployments** carry at least one Staked sibling allocation

Distribution of "how many Staked siblings are allocated to a single subgraph deployment":

| Staked siblings on deployment | # of deployments |
|---:|---:|
| **6** (all active siblings) | **3** |
| 5 | 27 |
| 4 | 68 |
| 3 | 109 |
| 2 | 98 |
| 1 | 66 |

For the 3 deployments where all 6 active siblings allocate, Staked is plausibly the entire chainhead indexer set (the gateway error from Agent0 Base — a 4-sibling deployment — already shows zero non-Staked indexers reaching chainhead; concentration in the 6-tier should be at least as severe, though confirming "zero non-Staked indexers at chainhead" for any specific deployment requires a per-deployment allocation audit).

For the 27 deployments at 5 siblings, Staked is the dominant majority of the indexer set. For the 68 at 4 siblings, Staked is usually at least half. The tail (1–2 siblings per deployment) is where Staked contributes coverage without dominating it — that tail represents the bulk of the 371 deployments, and the value Staked provides as an infra-of-last-resort indexer is real there.

The pagination cap most plausibly truncates nothing now (3 pages fully drained), but if anything were missed it would be in the long tail of low-sibling-count deployments — the 6/5/4-sibling tier counts are robust.

### How "blast radius" is ranked

In the supporting `staked_impact_ranking.json` artifact, deployments are scored by:

> **blast radius = (count of Staked siblings on deployment) × (30-day query volume)**

This captures correlated-failure harm better than concentration ratio alone: a fully-monocultured but low-traffic subgraph is less impactful than a 4-of-6-Staked subgraph with millions of monthly queries. The metric isn't the only reasonable choice (signaled GRT × siblings would capture economic exposure; sibling count / total indexers would capture concentration), but it's what the table below is sorted by.

---

## High-traffic subgraphs in the affected set

Cross-referencing the 371 deployments with 30-day query volume from `get_deployment_30day_query_counts` (as of 2026-06-11):

| Subgraph | IPFS hash | 30-day queries | Staked siblings | Signaled GRT |
|---|---|---:|---:|---:|
| TellerV2 Mainnet | `Qmd1NE…r231` | 748,878 | 4 | 12,663 |
| harbor-marks | `QmTuAY…F5Li` | 542,305 | 5 | 2,430 |
| Balancer Avalanche V2 Beta | `QmNudb…2xsU` | 461,042 | 5 | 5,929 |
| CreatorBid | `QmcvEX…tNZm` | 342,176 | 4 | 45,618 |
| unlock-protocol-polygon | `QmVNvc…ydgC` | 302,537 | 5 | 2,945 |
| Marlin Oyster Arbitrum | `QmVtjb…2kkR` | 181,365 | 5 | 2,970 |
| kleros-display-gnosis | `QmUxvQ…DhEJ` | 148,671 | 5 | 2,974 |
| swapbase | `QmU2qy…aYw` | 135,118 | 5 | 9,539 |
| nftmarket-base | `QmVtya…RZky` | 118,566 | 4 | 4,961 |
| Agent0 Base ERC-8004 | `QmcLwg…1e7u` | (currently unqueryable) | 4 active alloc | n/a |

These aren't fringe subgraphs. Several million queries per month flow through deployments where Staked is the majority indexer.

> Category descriptors in earlier drafts (e.g., "DeFi lending", "AI creator economy") have been dropped here pending verification against each subgraph's manifest.

---

## The Agent0 case: combined diversity loss + version skew

The Agent0 Base failure is the joint effect of two conditions:

1. **Staked concentration on this deployment** — the gateway error enumerates 6 chainhead Staked siblings plus 1 lagging non-Staked indexer (Ellipfra). Every indexer the gateway considered at chainhead is operationally one fleet.
2. **A subgraph-specific incompatibility, most plausibly graph-node version skew** — the Agent0 schema uses `@aggregation` directives and `timeseries` entities (relatively new graph-node features). The uniform `BadResponse(400)` across all Staked siblings (returning *identical* errors at the same instant on a request that should always succeed) is consistent with the graph-node version deployed on `prod-eks-ca-central-1` not compiling queries against this schema shape.

I have *not* directly confirmed the deployed graph-node version on the Staked cluster, nor verified that no other root cause (indexer-service proxy errors, attestation-signing failures, storage-layer issues) could produce the same symptom. The version-skew explanation is the cleanest fit for the observation but remains a hypothesis until either Staked confirms or someone queries the `/version` endpoint on one of the indexer URLs.

Either condition alone would be survivable. The first means "if Staked has a problem here, this subgraph has a problem." The second means "Staked currently has a problem with this subgraph's schema." Together: total blackout.

### Important: privileged routes do **not** rescue this

An earlier draft of this report claimed the Agent0 subgraph was queryable via "privileged routes (e.g. Pinax)" while failing on the public gateway. **That is wrong.** Re-probing via the `mcp__subgraph__execute_query_by_ipfs_hash` tool returns the identical 6 Staked `BadResponse(400)` errors plus Ellipfra "too far behind". The MCP-Pinax route uses the same indexer-selection pool, so the failure is universal at the indexer layer — there is currently **no way to query this subgraph through Graph Network rails** regardless of gateway or API key. Workarounds would require direct indexer queries (not currently available), a hosted-service-style fallback, or waiting for a non-Staked indexer to catch up.

### Broader probe: is Agent0 the only failure?

I ran the same minimal `_meta` query against two probe sets to see whether the Agent0 pattern generalizes:

**Probe set A — 30 well-known subgraphs (Uniswap V2/V3 on Eth/OP/Polygon/Arb/Base, Aave V2/V3 across 5 networks, Compound V2/V3 on Eth/Polygon/Arb, ENS, Lido, Rocket Pool, Chainlink, Balancer V2 on 5 networks):**

- 24/30 returned `_meta` cleanly
- 5/30 returned "subgraph not found: no allocations" (an indexing-economics issue — no indexer has chosen to allocate — not a sibling-fleet issue)
- 1/30 returned a "bad indexers" message: **Uniswap V3 Base**. The failure shape is *different* from Agent0: 2 indexers (Pinax `Unavailable(too far behind)` + Ellipfra `BadResponse(no attestation: indexing_error)`), neither under `staked.cloud`, and heterogeneous errors. Not the same pattern.

So in a representative cross-section of mainstream subgraphs, Agent0-style monoculture failure does not reproduce.

**Probe set B — top 25 Staked-concentrated deployments by blast-radius score:**

- 18/25 returned `_meta` cleanly (block heights consistent with chainhead)
- **7/25 returned `BadResponse(400)` from the same Staked sibling cohort** — the same 6–7 sibling addresses (`0x090f7382`, `0x2b3c7d1e`, `0x9af3fc81`, `0xa6ff993e`, `0xdc53e62d`, `0xe6de2325`, `0xe9e28427`) returning identical 400s

Sample of the failures from probe set B:

| IPFS hash | Chainhead indexers | Failure summary |
|---|---:|---|
| `QmbK9eGn…RHGM` | 7 | 7/7 Staked siblings `BadResponse(400)` |
| `QmSb9nsh…QKH8` | 6 | 6/6 Staked siblings `BadResponse(400)` |
| `QmT6prve…fHKw1` | 7 | 7/7 Staked siblings `BadResponse(400)` |
| `QmPNd3Tv…Rzpn` | 7 | 7/7 Staked siblings `BadResponse(400)` |
| `QmZczegB…D8bk7` | 8 | 7 Staked siblings `BadResponse(400)` + 1 `Unavailable(no status)` |
| `QmfKdZab…cRtg` | 7 | 6 Staked siblings `BadResponse(400)` + 1 `Unavailable(too far behind)` |
| `QmUGayCr…r9Q4` | 7 | 7/7 Staked siblings `BadResponse(400)` |

**Important reframing:** Agent0 Base is not a unique snowflake. About 28% of the highest-blast-radius Staked-concentrated deployments are currently failing with the same signature. The failure mode scales with Staked sibling concentration — wherever Staked dominates the chainhead set, a fleet-wide condition silently breaks the deployment. The earlier draft's framing of Agent0 as a one-off was incorrect; this is a class of failure.

---

## Is this Staked-specific or structural?

The most important question this report has to answer, before recommending anything, is: *does any other operator do this?*

A URL-hostname survey across all 152 indexers with URLs registered in the Graph Network subgraph turns up **four other operator clusters** that meet a "3+ on-chain addresses under one apex hostname" threshold:

| Operator | Apex hostname pattern | Addresses | Self-stake GRT | Delegated GRT | Active allocations |
|---|---|---:|---:|---:|---:|
| **Staked Cloud** | `*.prod-eks-ca-central-1.staked.cloud` | 11 | ~480.7M | ~136.6M | 2,136 |
| **StakeSquid** | `indexer-arb*.stakesquid.com` / `vps.mainnet.indexer.stakesquid.com` | 7 | ~5.15M | ~45.5M | 516 |
| **P2P.org** | `is-*-arbitrum.graph.p2p.org` (`big`, `booster`, `pillar`) | 3 | ~40.4M | ~289.0M | 807 |
| **Data Nexus** | `*.service.thegraph.data.nexus` (root, graphtronauts, secondary) | 3 | ~11.7M | ~106.3M | 258 |
| **UpNode** | `rampdefi{N}-arb.upnodedev.xyz` | 3 | ~5.2M | ~51.5M | 37 |

A few below-threshold pairs (2 addresses sharing a domain — InfraDAO, Ryabina, Grassets/Graphinx, Pinax, Protofire, DSRVLabs) are worth flagging for any concentration model but don't constitute full sibling fleets by the 3+ rule.

**So Staked is not unique — but is the outlier in scale.** Staked operates more on-chain addresses (11) than any other observed cluster, has roughly 10× the self-stake of any other cluster, and operates ~4× the active allocations of the next-largest cluster. P2P.org has comparable delegated stake but only 3 on-chain identities; StakeSquid has more identities than P2P but a fraction of the stake.

A few notes on operator-specific context:

- **Data Nexus** is the infrastructure provider for the Graphtronauts operator-group; the 3 addresses are sub-tenant identities sharing one cluster.
- **UpNode**'s "rampdefi" branding suggests they run these on behalf of a specific delegator/operator group.
- **P2P.org** is among the largest delegated indexers on the network; this is a multi-identity pattern by any reading.
- The Staked indexer-6 URL is shared by two distinct on-chain addresses (0xa6ff…b325 with 9.0M GRT, 0x0df8…a2af with 0 stake). Same physical endpoint, two on-chain identities.

The takeaway: the "diversity-illusion" pattern this report documents is industry-wide, but Staked is the largest instance of it and the only one whose fleet-wide failure mode currently produces complete unavailability for any subgraph in normal use (Agent0 Base + 6 others in the probed sample). Wherever StakeSquid wins 3+ of 6 chainhead slots on a subgraph, the same pattern is mechanically possible — and worth checking.

---

## Why this matters even though things mostly work

Staked's fleet currently serves the majority of chainhead coverage on 100+ deployments — many of which would have thinner coverage without them. The concern here is structural, not about operator quality:

- **Single-vendor exposure**: Plausible failure modes for any shared-infrastructure operator include misconfiguration, billing issues, regional outages, or version regressions. A condition at the `prod-eks-ca-central-1` cluster level would simultaneously affect indexer-0, -6, -7, -8, -12, -13, -14. On deployments where Staked is 6/6 of the chainhead set, that's a total blackout. On deployments where Staked is 5/N, it's a near-total blackout. The 7 deployments in probe set B that are *already* failing demonstrate this is not hypothetical.
- **Stake-weighted routing concentration**: The Graph's gateway considers indexer stake (alongside performance, freshness, fee, and a randomization term) when selecting which indexer to route a query to. Higher stake increases an indexer's selection probability, all else equal. Staked's siblings collectively hold ~480M GRT of self-stake — a meaningful share of total routing weight that flows operationally to one fleet.
- **Indexer-count metrics overstate operator diversity**: Tooling and dashboards that count "N indexers at chainhead" as a diversity proxy will count Staked's 6 sibling addresses as 6 — overstating operational resilience. This isn't intentional misleading; the metric just doesn't capture what users assume it does.

The protocol works on average because most subgraphs are fine with Staked's currently-deployed graph-node version. But the failure case is correlated, not distributed.

---

## Recommendations (offered for discussion)

These are starting points, not demands. Operator identity is a hard problem with real design tradeoffs — the people best positioned to weigh those are the gateway team at Edge & Node and the operators themselves. Several of the protocol-level options below have non-obvious implications that deserve broader discussion.

### For The Graph (Edge & Node / gateway team)

> These are tradeoff-laden. "Operator identity" has no canonical on-chain definition today, and URL-hostname clustering is a heuristic (anyone can split into subdomains). Offered as starting points for discussion.

1. **Consider exposing an operator-grouping signal** — e.g., a URL-hostname-derived cluster ID — so downstream tooling and dashboards can incorporate it without each consumer re-deriving it. Full deduplication has tradeoffs, but visibility is uncontroversial. *Channel:* `graphprotocol/gateway` GitHub issue or forum post under Network Governance.
2. **Surface operator concentration as a subgraph-level signal**. Per-deployment: "N distinct operator clusters serving queries" alongside "N indexer addresses serving queries." Useful for both consumers and curators.
3. **Consider whether the ISA should incorporate operator-cluster diversity** as a co-input alongside stake, performance, freshness, and fee. The design space here is non-trivial — there are good reasons not to penalize legitimate multi-identity operators, and good reasons to want correlated-failure-aware routing. Worth a forum thread or GIP.

### For Staked Cloud

> Staked may already be aware of the issue surfaced here; if not, the following may be useful inputs.

1. **Graph-node version on `prod-eks-ca-central-1`**: A graph-node update across the cluster that handles `@aggregation` + `timeseries` schemas would resolve the Agent0 Base case and likely a long tail of other subgraphs using newer schema features (probe set B suggests at least 7 affected deployments — see table above). The graph-node release notes will identify the minimum version that handles these features; the deployed version on the cluster would clarify whether this hypothesis is even correct.
2. **Operator metadata transparency** (optional): publishing a public list of "these N on-chain identities are operationally one indexer fleet at Staked" would let the protocol and downstream tools account for that correctly. Staked is well-positioned to set that norm if interested.

### For subgraph developers and consumers

1. **Check your own subgraph's indexer set.** Use the GraphQL snippet in Methodology below — it takes your deployment's IPFS hash and returns the operator clusters allocated to it.
2. **If your chainhead indexer list is dominated by URLs ending in `staked.cloud` (or any other shared apex hostname)**, you have effective single-vendor exposure under any routing surface that counts those as independent. Options:
   - **Curation**: directly signal toward indexers from other operators to attract diverse coverage. (This is a slow lever — useful for medium-term resilience, not immediate availability.)
   - **Fallback paths**: maintain a query path that bypasses gateway indexer-selection (self-hosted, direct indexer queries, or alternative serving infrastructure).
   - **Escalation**: if your subgraph is one of the currently-failing ones, the escalation template below may help.

### Escalation template (for affected subgraph teams)

For teams whose subgraphs are currently in the 7 affected from probe set B, a starting point for an escalation message:

> Subject: `<deployment IPFS hash>` returns BadResponse(400) from all chainhead indexers
>
> Our subgraph deployment `<IPFS hash>` is returning `bad indexers` errors from the public Graph gateway. All chainhead indexers serving this deployment appear to be sibling addresses operated by Staked Cloud (under `*.prod-eks-ca-central-1.staked.cloud`), and they are all returning identical `BadResponse(400)` on minimal queries (`{ _meta { block { number } } }`). Most plausible root cause is graph-node version skew between Staked's deployed version and this subgraph's schema (which uses `@aggregation` / `timeseries`). Requesting either (a) escalation to Staked to upgrade graph-node on `prod-eks-ca-central-1`, or (b) gateway-side surfacing of operator-cluster diversity to catch this class of issue earlier. Happy to provide gateway error output on request.

---

## Methodology / reproducibility

The Graph Network subgraph used throughout this report:

**Subgraph ID:** `DZz4kDTdmzWLWsV373w2bSmoar3umKKH9y82SUKr5qmp`
**Public gateway:** `https://gateway.thegraph.com/api/<API_KEY>/subgraphs/id/DZz4kDTdmzWLWsV373w2bSmoar3umKKH9y82SUKr5qmp` (get a free key at `thegraph.com/studio`), or query via the subgraph MCP tools (`mcp__subgraph__execute_query_by_subgraph_id`) which don't require a key.

### Step 1: Probe a subgraph's chainhead indexer set

Query its `_meta` via the gateway. If it errors with "bad indexers," inspect the listed addresses — that list IS the gateway's view of which indexers it considered at chainhead.

```graphql
{ _meta { block { number } } }
```

### Step 2: Look up indexer URLs

```graphql
{
  indexers(where: {
    id_in: [
      "0x2b3c7d1ef5fdfc0557934019c531d3e70d6200ae",
      "0x9af3fc811a66dbbca44acce94906d8743f9cf0d0",
      "0xa6ff993e0f6253f1b7f55c873577a2f0f0ceb325",
      "0xdc53e62df89fd07b31ed4ff886397b9e7ae4625e",
      "0xe6de2325ef1aac1f058fae59d3c38a472f569846",
      "0xe9e284277648fcdb09b8efc1832c73c09b5ecf59"
    ]
  }) {
    id
    url
    stakedTokens
    allocatedTokens
  }
}
```

Group by URL hostname. If multiple addresses share an apex hostname, you've found a multi-identity operator pattern — common, often operationally legitimate, but worth surfacing because it affects how diversity metrics should be interpreted.

### Step 3: Find all addresses for a given operator

```graphql
{
  indexers(first: 200, where: { url_contains: "staked.cloud" }) {
    id
    url
    stakedTokens
    allocatedTokens
  }
}
```

### Step 4: Find the affected deployment set for an operator's siblings

Paginate with `id_gt` until you stop getting full pages. The 7 active Staked addresses:

```graphql
{
  allocations(first: 1000, where: {
    status: Active,
    indexer_in: [
      "0xe9e284277648fcdb09b8efc1832c73c09b5ecf59",
      "0xa6ff993e0f6253f1b7f55c873577a2f0f0ceb325",
      "0x2b3c7d1ef5fdfc0557934019c531d3e70d6200ae",
      "0xe6de2325ef1aac1f058fae59d3c38a472f569846",
      "0x9af3fc811a66dbbca44acce94906d8743f9cf0d0",
      "0xdc53e62df89fd07b31ed4ff886397b9e7ae4625e",
      "0x090f7382f9ea85c733cd501f4d87f16cb5b83ed3"
    ],
    id_gt: ""
  }) {
    id
    subgraphDeployment { ipfsHash }
    indexer { id }
    allocatedTokens
  }
}
```

> Note on enum syntax: `status: Active` is an unquoted enum literal, not a string. Quoting it (`"Active"`) will cause a schema error.

Group by `subgraphDeployment.ipfsHash`, count distinct indexers per deployment, and you have the concentration distribution. (The data files in this investigation hit a 3-page paginated total of 2,136 allocations across 371 deployments.)

### Snapshot dates

All allocation and stake numbers are from the Graph Network subgraph snapshot taken on **2026-06-11**. Query-volume figures are 30-day rolling as of the same date. The Agent0 `BadResponse(400)` pattern was observed at the same timestamp; whether it has persisted continuously beforehand is not investigated here.

---

## Open questions

- **Does the gateway's ISA already deduplicate by URL hostname when routing?** If it tries to spread across "6 indexers" that share an apex hostname, are queries actually load-balanced across independent failure domains, or are they all hitting the same cluster? Worth confirming with the gateway team.
- **What graph-node version is deployed on `prod-eks-ca-central-1`?** Confirming this would either validate or invalidate the version-skew hypothesis for Agent0 (and probe set B's 7 failures). Either is informative.
- **What's a reasonable on-chain or off-chain definition of "operator"?** URL-hostname clustering works as a heuristic but is gameable; ECDSA operator-attestation would be cleaner but doesn't exist today. Worth a design-space conversation.

---

## Next steps

I plan to share this report with Edge & Node and Staked Cloud directly, and will append any responses or corrections they provide. If you operate an indexer in a similar multi-identity pattern and want context added to this report — please reach out. If you maintain a subgraph that appears in the affected table above, the escalation template under Recommendations may be useful as a starting point.

Reachable via The Graph forum, Discord, or directly through Graph Advocate at `graphadvocate.com`.

---

## Data appendix

**All 11 Staked sibling on-chain addresses:**

```
0xe9e284277648fcdb09b8efc1832c73c09b5ecf59  (indexer-0,  active,    8.9M GRT)
0xa6ff993e0f6253f1b7f55c873577a2f0f0ceb325  (indexer-6,  active,    9.0M GRT)
0x0df89dd9c34f78f70eb6a528a1eeac9a6238a2af  (indexer-6,  duplicate, 0 GRT)
0x2b3c7d1ef5fdfc0557934019c531d3e70d6200ae  (indexer-7,  active,    123.6M GRT)
0xe6de2325ef1aac1f058fae59d3c38a472f569846  (indexer-8,  active,    15.9M GRT)
0xe91273727203bcc827521fc8b0c762d435c3c5d0  (indexer-9,  standby,   ~320 GRT)
0xe48b586eeb81bde60f14b0b8d80ddd06c7a24720  (indexer-10, standby,   ~660 GRT)
0xd9819426c82e2b8fc58b9b62a78efe93f78077c6  (indexer-11, standby,   ~393 GRT)
0x9af3fc811a66dbbca44acce94906d8743f9cf0d0  (indexer-12, active,    102.2M GRT)
0xdc53e62df89fd07b31ed4ff886397b9e7ae4625e  (indexer-13, active,    100.7M GRT)
0x090f7382f9ea85c733cd501f4d87f16cb5b83ed3  (indexer-14, active,    120.5M GRT)
```

**Other multi-identity operator clusters (3+ addresses under shared apex hostname):**

```
StakeSquid (*.stakesquid.com, 7 addresses):
  0x6f3ce93a09f30f18d728d2364268b5fe9444b89e  (arbiencode,  2.0M)
  0xaa988dcb035518bc0e20082a3148a5d3dfd1776d  (arbititan,   1.9M)
  0xdec965f0604125be05cd8a136c85d02ef344d61a  (arbijumbo,   0.77M)
  0x3f74870f80ff7449fe4c6ff257da5fa72734c970  (arbigiga,    0.26M)
  0x60df13b7a598772e992f9365fba5ed6e1529e79a  (vps.mainnet, 0.13M)
  0xdeb712db301285ed483ef9e02dd08a1980f273f1  (arbie2s,     0.10M)
  0x066636093e6c3417a0b46c3ecfbd34b5bda00092  (arbimega,    0)

P2P.org (*.graph.p2p.org, 3 addresses):
  0x2f09092aacd80196fc984908c5a9a7ab3ee4f1ce  (is-big,     36.7M)
  0xf00f7157fa8fd0420b87956d46058a16b2f23adc  (is-booster,  3.6M)
  0x2121bc6437100fc21d19a9eea30898419e020afa  (is-pillar,   0.1M)

Data Nexus (*.service.thegraph.data.nexus, 3 addresses):
  0x4e5c87772c29381bcabc58c3f182b6633b5a274a  (service,                   9.6M)
  0x326c584e0f0eab1f1f83c93cc6ae1acc0feba0bc  (graphtronauts.service,     2.0M)
  0xa181d0f242b3730f8a244cc94eda05faf17a43e8  (secondary.service,         0.1M)

UpNode (rampdefi{N}-arb.upnodedev.xyz, 3 addresses):
  0xc9014686f6336ad558b539565d5dff840b339082  (rampdefi1-arb, 2.5M)
  0x17def1a43a323c711c7a32101ecf41e58eff54a2  (rampdefi4-arb, 1.6M)
  0x32bbd16a94ebb289edceebe77f35acc82664157b  (rampdefi3-arb, 1.1M)
```

**Reference IDs:**

- Graph Network subgraph (indexer/allocation queries): `DZz4kDTdmzWLWsV373w2bSmoar3umKKH9y82SUKr5qmp`
- Agent0 Base ERC-8004 subgraph (the failing case): `43s9hQRurMGjuYnC1r2ZwS6xSQktbFyXMPMqGKUFJojb` / deployment `QmcLwgyKn3RnyhkkSwLYscP9dL1Fc6omvfC9bFRgcK1e7u`

**Supporting data files** (in `scripts/reputation_v2/`):

- `staked_deployments.json` — full deployment list with sibling counts (371 rows after re-running paginated query)
- `staked_impact_ranking.json` — top 25 deployments ranked by blast radius (siblings × 30d query volume)

**Investigation timestamp:** 2026-06-11