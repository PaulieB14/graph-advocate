#!/bin/bash
# Daily GA audit — fires at 06:07 ET via launchd com.paul.ga-daily-audit.
# Shell-only: gathers signals + notifies. Auto-fix lives in the parallel
# Claude cron (which only fires if Claude session is alive). This file is
# the durable always-fires backup.
#
# Outputs:
#   - /tmp/ga-daily/audit-YYYYMMDD.md     human-readable summary
#   - /tmp/ga-daily/snapshot.json         baseline for next-day delta
#   - macOS notification on completion (loud if issues > 0)

set -euo pipefail
OUT_DIR=/tmp/ga-daily
TODAY=$(date +%Y%m%d)
REPORT="$OUT_DIR/audit-$TODAY.md"
SNAP="$OUT_DIR/snapshot.json"
PREV_SNAP_BAK="$OUT_DIR/snapshot-prev.json"
mkdir -p "$OUT_DIR"

# Save previous snapshot for delta comparison
if [ -f "$SNAP" ]; then
    cp "$SNAP" "$PREV_SNAP_BAK"
fi

# Resolve admin token from Railway (never logged)
cd /Users/paulbarba/graph-advocate
PROD_TOKEN=$(railway variables --kv 2>/dev/null | grep "^ADMIN_TOKEN=" | head -1 | cut -d= -f2- || echo "")
if [ -z "$PROD_TOKEN" ]; then
    echo "ERROR: could not read ADMIN_TOKEN from railway" > "$REPORT"
    osascript -e 'display notification "GA daily audit: token unavailable" with title "GA Audit FAILED" sound name "Basso"'
    exit 1
fi

# Pull parallel
curl -sS https://graphadvocate.com/dashboard/data > "$OUT_DIR/dashboard.json" &
curl -sS -H "Authorization: Bearer $PROD_TOKEN" 'https://graphadvocate.com/logs?limit=400' > "$OUT_DIR/logs.json" &
curl -sS -H "Authorization: Bearer $PROD_TOKEN" https://graphadvocate.com/quality > "$OUT_DIR/quality.json" &
wait

# Process with Python — same shape as the audit script we use in Claude
python3 <<PYEOF > "$REPORT"
import json, os
from datetime import datetime, timezone, timedelta
from collections import Counter

d = json.load(open('$OUT_DIR/dashboard.json'))
logs = json.load(open('$OUT_DIR/logs.json'))
qa = json.load(open('$OUT_DIR/quality.json'))
prev = None
prev_path = '$PREV_SNAP_BAK'
if os.path.exists(prev_path):
    try:
        prev = json.load(open(prev_path))
    except Exception:
        prev = None

snap = {
    'ts': datetime.now(timezone.utc).isoformat(),
    'total': d['total'],
    'hero_24h_requests': d['hero_24h']['requests'],
    'x402_log_count': d['onchain']['x402_log_count'],
    'usdc_paid_lifetime': d['onchain']['usdc_paid_lifetime'],
    'usdc_balance_inbound': d['onchain']['usdc_balance'],
    'quality_lifetime_avg': d['quality_summary']['avg_score'],
    'quality_24h_avg': d['quality_summary'].get('last_24h_avg'),
    'quality_24h_count': d['quality_summary'].get('last_24h_count', 0),
    'repeat_payer_count': len(d.get('repeat_payers') or []),
}

def delta(now, before, key):
    if not before or before.get(key) is None: return ''
    diff = now[key] - before[key]
    if isinstance(diff, float): return f"  ({diff:+.4f})"
    return f"  ({diff:+})"

print(f"# GA Daily Audit — {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}\n")

# 24h paid breakdown
parsed = []
for l in logs:
    try:
        ts = datetime.fromisoformat((l.get('ts') or '').replace('Z','+00:00'))
        parsed.append((ts, l))
    except: pass
parsed.sort(key=lambda x: x[0], reverse=True)
issues = []
if parsed:
    cutoff = parsed[0][0] - timedelta(hours=24)
    last24 = [l for ts,l in parsed if ts >= cutoff]
    by_svc = Counter(l.get('service') for l in last24)
    paid_real = [l for l in last24 if (l.get('service') or '') not in ('payment-required','introduction','out-of-scope') and not (l.get('service') or '').startswith('agent-exchange')]
    failed = [l for l in last24 if l.get('service') == 'x402-failed']
    if failed:
        issues.append(f"x402-failed: {len(failed)} (CHECK)")
        # Look for regression of 617fa89 fix (exception_type='str')
        regression = [l for l in failed if isinstance(l.get('response'), dict) and l['response'].get('exception_type') == 'str']
        if regression:
            issues.append(f"⚠️ REGRESSION: {len(regression)} rows have exception_type='str' (commit 617fa89 should have fixed this)")

snap['issues'] = issues
snap['paid_real_24h'] = len(paid_real) if parsed else 0
snap['x402_failed_24h'] = len(failed) if parsed else 0

# Headline
status = "OK" if not issues else f"⚠️ {len(issues)} ISSUE(S)"
print(f"## Status: {status}\n")
if issues:
    print("### Issues\n")
    for i in issues: print(f"- {i}")
    print()

print("## Deltas vs yesterday\n")
print("| Metric | Now | Δ |")
print("|---|---:|---:|")
def row(label, key, fmt='{}'):
    val = snap.get(key)
    d_str = delta(snap, prev, key) if prev else '  (first)'
    print(f"| {label} | {fmt.format(val) if val is not None else '—'} | {d_str.strip()} |")
row("Total all-time", 'total')
row("Hero 24h reqs", 'hero_24h_requests')
row("x402 settlements", 'x402_log_count')
row("USDC paid lifetime", 'usdc_paid_lifetime', '\${:.4f}')
row("USDC inbound balance", 'usdc_balance_inbound', '\${:.4f}')
row("Quality lifetime avg", 'quality_lifetime_avg')
row("Quality 24h avg", 'quality_24h_avg')
row("Quality 24h count", 'quality_24h_count')
row("Repeat payers", 'repeat_payer_count')
row("Paid real (24h)", 'paid_real_24h')
row("x402 failed (24h)", 'x402_failed_24h')

# Repeat payers panel
repeat = d.get('repeat_payers') or []
print(f"\n## Repeat payers ({len(repeat)})\n")
if repeat:
    print("| Wallet | Calls | USDC | First | Last |")
    print("|---|---:|---:|---|---|")
    for r in repeat:
        print(f"| {r['short']} | {r['call_count']} | \${r['usdc_total']:.4f} | {r['first_seen']} | {r['last_seen']} |")
else:
    print("_(none yet — paid_by_wallet capture started 2026-06-18 via commit 43c6724)_")

# Persist new snapshot
json.dump(snap, open('$SNAP', 'w'), indent=2, default=str)
PYEOF

# Notify
ISSUE_COUNT=$(python3 -c "import json; print(len(json.load(open('$SNAP')).get('issues',[])))")
if [ "$ISSUE_COUNT" = "0" ]; then
    osascript -e 'display notification "GA daily audit: all clear. Report saved." with title "GA Audit OK" sound name "Glass"'
else
    osascript -e "display notification \"GA daily audit: $ISSUE_COUNT issue(s) flagged. See /tmp/ga-daily/audit-$TODAY.md\" with title \"GA Audit FLAGGED\" sound name \"Basso\""
    open "$REPORT" 2>/dev/null || true
fi
