#!/usr/bin/env bash
# Refresh graphadvocate.eth's ERC-8004 tokenURI on both chains to point at
# the freshly-pinned registration JSON for the predmarket/spread + kalshi
# suite + cross-venue spread additions.
#
# Old pin: ipfs://QmXuFpFMR5vDt7sHq9JhwuCBZvCNk29JQvboz9oXnEtwwE (2026-05-22)
# New pin: ipfs://QmfKtSrPYgMvUn39bcN44Lexd3xnH69HgC7ckA4S8SeL3r (2026-06-14, 19 a2aSkills)
#
# REQUIRES: PK_OWNER env var set to graphadvocate.eth's private key
#           (the agent #41034 / #734 NFT owner — 0x575267eED09c338FAE5716A486A7B58A5749A292)
# COST:   ~$0.001 on Base, ~$0.01 on Arbitrum
#
# Usage:
#   export PK_OWNER=0x...
#   ./scripts/update_erc8004_tokenuri_2026-06-14.sh

set -euo pipefail

if [ -z "${PK_OWNER:-}" ]; then
  echo "ERROR: PK_OWNER not set (graphadvocate.eth private key)"
  exit 1
fi

NEW_URI="ipfs://QmfKtSrPYgMvUn39bcN44Lexd3xnH69HgC7ckA4S8SeL3r"
REGISTRY="0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"

echo "=== Arbitrum #734 ==="
cast send "$REGISTRY" \
  "setAgentURI(uint256,string)" \
  734 "$NEW_URI" \
  --rpc-url https://arb1.arbitrum.io/rpc \
  --private-key "$PK_OWNER"

echo
echo "=== Base #41034 ==="
cast send "$REGISTRY" \
  "setAgentURI(uint256,string)" \
  41034 "$NEW_URI" \
  --rpc-url https://mainnet.base.org \
  --private-key "$PK_OWNER"

echo
echo "Done. Verify via:"
echo "  cast call $REGISTRY 'tokenURI(uint256)(string)' 734 --rpc-url https://arb1.arbitrum.io/rpc"
echo "  cast call $REGISTRY 'tokenURI(uint256)(string)' 41034 --rpc-url https://mainnet.base.org"
echo
echo "8004scan sweep happens every 30-60 min — re-check after that for the refreshed listing."
