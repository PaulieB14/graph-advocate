#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# build_dashboard_v2.sh — Full x402 ecosystem dashboard with:
#   - All 27 facilitators × 112 wallet addresses (per x402-omnigraph registry)
#   - Inline agentic.market category enrichment (50 services as VALUES)
#   - Inline facilitator name→address map (27 names)
#   - The Graph subgraph credits at the top
#   - Compact layout: 4 counter tiles per row + wide charts
#
# Usage:  DUNE_API_KEY=<key> bash dune/build_dashboard_v2.sh
# ════════════════════════════════════════════════════════════════════════
set -euo pipefail

DUNE="${DUNE:-/Users/paulbarba/.local/bin/dune}"
DASH_NAME="${DASH_NAME:-x402 on Base · Powered by The Graph}"

if [ -z "${DUNE_API_KEY:-}" ]; then
  echo "ERROR: export DUNE_API_KEY=<your-key> first."; exit 1
fi

mkquery() {
  local NAME="$1"; local SQL="$2"; local DESC="$3"
  local QID
  QID=$($DUNE query create --name "$NAME" --description "$DESC" --sql "$SQL" -o json 2>/dev/null | \
    /usr/bin/python3 -c "import json,sys;print(json.load(sys.stdin).get('query_id',''))")
  if [ -z "$QID" ]; then echo "  ✗ failed: $NAME" >&2; exit 1; fi
  echo "  ✓ query $QID: $NAME" >&2
  echo "$QID"
}

mkviz() {
  local QID="$1"; local NAME="$2"; local TYPE="$3"; local OPTS="$4"
  local VID
  VID=$($DUNE viz create --query-id "$QID" --name "$NAME" --type "$TYPE" --options "$OPTS" -o json 2>/dev/null | \
    /usr/bin/python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('id') or '')")
  if [ -z "$VID" ]; then echo "  ✗ failed viz: $NAME" >&2; exit 1; fi
  echo "  ✓ viz $VID: $NAME" >&2
  echo "$VID"
}

USDC='0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'

# ── Inline facilitator name→address map (CTE) ─────────────────────────
# Derived from PaulieB14/x402-omnigraph/broadcast/DeployRegistry.s.sol/8453
FACS_CTE="WITH facilitators(facilitator, addr) AS (VALUES
  ('Coinbase', 0x8f5cb67b49555e614892b7233cfddebfb746e531),
  ('Coinbase', 0x68a96f41ff1e9f2e7b591a931a4ad224e7c07863),
  ('Coinbase', 0xa32ccda98ba7529705a059bd2d213da8de10d101),
  ('Coinbase', 0x97acce27d5069544480bde0f04d9f47d7422a016),
  ('Coinbase', 0x67b9ce703d9ce658d7c4ac3c289cea112fe662af),
  ('Coinbase', 0xdbdf3d8ed80f84c35d01c6c9f9271761bad90ba6),
  ('Coinbase', 0x9aae2b0d1b9dc55ac9bab9556f9a26cb64995fb9),
  ('Coinbase', 0x3a70788150c7645a21b95b7062ab1784d3cc2104),
  ('Coinbase', 0x708e57b6650a9a741ab39cae1969ea1d2d10eca1),
  ('Coinbase', 0xce82eeec8e98e443ec34fda3c3e999cbe4cb6ac2),
  ('Coinbase', 0x7f6d822467df2a85f792d4508c5722ade96be056),
  ('Coinbase', 0x001ddabba5782ee48842318bd9ff4008647c8d9c),
  ('Coinbase', 0x9c09faa49c4235a09677159ff14f17498ac48738),
  ('Coinbase', 0xcbb10c30a9a72fae9232f41cbbd566a097b4e03a),
  ('Coinbase', 0x9fb2714af0a84816f5c6322884f2907e33946b88),
  ('Coinbase', 0x47d8b3c9717e976f31025089384f23900750a5f4),
  ('Coinbase', 0x94701e1df9ae06642bf6027589b8e05dc7004813),
  ('Coinbase', 0x552300992857834c0ad41c8e1a6934a5e4a2e4ca),
  ('Coinbase', 0xd7469bf02d221968ab9f0c8b9351f55f8668ac4f),
  ('Coinbase', 0x88800e08e20b45c9b1f0480cf759b5bf2f05180c),
  ('Coinbase', 0x6831508455a716f987782a1ab41e204856055cc2),
  ('Coinbase', 0xdc8fbad54bf5151405de488f45acd555517e0958),
  ('Coinbase', 0x91d313853ad458addda56b35a7686e2f38ff3952),
  ('Coinbase', 0xadd5585c776b9b0ea77e9309c1299a40442d820f),
  ('Coinbase', 0x4ffeffa616a1460570d1eb0390e264d45a199e91),
  ('AurraCloud', 0x222c4367a2950f3b53af260e111fc3060b0983ff),
  ('AurraCloud', 0xb70c4fe126de09bd292fe3d1e40c6d264ca6a52a),
  ('AurraCloud', 0xd348e724e0ef36291a28dfeccf692399b0e179f8),
  ('Thirdweb', 0x80c08de1a05df2bd633cf520754e40fde3c794d3),
  ('Thirdweb', 0xaaca1ba9d2627cbc0739ba69890c30f95de046e4),
  ('Thirdweb', 0xa1822b21202a24669eaf9277723d180cd6dae874),
  ('Thirdweb', 0xec10243b54df1a71254f58873b389b7ecece89c2),
  ('Thirdweb', 0x052aaae3cad5c095850246f8ffb228354c56752a),
  ('Thirdweb', 0x91ddea05f741b34b63a7548338c90fc152c8631f),
  ('Thirdweb', 0xea52f2c6f6287f554f9b54c5417e1e431fe5710e),
  ('Thirdweb', 0x3a5ca1c6aa6576ae9c1c0e7fa2b4883346bc5aa0),
  ('Thirdweb', 0x7e20b62bf36554b704774afb0fcc0ae8f899213b),
  ('Thirdweb', 0xd88a9a58806b895ff06744082c6a20b9d7184b0f),
  ('X402rs', 0xd8dfc729cbd05381647eb5540d756f4f8ad63eec),
  ('X402rs', 0x76eee8f0acabd6b49f1cc4e9656a0c8892f3332e),
  ('X402rs', 0x97d38aa5de015245dcca76305b53abe6da25f6a5),
  ('X402rs', 0x0168f80e035ea68b191faf9bfc12778c87d92008),
  ('X402rs', 0x5e437bee4321db862ac57085ea5eb97199c0ccc5),
  ('X402rs', 0xc19829b32324f116ee7f80d193f99e445968499a),
  ('PayAI', 0xc6699d2aada6c36dfea5c248dd70f9cb0235cb63),
  ('PayAI', 0xb2bd29925cbbcea7628279c91945ca5b98bf371b),
  ('PayAI', 0x25659315106580ce2a787ceec5efb2d347b539c9),
  ('PayAI', 0xb8f41cb13b1f213da1e94e1b742ec1323235c48f),
  ('PayAI', 0xe575fa51af90957d66fab6d63355f1ed021b887b),
  ('PayAI', 0x03a3f7ce8e21e6f8d9fa14c67d8876b2470dc2f1),
  ('PayAI', 0x675707bc7d03089f820c1b7d49f7480083e8f4df),
  ('PayAI', 0xf46833d4ac4f0f1405cc05c30edfd86770f721c9),
  ('PayAI', 0x2daaef6f941de214bf7d6daf322bc6bc7406accb),
  ('PayAI', 0x2fae4026a31f19183947f0a6045ef975ebfa9ca8),
  ('PayAI', 0xe299c486066739c4a31609e1268d93229632dd47),
  ('PayAI', 0x6ccf245c883f9f3c6caee0687aa61daf7bc96e32),
  ('PayAI', 0xaf990eef9846b63d896056050fdc0b28bca9c24b),
  ('PayAI', 0x489c40fc3c2a19ad8cb275b7dd6aa194e9219c4f),
  ('PayAI', 0x9df61a719ddae27c20a63a417271cc2c704654bd),
  ('Daydreams', 0x279e08f711182c79ba6d09669127a426228a4653),
  ('Daydreams', 0x1363c7ff51ccce10258a7f7bddd63baab6aaf678),
  ('Heurist', 0xb578b7db22581507d62bdbeb85e06acd1be09e11),
  ('Heurist', 0x021cc47adeca6673def958e324ca38023b80a5be),
  ('Heurist', 0x3f61093f61817b29d9556d3b092e67746af8cdfd),
  ('Heurist', 0x290d8b8edcafb25042725cb9e78bcac36b8865f8),
  ('Heurist', 0x612d72dc8402bba997c61aa82ce718ea23b2df5d),
  ('Heurist', 0x1fc230ee3c13d0d520d49360a967dbd1555c8326),
  ('Heurist', 0x48ab4b0af4ddc2f666a3fcc43666c793889787a3),
  ('Heurist', 0xd97c12726dcf994797c981d31cfb243d231189fb),
  ('Heurist', 0x90d5e567017f6c696f1916f4365dd79985fce50f),
  ('Questflow', 0x724efafb051f17ae824afcdf3c0368ae312da264),
  ('Questflow', 0xa9a54ef09fc8b86bc747cec6ef8d6e81c38c6180),
  ('Questflow', 0x4638bc811c93bf5e60deed32325e93505f681576),
  ('Questflow', 0xd7d91a42dfadd906c5b9ccde7226d28251e4cd0f),
  ('Questflow', 0x4544b535938b67d2a410a98a7e3b0f8f68921ca7),
  ('Questflow', 0x59e8014a3b884392fbb679fe461da07b18c1ff81),
  ('Questflow', 0xe6123e6b389751c5f7e9349f3d626b105c1fe618),
  ('Questflow', 0xf70e7cb30b132fab2a0a5e80d41861aa133ea21b),
  ('Questflow', 0x90da501fdbec74bb0549100967eb221fed79c99b),
  ('Questflow', 0xce7819f0b0b871733c933d1f486533bab95ec47b),
  ('CodeNut', 0x8d8fa42584a727488eeb0e29405ad794a105bb9b),
  ('CodeNut', 0x87af99356d774312b73018b3b6562e1ae0e018c9),
  ('CodeNut', 0x65058cf664d0d07f68b663b0d4b4f12a5e331a38),
  ('CodeNut', 0x88e13d4c764a6c840ce722a0a3765f55a85b327e),
  ('Meridian', 0x8e7769d440b3460b92159dd9c6d17302b036e2d6),
  ('Meridian', 0x3210d7b21bfe1083c9dddbe17e8f947c9029a584),
  ('OpenX402', 0x97316fa4730bc7d3b295234f8e4d04a0a4c093e8),
  ('OpenX402', 0x97db9b5291a218fc77198c285cefdc943ef74917),
  ('Virtuals Protocol', 0x80735b3f7808e2e229ace880dbe85e80115631ca),
  ('Corbits', 0x06f0bfd2c8f36674df5cde852c1eed8025c268c9),
  ('Dexter', 0x40272e2eac848ea70db07fd657d799bd309329c4),
  ('Mogami', 0xfe0920a0a7f0f8a1ec689146c30c3bbef439bf8a),
  ('402104', 0x73b2b8df52fbe7c40fe78db52e3dffdd5db5ad07),
  ('xEcho', 0x3be45f576696a2fd5a93c1330cd19f1607ab311d),
  ('Ultravioleta DAO', 0x103040545ac5031a11e8c03dd11324c7333a13c7),
  ('Treasure', 0xe07e9cbf9a55d02e3ac356ed4706353d98c5a618),
  ('AnySpend', 0x179761d9eed0f0d1599330cc94b0926e68ae87f1),
  ('Polymer', 0x66c40946b0dffd04be467e18309857307ecd37cb),
  ('Openmid', 0x16e47d275198ed65916a560bab4af6330c36ae09),
  ('Primer', 0x37dfb4033d5dd98fd335f24d0d42e8fe68d587d6),
  ('x402 Jobs', 0x51fec16843e49b99aaf9814e525aee1756e66a62),
  ('OpenFacilitator', 0x7c766f5fd9ab3dc09acad5ecfacc99c4781efe29),
  ('RelAI', 0x1892f72fdb3a966b2ad8595aa5f7741ef72d6085),
  ('Bitrefill', 0x15e2e2da7539ef1f652aa3c1d6142a535aa3d7ea),
  ('Cascade', 0x2bb201f1bb056eb738718bd7a3ad1bef24b883bb)
)"

# Base settle event template — reusable WHERE clause
SETTLE_FROM_FAC="JOIN base.transactions tx ON tx.hash = t.evt_tx_hash
JOIN facilitators f ON f.addr = tx.\"from\"
WHERE t.contract_address = ${USDC}
  AND t.evt_block_time >= NOW() - INTERVAL '30' DAY"

echo ""
echo "═══ Creating v2 queries (5 panels, real addresses, all 27 facilitators) ═══"

# ── Q1: Headline hero stats ──
Q1_SQL="${FACS_CTE}
SELECT
  COUNT(*)                                AS tx_count,
  SUM(CAST(t.value AS DOUBLE) / 1e6)      AS volume_usdc,
  COUNT(DISTINCT t.\"to\")                 AS unique_merchants,
  COUNT(DISTINCT t.\"from\")               AS unique_buyers,
  COUNT(DISTINCT f.facilitator)            AS active_facilitators,
  APPROX_PERCENTILE(CAST(t.value AS DOUBLE) / 1e6, 0.50) AS median_price_usdc
FROM erc20_base.evt_transfer t
${SETTLE_FROM_FAC}"

Q1_ID=$(mkquery "x402 Base · 30d hero (all facilitators)" "$Q1_SQL" "30-day x402 ecosystem stats across all 27 known facilitators on Base")
V_TX=$(mkviz   "$Q1_ID" "Transactions"  counter '{"counterColName":"tx_count","rowNumber":1,"stringDecimal":0,"stringPrefix":"","stringSuffix":"","counterLabel":"30D Txs","coloredPositiveValues":false,"coloredNegativeValues":false}')
V_VOL=$(mkviz  "$Q1_ID" "Volume"        counter '{"counterColName":"volume_usdc","rowNumber":1,"stringDecimal":2,"stringPrefix":"$","stringSuffix":"","counterLabel":"30D Volume","coloredPositiveValues":false,"coloredNegativeValues":false}')
V_MER=$(mkviz  "$Q1_ID" "Merchants"     counter '{"counterColName":"unique_merchants","rowNumber":1,"stringDecimal":0,"stringPrefix":"","stringSuffix":"","counterLabel":"Merchants","coloredPositiveValues":false,"coloredNegativeValues":false}')
V_BUY=$(mkviz  "$Q1_ID" "Buyers"        counter '{"counterColName":"unique_buyers","rowNumber":1,"stringDecimal":0,"stringPrefix":"","stringSuffix":"","counterLabel":"Buyers","coloredPositiveValues":false,"coloredNegativeValues":false}')

# ── Q2: Daily volume time series (stacked area by facilitator) ──
Q2_SQL="${FACS_CTE}
SELECT
  DATE_TRUNC('day', t.evt_block_time)     AS day,
  f.facilitator,
  SUM(CAST(t.value AS DOUBLE) / 1e6)      AS volume_usdc,
  COUNT(*)                                AS tx_count
FROM erc20_base.evt_transfer t
${SETTLE_FROM_FAC}
GROUP BY 1, 2
ORDER BY 1"

Q2_ID=$(mkquery "x402 Base · daily volume by facilitator" "$Q2_SQL" "Stacked daily volume per facilitator")
V_DAILY=$(mkviz "$Q2_ID" "Daily Volume by Facilitator" chart '{"globalSeriesType":"area","sortX":true,"legend":{"enabled":true},"series":{"stacking":"normal"},"xAxis":{"title":{"text":"Day"}},"yAxis":[{"title":{"text":"Volume (USDC)"}}],"groupBy":"facilitator","columnMapping":{"day":"x","volume_usdc":"y"},"seriesOptions":{}}')

# ── Q3: Facilitator leaderboard (table) ──
Q3_SQL="${FACS_CTE}
SELECT
  f.facilitator,
  COUNT(*)                                AS tx_count,
  SUM(CAST(t.value AS DOUBLE) / 1e6)      AS volume_usdc,
  COUNT(DISTINCT t.\"to\")                 AS unique_merchants,
  COUNT(DISTINCT t.\"from\")               AS unique_buyers,
  AVG(CAST(t.value AS DOUBLE) / 1e6)      AS avg_price_usdc,
  MAX(t.evt_block_time)                   AS last_activity
FROM erc20_base.evt_transfer t
${SETTLE_FROM_FAC}
GROUP BY 1
ORDER BY volume_usdc DESC"

Q3_ID=$(mkquery "x402 Base · facilitator leaderboard" "$Q3_SQL" "Per-facilitator volume + tx + buyer/seller counts last 30d")
V_FAC=$(mkviz "$Q3_ID" "Facilitator Leaderboard" table '{"itemsPerPage":15,"columns":[{"name":"facilitator","title":"Facilitator","type":"normal","alignContent":"left","isHidden":false},{"name":"volume_usdc","title":"30d Volume","type":"normal","alignContent":"right","isHidden":false,"formatNumber":"0,0.00"},{"name":"tx_count","title":"Tx","type":"normal","alignContent":"right","isHidden":false},{"name":"unique_merchants","title":"Merchants","type":"normal","alignContent":"right","isHidden":false},{"name":"unique_buyers","title":"Buyers","type":"normal","alignContent":"right","isHidden":false},{"name":"avg_price_usdc","title":"Avg Price","type":"normal","alignContent":"right","isHidden":false,"formatNumber":"0,0.0000"},{"name":"last_activity","title":"Last Active","type":"normal","alignContent":"left","isHidden":false}]}')

# ── Q4: Facilitator pie chart by volume ──
Q4_SQL="${FACS_CTE}
SELECT
  f.facilitator,
  SUM(CAST(t.value AS DOUBLE) / 1e6) AS volume_usdc
FROM erc20_base.evt_transfer t
${SETTLE_FROM_FAC}
GROUP BY 1
ORDER BY volume_usdc DESC"

Q4_ID=$(mkquery "x402 Base · share of volume per facilitator" "$Q4_SQL" "Pie chart of who holds what % of x402 economy")
V_PIE=$(mkviz "$Q4_ID" "Facilitator Volume Share" chart '{"globalSeriesType":"pie","sortX":false,"showDataLabels":true,"columnMapping":{"facilitator":"x","volume_usdc":"y"},"seriesOptions":{}}')

# ── Q5: Top merchants (enriched with inline agentic.market data) ──
# Inline first 50 services from agentic.market for category enrichment
AMARKET_CTE=$(/usr/bin/python3 <<'PY'
import csv
rows = []
seen = set()
with open('/Users/paulbarba/graph-advocate/dune/agentic_market_services.csv') as f:
    for r in csv.DictReader(f):
        pt = (r.get('pay_to') or '').lower()
        if not pt or not pt.startswith('0x') or len(pt) != 42: continue
        if pt in seen: continue
        seen.add(pt)
        name = (r.get('name','') or '').replace("'", "''")[:60]
        cat = (r.get('category','') or '').replace("'", "''")[:40]
        rows.append(f"  ({pt}, '{name}', '{cat}')")
        if len(rows) >= 50: break
print(",\n".join(rows))
PY
)

Q5_SQL="${FACS_CTE},
amarket(pay_to, name, category) AS (VALUES
${AMARKET_CTE}
)
SELECT
  t.\"to\" AS merchant,
  COALESCE(am.name, '—') AS service_name,
  COALESCE(am.category, 'Uncategorized') AS category,
  COUNT(*) AS tx_count,
  SUM(CAST(t.value AS DOUBLE) / 1e6) AS volume_usdc,
  COUNT(DISTINCT t.\"from\") AS unique_buyers,
  AVG(CAST(t.value AS DOUBLE) / 1e6) AS avg_price_usdc
FROM erc20_base.evt_transfer t
${SETTLE_FROM_FAC}
LEFT JOIN amarket am ON am.pay_to = t.\"to\"
GROUP BY 1, 2, 3
ORDER BY volume_usdc DESC
LIMIT 50"

Q5_ID=$(mkquery "x402 Base · top 50 merchants enriched" "$Q5_SQL" "Top 50 x402 merchants with agentic.market name + category enrichment")
V_TOP=$(mkviz "$Q5_ID" "Top Merchants (with agentic.market enrichment)" table '{"itemsPerPage":15,"columns":[{"name":"service_name","title":"Service","type":"normal","alignContent":"left","isHidden":false},{"name":"category","title":"Category","type":"normal","alignContent":"left","isHidden":false},{"name":"merchant","title":"Wallet","type":"normal","alignContent":"left","isHidden":false},{"name":"volume_usdc","title":"Volume","type":"normal","alignContent":"right","isHidden":false,"formatNumber":"0,0.00"},{"name":"tx_count","title":"Txs","type":"normal","alignContent":"right","isHidden":false},{"name":"unique_buyers","title":"Buyers","type":"normal","alignContent":"right","isHidden":false},{"name":"avg_price_usdc","title":"Avg \$","type":"normal","alignContent":"right","isHidden":false,"formatNumber":"0,0.0000"}]}')

# ── Q6: Pricing distribution ──
Q6_SQL="${FACS_CTE}
SELECT
  CASE
    WHEN CAST(t.value AS DOUBLE) / 1e6 < 0.001 THEN '< \$0.001'
    WHEN CAST(t.value AS DOUBLE) / 1e6 < 0.01  THEN '\$0.001-\$0.01'
    WHEN CAST(t.value AS DOUBLE) / 1e6 < 0.10  THEN '\$0.01-\$0.10'
    WHEN CAST(t.value AS DOUBLE) / 1e6 < 1.00  THEN '\$0.10-\$1'
    WHEN CAST(t.value AS DOUBLE) / 1e6 < 10.0  THEN '\$1-\$10'
    ELSE '\$10+'
  END                                AS price_bucket,
  COUNT(*)                            AS tx_count
FROM erc20_base.evt_transfer t
${SETTLE_FROM_FAC}
GROUP BY 1
ORDER BY MIN(CAST(t.value AS DOUBLE)) ASC"

Q6_ID=$(mkquery "x402 Base · pricing distribution" "$Q6_SQL" "Histogram of x402 settlement prices")
V_PRICE=$(mkviz "$Q6_ID" "Pricing Distribution" chart '{"globalSeriesType":"column","sortX":false,"legend":{"enabled":false},"xAxis":{"title":{"text":"Price Bucket"}},"yAxis":[{"title":{"text":"# Calls"}}],"columnMapping":{"price_bucket":"x","tx_count":"y"},"seriesOptions":{"tx_count":{"type":"column","yAxis":0,"color":"#7c8cf6"}}}')

# ── Q7: Category breakdown (volume per agentic.market category) ──
Q7_SQL="${FACS_CTE},
amarket(pay_to, name, category) AS (VALUES
${AMARKET_CTE}
)
SELECT
  COALESCE(am.category, 'Uncategorized') AS category,
  COUNT(DISTINCT t.\"to\") AS service_count,
  COUNT(*) AS tx_count,
  SUM(CAST(t.value AS DOUBLE) / 1e6) AS volume_usdc
FROM erc20_base.evt_transfer t
${SETTLE_FROM_FAC}
LEFT JOIN amarket am ON am.pay_to = t.\"to\"
GROUP BY 1
ORDER BY volume_usdc DESC"

Q7_ID=$(mkquery "x402 Base · category breakdown" "$Q7_SQL" "Volume per agentic.market category")
V_CAT=$(mkviz "$Q7_ID" "Volume by Category" chart '{"globalSeriesType":"column","sortX":false,"legend":{"enabled":false},"xAxis":{"title":{"text":"Category"}},"yAxis":[{"title":{"text":"Volume (USDC)"}}],"columnMapping":{"category":"x","volume_usdc":"y"},"seriesOptions":{"volume_usdc":{"type":"column","yAxis":0,"color":"#22d3ee"}}}')

echo ""
echo "═══ Creating dashboard ═══"
# 4 counter tiles (compact, 4-per-row) + wide charts
ALL_VIZ="${V_TX},${V_VOL},${V_MER},${V_BUY},${V_DAILY},${V_PIE},${V_FAC},${V_TOP},${V_PRICE},${V_CAT}"

TEXT='[{"text":"# x402 Ecosystem on Base · Powered by The Graph\n\nLive view of the entire x402 micropayment economy on Base — **27 facilitators**, **112 wallet addresses**, **all merchants**. \n\n**Powered by:** [`erc20_base.evt_transfer`](https://docs.dune.com) (Dune-indexed) · [Agent0 ERC-8004 subgraph](https://thegraph.com/explorer?search=agent0) · [The Graph Token API](https://token-api.thegraph.com) · [agentic.market catalog](https://agentic.market) · facilitator registry from [PaulieB14/x402-omnigraph](https://github.com/PaulieB14/x402-omnigraph) (sourced from [Merit-Systems/x402scan](https://github.com/Merit-Systems/x402scan)).\n\n*Built by [Graph Advocate](https://graphadvocate.com) — the routing agent for The Graph Protocol. [Run your own paid agent on x402](https://graphadvocate.com/route).*"}]'

DASH_OUT=$($DUNE dashboard create \
  --name "$DASH_NAME" \
  --visualization-ids "$ALL_VIZ" \
  --text-widgets "$TEXT" \
  --columns-per-row 2 \
  -o json 2>&1)

DASH_ID=$(echo "$DASH_OUT" | /usr/bin/python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('dashboard_id') or d.get('id') or '')")
DASH_URL=$(echo "$DASH_OUT" | /usr/bin/python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('dashboard_url') or '')")

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ v2 dashboard created"
echo "  ID:  $DASH_ID"
echo "  URL: ${DASH_URL:-https://dune.com/dashboards/$DASH_ID}"
echo "  Queries:    $Q1_ID  $Q2_ID  $Q3_ID  $Q4_ID  $Q5_ID  $Q6_ID  $Q7_ID"
echo "  Viz: $ALL_VIZ"
echo "═══════════════════════════════════════════════════"
