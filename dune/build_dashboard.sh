#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# build_dashboard.sh — Create the agentic.market × ERC-8004 × x402 dashboard
# via Dune CLI (https://github.com/duneanalytics/dune-cli).
#
# Usage:
#   export DUNE_API_KEY=<your-key>
#   bash dune/build_dashboard.sh
#
# What it does:
#   1. Creates 5 saved queries (on-chain only — no CSV upload required)
#   2. Creates one visualization per query
#   3. Creates the dashboard and attaches all viz
#   4. Prints the dashboard URL
#
# Queries that need CSV-uploaded datasets (top merchants enriched, agent
# leaderboard, category breakdown, etc.) are NOT created here — they
# need the 4 CSVs uploaded manually first via Dune UI. Add them later.
# ════════════════════════════════════════════════════════════════════════

set -euo pipefail

DUNE="${DUNE:-/Users/paulbarba/.local/bin/dune}"
DASH_NAME="${DASH_NAME:-x402 Ecosystem on Base · agentic.market view}"

if [ -z "${DUNE_API_KEY:-}" ]; then
  echo "ERROR: export DUNE_API_KEY=<your-key> first."
  exit 1
fi

# ── facilitator addresses (top 5 by volume, hardcoded for v1) ──────────
# Full list of 29 in dune/facilitators.csv. For v1 we hardcode Coinbase
# (87% of ecosystem volume) + four next-biggest into IN clauses.
COINBASE='0x5f6c0fee8a30ca4eddd1aef0c5612fda63d51b62'  # representative — see facilitators.csv
# (We use a multi-address IN list in SQL so v2 can add more without rebuilding.)

# For v1 we'll use the on-chain heuristic: any address from x402scan's
# Coinbase facilitator list. The SQL embeds the list.

run() {
  echo "▸ $*"
  eval "$@"
}

# Helper: create query → echo ID to STDOUT only. Status messages go to STDERR.
mkquery() {
  local NAME="$1"; local SQL="$2"; local DESC="$3"
  local QID
  QID=$($DUNE query create --name "$NAME" --description "$DESC" --sql "$SQL" -o json 2>/dev/null | \
    /usr/bin/python3 -c "import json,sys;print(json.load(sys.stdin).get('query_id',''))")
  if [ -z "$QID" ]; then
    echo "  ✗ failed to create query '$NAME'" >&2
    exit 1
  fi
  echo "  ✓ query $QID: $NAME" >&2
  echo "$QID"
}

# Helper: create viz on a query
mkviz() {
  local QID="$1"; local NAME="$2"; local TYPE="$3"; local OPTS="$4"
  local VID
  VID=$($DUNE viz create --query-id "$QID" --name "$NAME" --type "$TYPE" --options "$OPTS" -o json 2>/dev/null | \
    /usr/bin/python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('id') or d.get('visualization_id') or '')")
  if [ -z "$VID" ]; then
    echo "  ✗ failed to create viz '$NAME' (query $QID)" >&2
    exit 1
  fi
  echo "  ✓ viz $VID: $NAME" >&2
  echo "$VID"
}

# ── Coinbase facilitator addresses (top 25 per facilitators.csv) ───────
# Read from CSV into a SQL IN-list
COINBASE_ADDRS=$(/usr/bin/python3 -c "
import csv
addrs = []
with open('/Users/paulbarba/graph-advocate/dune/facilitators.csv') as f:
    for r in csv.DictReader(f):
        if r['facilitator'] == 'Coinbase' and 'base' in r['chains']:
            addrs.append(r['address'])
print(','.join(repr(a) for a in addrs[:25]))
")

USDC='0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'

echo ""
echo "═══ Creating queries ═══"

# ── Q1: Hero stats — 30d Coinbase facilitator volume on Base ──
Q1_SQL="SELECT
  COUNT(*) AS tx_count,
  SUM(CAST(value AS DOUBLE) / 1e6) AS volume_usdc,
  COUNT(DISTINCT \"to\") AS unique_merchants,
  COUNT(DISTINCT \"from\") AS unique_buyers,
  APPROX_PERCENTILE(CAST(value AS DOUBLE) / 1e6, 0.50) AS median_price_usdc,
  APPROX_PERCENTILE(CAST(value AS DOUBLE) / 1e6, 0.90) AS p90_price_usdc
FROM erc20_base.evt_transfer
WHERE contract_address = ${USDC}
  AND \"from\" IN (${COINBASE_ADDRS})
  AND evt_block_time >= NOW() - INTERVAL '30' DAY"

Q1_ID=$(mkquery "x402 Base · 30d hero stats" "$Q1_SQL" "Last 30 days of x402 settlements via Coinbase facilitator on Base")
V1=$(mkviz "$Q1_ID" "30d Volume" "counter" '{"counterColName":"volume_usdc","rowNumber":1,"stringDecimal":2,"stringPrefix":"$","stringSuffix":"","counterLabel":"30d Volume (USDC)","coloredPositiveValues":false,"coloredNegativeValues":false}')
V2=$(mkviz "$Q1_ID" "30d Transactions" "counter" '{"counterColName":"tx_count","rowNumber":1,"stringDecimal":0,"stringPrefix":"","stringSuffix":"","counterLabel":"30d Transactions","coloredPositiveValues":false,"coloredNegativeValues":false}')
V3=$(mkviz "$Q1_ID" "30d Merchants" "counter" '{"counterColName":"unique_merchants","rowNumber":1,"stringDecimal":0,"stringPrefix":"","stringSuffix":"","counterLabel":"Unique Merchants","coloredPositiveValues":false,"coloredNegativeValues":false}')
V4=$(mkviz "$Q1_ID" "30d Buyers" "counter" '{"counterColName":"unique_buyers","rowNumber":1,"stringDecimal":0,"stringPrefix":"","stringSuffix":"","counterLabel":"Unique Buyers","coloredPositiveValues":false,"coloredNegativeValues":false}')

# ── Q2: Daily volume line chart ──
Q2_SQL="SELECT
  DATE_TRUNC('day', evt_block_time) AS day,
  SUM(CAST(value AS DOUBLE) / 1e6) AS volume_usdc,
  COUNT(*) AS tx_count
FROM erc20_base.evt_transfer
WHERE contract_address = ${USDC}
  AND \"from\" IN (${COINBASE_ADDRS})
  AND evt_block_time >= NOW() - INTERVAL '30' DAY
GROUP BY 1 ORDER BY 1"

Q2_ID=$(mkquery "x402 Base · daily volume" "$Q2_SQL" "Daily x402 settlement volume + tx count")
V5=$(mkviz "$Q2_ID" "Daily Volume" "chart" '{"globalSeriesType":"area","sortX":true,"legend":{"enabled":true},"series":{"stacking":null},"xAxis":{"title":{"text":"Day"}},"yAxis":[{"title":{"text":"Volume (USDC)"}}],"columnMapping":{"day":"x","volume_usdc":"y"},"seriesOptions":{"volume_usdc":{"type":"area","yAxis":0,"zIndex":0,"color":"#22d3ee"}}}')

# ── Q3: Top merchants ──
Q3_SQL="SELECT
  \"to\" AS merchant,
  COUNT(*) AS tx_count,
  SUM(CAST(value AS DOUBLE) / 1e6) AS volume_usdc,
  COUNT(DISTINCT \"from\") AS unique_buyers,
  AVG(CAST(value AS DOUBLE) / 1e6) AS avg_price_usdc,
  MAX(evt_block_time) AS last_paid_at
FROM erc20_base.evt_transfer
WHERE contract_address = ${USDC}
  AND \"from\" IN (${COINBASE_ADDRS})
  AND evt_block_time >= NOW() - INTERVAL '30' DAY
GROUP BY 1
ORDER BY volume_usdc DESC
LIMIT 50"

Q3_ID=$(mkquery "x402 Base · top 50 merchants 30d" "$Q3_SQL" "Top 50 merchants by 30-day x402 revenue on Base")
V6=$(mkviz "$Q3_ID" "Top Merchants" "table" '{"itemsPerPage":25,"columns":[{"name":"merchant","title":"Merchant Wallet","type":"normal","alignContent":"left","isHidden":false},{"name":"volume_usdc","title":"Volume (USDC)","type":"normal","alignContent":"right","isHidden":false,"formatNumber":"0,0.00"},{"name":"tx_count","title":"Tx Count","type":"normal","alignContent":"right","isHidden":false},{"name":"unique_buyers","title":"Buyers","type":"normal","alignContent":"right","isHidden":false},{"name":"avg_price_usdc","title":"Avg Price","type":"normal","alignContent":"right","isHidden":false,"formatNumber":"0,0.0000"},{"name":"last_paid_at","title":"Last Paid","type":"normal","alignContent":"left","isHidden":false}]}')

# ── Q4: Pricing distribution ──
Q4_SQL="SELECT
  CASE
    WHEN CAST(value AS DOUBLE) / 1e6 < 0.001 THEN '< \$0.001'
    WHEN CAST(value AS DOUBLE) / 1e6 < 0.01  THEN '\$0.001-\$0.01'
    WHEN CAST(value AS DOUBLE) / 1e6 < 0.10  THEN '\$0.01-\$0.10'
    WHEN CAST(value AS DOUBLE) / 1e6 < 1.00  THEN '\$0.10-\$1'
    WHEN CAST(value AS DOUBLE) / 1e6 < 10.0  THEN '\$1-\$10'
    ELSE '\$10+'
  END AS price_bucket,
  COUNT(*) AS tx_count
FROM erc20_base.evt_transfer
WHERE contract_address = ${USDC}
  AND \"from\" IN (${COINBASE_ADDRS})
  AND evt_block_time >= NOW() - INTERVAL '30' DAY
GROUP BY 1
ORDER BY MIN(CAST(value AS DOUBLE)) ASC"

Q4_ID=$(mkquery "x402 Base · pricing distribution" "$Q4_SQL" "Histogram of x402 call prices")
V7=$(mkviz "$Q4_ID" "Pricing Distribution" "chart" '{"globalSeriesType":"column","sortX":false,"legend":{"enabled":false},"xAxis":{"title":{"text":"Price Bucket"}},"yAxis":[{"title":{"text":"# Calls"}}],"columnMapping":{"price_bucket":"x","tx_count":"y"},"seriesOptions":{"tx_count":{"type":"column","yAxis":0,"color":"#7c8cf6"}}}')

# ── Q5: Top buyers ──
Q5_SQL="SELECT
  \"from\" AS facilitator_signer,
  COUNT(*) AS tx_count,
  SUM(CAST(value AS DOUBLE) / 1e6) AS volume_usdc,
  COUNT(DISTINCT \"to\") AS unique_merchants
FROM erc20_base.evt_transfer
WHERE contract_address = ${USDC}
  AND \"from\" IN (${COINBASE_ADDRS})
  AND evt_block_time >= NOW() - INTERVAL '30' DAY
GROUP BY 1
ORDER BY volume_usdc DESC"

Q5_ID=$(mkquery "x402 Base · facilitator addresses used" "$Q5_SQL" "Which of Coinbase's 25 facilitator wallets are most active")
V8=$(mkviz "$Q5_ID" "Facilitator Activity" "table" '{"itemsPerPage":25,"columns":[{"name":"facilitator_signer","title":"Wallet","type":"normal","alignContent":"left","isHidden":false},{"name":"volume_usdc","title":"Volume","type":"normal","alignContent":"right","isHidden":false,"formatNumber":"0,0.00"},{"name":"tx_count","title":"Tx","type":"normal","alignContent":"right","isHidden":false},{"name":"unique_merchants","title":"Merchants","type":"normal","alignContent":"right","isHidden":false}]}')

echo ""
echo "═══ Creating dashboard ═══"
# Order: hero counters (V1-V4), daily volume (V5), top merchants (V6),
# pricing distribution (V7), facilitator activity (V8)
ALL_VIZ="${V1},${V2},${V3},${V4},${V5},${V6},${V7},${V8}"

TEXT_WIDGETS=$(cat <<'EOF'
[{"text":"# x402 Ecosystem on Base · agentic.market lens\n\nLive view of the x402 payment economy on Base, with [agentic.market](https://agentic.market) as the curated lens and ERC-8004 as the planned identity layer.\n\n**Data sources:** on-chain `erc20_base.evt_transfer` (Dune-indexed) filtered to Coinbase's 25 facilitator wallets · [agentic.market catalog](https://api.agentic.market/v1/services) · [Agent0 subgraph](https://thegraph.com/explorer?search=agent0) on Base · facilitator address registry from [Merit-Systems/x402scan](https://github.com/Merit-Systems/x402scan).\n\n*This v1 covers Coinbase-facilitator volume only (≈87% of the Base x402 economy). v2 will join in the agentic.market name/category enrichment + ERC-8004 agent identity once the CSV datasets are uploaded.*\n"}]
EOF
)

DASH_OUT=$($DUNE dashboard create \
  --name "$DASH_NAME" \
  --visualization-ids "$ALL_VIZ" \
  --text-widgets "$TEXT_WIDGETS" \
  --columns-per-row 2 \
  -o json 2>&1)
echo "$DASH_OUT" | /usr/bin/head -10
DASH_ID=$(echo "$DASH_OUT" | /usr/bin/python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('dashboard_id') or d.get('id') or '')")
DASH_URL=$(echo "$DASH_OUT" | /usr/bin/python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('dashboard_url') or d.get('url') or '')")

if [ -z "$DASH_ID" ]; then
  echo "  ✗ failed to create dashboard"
  exit 1
fi

# Dune dashboard URLs follow /<user>/<slug-or-id>
echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Dashboard created!"
echo "  Dashboard ID: $DASH_ID"
echo "  URL: ${DASH_URL:-https://dune.com/dashboards/$DASH_ID}"
echo ""
echo "  Query IDs:"
echo "    Q1 hero stats:        $Q1_ID"
echo "    Q2 daily volume:      $Q2_ID"
echo "    Q3 top merchants:     $Q3_ID"
echo "    Q4 pricing dist:      $Q4_ID"
echo "    Q5 facilitator usage: $Q5_ID"
echo ""
echo "  Visualization IDs: $ALL_VIZ"
echo "═══════════════════════════════════════════════════"
