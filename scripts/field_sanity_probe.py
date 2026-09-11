#!/usr/bin/env python3
"""
Execute the queries GA recommends and check whether the NUMBERS are believable.

Why this exists
---------------
GA's auto-scorer grades the SHAPE of an answer — does it carry a query_ready, a
subgraph_id, a curl example. It cannot see that a field inside the query returns
nonsense, so it rated 5.0/5 an Aave answer whose `profitUSD` column reported a
$107,988,926 loss on a $112.85 liquidation. Two such traps surfaced in three days
(Uniswap `totalValueLockedUSD`, Aave `profitUSD`) and both were found only by
running the query, never by reading the answer.

So this probe runs them. Each check states a relationship that must hold in real
data — a liquidator's profit cannot be a million times the debt repaid; a pool
with no volume cannot hold a trillion dollars — and fails loudly when it doesn't.

A check that cannot fail is not a check: every rule here is one that a real,
observed defect would have tripped.

Run:  GRAPH_API_KEY=... python3 scripts/field_sanity_probe.py
Exit: 0 = all plausible, 1 = at least one field is not to be trusted.
"""
import json
import os
import sys
import urllib.request

GATEWAY = "https://gateway.thegraph.com/api/subgraphs/id/"
KEY = (os.environ.get("GRAPH_API_KEY")
       or os.environ.get("GATEWAY_API_KEY")
       or os.environ.get("THE_GRAPH_STUDIO_API_KEY") or "")


def gql(subgraph_id, query, timeout=45):
    req = urllib.request.Request(
        GATEWAY + subgraph_id,
        data=json.dumps({"query": query}).encode(),
        headers={
            "content-type": "application/json",
            "Authorization": f"Bearer {KEY}",
            # The gateway 403s the default python-urllib agent while accepting the
            # identical request from curl. Same trap as arb1.arbitrum.io. Send a
            # real UA or every probe silently SKIPs and the run reports all-clear.
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ratio_rule(rows, numer, denom, max_abs_ratio, label):
    """|numer| must not exceed denom by more than max_abs_ratio on any row."""
    bad = []
    for row in rows:
        try:
            d = float(row.get(denom) or 0)
            n = float(row.get(numer) or 0)
        except (TypeError, ValueError):
            continue
        if d > 0 and abs(n) > d * max_abs_ratio:
            bad.append((n, d, n / d))
    if not bad:
        return None
    worst = max(bad, key=lambda t: abs(t[2]))
    return (f"{label}: {len(bad)}/{len(rows)} rows implausible — "
            f"worst {numer}={worst[0]:,.2f} against {denom}={worst[1]:,.2f} "
            f"({worst[2]:,.0f}x)")


def dead_top_rule(rows, rank_field, activity_field, label):
    """The top-ranked row by rank_field must show SOME activity. A pool holding a
    trillion dollars with zero volume is a spam pool, not a market."""
    if not rows:
        return None
    top = rows[0]
    try:
        act = float(top.get(activity_field) or 0)
        rank = float(top.get(rank_field) or 0)
    except (TypeError, ValueError):
        return None
    if rank > 0 and act == 0:
        return (f"{label}: top row by {rank_field} ({rank:,.0f}) has "
                f"{activity_field}=0 — ranking is being driven by a dead entity")
    return None


PROBES = [
    {
        "label": "Aave V3 Ethereum · profitUSD",
        "id": "JCNWRypm7FYwV8fx5HhzZPSFaMxgkPuw4TnR3Gpi81zk",
        "query": "{ liquidates(first:20, orderBy: timestamp, orderDirection: desc)"
                 "{ amountUSD profitUSD } }",
        "root": "liquidates",
        "rules": [lambda r: ratio_rule(r, "profitUSD", "amountUSD", 10,
                                       "Aave V3 Ethereum profitUSD")],
    },
    {
        "label": "Aave V3 Arbitrum · profitUSD",
        "id": "4xyasjQeREe7PxnF6wVdobZvCw5mhoHZq3T7guRpuNPf",
        "query": "{ liquidates(first:20, orderBy: timestamp, orderDirection: desc)"
                 "{ amountUSD profitUSD } }",
        "root": "liquidates",
        "rules": [lambda r: ratio_rule(r, "profitUSD", "amountUSD", 10,
                                       "Aave V3 Arbitrum profitUSD")],
    },
    {
        "label": "Uniswap V3 Ethereum · TVL ranking",
        "id": "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV",
        "query": "{ pools(first:5, orderBy: totalValueLockedUSD, orderDirection: desc)"
                 "{ totalValueLockedUSD volumeUSD } }",
        "root": "pools",
        "rules": [lambda r: dead_top_rule(r, "totalValueLockedUSD", "volumeUSD",
                                          "Uniswap V3 TVL ranking")],
    },
    {
        # The control. GA answers Uniswap questions with this ordering, so if this
        # ever fails the probe itself is suspect, not the data.
        "label": "Uniswap V3 Ethereum · volume ranking (control, must pass)",
        "id": "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV",
        "query": "{ pools(first:5, orderBy: volumeUSD, orderDirection: desc)"
                 "{ totalValueLockedUSD volumeUSD } }",
        "root": "pools",
        "rules": [lambda r: dead_top_rule(r, "volumeUSD", "totalValueLockedUSD",
                                          "Uniswap V3 volume ranking")],
    },
]


def main():
    if not KEY:
        print("GRAPH_API_KEY is not set — cannot query the gateway.", file=sys.stderr)
        return 2
    findings, checked = [], 0
    for p in PROBES:
        try:
            res = gql(p["id"], p["query"])
        except Exception as e:  # network/gateway problems are not field defects
            print(f"  SKIP  {p['label']} — {str(e)[:70]}")
            continue
        if "errors" in res:
            print(f"  SKIP  {p['label']} — {str(res['errors'])[:70]}")
            continue
        rows = (res.get("data") or {}).get(p["root"]) or []
        if not rows:
            print(f"  SKIP  {p['label']} — no rows")
            continue
        checked += 1
        hits = [msg for rule in p["rules"] if (msg := rule(rows))]
        if hits:
            findings.extend(hits)
            for m in hits:
                print(f"  FAIL  {m}")
        else:
            print(f"  ok    {p['label']}")

    print(f"\n{checked} probes executed, {len(findings)} field(s) not to be trusted.")
    if findings:
        print("Any field listed above must NOT appear in a query GA hands to a caller "
              "without an explicit warning in `reason`.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
