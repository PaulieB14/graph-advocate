#!/usr/bin/env bash
# Graph Advocate demo runner — executes the on-screen actions in order.
#
# Usage:
#   1. Open Tella (or QuickTime) and start screen recording
#   2. In a clean terminal, run: bash demo.sh
#   3. The script pauses between segments so you (or the AI voiceover)
#      can land each beat at the right time
#
# Each segment maps to a section of SCRIPT.md.

set -euo pipefail
BASE="https://graph-advocate-production.up.railway.app"
WALLET="0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86"
USDC_BASE="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

pause_for() {
  # Beat marker — gives you a moment to switch tabs / let voiceover catch up
  echo ""
  read -rp "  ⏎ press enter to advance to next segment..."
  echo ""
}

banner() {
  echo ""
  echo "════════════════════════════════════════════════════════"
  echo "  $1"
  echo "════════════════════════════════════════════════════════"
}

# ── 0:00 — Hook: paid query ──────────────────────────────────────────────────
banner "0:00 — HOOK · agent paying agent"

echo "Step 1: Confirm /tip is gated (returns 402 without payment)"
curl -sS -i -X POST "$BASE/tip" -H "Content-Type: application/json" -d '{}' 2>&1 | head -3
echo ""

echo "Step 2: Pay-per-query via x402 — agent → agent"
echo "(send_paid_query.py uses your test wallet's PK from \$X402_TIP_PK)"
python3 ~/graph-advocate/demo/send_paid_query.py
pause_for

# ── 0:50 — Demo: multi-service routing ───────────────────────────────────────
banner "0:50 — DEMO · 4 queries, 4 services"

queries=(
  "Top Uniswap V3 pools on Ethereum mainnet by TVL"
  "Top 20 USDC holders on Ethereum"
  "Aave liquidations above 25K USD on Ethereum last week"
  "Top Polymarket prediction markets by 24h volume"
)

for q in "${queries[@]}"; do
  echo ""
  echo "▸ Query: $q"
  resp=$(curl -sS -m 30 -X POST "$BASE/" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg q "$q" --arg id "demo-$RANDOM" \
      '{jsonrpc:"2.0",id:1,method:"message/send",params:{message:{role:"user",parts:[{kind:"text",text:$q}],messageId:$id}}}')")
  echo "$resp" | jq -r '.result.parts[0].text' 2>/dev/null | jq '{recommendation, confidence, "validation_ok": .query_validation.ok, "subgraph_id": .query_ready.args.subgraph_id, "tool": .query_ready.tool}' 2>/dev/null || echo "$resp" | head -c 300
  sleep 1.5
done
pause_for

# ── 1:50 — Multi-protocol identity ───────────────────────────────────────────
banner "1:50 — IDENTITY · ERC-8004, A2A, MCP, Bazaar, ENS"

echo "▸ Agent card (4 skills declared)"
curl -sS "$BASE/.well-known/agent-card.json" | jq '{name, url, skills: [.skills[].id]}'

echo ""
echo "▸ ERC-8004 #734 on 8004scan"
curl -sS "https://8004scan.io/api/v1/public/agents/42161/734" | jq '.data | {name, is_active, health_status: .health_status.overall_status, total_score, ens, x402_supported}'

pause_for

# ── 2:30 — Production receipts ───────────────────────────────────────────────
banner "2:30 — RECEIPTS · live production data"

echo "▸ Live dashboard stats"
curl -sS "$BASE/dashboard/data" | jq '{
  total: .total,
  legit_pct: .legit_pct,
  unique_callers: .leaderboard | length,
  last_request_time: .last_request_time,
  wallet_balance_usdc: .onchain.usdc_balance,
  paid_query_count: .onchain.x402_log_count,
  quality_24h_avg: .quality_summary.last_24h_avg,
  quality_7d_avg: .quality_summary.last_7d_avg
}'

echo ""
echo "▸ Onchain — last 5 USDC transfers to wallet"
curl -sS -H "Authorization: Bearer $TOKEN_API_JWT" \
  "https://token-api.thegraph.com/v1/evm/transfers?network=base&to_address=$WALLET&contract=$USDC_BASE&limit=5" \
  | jq '.data[] | {time: .datetime, amount: .value, from: .from[0:14]}'

pause_for

banner "Done. Stop recording, paste SCRIPT.md into Tella for AI voiceover."
