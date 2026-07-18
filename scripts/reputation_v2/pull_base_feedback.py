"""Pull ALL ERC-8004 feedback from Base mainnet (chain 8453) via Agent0 subgraph.

Paginates by createdAt+id to get past the 1000-row gateway cap. Writes raw rows
to base_feedback.json so downstream scoring runs offline (no quota burn per
iteration).
"""

import json
import os
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

API_KEY = os.environ.get("GRAPH_API_KEY") or os.environ.get("VITE_GRAPH_API_KEY")
if not API_KEY:
    sys.exit("set GRAPH_API_KEY (read from ~/graph-advocate/.env)")

IPFS_HASH = "QmcLwgyKn3RnyhkkSwLYscP9dL1Fc6omvfC9bFRgcK1e7u"  # agent0-base-mainnet deployment
# Use deployments/id route — subgraphs/id was breaking on every indexer
# with BadResponse(400) for queries with orderBy or large `first` values.
URL = f"https://gateway.thegraph.com/api/{API_KEY}/deployments/id/{IPFS_HASH}"
OUT = Path(__file__).parent / "base_feedback.json"

PAGE = 100  # indexers reject larger pages on this subgraph


def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read())
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]


def pull_feedbacks():
    rows = []
    last_ts = 0
    while True:
        q = """
        query($first: Int!, $lastTs: BigInt!) {
          feedbacks(
            first: $first
            where: { createdAt_gte: $lastTs }
            orderBy: createdAt
            orderDirection: asc
          ) {
            id
            agent { id }
            clientAddress
            value
            tag1
            tag2
            endpoint
            isRevoked
            createdAt
            feedbackURI
          }
        }
        """
        data = gql(q, {"first": PAGE, "lastTs": str(last_ts)})
        batch = data["feedbacks"]
        if not batch:
            break
        new = [r for r in batch if r["id"] not in {x["id"] for x in rows[-PAGE * 2:]}]
        rows.extend(new)
        print(f"  +{len(new)} (running total {len(rows)}), last_ts={batch[-1]['createdAt']}", file=sys.stderr)
        if len(batch) < PAGE:
            break
        last_ts = int(batch[-1]["createdAt"])
        time.sleep(0.2)
    return rows


def pull_agents():
    rows = []
    last_id = ""
    while True:
        q = """
        query($first: Int!, $lastId: String!) {
          agents(
            first: $first
            where: { id_gt: $lastId }
            orderBy: id
            orderDirection: asc
          ) {
            id
            totalFeedback
            lastActivity
            owner
            agentWallet
          }
        }
        """
        data = gql(q, {"first": PAGE, "lastId": last_id})
        batch = data["agents"]
        if not batch:
            break
        rows.extend(batch)
        print(f"  +{len(batch)} agents (running total {len(rows)})", file=sys.stderr)
        if len(batch) < PAGE:
            break
        last_id = batch[-1]["id"]
        time.sleep(0.2)
    return rows


def main():
    print("pulling agents…", file=sys.stderr)
    agents = pull_agents()
    print(f"agents: {len(agents)}", file=sys.stderr)

    print("pulling feedbacks…", file=sys.stderr)
    feedbacks = pull_feedbacks()
    print(f"feedbacks: {len(feedbacks)}", file=sys.stderr)

    OUT.write_text(json.dumps({"agents": agents, "feedbacks": feedbacks}, indent=2))
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
