#!/bin/bash
# Register Graph Advocate with a2aregistry.org using its PERMANENT public URL.
#
# NOTE: This script used to start a local a2a_server.py and expose it via an
# EPHEMERAL ngrok tunnel, then register the tunnel URL. That URL died the moment
# the tunnel closed, so a2aregistry's health checks dropped GA as unreachable.
# GA is now hosted permanently at graphadvocate.com, so we register that directly.
# No local server, no ngrok — just (re)register the live public endpoint.
set -e

PUBLIC_URL="${ADVOCATE_PUBLIC_URL:-https://graphadvocate.com}"
CARD_URL="$PUBLIC_URL/.well-known/agent.json"

echo "Verifying agent card is live at $CARD_URL ..."
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$CARD_URL")
if [ "$CODE" != "200" ]; then
  echo "ERROR: agent card not reachable ($CODE). Is $PUBLIC_URL deployed?"
  exit 1
fi

echo "Registering $PUBLIC_URL with a2aregistry.org ..."
RESPONSE=$(curl -s --max-time 30 -X POST https://a2aregistry.org/api/agents/register \
  -H "Content-Type: application/json" \
  -d "{\"wellKnownURI\": \"$CARD_URL\"}")
echo "Response: $RESPONSE"
echo ""
echo "Done. a2aregistry health-checks the permanent URL, so the listing will persist."
