#!/bin/bash
# Starts the A2A server, tunnels it publicly via ngrok, and registers with a2aregistry.org
set -e
cd "$(dirname "$0")"
set -a; source .env; set +a
source venv/bin/activate

echo "Starting A2A server on port 8765..."
python a2a_server.py &
A2A_PID=$!
sleep 2

echo "Starting ngrok tunnel..."
ngrok http 8765 --log=stdout --log-format=json > /tmp/ngrok_advocate.log 2>&1 &
NGROK_PID=$!
sleep 3

# Get public URL from ngrok API
PUBLIC_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "
import sys, json
data = json.load(sys.stdin)
tunnels = data.get('tunnels', [])
for t in tunnels:
    if t.get('proto') == 'https':
        print(t['public_url'])
        break
")

if [ -z "$PUBLIC_URL" ]; then
    echo "ERROR: Could not get ngrok URL. Is ngrok authenticated?"
    echo "Run: ngrok config add-authtoken <your-token> (free at ngrok.com)"
    kill $A2A_PID $NGROK_PID 2>/dev/null
    exit 1
fi

echo "Public URL: $PUBLIC_URL"
echo "Agent card: $PUBLIC_URL/.well-known/agent.json"

# Update a2a_server.py URL on the fly (env var override)
export ADVOCATE_PUBLIC_URL="$PUBLIC_URL"

# Register with a2aregistry.org
echo ""
echo "Registering with a2aregistry.org..."
RESPONSE=$(curl -s -X POST https://a2aregistry.org/api/agents/register \
  -H "Content-Type: application/json" \
  -d "{\"wellKnownURI\": \"$PUBLIC_URL/.well-known/agent.json\"}")
echo "Response: $RESPONSE"

# Save the public URL for reference
echo "$PUBLIC_URL" > /tmp/advocate_public_url.txt
echo ""
echo "Graph Advocate is live and registered."
echo "Public URL: $PUBLIC_URL"
echo ""
echo "Press Ctrl+C to stop."
wait $A2A_PID
