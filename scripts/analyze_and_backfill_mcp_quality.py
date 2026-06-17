#!/usr/bin/env python3
"""Sample low-scoring graph-aave-mcp rows + backfill MCP/REST service scores
using the current scoring rubric.

Run on Railway:
    railway run python3 scripts/analyze_and_backfill_mcp_quality.py
    railway run python3 scripts/analyze_and_backfill_mcp_quality.py --apply

Without --apply: dry-run. Prints the deep-sample, lists what WOULD change,
and the projected new averages.

With --apply: rewrites the score column for MCP + REST-only services using
the current rubric (auto-credit for subgraph_id where N/A, curl where N/A,
install where N/A). The boolean columns aren't touched; only `score` is
recomputed from existing flags.

This exists because the MCP-credit logic in _score_response (a2a_server.py:
2974-3006) only applies to NEW rows. Historical rows scored under the buggy
rubric still drag graph-aave-mcp to q=2.05 across 880 calls. The backfill
re-applies current rubric to the existing has_query_ready / has_subgraph_id
/ has_curl_example / has_install / parse_success columns.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


MCP_SERVICES = {
    "graph-aave-mcp", "graph-polymarket-mcp", "graph-lending-mcp",
    "graph-limitless-mcp", "predictfun-mcp", "mcp8004",
}
NO_CURL_NEEDED = {
    "token-api", "8004scan", "x402-analytics", "substreams",
    "hyperliquid-token-api", "polymarket-token-api",
}
REST_ONLY_SERVICES = MCP_SERVICES | NO_CURL_NEEDED


def recompute_score(service: str, parse_ok: bool, has_query_ready: bool,
                    has_subgraph_id: bool, has_curl: bool, has_install: bool) -> int:
    is_rest_only = service in REST_ONLY_SERVICES
    if is_rest_only:
        curl_credit = 1 if (has_curl or service in NO_CURL_NEEDED or service in MCP_SERVICES) else 0
        install_credit = 1 if (
            has_install or service in NO_CURL_NEEDED or service in MCP_SERVICES
        ) else 0
        return sum([
            1 if parse_ok else 0,
            1 if (has_query_ready or has_curl) else 0,
            1,
            curl_credit,
            install_credit,
        ])
    # Non-REST (subgraph-registry, substreams): install auto-credit for direct-HTTP services
    install_na = service in {"subgraph-registry", "substreams"}
    return sum([
        1 if parse_ok else 0,
        1 if has_query_ready else 0,
        1 if has_subgraph_id else 0,
        1 if has_curl else 0,
        1 if (has_install or install_na) else 0,
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write the backfilled scores")
    ap.add_argument("--db", default=os.environ.get("DB_PATH", "advocate.db"))
    ap.add_argument("--sample-service", default="graph-aave-mcp")
    ap.add_argument("--sample-n", type=int, default=50)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        sys.exit(f"DB not found at {db}. Pass --db or set DB_PATH.")

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    # ── Deep sample of low-scoring rows for the requested service ─────────
    print(f"\n=== DEEP SAMPLE: lowest-scoring {args.sample_service} (n={args.sample_n}) ===\n")
    sample = conn.execute(
        f"SELECT timestamp, request, parse_success, has_query_ready, "
        f"has_subgraph_id, has_curl_example, has_install, score "
        f"FROM quality_scores WHERE service = ? "
        f"ORDER BY score ASC, timestamp DESC LIMIT ?",
        (args.sample_service, args.sample_n),
    ).fetchall()

    if not sample:
        print(f"  (no quality_scores rows for service={args.sample_service})")
    else:
        flag_combos = defaultdict(int)
        for r in sample:
            flags = f"parse={int(r['parse_success'])} qr={int(r['has_query_ready'])} sg={int(r['has_subgraph_id'])} curl={int(r['has_curl_example'])} install={int(r['has_install'])}"
            flag_combos[flags] += 1
            new_score = recompute_score(
                args.sample_service,
                bool(r["parse_success"]),
                bool(r["has_query_ready"]),
                bool(r["has_subgraph_id"]),
                bool(r["has_curl_example"]),
                bool(r["has_install"]),
            )
            req = (r["request"] or "")[:90]
            print(f"  [{r['timestamp'][:19]}] old={r['score']} new={new_score}  {flags}  | {req}")

        print(f"\n  Flag-combo frequency in sample (what's missing on the low-scorers):")
        for combo, n in sorted(flag_combos.items(), key=lambda x: -x[1]):
            print(f"    {n:>3}x  {combo}")

    # ── Projected backfill across ALL services where scoring rules changed ─
    print(f"\n=== BACKFILL PROJECTION (across all REST-only + MCP services) ===\n")
    projection = []
    for service in sorted(REST_ONLY_SERVICES):
        rows = conn.execute(
            "SELECT score, parse_success, has_query_ready, has_subgraph_id, "
            "has_curl_example, has_install FROM quality_scores WHERE service = ?",
            (service,),
        ).fetchall()
        if not rows:
            continue
        old_avg = sum(r["score"] for r in rows) / len(rows)
        new_scores = [
            recompute_score(
                service,
                bool(r["parse_success"]),
                bool(r["has_query_ready"]),
                bool(r["has_subgraph_id"]),
                bool(r["has_curl_example"]),
                bool(r["has_install"]),
            )
            for r in rows
        ]
        new_avg = sum(new_scores) / len(new_scores)
        changed = sum(1 for r, n in zip(rows, new_scores) if r["score"] != n)
        projection.append((service, len(rows), old_avg, new_avg, changed))
        print(f"  {service:30s} n={len(rows):>5}  old={old_avg:.2f}  new={new_avg:.2f}  changed={changed}")

    # ── Apply or not ──────────────────────────────────────────────────────
    if not args.apply:
        print(f"\n(dry-run — re-run with --apply to write the backfilled scores)\n")
        conn.close()
        return

    print(f"\nApplying backfill...")
    total_updated = 0
    for service, _, _, _, _ in projection:
        rows = conn.execute(
            "SELECT rowid, parse_success, has_query_ready, has_subgraph_id, "
            "has_curl_example, has_install FROM quality_scores WHERE service = ?",
            (service,),
        ).fetchall()
        for r in rows:
            new_score = recompute_score(
                service,
                bool(r["parse_success"]),
                bool(r["has_query_ready"]),
                bool(r["has_subgraph_id"]),
                bool(r["has_curl_example"]),
                bool(r["has_install"]),
            )
            conn.execute("UPDATE quality_scores SET score = ? WHERE rowid = ?",
                         (new_score, r["rowid"]))
            total_updated += 1
    conn.commit()
    conn.close()
    print(f"Updated {total_updated} rows.\n")


if __name__ == "__main__":
    main()
