"""Terminal dashboard — shows recommendation log performance stats."""
import sqlite3
import json
from collections import Counter
from datetime import datetime

DB = "/Users/paulbarba/graph-advocate/recommendations.db"

def run():
    try:
        conn = sqlite3.connect(DB)
        rows = conn.execute(
            "SELECT timestamp, requesting_agent, request, service_chosen, confidence FROM recommendations ORDER BY timestamp"
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"No data yet: {e}")
        return

    if not rows:
        print("No recommendations logged yet. Run some queries first.")
        return

    total = len(rows)
    services = Counter(r[3] for r in rows)
    confidence = Counter(r[4] for r in rows)
    agents = Counter(r[1] for r in rows)

    print("\n" + "="*60)
    print("  GRAPH ADVOCATE — PERFORMANCE DASHBOARD")
    print("="*60)
    print(f"\n  Total recommendations: {total}")
    print(f"  First query: {rows[0][0][:19]}")
    print(f"  Last query:  {rows[-1][0][:19]}")

    print("\n  ROUTING BREAKDOWN")
    print("  " + "-"*40)
    for svc, count in services.most_common():
        bar = "█" * count
        pct = count / total * 100
        print(f"  {svc:<22} {bar:<15} {count:>3} ({pct:.0f}%)")

    print("\n  CONFIDENCE SCORES")
    print("  " + "-"*40)
    for conf in ["high", "medium", "low", "unknown"]:
        count = confidence.get(conf, 0)
        bar = "█" * count
        pct = count / total * 100
        print(f"  {conf:<22} {bar:<15} {count:>3} ({pct:.0f}%)")

    print("\n  REQUESTING AGENTS")
    print("  " + "-"*40)
    for agent, count in agents.most_common():
        print(f"  {agent:<30} {count:>3} requests")

    print("\n  RECENT RECOMMENDATIONS (last 5)")
    print("  " + "-"*40)
    for row in rows[-5:]:
        ts, agent, request, service, conf = row
        print(f"\n  [{ts[:19]}] {agent}")
        print(f"  Q: {request[:60]}{'...' if len(request)>60 else ''}")
        print(f"  → {service} ({conf})")

    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    run()
