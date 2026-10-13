# Directory listing kit (prepare-only — nothing here has been submitted)

Shared copy
-----------
**Name:** Graph Advocate
**Homepage:** https://graphadvocate.com · **Repo:** https://github.com/PaulieB14/graph-advocate
**Icon:** https://graphadvocate.com/graphadvocate.png (1024x1024 PNG)
**MCP endpoint:** https://graphadvocate.com/mcp (streamable HTTP) · https://graphadvocate.com/mcp/sse (SSE)
**A2A card:** https://graphadvocate.com/.well-known/agent-card.json · **x402:** https://graphadvocate.com/.well-known/x402 · **OpenAPI:** https://graphadvocate.com/openapi.json

**Short description (<=100 chars):**
Routes plain-English onchain data questions to the right subgraph or API, with a query.

**Long description:**
Graph Advocate is an onchain data router for AI agents. Ask in plain English ("Uniswap v3 swaps on Base", "Aave borrow rates", "wallet balances for vitalik.eth") and it returns the right data source across 15,500+ subgraphs on The Graph plus Token API / Substreams, with a ready-to-run GraphQL or REST query and install hints. MCP tools: `route_data_request`, `recommend_npm_package`, `compare_graph_services` (free). Paid pay-per-call endpoints via x402 (USDC on Base, $0.01-$0.10, no API key or signup): Polymarket and Hyperliquid trader PnL/skill/risk, Uniswap pre-trade due diligence and spot-perp basis, Kalshi-Polymarket spreads, x402 settlement analytics and an ERC-8004 agent reputation score. Also reachable as an A2A agent (ERC-8004 #734, graphadvocate.eth).

**Tags:** the-graph, subgraph, onchain-data, blockchain, graphql, defi, polymarket, hyperliquid, uniswap, x402, a2a, erc-8004

---

1. Official MCP Registry (registry.modelcontextprotocol.io)
-----------------------------------------------------------
File: `listings/server.json` (identical to the live https://graphadvocate.com/.well-known/mcp/server.json; validated against the 2025-12-11 schema in CI tests).
Name `io.github.PaulieB14/graph-advocate` requires GitHub auth as **PaulieB14**.
Alternative `com.graphadvocate/graph-advocate` requires DNS auth: a TXT record on graphadvocate.com (`mcp-publisher login dns --domain graphadvocate.com --private-key ...`) — change `name` before publishing if you go that way.

```bash
# install (macOS/Linux)
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher
cd graph-advocate/listings
./mcp-publisher login github      # opens a device-code flow: sign in as PaulieB14
./mcp-publisher publish           # reads ./server.json
curl "https://registry.modelcontextprotocol.io/v0/servers?search=graph-advocate"   # verify
```
Bump `version` in server.json (and discovery_files.MCP_SERVER_VERSION) for each re-publish. PulseMCP and several other directories ingest from this registry, so do it first.

2. Smithery — https://smithery.ai/new
-------------------------------------
Sign in with GitHub → "Publish a server" → choose **URL / remote** (hosted elsewhere) → paste `https://graphadvocate.com/mcp` → name "Graph Advocate", short description, icon URL, homepage. Smithery scans tools/list itself. (Exact form labels unverified; flow may require selecting the repo instead.)

3. Glama — https://glama.ai/mcp/servers
---------------------------------------
Click "Add Server" (GitHub sign-in) → submit repo `https://github.com/PaulieB14/graph-advocate`. To claim/own the listing, commit `listings/glama.json` to the **repo root** as `glama.json` (Glama looks there). Then add description/tags on the claimed listing.

4. mcp.so — https://mcp.so/submit
---------------------------------
Sign in (GitHub/Google) → fill: Name "Graph Advocate", URL https://github.com/PaulieB14/graph-advocate (or https://graphadvocate.com), short description, server config:
```json
{"mcpServers": {"graph-advocate": {"url": "https://graphadvocate.com/mcp"}}}
```

5. PulseMCP — https://www.pulsemcp.com/submit
---------------------------------------------
Usually auto-imported from the official registry within ~a week. If not: submit form with the repo URL + homepage + short description (email may be required for follow-up).

6. x402scan — https://www.x402scan.com/resources/register
---------------------------------------------------------
Paste origin `https://graphadvocate.com` (it reads /.well-known/x402 + /openapi.json + landing-page OG tags) and register; it probes each resource for a valid 402. Sign-in may be required (wallet connect). Currently shows "Not Found" for graphadvocate.com.

x402 Bazaar (CDP) — no submission form
--------------------------------------
Listing is automatic once a resource *settles* through the CDP facilitator. The PR adds serviceName/tags/iconUrl to every 402 so entries are branded once they settle. Only 4/24 endpoints are indexed today; the other 20 appear after their first real paid call (not done — no spending).
