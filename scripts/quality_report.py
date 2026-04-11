"""
Quality report — analyzes routing quality scores to find systematic issues.

Reads from the activity + quality_scores SQLite tables and outputs
actionable recommendations for improving the system prompt.

Usage:
    python scripts/quality_report.py
    python scripts/quality_report.py --db /data/activity.db
"""

import json
import os
import sqlite3
import sys

DB_PATH = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else os.environ.get("ACTIVITY_DB_PATH", "/data/activity.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=" * 60)
    print("  GRAPH ADVOCATE QUALITY REPORT")
    print("=" * 60)

    # 1. Low-score queries (score <= 2)
    low_scores = conn.execute("""
        SELECT q.request, q.service, q.score, q.has_query_ready, q.has_subgraph_id,
               q.has_curl_example, q.has_install, q.parse_success
        FROM quality_scores q
        WHERE q.score <= 2
        ORDER BY q.timestamp DESC
        LIMIT 20
    """).fetchall()

    print(f"\n1. LOW QUALITY RESPONSES (score <= 2/5): {len(low_scores)}")
    print("-" * 60)
    for r in low_scores:
        missing = []
        if not r["has_query_ready"]:
            missing.append("no query_ready")
        if not r["has_subgraph_id"]:
            missing.append("no subgraph_id")
        if not r["has_curl_example"]:
            missing.append("no curl_example")
        if not r["has_install"]:
            missing.append("no install")
        print(f"  [{r['score']}/5] [{r['service']:25s}] {r['request'][:55]}")
        print(f"         Missing: {', '.join(missing)}")

    # 2. Service-level quality gaps
    print(f"\n2. SERVICE QUALITY GAPS")
    print("-" * 60)
    service_stats = conn.execute("""
        SELECT service,
               COUNT(*) as total,
               AVG(score) as avg_score,
               AVG(has_query_ready) * 100 as qr_rate,
               AVG(has_subgraph_id) * 100 as sg_rate,
               AVG(has_curl_example) * 100 as curl_rate
        FROM quality_scores
        GROUP BY service
        HAVING total >= 2
        ORDER BY avg_score ASC
    """).fetchall()

    for s in service_stats:
        grade = "A" if s["avg_score"] >= 4 else "B" if s["avg_score"] >= 3 else "C" if s["avg_score"] >= 2 else "F"
        print(f"  [{grade}] {s['service']:35s} avg:{s['avg_score']:.1f}/5 ({s['total']} queries)")
        print(f"       query_ready:{s['qr_rate']:.0f}% subgraph_id:{s['sg_rate']:.0f}% curl:{s['curl_rate']:.0f}%")

    # 3. Routing failures (unknown, out-of-scope, unclear)
    print(f"\n3. ROUTING FAILURES")
    print("-" * 60)
    failures = conn.execute("""
        SELECT request, service, COUNT(*) as cnt
        FROM activity
        WHERE service IN ('unknown', 'out-of-scope', 'unclear-request', 'no-match', 'clarification-needed')
        GROUP BY request
        ORDER BY cnt DESC
        LIMIT 15
    """).fetchall()

    for f in failures:
        print(f"  [{f['cnt']:>3}x] [{f['service']:20s}] {f['request'][:55]}")

    # 4. Non-standard service names (Claude not following routing rules)
    print(f"\n4. NON-STANDARD SERVICE NAMES (Claude inventing names)")
    print("-" * 60)
    standard = {
        'token-api', 'subgraph-registry', 'substreams', 'graph-aave-mcp',
        'graph-polymarket-mcp', 'graph-lending-mcp', 'graph-limitless-mcp',
        'predictfun-mcp', 'mcp8004', '8004scan', 'x402-analytics',
        'introduction', 'out-of-scope', 'conformance', 'cached',
        'benchmark-static', 'comparison', 'chat',
    }
    nonstandard = conn.execute("""
        SELECT service, COUNT(*) as cnt
        FROM activity
        WHERE service NOT IN ({})
        GROUP BY service
        ORDER BY cnt DESC
    """.format(','.join(f"'{s}'" for s in standard))).fetchall()

    for ns in nonstandard:
        if ns['cnt'] > 0:
            print(f"  [{ns['cnt']:>3}x] {ns['service']}")

    # 5. Recommendations
    print(f"\n5. RECOMMENDATIONS")
    print("-" * 60)

    # Token API quality
    token_stats = conn.execute("""
        SELECT AVG(has_query_ready) * 100 as qr, AVG(score) as avg
        FROM quality_scores WHERE service = 'token-api'
    """).fetchone()
    if token_stats and token_stats["qr"] and token_stats["qr"] < 80:
        print(f"  - TOKEN API: query_ready rate is {token_stats['qr']:.0f}% — Claude sometimes")
        print(f"    omits required params (network, contract). Consider adding more")
        print(f"    examples with exact params to the system prompt.")

    # Subgraph ID rate
    sg_stats = conn.execute("""
        SELECT AVG(has_subgraph_id) * 100 as sg
        FROM quality_scores WHERE service LIKE '%subgraph%' OR service LIKE '%Uniswap%'
    """).fetchone()
    if sg_stats and sg_stats["sg"] and sg_stats["sg"] < 60:
        print(f"  - SUBGRAPH ID: only {sg_stats['sg']:.0f}% of subgraph queries include a")
        print(f"    real subgraph ID. Claude still hallucinating IDs sometimes.")
        print(f"    The query_hint column helps — ensure the registry DB is fresh.")

    # Non-standard names
    if len(nonstandard) > 5:
        print(f"  - SERVICE NAMES: Claude is inventing {len(nonstandard)} non-standard service")
        print(f"    names instead of using the defined ones. Add stricter rules to the")
        print(f"    system prompt: 'recommendation MUST be one of: token-api, subgraph-registry, ...'")

    # Low-score services
    for s in service_stats:
        if s["avg_score"] < 2.5 and s["service"] not in ('out-of-scope', 'introduction', 'unclear-request', 'no-match', 'operational-confirmation'):
            print(f"  - {s['service'].upper()}: avg score {s['avg_score']:.1f}/5 — needs prompt improvement")

    conn.close()
    print()


if __name__ == "__main__":
    main()
