"""Generate dashboard.html from the SQLite log."""
import sqlite3, json
from collections import Counter
from datetime import datetime

DB = "/Users/paulbarba/graph-advocate/recommendations.db"
OUT = "/Users/paulbarba/graph-advocate/dashboard.html"

def generate():
    try:
        conn = sqlite3.connect(DB)
        rows = conn.execute(
            "SELECT timestamp, requesting_agent, request, service_chosen, confidence FROM recommendations ORDER BY timestamp"
        ).fetchall()
        conn.close()
    except Exception:
        rows = []

    total = len(rows)
    services = Counter(r[3] for r in rows)
    confidence = Counter(r[4] for r in rows)

    service_colors = {
        "token-api": "#10b981",
        "subgraph-registry": "#6366f1",
        "substreams": "#f59e0b",
        "graph-aave-mcp": "#3b82f6",
        "graph-lending-mcp": "#8b5cf6",
        "graph-polymarket-mcp": "#ec4899",
        "predictfun-mcp": "#14b8a6",
        "unknown": "#6b7280",
    }

    # Build service bars
    service_rows = ""
    for svc, count in services.most_common():
        pct = round(count / total * 100) if total else 0
        color = service_colors.get(svc, "#6b7280")
        service_rows += f"""
        <tr>
          <td>{svc}</td>
          <td><div class="bar" style="width:{pct}%;background:{color}"></div></td>
          <td>{count}</td>
          <td>{pct}%</td>
        </tr>"""

    # Recent 10
    recent_rows = ""
    for r in reversed(rows[-10:]):
        ts, agent, request, service, conf = r
        color = service_colors.get(service, "#6b7280")
        badge = f'<span class="badge" style="background:{color}">{service}</span>'
        conf_class = {"high": "conf-high", "medium": "conf-med", "low": "conf-low"}.get(conf, "")
        recent_rows += f"""
        <tr>
          <td class="ts">{ts[:19]}</td>
          <td>{agent}</td>
          <td class="req">{request[:70]}{'…' if len(request)>70 else ''}</td>
          <td>{badge}</td>
          <td class="{conf_class}">{conf}</td>
        </tr>"""

    high_pct = round(confidence.get("high", 0) / total * 100) if total else 0
    first_ts = rows[0][0][:19] if rows else "—"
    last_ts = rows[-1][0][:19] if rows else "—"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Graph Advocate — Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f172a; color: #e2e8f0; padding: 2rem; }}
  h1 {{ font-size: 1.6rem; font-weight: 700; color: #f8fafc; margin-bottom: .25rem; }}
  .subtitle {{ color: #64748b; font-size: .9rem; margin-bottom: 2rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
           gap: 1rem; margin-bottom: 2rem; }}
  .card {{ background: #1e293b; border-radius: 12px; padding: 1.25rem; }}
  .card .num {{ font-size: 2rem; font-weight: 700; color: #f8fafc; }}
  .card .label {{ font-size: .8rem; color: #64748b; margin-top: .25rem; }}
  .card .sub {{ font-size: .75rem; color: #94a3b8; margin-top: .5rem; }}
  h2 {{ font-size: 1.1rem; font-weight: 600; color: #f8fafc; margin: 1.5rem 0 .75rem; }}
  table {{ width: 100%; border-collapse: collapse; background: #1e293b;
           border-radius: 12px; overflow: hidden; }}
  th {{ text-align: left; padding: .75rem 1rem; font-size: .75rem; font-weight: 600;
        color: #64748b; text-transform: uppercase; letter-spacing: .05em;
        border-bottom: 1px solid #334155; }}
  td {{ padding: .65rem 1rem; font-size: .85rem; border-bottom: 1px solid #1e293b; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #243044; }}
  .bar {{ height: 10px; border-radius: 5px; min-width: 4px; }}
  .badge {{ display: inline-block; padding: .2rem .5rem; border-radius: 6px;
            font-size: .75rem; font-weight: 600; color: #fff; }}
  .conf-high {{ color: #10b981; font-weight: 600; }}
  .conf-med  {{ color: #f59e0b; font-weight: 600; }}
  .conf-low  {{ color: #ef4444; font-weight: 600; }}
  .ts {{ color: #64748b; font-size: .78rem; font-family: monospace; }}
  .req {{ max-width: 320px; color: #94a3b8; }}
  .updated {{ color: #475569; font-size: .75rem; margin-top: 2rem; text-align: right; }}
</style>
</head>
<body>
<h1>Graph Advocate</h1>
<p class="subtitle">Routing performance dashboard · {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

<div class="grid">
  <div class="card">
    <div class="num">{total}</div>
    <div class="label">Total Recommendations</div>
    <div class="sub">{first_ts} → {last_ts}</div>
  </div>
  <div class="card">
    <div class="num">{high_pct}%</div>
    <div class="label">High Confidence</div>
    <div class="sub">{confidence.get('high',0)} of {total} responses</div>
  </div>
  <div class="card">
    <div class="num">{len(services)}</div>
    <div class="label">Services Routed To</div>
    <div class="sub">{', '.join(list(services.keys())[:2])}…</div>
  </div>
  <div class="card">
    <div class="num">{services.most_common(1)[0][0] if services else '—'}</div>
    <div class="label">Top Service</div>
    <div class="sub">{services.most_common(1)[0][1] if services else 0} requests</div>
  </div>
</div>

<h2>Routing Breakdown</h2>
<table>
  <thead><tr><th>Service</th><th>Volume</th><th>Count</th><th>%</th></tr></thead>
  <tbody>{service_rows}</tbody>
</table>

<h2>Recent Recommendations</h2>
<table>
  <thead><tr><th>Timestamp</th><th>Agent</th><th>Request</th><th>Routed To</th><th>Confidence</th></tr></thead>
  <tbody>{recent_rows}</tbody>
</table>

<p class="updated">Regenerate: <code>bash run.sh generate_dashboard.py</code></p>
</body>
</html>"""

    with open(OUT, "w") as f:
        f.write(html)
    print(f"Dashboard written to {OUT}")

if __name__ == "__main__":
    generate()
