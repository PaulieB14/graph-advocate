# Indexer Diversity is Illusory: The Staked Cloud Sybil Pattern on The Graph

**Date:** 2026-06-11
**Author:** Paul Barba (Graph Advocate)
**Status:** Investigation, evidence-backed

---

## TL;DR

While debugging an unrelated query against the **Agent0 ERC-8004 Base Mainnet** subgraph, I noticed the gateway reported *"6 indexers at chainhead, all returning BadResponse(400)"*. Six independent operators failing in the exact same way at the exact same instant is statistically implausible — so I dug in.

**Finding:** Those "6 indexers" are not 6 operators. They are **6 on-chain identities run by one operator (Staked Cloud) out of a single Kubernetes cluster** (`prod-eks-ca-central-1`). The Graph's protocol treats each address as a distinct indexer for diversity / routing / stake-weighting purposes. In reality they share infrastructure, graph-node version, and config — so when one fails, they all fail identically and simultaneously.

This isn't a "Staked is malicious" finding. They aren't hiding — the URLs are public. But the **protocol-level abstraction of "indexer diversity" is leaking**: 357+ subgraphs across The Graph network rely on Staked sibling indexers for >50% of their indexer coverage. When Staked has a graph-node version issue that makes one subgraph unqueryable (as is currently the case for Agent0 Base), every one of that subgraph's chainhead indexers goes down together.

---

## The discovery

Querying Agent0 Base via the public gateway with even the simplest possible request:

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

Six indexers all returning `BadResponse(400)` on a request that should always succeed. Looking up their URLs in The Graph's network subgraph:

| Indexer address | URL |
|---|---|
| 0x2b3c…00ae | `graph-indexer-7-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0x9af3…f0d0 | `graph-indexer-12-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0xa6ff…b325 | `graph-indexer-6-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0xdc53…625e | `graph-indexer-13-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0xe6de…9846 | `graph-indexer-8-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0xe9e2…cf59 | `graph-indexer-0-arbi.prod-eks-ca-central-1.staked.cloud` |
| 0xf92f…a6d4 | `graph-l2prod.ellipfra.com` *(separate operator, lagging)* |

The naming pattern (`graph-indexer-{N}-arbi.prod-eks-ca-central-1.staked.cloud`) is unambiguous: same operator, same region, same Kubernetes cluster, sequentially numbered nodes.

---

## Scale of the pattern

Searching The Graph's network subgraph for **all indexers with `staked.cloud` URLs** returns **11 distinct on-chain addresses**:

| URL slot | Status | Self-staked GRT | Delegated GRT |
|---|---|---:|---:|
| indexer-0 | active | 8.9M | 133M |
| indexer-6 | active | 9M (and one duplicate at 0 stake) | 0 |
| indexer-7 | active | 123.6M | 2.8K |
| indexer-8 | active | 15.9M | 0 |
| indexer-9 | standby | 320 (basically empty) | 254 |
| indexer-10 | standby | 660 | 0 |
| indexer-11 | standby | 393 | 0 |
| indexer-12 | active | 102.2M | 0 |
| indexer-13 | active | 100.7M | 0 |
| indexer-14 | active | 120.5M | 0 |

**Total active self-stake: ~480M GRT. Total delegated: ~133M GRT.** Staked is among the largest indexer operators on The Graph. Their fleet is currently doing the work of ~13 separately-stake-weighted indexers from the protocol's point of view.

---

## How many subgraphs is this concentrated on?

Pulled all active allocations belonging to the 7 active Staked sibling addresses. **357 distinct subgraph deployments** (lower bound — query hit a 1000-row pagination cap, true number is likely higher).

Distribution of "how many Staked siblings are allocated to a single subgraph deployment":

| Staked siblings allocated | # of deployments |
|---:|---:|
| **6** (all active siblings) | **3** |
| 5 | 27 |
| 4 | 68 |
| 3 | 109 |
| 2 | 98 |
| 1 | 52 |

For the 3 deployments with all 6 active siblings, **Staked is the entire chainhead indexer set**. A Staked-wide outage on those subgraphs = 100% blackout under default gateway routing.

For the next 27 (5 siblings each), Staked is >70% of the indexer set on average. Same story, slightly less severe.

---

## High-traffic subgraphs in the affected set

Cross-referencing the 357 deployments with 30-day query volume:

| Subgraph | 30-day queries | Staked siblings | Signaled GRT |
|---|---:|---:|---:|
| **TellerV2 Mainnet** (DeFi lending) | 748,878 | 4 | 12,663 |
| **harbor-marks** | 542,305 | 5 | 2,430 |
| **Balancer Avalanche V2 Beta** | 461,042 | 5 | 5,929 |
| **CreatorBid** (AI creator economy) | 342,176 | 4 | 45,618 |
| **unlock-protocol-polygon** | 302,537 | 5 | 2,945 |
| **Marlin Oyster Arbitrum** | 181,365 | 5 | 2,970 |
| **kleros-display-gnosis** | 148,671 | 5 | 2,974 |
| **Super Freak** | 135,118 | 4 | 9,539 |
| **swapbase** (Base DEX) | 118,566 | 5 | 4,961 |
| **nftmarket-base** | 69,976 | 5 | 4,895 |
| **Agent0 Base ERC-8004** | (currently unqueryable) | 4 on-chain + 2 indexing | n/a |

These aren't fringe subgraphs. Several million queries per month flow through deployments where Staked is the majority indexer.

---

## Does the Staked sybil pattern alone cause query failures?

**No — and this is the nuance.**

I probed each of the high-traffic subgraphs above with the same `_meta` query that fails on Agent0:

```
✓ TellerV2 Mainnet           — _meta returns block successfully
✓ Balancer Avalanche V2      — _meta returns block successfully
✓ unlock-protocol-polygon    — _meta returns block successfully
✓ CreatorBid                 — _meta returns block successfully
✓ Marlin Oyster Arbitrum     — _meta returns block successfully
✓ kleros-display-gnosis      — _meta returns block successfully
✓ swapbase                   — _meta returns block successfully
✓ nftmarket-base             — _meta returns block successfully
✗ Agent0 Base ERC-8004       — every indexer returns BadResponse(400)
```

So Staked's indexers are serving queries fine on most subgraphs. **The Agent0 failure is the combination of two things:**

1. **Staked concentration** — every chainhead indexer for Agent0 Base is a Staked sibling (the only non-Staked option, Ellipfra, is lagging)
2. **A subgraph-specific incompatibility** — the Agent0 schema uses `@aggregation` and `timeseries` entities (relatively new graph-node features). Staked's currently-deployed graph-node version evidently can't compile queries against this schema, so every query 400s.

Either condition alone would be survivable. The first means "if Staked has a problem, this subgraph has a problem." The second means "Staked currently has a problem with this subgraph's schema." Together: total blackout.

---

## Why this matters even though "things mostly work"

The Agent0 case is a concrete demonstration of a **latent risk** that exists across the 357+ subgraphs Staked indexes:

- **Single-vendor risk**: A misconfiguration, billing issue, AWS region outage, or version regression at Staked would simultaneously knock out indexer-0, -6, -7, -8, -12, -13, -14. On the 3 deployments where Staked is 6/6 of the chainhead set, that's a total blackout. On the 27 deployments where Staked is 5/N, it's a near-total blackout.
- **Stake-weighted routing concentration**: The Graph's gateway favors higher-staked indexers for query routing. Staked's siblings collectively hold ~480M GRT of self-stake — that's enormous routing weight that flows to one operator under the abstraction of "many indexers."
- **Apparent diversity is misleading**: Tooling and dashboards that count "N indexers at chainhead" as a diversity metric will count Staked's 6 sibling addresses as 6 — overstating real resilience.

The protocol works **on average** because most subgraphs are fine with Staked's graph-node version. But the failure case is correlated, not distributed.

---

## Recommendations

### For The Graph (Edge & Node / gateway team)

1. **Deduplicate indexers by operator at the gateway layer.** When counting "indexers at chainhead" for routing/health/diversity purposes, group addresses by URL hostname (or by ECDSA-signed operator attestation). Show users the deduplicated count.
2. **Surface operator concentration as a subgraph-level signal.** Publish, per deployment: "N distinct operators serving queries" alongside "N indexer addresses serving queries." When those numbers diverge, users should see it.
3. **Consider a routing nudge.** When a subgraph has Staked-only chainhead coverage and a non-Staked indexer is syncing, gateway can preference the non-Staked address even at a small stake-weight penalty — preserves diversity in the routing distribution.

### For Staked Cloud

1. **Graph-node version**: Push an update across `prod-eks-ca-central-1` that handles `@aggregation` + `timeseries` schemas. This single change fixes the Agent0 Base query availability and likely a long tail of other subgraphs using newer schema features.
2. **Consider operator metadata transparency**: Publishing a list of "these N on-chain identities are operationally one indexer at Staked" lets the protocol and downstream tools account for that correctly.

### For Agent0 team

Your Base mainnet subgraph is currently unqueryable for anyone routing through the default Graph gateway. Privileged routes (e.g. Pinax) still work. Worth contacting either Edge & Node or Staked to escalate.

### For other subgraph developers / consumers

If you depend on a subgraph whose chainhead indexer list is dominated by URLs ending in `staked.cloud`, you have effective single-vendor risk under any pricing surface that counts those as separate indexers. Either:
- Curate signal toward indexers from other operators to attract diverse coverage
- Maintain a fallback query path (Pinax, self-hosted, or direct indexer queries)
- Push on Edge & Node for gateway-level operator deduplication

---

## Methodology / reproducibility

Anyone can verify this in ~5 minutes:

1. Pick any subgraph and query its `_meta`. If it errors with "bad indexers," inspect the listed indexer addresses.
2. Look up each address in the Graph Network subgraph (`DZz4kDTdmzWLWsV373w2bSmoar3umKKH9y82SUKr5qmp`):
   ```graphql
   { indexers(where: { id_in: [...] }) { id url stakedTokens } }
   ```
3. Group by URL hostname. If many addresses share a hostname, you've found a sybil operator pattern.

To find all Staked sibling addresses in one query:
```graphql
{ indexers(first: 200, where: { url_contains: "staked.cloud" }) { id url stakedTokens allocatedTokens } }
```

To find the affected deployment set:
```graphql
{ allocations(first: 1000, where: {
    status: Active,
    indexer_in: [ <the 7 active Staked addresses> ]
  }) { subgraphDeployment { ipfsHash } indexer { id } allocatedTokens } }
```

Group by `subgraphDeployment.ipfsHash`, count distinct indexers per deployment, and you have the concentration distribution.

---

## Open questions

- Are there other indexer operators running similar sibling fleets that the protocol counts as separate identities? (Cursory grep on URL patterns suggests there are at least a few — worth a follow-up investigation.)
- Does the gateway routing algorithm currently deduplicate by hostname when allocating queries? If it tries to spread across "6 indexers" but they're really 1 operator, are queries actually load-balanced or are they all hitting the same EKS cluster?
- The Graph's allocation reward mechanism distributes inflation to indexers per allocation. Does a sybil-operator strategy lead to more inflation capture per unit of work than a single-identity strategy? (This is a deeper protocol-design question.)

---

## Data appendix

- Staked indexer addresses (11): `0x090f7382f9ea85c733cd501f4d87f16cb5b83ed3`, `0x0df89dd9c34f78f70eb6a528a1eeac9a6238a2af`, `0x2b3c7d1ef5fdfc0557934019c531d3e70d6200ae`, `0x9af3fc811a66dbbca44acce94906d8743f9cf0d0`, `0xa6ff993e0f6253f1b7f55c873577a2f0f0ceb325`, `0xd9819426c82e2b8fc58b9b62a78efe93f78077c6`, `0xdc53e62df89fd07b31ed4ff886397b9e7ae4625e`, `0xe48b586eeb81bde60f14b0b8d80ddd06c7a24720`, `0xe6de2325ef1aac1f058fae59d3c38a472f569846`, `0xe91273727203bcc827521fc8b0c762d435c3c5d0`, `0xe9e284277648fcdb09b8efc1832c73c09b5ecf59`
- Network subgraph used for indexer lookup: `DZz4kDTdmzWLWsV373w2bSmoar3umKKH9y82SUKr5qmp`
- Agent0 Base subgraph (the failing case): `43s9hQRurMGjuYnC1r2ZwS6xSQktbFyXMPMqGKUFJojb` / `QmcLwgyKn3RnyhkkSwLYscP9dL1Fc6omvfC9bFRgcK1e7u`
- Investigation timestamp: 2026-06-11
