#!/bin/bash
# Close 43 verified stale allocations on The Graph Horizon (SubgraphService)
# Contract: 0xb2Bb92d0DE618878E438b55D5846cfecD9301105 (Arbitrum One)
# Dry-run verified: 2026-04-02, epoch 1218
#
# Usage: PRIVATE_KEY=0x... ./close-stale-allocations.sh
# Requires: foundry (cast)

set -e

CONTRACT="0xb2Bb92d0DE618878E438b55D5846cfecD9301105"
RPC="${RPC_URL:-https://arb1.arbitrum.io/rpc}"

if [ -z "$PRIVATE_KEY" ]; then
  echo "Error: Set PRIVATE_KEY env var"
  exit 1
fi

# 43 allocations verified closable via cast call dry-run
ALLOCATIONS=(
  "0x02c530401a145a62a8daa06c254546ab61bf19a8"  # 1,695,454 GRT
  "0xea3199843904fb8b335d8f1b1cf8acedfb01bd8e"  # 1,538,187 GRT
  "0x2c2247b67ac7c7c50fa2c3beb3d9844b2def1a86"  #   328,420 GRT
  "0x3f9be1d98f584ace6d4f3a4e092eed47c798f64f"  #   327,000 GRT
  "0x498caab13510a264f0c1d7e456126f279f39efeb"  #   178,266 GRT
  "0x674e8f1ba0d0696d20ccb8e70b8029392737ef4f"  #   136,000 GRT
  "0x83bb3228b1dbf8d52d17d9f4e193e431066af551"  #   115,579 GRT
  "0x4b39985bee3eca8f8b9b5dc9fc7458ffa2f9aac5"  #    79,200 GRT
  "0x08118df89f6058bb76ab0a496e54a785f4abfce2"  #    53,748 GRT
  "0xdaaf965edc83dfff3e49c26be1486f96368c100b"  #    50,000 GRT
  "0x008960ea8880cfb3e72622b026ec3200c47c700e"  #    50,000 GRT
  "0x8019ce20428800bed93e648283bd08c01cd72f2b"  #    45,000 GRT
  "0xe4147377e5cc6071ced9db7d060f558c94e938a2"  #    40,000 GRT
  "0x948fa26eb9224b109468b7c1db1222c97c7b5a9a"  #    40,000 GRT
  "0x9348944d0fdf05d3b0e51a4dc1dafe2ffd9e444b"  #    40,000 GRT
  "0x55859ce8987881e1e28070a732a4e5ad3eb6013b"  #    40,000 GRT
  "0xd125e955a2ef3e573ccb44c48b957d7a3c7f0a39"  #    30,000 GRT
  "0x13a83a3d91ca34f088fe0656dfccefebd24edde3"  #    30,000 GRT
  "0x19fe81f6b86e3d407a9112074ba2fc342812255d"  #    25,000 GRT
  "0x90fb366d78c63e43a364c5d54cdf748584e63190"  #    20,000 GRT
  "0x54b4fbf0aaae99d6160518e1381755be5eda579e"  #    20,000 GRT
  "0xaf76d0e480e304ed41bf05c8a131a9e55c113c3b"  #    15,000 GRT
  "0x2ac0f6132421adc64162d5f8744e72147778222d"  #    15,000 GRT
  "0x06bb924549a5e621e84be1c7b77f062c26edce29"  #    15,000 GRT
  "0x217bd58f5338c6cf9196e52206ba6dac5160c72a"  #    14,750 GRT
  "0x596c1b436251d1fdc95a2829125525307ca08de0"  #    10,250 GRT
  "0x7272e51de9da472bdf032bc2ad02146bd851101e"  #    10,000 GRT
  "0x3996b4a7bf873331bdf3485e00d2b02d697db0e4"  #    10,000 GRT
  "0x382256a032e2a6a8405c72b935c9d4d335515506"  #    10,000 GRT
  "0xc1753823ee8e42997072ea22e04ba739c4ddb4da"  #     9,000 GRT
  "0xc866daf8c755fe89ffae47e7ecc6459275e4379a"  #     8,980 GRT
  "0xa5397957103ac7c8e2ace958b752cfdf0119cde2"  #     8,000 GRT
  "0xce9c6fd51106090282e580cfea950c1740cc524c"  #     7,500 GRT
  "0x0a7a46b9af573f4d865617a6d9c0b30d885e3cfe"  #     7,300 GRT
  "0xc0e83dfee32504f0bc84ab51a6278489ff7419f9"  #     5,000 GRT
  "0x4873cec56eb9be3819fef04b5b5fd5e8b6b75fd6"  #     5,000 GRT
  "0x2c03fec114a6ab548f8b1285ea02efba20bdd76e"  #     4,500 GRT
  "0xd73b631089af8c206322e864d49399ffc43f8e43"  #     4,100 GRT
  "0xb953a54fa7177dce6eec62db0fc60389e6061897"  #     4,100 GRT
  "0x3de78ffae8fd84532c93e43d1769a4d7e9bf51f9"  #     3,700 GRT
  "0x29d9428d00e06d36f83b5f9bbaa7a66ec5f0f857"  #     3,187 GRT
  "0x8017a67e82843f579a0adc6cca63f9e94ae34906"  #     3,000 GRT
  "0x0d14796e1b702f50e617270b1378c16324227460"  #     2,548 GRT
)

echo "=== Close Stale Allocations on The Graph Horizon ==="
echo "Contract: $CONTRACT"
echo "Allocations: ${#ALLOCATIONS[@]} (dry-run verified)"
echo "Total GRT to free: ~4.6M"
echo ""
echo "Press Enter to proceed or Ctrl+C to cancel..."
read

CLOSED=0
FAILED=0

for ALLOC in "${ALLOCATIONS[@]}"; do
  ALLOC_ID=$(echo "$ALLOC" | awk '{print $1}')
  echo -n "Closing $ALLOC_ID ... "

  TX=$(cast send "$CONTRACT" \
    "closeStaleAllocation(address)" \
    "$ALLOC_ID" \
    --rpc-url "$RPC" \
    --private-key "$PRIVATE_KEY" \
    --json 2>&1)

  if echo "$TX" | grep -q '"status":"0x1"'; then
    HASH=$(echo "$TX" | python3 -c "import json,sys; print(json.load(sys.stdin)['transactionHash'])" 2>/dev/null || echo "?")
    echo "OK (tx: $HASH)"
    CLOSED=$((CLOSED + 1))
  else
    echo "FAILED"
    FAILED=$((FAILED + 1))
  fi

  sleep 0.5
done

echo ""
echo "=== Done ==="
echo "Closed: $CLOSED / ${#ALLOCATIONS[@]}"
echo "Failed: $FAILED"
