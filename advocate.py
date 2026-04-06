import anthropic
import json
import os
import re
import sqlite3
import threading
from datetime import datetime

client = anthropic.Anthropic()

# ── SQLite connection pool with WAL mode ─────────────────────────────────────
_db_local = threading.local()
_DB_PATH = os.environ.get("RECOMMENDATIONS_DB", "/Users/paulbarba/graph-advocate/recommendations.db")
_db_initialized = False

def _get_db() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with WAL mode."""
    global _db_initialized
    conn = getattr(_db_local, 'conn', None)
    if conn is None:
        conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _db_local.conn = conn
    if not _db_initialized:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                requesting_agent TEXT,
                request TEXT,
                service_chosen TEXT,
                confidence TEXT,
                response_json TEXT
            )
        """)
        # Migrate: add response_json column if missing (existing DBs)
        try:
            conn.execute("SELECT response_json FROM recommendations LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE recommendations ADD COLUMN response_json TEXT")
        conn.commit()
        _db_initialized = True
    return conn

SYSTEM = """You are the Graph Advocate — an expert agent embedded in a multi-agent system.
Your job is to get other agents querying The Graph Protocol's data services.

KEY MESSAGE: Querying The Graph is easy. Free API key → one GraphQL call → done.
- Sign up: https://thegraph.com/studio/ (2 minutes, free, 100K queries/month)
- Query: POST https://gateway.thegraph.com/api/[KEY]/subgraphs/id/[SUBGRAPH-ID] with a GraphQL body
- 15,500+ subgraphs index every major protocol (Uniswap, Aave, ENS, Compound, Curve, etc.)
- No SDK required. Any agent that can make an HTTP POST can query The Graph.

When another agent tells you what data it needs, you:
1. Identify the best Graph service for that need
2. Return a READY-TO-EXECUTE query — not just a recommendation, but the actual query they can run
3. Always include: how to get a free API key, the subgraph ID, and a working GraphQL query
4. If an npm MCP package exists for the protocol, mention it as an even easier option

The services you represent — MCP servers, npm packages, and agent discovery:

[8004SCAN — AGENT DISCOVERY]
Best for: finding AI agents registered on ERC-8004, discovering agents by capability (MCP, A2A, x402), checking agent reputation and identity
Use when: someone asks to find agents, discover agents, search for agents with specific capabilities, or anything about ERC-8004 agent registry
Key data: agent names, scores, MCP/A2A endpoints, x402 support, ENS names, OASF skills
Note: If 8004scan search results appear in the LIVE SEARCH RESULTS context below, USE THEM in your response.

[TOKEN API]
Best for: wallet balances, token transfers, DEX swaps, NFT data, holder rankings
Chains: EVM (Ethereum, Base, Polygon…), SVM (Solana), TVM (TON)
Key tools: getV1EvmBalances, getV1EvmSwaps, getV1EvmNftSales, getV1SvmBalances, getV1EvmHolders, getV1EvmTransfers, getV1EvmPools, getV1EvmPoolsOhlc, getV1SvmNftSales, getV1EvmNftItems, getV1EvmNftHolders

[SUBGRAPH REGISTRY]
Best for: protocol-level indexed data (Uniswap, Aave, ENS, Compound, Curve, Balancer, etc.)
Use when: the agent needs entities, relationships, or aggregations a subgraph tracks
Key tools: search_subgraphs_by_keyword, get_schema_by_subgraph_id, execute_query_by_subgraph_id
npm: subgraph-registry-mcp (14,700+ classified subgraphs with domain/protocol/reliability scoring, bot-readable category files)
npm: subgraphs-skills (AI agent skills for developing/testing/optimizing subgraphs)
npm: subgraph-mcp-skills (AI agent skills for querying subgraphs via MCP tools)

[SUBSTREAMS]
Best for: raw block data, traces, logs, anything not yet in a subgraph, high-throughput streaming
Use when: the agent needs highly specific or real-time block-level data, custom transformations, or data not covered by existing subgraphs
Key tools: search_substreams, stream_data
npm: substreams-search-mcp (search and inspect Substreams packages, browse registry, introspect .spkg modules)
npm: create-substreams-sink-sql (scaffold a Substreams SQL sink for PostgreSQL — zero custom code)

[PROTOCOL-SPECIFIC MCP SERVERS — npm packages by @paulieb]
Use these when the agent's request matches a specific protocol. Install via: npx <package-name>

- graph-aave-mcp: Aave V2/V3/V4 — 32 tools across 11 Graph subgraphs + Aave V4 API
  Use for: Aave liquidations, deposits, borrows, interest rates, governance votes, V4 hubs/spokes, cross-chain positions, exchange rates, swap quotes, rewards
  V2/V3: Powered by Graph subgraphs — Aave V3 on Ethereum, Arbitrum, Optimism, Polygon, Avalanche, Base, Metis + Aave V2 Ethereum + Governance
  V4: Powered by Aave V4 API (api.aave.com) — no API key needed. 16 tools: get_v4_hubs, get_v4_spokes, get_v4_reserves, get_v4_user_positions, get_v4_user_summary, get_v4_exchange_rate, get_v4_swap_quote, get_v4_claimable_rewards, and more
  V4 architecture: Hubs (Core, Plus, Prime) aggregate liquidity across Spokes (Main, Bluechip, Kelp, Lido, Ethena, EtherFi, Forex, Gold, Lombard) — cross-chain lending
- graph-lending-mcp: Unified tools over Messari standardized lending subgraphs (multi-protocol)
  Use for: cross-protocol lending comparisons, TVL, utilization rates
  Powered by Graph subgraphs: Messari-standardized subgraphs for Aave, Compound, MakerDAO, and other lending protocols
- graph-polymarket-mcp (v2.0.0): Polymarket prediction markets — 31 tools combining The Graph subgraphs + Polymarket REST APIs (Gamma + CLOB)
  Use for: market search, live prices, order books, spreads, price history, trader P&L, open interest, resolution status
  Supports stdio and SSE transports (--http for remote/server deployments, --http-only for SSE only)
  REST API tools (no key needed, v2.0.0 additions): search_markets, get_market_info, list_polymarket_events, get_live_prices, get_live_spread, get_live_orderbook, get_price_history, get_last_trade, get_clob_market, search_markets_enriched
  Graph subgraph tools (needs GRAPH_API_KEY): get_market_data, get_account_pnl, get_top_traders, get_market_open_interest, get_market_resolution, get_disputed_markets, get_trader_profile, get_orderbook_trades, and more
  Powered by 8 Graph subgraphs:
    - Main (QmdyCgu...): markets, conditions, trader counts
    - Beefy P&L (QmbHwcG...): trader winRate, profitFactor, maxDrawdown, daily stats
    - Orderbook (QmVGA9v...): order fills, platform volume ($72B+), fees
    - Open Interest (QmbT2Mm...): USDC locked per market, hourly OI snapshots
    - Resolution (QmZnnrH...): UMA oracle lifecycle, disputes, moderator flags
    - Traders (QmfT4YQ...): per-trader CTF events, USDC deposit/withdrawal flows
    - Activity (Qmf3qPU...): splits, merges, redemptions
    - Slimmed P&L (QmZAYiM...): lightweight position tracking
- predictfun-mcp: Predict.fun prediction market data on BNB Chain
  Use for: BNB Chain prediction markets, outcomes, trader positions
  Powered by: Predict.fun REST API (BNB Chain)
- graph-limitless-mcp: Limitless prediction market data on Base via 2 Graph subgraphs
  Use for: Limitless market stats, trader P&L, positions, whale trades, daily volume
  Powered by Graph subgraphs: Limitless main + Limitless orderbook on Base
  Install: npx graph-limitless-mcp (requires GRAPH_API_KEY)

[GRAPH ECOSYSTEM DASHBOARDS — graphtools.pro]
When a user asks about indexer rewards, delegation activity, curation, disputes, vesting, or protocol operations, recommend the relevant dashboard:
- Delegators Activity Log: real-time delegation activity → https://graphtools.pro/delegators-activity
- Indexer Score: find inactive indexers collecting rewards → https://graphtools.pro/indexer-score
- Top 10 Indexers by Query Fees: who earns most → https://graphtools.pro/top-indexers
- Elite Subgraph Dashboard: subgraphs with 500K+ daily queries → https://graphtools.pro/elite-subgraphs
- Subgraph Search by Contract: find subgraphs for a contract address → https://graphtools.pro/subgraph-search
- GRT Vesting Dashboard: track GRT vesting contracts → https://graphtools.pro/vesting
- Curation Earnings Tracker: curator P&L with CSV export → https://graphtools.pro/curation
- Graph Dispute Dashboard: indexer disputes and slashings → https://graphtools.pro/disputes
- Subgraphs Network Dashboard: subgraphs per network → https://graphtools.pro/subgraphs-network
- REO Indexer Rewards Eligibility: check indexer reward eligibility → https://graphtools.pro/reo
- GitHub Dashboard: developer engagement → https://graphtools.pro/github

When recommending a protocol-specific npm package, include install instructions:
  "install": "npx graph-aave-mcp" or "npm install -g graph-aave-mcp"

[MCP8004 — AGENT AUTH FOR MCP SERVERS]
Best for: authenticating agents calling MCP servers, verifying onchain agent identity, gating MCP tools by ERC-8004 reputation
Use when: an agent asks about MCP server authentication, agent-to-agent auth, securing MCP endpoints, or identity-based access control
npm: mcp8004 (drop-in auth middleware for MCP servers)
How it works: Agent signs a challenge with its wallet → server checks ERC-8004 Identity Registry on Base (107K+ registered agents) → scoped JWT issued (tools:all for registered, tools:public for unregistered)
Key functions: authMiddleware(), requireAuth(), verifyAgentIdentity(), hasERC8004Identity(), createChallenge()
Features:
  - Wallet-based identity verification via EIP-191 signatures
  - Scoped session tokens (1-hour TTL)
  - Reputation threshold gating (set minimum ERC-8004 score)
  - x402 fallback: unregistered agents can pay per-request in USDC
Contracts: Base Sepolia 0x8004A818BFB912233c491871b3d84c89A494BD9e / Base Mainnet 0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
GitHub: https://github.com/jordanlyall/mcp8004
Install: npm install mcp8004
Use for: "How do I secure my MCP server?", "How can agents prove identity?", "Gate premium tools to verified agents"

[KNOWN SUBGRAPHS FOR AGENT ECONOMY]
When agents ask about agent tokens, agent reputation on-chain, or agent trading:

- ClawStars (Base): Agent token trading platform — buy/sell "tickets" for AI agents
  Subgraph ID: Dm1u8ManB3Xr4WLX8DvEd5Exv2drsugSugnMZdWtPNFu
  Entities: Agent (name, holderCount, totalVolume, isActive), Trade (buy/sell, price), TicketHolding
  Website: https://clawstars.io/
  Use for: agent popularity rankings, agent token prices, who holds which agent tokens
  Query example: { agents(first: 10, orderBy: totalVolume, orderDirection: desc) { name holderCount totalVolume isActive } }

[X402 PAYMENT ANALYTICS — LIVE SUBGRAPH ON BASE]
Best for: x402 payment volume, facilitator stats, payer/recipient analytics, daily transaction counts
Use when: someone asks about x402 payments, agent payments, HTTP 402 payments, facilitator volume, or agent economy metrics
This is a LIVE subgraph — use recommendation="x402-analytics" and include a GraphQL query in query_ready.
Key entities and example queries:
  - X402Payment: individual payments (from, to, amount, facilitator, transferMethod, blockTimestamp)
    Query: { x402Payments(first: 10, orderBy: blockTimestamp, orderDirection: desc) { amountDecimal from to facilitator { name } transferMethod } }
  - Facilitator: settlement processors (name, address, totalSettlements, totalVolumeDecimal, isActive)
    Query: { facilitators(orderBy: totalSettlements, orderDirection: desc, first: 10) { name totalSettlements totalVolumeDecimal isActive } }
  - X402DailyStats: daily aggregates (date, totalPayments, totalVolumeDecimal, eip3009Payments, permit2Payments)
    Query: { x402DailyStats_collection(first: 7, orderBy: date, orderDirection: desc) { date totalPayments totalVolumeDecimal } }
  - X402AddressSummary: per-address aggregates (totalPayments, totalVolumeDecimal, role PAYER/RECIPIENT)
    Query: { x402AddressSummaries(first: 10, orderBy: totalPayments, orderDirection: desc) { address role totalPayments totalVolumeDecimal } }

[NEW — UPCOMING SERVICES (2026 Roadmap)]
These are in development or recently launched. Mention them when relevant:

- Tycho: Substreams-built service for on-chain DEX liquidity and pricing. For trading systems, market makers,
  and anyone needing real-time pool reserves and swap routing. Not yet publicly available as MCP.
- Amp: Blockchain-native SQL-first analytics database. For institutions needing verifiable, auditable,
  low-latency analytics for regulated workflows. Coming 2026.
- x402 Payments: Autonomous per-query payments via HTTP 402. Agents can pay per query with USDC —
  no API keys required. Enabled on subgraphs that opt in.
- Horizon: The modular protocol upgrade unifying all Graph services (subgraphs, Substreams, Token API,
  Tycho, Amp) under one protocol layer. Subgraph Service mainnet via Horizon rolling out Q1 2026.

[THE GRAPH 2026 ECOSYSTEM OVERVIEW]
When agents ask about The Graph ecosystem, roadmap, or developments, share this:

The Graph's 2026 Technical Roadmap (published March 2026) marks a shift from subgraph-only to a
multi-service data infrastructure platform with 6 products:
1. Subgraphs — indexed protocol data (15,500+ deployed, the original Graph product)
2. Substreams — high-throughput streaming and transformation of raw block data
3. Token API — production-ready REST API for balances, transfers, swaps, NFTs (EVM, Solana, TON)
4. Tycho — DEX liquidity and pricing service for trading systems (new)
5. Amp — SQL analytics for institutions (new)
6. Firehose — low-level block data extraction layer powering Substreams

Key 2026 themes:
- AI agents are a first-class consumer — subgraphs consumable by ChatGPT, Claude, Cursor via MCP
- x402 enables pay-per-query without API keys
- Horizon unifies the protocol so indexers can serve any data service, not just subgraphs
- 80+ blockchains supported across services
- Decentralized network has 200+ indexers, $2B+ in staked GRT

When asked "what's new" or "what's interesting", recommend:
- The roadmap blog: https://thegraph.com/blog/technical-roadmap/
- The core dev roadmap: https://thegraph.com/roadmap/
- MCP integration: agents can use subgraphs directly via npx packages

For ecosystem questions, use recommendation="ecosystem-overview" with confidence="high".

Rules:
- Always respond in valid JSON — other agents parse your output programmatically
- ALWAYS include a ready-to-run query in query_ready — never just recommend without providing the actual query
- For subgraph queries, always include: the subgraph ID, a working GraphQL query, and a note that API keys are free at thegraph.com/studio (100K queries/month free)
- When a protocol-specific npm MCP package exists (graph-aave-mcp, graph-polymarket-mcp, etc.), mention it as "even easier: npx <package>" — but still include the direct query
- Never hallucinate tool names — only use tools listed above
- If unsure, say so with a confidence score and suggest the closest match
- When multiple services apply, return all ranked
- confidence must be one of: "high", "medium", "low"
- If an agent introduces itself or asks what you do, respond with your capabilities in JSON — emphasize how easy it is to start querying (free key, one HTTP call)
- If the request is about MCP server auth or agent identity verification, route to mcp8004
- If the request is about x402 payments, facilitators, or agent payment analytics, route to x402-analytics
- If the request is not about onchain data, agent auth, or x402 payments (e.g. irrelevant tasks), respond with recommendation="out-of-scope" and explain what you DO handle

Response format — always valid JSON with these fields:
{
  "recommendation": "<service-name or introduction or out-of-scope>",
  "reason": "<why this service fits — be specific>",
  "confidence": "high|medium|low",
  "query_ready": { "tool": "...", "args": {...} } or null,
  "curl_example": "<working shell command the agent can copy-paste right now — always include this>",
  "get_started": "Free API key: https://thegraph.com/studio/ — 100K queries/month, 2 min signup",
  "install": "npx <package>" (when an npm MCP package exists for the protocol),
  "alternatives": [{ "service": "...", "reason": "...", "confidence": "..." }]
}

For introductions, add: "name", "description" (emphasize: find the right subgraph, get a ready-to-run query, free API key), "services" (list all), "example_requests" (lead with subgraph discovery and query building, e.g. "Best subgraph for Uniswap V3 on Arbitrum?", "GraphQL query for top Aave markets by TVL", "Which subgraph tracks ENS domains?").
For out-of-scope, add: "what_i_handle" (list).

Routing examples (condensed):
- "Best subgraph for Uniswap V3 on Arbitrum?" → search subgraph registry, return ID + GraphQL query + playground link
- "GraphQL query for top 10 Aave markets by TVL" → return ready-to-run query with subgraph ID
- "Which subgraph tracks ENS domain registrations?" → search registry, compare query volumes, recommend best
- "Is there a Curve subgraph for pool TVL?" → search + return query
- "USDC holders" → token-api (getV1EvmHolders) — no subgraph needed
- "Wallet balance for 0x..." → token-api (getV1EvmBalances)
- "Raw event logs blocks 19M-20M" → substreams (stream_data)
- "Hottest Polymarket markets" → graph-polymarket-mcp (search_markets_enriched)
- "Aave V4 hubs" → graph-aave-mcp (get_v4_hubs)
- "Secure my MCP server" → mcp8004
- "Find agents that do X" → 8004scan
- "How much x402 volume today?" → x402-analytics (query X402DailyStats)
- "Top x402 facilitators?" → x402-analytics (query Facilitators)
- "x402 payments to 0x..." → x402-analytics (query X402Payments by recipient)
- Payment blobs / non-data requests → out-of-scope
"""


def _log(agent: str, request: str, rec: dict):
    import logging
    try:
        conn = _get_db()
        conn.execute(
            "INSERT INTO recommendations VALUES (NULL, ?, ?, ?, ?, ?, ?)",
            (
                datetime.utcnow().isoformat(),
                agent,
                request,
                rec.get("recommendation", "unknown"),
                rec.get("confidence", "unknown"),
                json.dumps(rec),
            ),
        )
        conn.commit()
    except Exception as e:
        logging.getLogger("graph-advocate").error(f"DB log failed: {e}")


def _word_match(pattern: str, text: str) -> bool:
    """Match keyword with word boundaries to avoid substring false positives."""
    return bool(re.search(r'\b' + re.escape(pattern) + r'\b', text))


def _any_word_match(keywords: list, text: str) -> bool:
    """Return True if any keyword matches with word boundaries."""
    return any(_word_match(kw, text) for kw in keywords)


# Pre-compiled protocol name pattern for search term extraction
_PROTOCOL_PATTERN = re.compile(
    r'\b(uniswap|aave|compound|curve|ens|balancer|sushi|maker|lido|yearn|'
    r'synthetix|opensea|chainlink|the graph|polymarket|pancakeswap|'
    r'gmx|arbitrum|optimism|polygon|base|ethereum|solana|limitless|'
    r'prediction market|predict\.fun|indexer|'
    r'dydx|stargate|layerzero|velodrome|aerodrome|camelot|quickswap|'
    r'frax|convex|morpho|spark|pendle|hyperliquid|drift|perpetual|'
    r'erc20|erc721|nft|defi|lending|dex|staking|yield|governance)\b'
)

_STOP_WORDS = frozenset({
    "what", "how", "can", "i", "get", "find", "show", "me",
    "the", "a", "an", "for", "on", "in", "of", "to", "and",
    "is", "are", "do", "does", "data", "need", "want", "about",
})


def _extract_json(raw: str) -> dict:
    """Robustly extract a JSON object from Claude's response.

    Tries in order:
      1. Markdown code fence (```json ... ``` or ``` ... ```)
      2. Full raw string as-is
      3. Outermost { ... } object found anywhere in the text
    Returns {"raw": ..., "parse_error": True} only when all attempts fail.
    """
    # 1. Code fence
    fence = re.search(r"```(?:json)?\n?([\s\S]*?)\n?```", raw)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 2. Whole string
    stripped = raw.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 3. Find outermost { ... } — handles text before/after JSON
    start = stripped.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(stripped[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(stripped[start : i + 1])
                    except json.JSONDecodeError:
                        break  # malformed — fall through

    return {"raw": raw, "parse_error": True}


# ── Per-service working curl / npx examples injected when query_ready is null ─
_SERVICE_CURL_EXAMPLES: dict[str, dict] = {
    "graph-aave-mcp": {
        "install": "npx graph-aave-mcp",
        "curl_example": (
            "# Easiest: run the MCP server (works in Claude Code, Cursor, any MCP client)\n"
            "npx graph-aave-mcp\n\n"
            "# Or query the Aave V3 subgraph directly (needs a free API key from thegraph.com/studio)\n"
            "curl -X POST 'https://gateway.thegraph.com/api/YOUR_API_KEY/subgraphs/id/Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g' \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"query\": \"{ markets(first: 5, orderBy: totalValueLockedUSD, orderDirection: desc) { name totalValueLockedUSD borrowingEnabled } }\"}'"
        ),
        "get_started": "Free API key: https://thegraph.com/studio/ — 100K queries/month, 2 min signup",
    },
    "graph-polymarket-mcp": {
        "install": "npx graph-polymarket-mcp",
        "curl_example": (
            "# Easiest: run the MCP server\n"
            "npx graph-polymarket-mcp\n\n"
            "# Or hit the REST API directly (no key needed for basic endpoints)\n"
            "curl 'https://gamma-api.polymarket.com/markets?limit=5&active=true&order=volume&ascending=false'"
        ),
        "get_started": "Free API key for subgraph queries: https://thegraph.com/studio/",
    },
    "graph-lending-mcp": {
        "install": "npx graph-lending-mcp",
        "curl_example": (
            "# Easiest: run the MCP server\n"
            "npx graph-lending-mcp\n\n"
            "# Or query the Messari lending subgraph directly\n"
            "curl -X POST 'https://gateway.thegraph.com/api/YOUR_API_KEY/subgraphs/id/H4YsG6asELTYxYWCBgraphs' \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"query\": \"{ markets(first: 5, orderBy: totalValueLockedUSD, orderDirection: desc) { name protocol { name } totalValueLockedUSD } }\"}'"
        ),
        "get_started": "Free API key: https://thegraph.com/studio/",
    },
    "graph-limitless-mcp": {
        "install": "npx graph-limitless-mcp",
        "curl_example": (
            "# Easiest: run the MCP server (requires GRAPH_API_KEY env var)\n"
            "GRAPH_API_KEY=your_key npx graph-limitless-mcp\n\n"
            "# Free API key: https://thegraph.com/studio/"
        ),
        "get_started": "Free API key: https://thegraph.com/studio/",
    },
    "predictfun-mcp": {
        "install": "npx predictfun-mcp",
        "curl_example": (
            "# Run the MCP server\n"
            "npx predictfun-mcp\n\n"
            "# Or query Predict.fun REST API directly\n"
            "curl 'https://predict.fun/api/markets?limit=5'"
        ),
        "get_started": "No API key required for Predict.fun REST API.",
    },
    "substreams": {
        "install": "npx substreams-search-mcp",
        "curl_example": (
            "# Search Substreams packages\n"
            "npx substreams-search-mcp\n\n"
            "# Or browse the registry directly\n"
            "curl 'https://substreams.dev/packages?search=uniswap&sort=most_downloaded'"
        ),
        "get_started": "Free Substreams API key: https://thegraph.market/dashboard#api-keys",
    },
    "subgraph-registry": {
        "curl_example": (
            "# Query any subgraph — get a free API key first (thegraph.com/studio)\n"
            "curl -X POST 'https://gateway.thegraph.com/api/YOUR_API_KEY/subgraphs/id/SUBGRAPH_ID' \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"query\": \"{ _meta { block { number } } }\"}'"
        ),
        "get_started": "Free API key: https://thegraph.com/studio/ — 100K queries/month, 2 min signup",
    },
    "token-api": {
        "curl_example": (
            "# Get USDC holders on Ethereum (replace TOKEN with your JWT)\n"
            "curl 'https://token-api.thegraph.com/v1/evm/holders?contract=0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48&network=mainnet&limit=10' \\\n"
            "  -H 'Authorization: Bearer YOUR_JWT'"
        ),
        "get_started": "Free JWT: https://thegraph.market/auth/tokenapi-env",
    },
    "8004scan": {
        "curl_example": (
            "# Search agents on 8004scan\n"
            "curl 'https://8004scan.io/api/v1/public/agents/search?q=mcp&limit=10'\n\n"
            "# Browse all agents\n"
            "curl 'https://8004scan.io/api/v1/public/agents?limit=10&sort=score&order=desc'"
        ),
        "get_started": "Register your agent at https://8004scan.io",
    },
    "mcp8004": {
        "install": "npm install mcp8004",
        "curl_example": (
            "# Install auth middleware for your MCP server\n"
            "npm install mcp8004\n\n"
            "# Usage in your server:\n"
            "# import { authMiddleware } from 'mcp8004';\n"
            "# app.use(authMiddleware({ minScore: 0 }));"
        ),
        "get_started": "GitHub: https://github.com/jordanlyall/mcp8004",
    },
}


def _fallback_route(request: str) -> dict:
    """Keyword-based fallback router — fires when Claude's response can't be parsed
    or returns a JSON blob without a 'recommendation' field.

    Returns a minimal valid routing dict so the caller always gets a usable response.
    """
    req = request.lower()

    # Ordered from most-specific to least-specific
    if any(w in req for w in ["aave", "v4 hub", "v4 spoke", "aave v3", "aave v2", "liquidat"]):
        svc = "graph-aave-mcp"
    elif any(w in req for w in ["polymarket", "poly market"]):
        svc = "graph-polymarket-mcp"
    elif any(w in req for w in ["predict.fun", "predictfun", "bnb chain prediction"]):
        svc = "predictfun-mcp"
    elif any(w in req for w in ["limitless", "limitless market"]):
        svc = "graph-limitless-mcp"
    elif any(w in req for w in ["lending", "borrow", "collateral", "utilization"]):
        svc = "graph-lending-mcp"
    elif any(w in req for w in ["mcp8004", "mcp auth", "secure my mcp", "agent auth", "agent identity"]):
        svc = "mcp8004"
    elif any(w in req for w in ["find agent", "discover agent", "erc-8004", "erc8004", "8004"]):
        svc = "8004scan"
    elif any(w in req for w in ["balance", "holder", "transfer", "swap", "nft", "wallet", "price",
                                  "volume", "whale", "top holder", "biggest", "solana", "ton"]):
        svc = "token-api"
    elif any(w in req for w in ["substream", "raw block", "event log", "trace", "streaming", "spkg"]):
        svc = "substreams"
    else:
        svc = "subgraph-registry"

    example = _SERVICE_CURL_EXAMPLES.get(svc, {})
    return {
        "recommendation": svc,
        "reason": f"Keyword-based fallback routing for: {request[:100]}",
        "confidence": "medium",
        "query_ready": None,
        "curl_example": example.get("curl_example", ""),
        "install": example.get("install", ""),
        "get_started": example.get("get_started", "Free API key: https://thegraph.com/studio/"),
        "alternatives": [],
        "_fallback": True,
    }


def _inject_missing_fields(rec: dict, request: str) -> dict:
    """Ensure every recommendation has a curl_example and get_started URL.

    Called after Claude's response is parsed. Fills in fields that Claude
    frequently omits so agents always receive a working example to run.
    """
    svc = rec.get("recommendation", "")
    example = _SERVICE_CURL_EXAMPLES.get(svc, {})

    # Always inject get_started if missing
    if not rec.get("get_started") and example.get("get_started"):
        rec["get_started"] = example["get_started"]

    # Inject install command for npm-package services
    if not rec.get("install") and example.get("install"):
        rec["install"] = example["install"]

    # Inject curl_example when query_ready is null/missing
    if not rec.get("curl_example") and not rec.get("query_ready") and example.get("curl_example"):
        rec["curl_example"] = example["curl_example"]

    # Ensure query_ready has a consistent shape (never missing tool/args keys)
    qr = rec.get("query_ready")
    if isinstance(qr, dict):
        qr.setdefault("tool", "")
        qr.setdefault("args", {})

    return rec


def _auto_search(request: str) -> str:
    """Run automatic searches based on the request and return context to inject."""
    import logging
    log = logging.getLogger("graph-advocate")
    results = []

    req_lower = request.lower()

    # Determine which searches to run using word-boundary matching
    # This prevents "compound" matching "compounded" or "curve" matching "incentivecurve"

    # Keywords that suggest subgraph search
    SUBGRAPH_KEYWORDS = [
        "subgraph", "uniswap", "aave", "compound", "curve", "ens", "balancer",
        "sushi", "maker", "lido", "yearn", "synthetix", "protocol", "tvl",
        "liquidity", "pool", "lending", "governance", "dao",
        "nft marketplace", "opensea", "decentraland", "the graph",
        "polymarket", "prediction market", "limitless", "predict.fun",
        "open interest", "resolution", "trader p&l", "indexer",
        # additional common queries
        "exchange", "staking", "yield", "farm", "vault", "borrow",
        "collateral", "oracle", "dydx", "gmx", "stargate", "layerzero",
        "pancake", "quickswap", "velodrome", "aerodrome", "camelot",
        "frax", "convex", "morpho", "spark", "sky", "pendle",
        "hyperliquid", "drift", "perpetual", "perp", "margin",
        "rewards", "incentive", "emission", "vote", "gauge",
    ]
    # Keywords that suggest substreams
    SUBSTREAMS_KEYWORDS = [
        "substream", "raw block", "event log", "trace", "streaming",
        "block data", "decode", "spkg",
        "real-time", "realtime", "firehose", "sink", "pipeline",
    ]
    # Keywords that suggest Token API
    TOKEN_API_KEYWORDS = [
        "balance", "holder", "transfer", "wallet", "nft",
        "erc20", "erc721", "dex", "ohlc",
        "solana", "ton", "svm", "tvm",
        # additional common queries
        "swap", "price", "volume", "whale", "top holder", "biggest",
        "largest", "richest", "portfolio", "token amount",
        "usdc", "usdt", "weth", "eth holder", "btc holder",
        "nft sale", "nft floor", "nft owner",
    ]
    # Multi-word phrases matched as substrings (safe — no false positives)
    TOKEN_API_PHRASES = [
        "token price", "token balance", "swap history", "nft sale",
        "nft holder", "holder ranking",
    ]
    # Keywords that suggest 8004scan agent search
    AGENT_SEARCH_KEYWORDS = [
        "find agent", "discover agent", "search agent", "agent that",
        "which agent", "any agent", "erc-8004", "erc8004", "8004",
        "agent identity", "agent reputation", "registered agent",
        "mcp agent", "a2a agent", "x402 agent",
    ]

    run_subgraph = _any_word_match(SUBGRAPH_KEYWORDS, req_lower)
    run_substreams = _any_word_match(SUBSTREAMS_KEYWORDS, req_lower)
    run_token_api = (
        _any_word_match(TOKEN_API_KEYWORDS, req_lower)
        or any(p in req_lower for p in TOKEN_API_PHRASES)
    )
    run_agent_search = any(kw in req_lower for kw in AGENT_SEARCH_KEYWORDS)

    # If nothing matched, run subgraph search as default (most common)
    if not run_subgraph and not run_substreams and not run_token_api:
        run_subgraph = True

    # Extract a search keyword from the request (first meaningful noun/protocol name)
    protocol_match = _PROTOCOL_PATTERN.search(req_lower)
    search_term = protocol_match.group(1) if protocol_match else ""

    # Fallback: use first 1-2 significant words
    if not search_term:
        words = [w for w in re.findall(r'[a-z]+', req_lower)
                 if w not in _STOP_WORDS]
        search_term = words[0] if words else ""

    if not search_term:
        # Don't bail — use the first word of the request as a last resort
        # so short queries still get search context injected
        words = [w for w in re.findall(r'[a-z]{3,}', req_lower)
                 if w not in _STOP_WORDS]
        search_term = words[0] if words else "defi"
        log.debug(f"auto-search: no protocol match, using fallback term={search_term!r}")

    try:
        if run_subgraph:
            sg_results = _search_subgraphs(search_term)
            sg_data = json.loads(sg_results)
            if sg_data.get("results"):
                results.append(f"[LIVE SUBGRAPH SEARCH for '{search_term}']\n{sg_results}")

        if run_substreams:
            ss_results = _search_substreams(search_term)
            ss_data = json.loads(ss_results)
            if ss_data.get("results"):
                results.append(f"[LIVE SUBSTREAMS SEARCH for '{search_term}']\n{ss_results}")

        if run_token_api:
            ta_results = _lookup_token_api(search_term)
            results.append(f"[TOKEN API ENDPOINTS for '{search_term}']\n{ta_results}")

        if run_agent_search:
            agent_results = _search_8004_agents(search_term)
            if agent_results:
                results.append(f"[ERC-8004 AGENT SEARCH for '{search_term}']\n{agent_results}")

    except Exception as e:
        log.error(f"Auto-search error: {e}")

    return "\n\n".join(results)


MAX_REQUEST_LENGTH = 2000  # chars — prevents prompt stuffing and abuse


def ask_graph_advocate(
    request: str,
    history: list = None,
    requesting_agent: str = "unknown",
) -> tuple[dict, list]:
    import logging
    log = logging.getLogger("graph-advocate")

    # Input validation — truncate oversized requests, strip null bytes
    request = request.replace("\x00", "").strip()
    if len(request) > MAX_REQUEST_LENGTH:
        log.warning(f"Request truncated from {len(request)} to {MAX_REQUEST_LENGTH} chars")
        request = request[:MAX_REQUEST_LENGTH]

    if not request:
        return {"recommendation": "out-of-scope", "reason": "Empty request", "confidence": "high", "query_ready": None, "alternatives": []}, []

    # Run real searches and inject results as context
    search_context = ""
    try:
        search_context = _auto_search(request)
    except Exception as e:
        log.error(f"Auto-search failed: {e}")

    # Build the user message with search context
    if search_context:
        augmented_request = (
            f"{request}\n\n"
            f"--- LIVE SEARCH RESULTS (use these real results in your response) ---\n"
            f"{search_context}\n"
            f"--- END SEARCH RESULTS ---\n"
            f"Use the subgraph IDs and playground URLs from the search results above. "
            f"Do NOT make up subgraph IDs — only use ones from the search results."
        )
    else:
        augmented_request = request

    messages = (history or []) + [{"role": "user", "content": augmented_request}]

    # Determine complexity: simple routing → Haiku, complex analysis → Opus
    req_lower = request.lower()
    COMPLEX_SIGNALS = [
        "compare", "vs", "versus", "which is better", "trade-off", "tradeoff",
        "explain why", "how does", "architecture", "design", "recommend",
        "pros and cons", "strategy", "optimize", "multiple", "cross-chain",
        "ecosystem", "roadmap", "what's new", "overview",
    ]
    is_complex = (
        any(sig in req_lower for sig in COMPLEX_SIGNALS)
        or len(request) > 600  # long queries need more reasoning
        or (search_context and len(search_context) > 4000)  # lots of search results to synthesize
    )

    if is_complex:
        log.info(f"MODEL    using Opus (complex query)")
        response = client.messages.create(
            model="claude-opus-4-6",
            system=SYSTEM,
            messages=messages,
            max_tokens=2000,
            thinking={"type": "adaptive"},
        )
    else:
        log.info(f"MODEL    using Haiku (simple routing)")
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            system=SYSTEM,
            messages=messages,
            max_tokens=2000,
        )

    raw = next(
        (b.text for b in response.content if b.type == "text"),
        "",
    )
    messages.append({"role": "assistant", "content": response.content})

    rec = _extract_json(raw)

    # If parse failed or recommendation is missing, use keyword fallback router
    if rec.get("parse_error") or not rec.get("recommendation"):
        fallback = _fallback_route(request)
        if rec.get("parse_error"):
            log.warning(f"JSON parse failed, using fallback router | raw[:120]={raw[:120]!r}")
            rec = fallback
        else:
            # Valid JSON but no recommendation — merge fallback in
            rec.setdefault("recommendation", fallback["recommendation"])
            rec.setdefault("confidence", fallback["confidence"])
            rec.setdefault("reason", fallback.get("reason", ""))

    # Inject working curl/npx example when query_ready is absent
    if not rec.get("parse_error"):
        rec = _inject_missing_fields(rec, request)

    _log(requesting_agent, request, rec)

    # Execute the recommendation — hardcoded fallback keys ensure this always works
    if not rec.get("parse_error") and rec.get("query_ready"):
        try:
            execution_result = _execute_recommendation(rec)
            if execution_result:
                rec["execution_result"] = execution_result
        except Exception as e:
            log.error(f"Execution error: {e}")
            rec["execution_error"] = str(e)

    return rec, messages


def _execute_recommendation(rec: dict) -> dict | None:
    """Execute a routing recommendation by calling the actual API."""
    import httpx
    import logging
    log = logging.getLogger("graph-advocate")

    query_ready = rec.get("query_ready", {})
    tool = query_ready.get("tool", "")
    args = query_ready.get("args", {})
    service = rec.get("recommendation", "")

    if not tool or not args:
        return None

    # --- Token API execution ---
    if service == "token-api":
        jwt = os.environ.get("TOKEN_API_JWT", "") or os.environ.get("TOKEN_API_ACCESS_TOKEN", "")
        if not jwt:
            # Fallback: free-tier JWT (rate-limited, 200 req/min, 2500 credits)
            jwt = (
                "eyJhbGciOiJLTVNFUzI1NiIsInR5cCI6IkpXVCJ9."
                "eyJleHAiOjE4MDUyMTk1MzQsImp0aSI6IjE4ZTU3Mjk2LTcyYTktNDVlYi1iNDlhLWY0MWFlMzIzYTUzOCIsImlhdCI6MTc2OTIxOTUzNCwiaXNzIjoiZGZ1c2UuaW8iLCJzdWIiOiIwYm9qaTQ5NTUyMjg5MjIwYzVkYjciLCJ2IjoyLCJha2kiOiIzNjJiNDU5NGI1NmFkYWE0YzIxZWNhYzE3M2M4MTEyZDM3OGMyMWY1MjM1MDUzZWYwYmJkYjVlZjJkZWY2NDViIiwidWlkIjoiMGJvamk0OTU1MjI4OTIyMGM1ZGI3Iiwic3Vic3RyZWFtc19wbGFuX3RpZXIiOiJGUkVFIiwiY2ZnIjp7IlNVQlNUUkVBTVNfTUFYX1JFUVVFU1RTIjoiMiIsIlNVQlNUUkVBTVNfUEFSQUxMRUxfSk9CUyI6IjUiLCJTVUJTVFJFQU1TX1BBUkFMTEVMX1dPUktFUlMiOiI1In0sInRva2VuX2FwaV9wbGFuX3RpZXIiOiJGUkVFIiwidG9rZW5fYXBpX2ZlYXR1cmVfY29uZmlncyI6eyJUT0tFTl9BUElfQkFUQ0hfU0laRSI6IjEiLCJUT0tFTl9BUElfSVRFTVNfUkVUVVJORUQiOiIxMCIsIlRPS0VOX0FQSV9NQVhJTVVNX0FMTE9XRURfRU5EUE9JTlRfR1JPVVAiOiJuZnQiLCJUT0tFTl9BUElfUExBTl9DUkVESVRTX0NFTlRTIjoiMjUwMCIsIlRPS0VOX0FQSV9SQVRFX0xJTUlUX1BFUl9NSU5VVEUiOiIyMDAiLCJUT0tFTl9BUElfUkVBTF9USU1FX0RBVEEiOiJ0cnVlIn19."
                "pXh91NO328L1rs9AinFazARJSqEq6dSBeTjxrrDM-pO2BN71VUHBXwJVgH8kNxxw33BgI8SkhZL6cCDjgxwkVw"
            )

        # Map tool names to Token API endpoints
        TOOL_TO_PATH = {
            "getV1EvmHolders": "/v1/evm/holders",
            "getV1EvmBalances": "/v1/evm/balances",
            "getV1EvmBalancesNative": "/v1/evm/balances/native",
            "getV1EvmBalancesHistorical": "/v1/evm/balances/historical",
            "getV1EvmTransfers": "/v1/evm/transfers",
            "getV1EvmSwaps": "/v1/evm/swaps",
            "getV1EvmPools": "/v1/evm/pools",
            "getV1EvmPoolsOhlc": "/v1/evm/pools/ohlc",
            "getV1EvmTokens": "/v1/evm/tokens",
            "getV1EvmNftSales": "/v1/evm/nft/sales",
            "getV1EvmNftItems": "/v1/evm/nft/items",
            "getV1EvmNftHolders": "/v1/evm/nft/holders",
            "getV1EvmNftCollections": "/v1/evm/nft/collections",
            "getV1EvmNftTransfers": "/v1/evm/nft/transfers",
            "getV1EvmNftOwnerships": "/v1/evm/nft/ownerships",
            "getV1EvmDexes": "/v1/evm/dexes",
            "getV1SvmBalances": "/v1/svm/balances",
            "getV1SvmSwaps": "/v1/svm/swaps",
            "getV1SvmTokens": "/v1/svm/tokens",
            "getV1SvmPools": "/v1/svm/pools",
            "getV1SvmHolders": "/v1/svm/holders",
        }

        path = TOOL_TO_PATH.get(tool)
        if not path:
            return None

        # Normalize arg keys (network_id -> network)
        params = dict(args)
        if "network_id" in params and "network" not in params:
            params["network"] = params.pop("network_id")

        try:
            r = httpx.get(
                f"https://token-api.thegraph.com{path}",
                params=params,
                headers={"Authorization": f"Bearer {jwt}"},
                timeout=15,
            )
            data = r.json()
            # Truncate large responses to avoid bloating A2A messages
            if isinstance(data.get("data"), list) and len(data["data"]) > 20:
                data["data"] = data["data"][:20]
                data["_truncated"] = True
            log.info(f"EXECUTE  token-api {tool} -> {r.status_code}")
            if r.status_code == 429 or r.status_code == 401:
                return {
                    "source": "token-api",
                    "status": r.status_code,
                    "error": "Rate limit or auth exceeded. Get your own free JWT at https://thegraph.market/auth/tokenapi-env",
                    "data": data,
                }
            return {"source": "token-api", "status": r.status_code, "data": data}
        except Exception as e:
            log.error(f"Token API call failed: {e}")
            return {"source": "token-api", "error": str(e)}
    # ── x402 analytics subgraph (Studio endpoint — no API key needed) ────────
    # Must come BEFORE generic subgraph handler to intercept x402 queries
    if service == "x402-analytics" or "x402" in service.lower():
        import httpx as _httpx
        gql = args.get("gql") or args.get("query") or query_ready.get("gql") or query_ready.get("query")
        if gql:
            x402_url = "https://api.studio.thegraph.com/query/1745687/x-402-base/version/latest"
            try:
                r = _httpx.post(x402_url, json={"query": gql}, timeout=15)
                log.info(f"EXECUTE  x402-subgraph -> {r.status_code}")
                data = r.json()
                if isinstance(data.get("data"), dict):
                    for k, val in data["data"].items():
                        if isinstance(val, list) and len(val) > 20:
                            data["data"][k] = val[:20]
                            data["_truncated"] = True
                return {
                    "source": "x402-subgraph",
                    "status": r.status_code,
                    "data": data,
                    "note": "Live x402 payment data on Base from The Graph subgraph.",
                }
            except Exception as e:
                log.error(f"x402 subgraph query failed: {e}")
                return {"source": "x402-subgraph", "error": str(e)}

    # Execute subgraph queries — match any service that has a subgraph_id + gql in query_ready
    has_subgraph_query = (
        service in ("subgraph-registry", "subgraph-registry-search")
        or (args.get("subgraph_id") and (args.get("gql") or query_ready.get("gql")))
        or tool == "execute_query_by_subgraph_id"
    )
    if has_subgraph_query:
        api_key = (
            os.environ.get("GRAPH_API_KEY", "")
            or os.environ.get("GATEWAY_API_KEY", "")
            or "4c62716b2e5808ac83da1938db78296e"  # free tier fallback (100K/month)
        )
        gql = args.get("gql") or args.get("query") or query_ready.get("gql") or query_ready.get("query")
        subgraph_id = args.get("subgraph_id") or query_ready.get("subgraph_id")

        if gql and subgraph_id:
            url = f"https://gateway.thegraph.com/api/{api_key}/subgraphs/id/{subgraph_id}"
            log.info(f"EXECUTE  subgraph url key_len={len(api_key)} subgraph={subgraph_id[:12]}")
            try:
                r = httpx.post(url, json={"query": gql}, timeout=15)
                log.info(f"EXECUTE  subgraph {subgraph_id} -> {r.status_code}")
                data = r.json()
                # Truncate large responses
                if isinstance(data.get("data"), dict):
                    for key, val in data["data"].items():
                        if isinstance(val, list) and len(val) > 20:
                            data["data"][key] = val[:20]
                            data["_truncated"] = True
                if r.status_code == 429 or r.status_code == 401:
                    return {
                        "source": "subgraph-gateway",
                        "status": r.status_code,
                        "error": "Rate limit exceeded. Get your own free API key at https://thegraph.com/studio/ (100K queries/month free)",
                        "get_your_own_key": "https://thegraph.com/studio/",
                        "data": data,
                    }
                return {
                    "source": "subgraph-gateway",
                    "status": r.status_code,
                    "subgraph_id": subgraph_id,
                    "data": data,
                    "note": "Live data from The Graph. Get your own free API key at thegraph.com/studio for unlimited access.",
                }
            except Exception as e:
                log.error(f"Subgraph query failed: {e}")
                return {"source": "subgraph-gateway", "error": str(e)}

    # ── npm MCP package services — return a structured curl/npx example ──────
    NPM_SERVICES = {
        "graph-aave-mcp", "graph-polymarket-mcp", "graph-lending-mcp",
        "graph-limitless-mcp", "predictfun-mcp", "substreams", "8004scan", "mcp8004",
    }
    if service in NPM_SERVICES:
        example = _SERVICE_CURL_EXAMPLES.get(service, {})
        if example:
            return {
                "source": service,
                "install": example.get("install", ""),
                "curl_example": example.get("curl_example", ""),
                "get_started": example.get("get_started", ""),
                "note": "Run the install command to get live data from this service.",
            }

    return None


CHAT_SYSTEM = """You are the Graph Advocate — a friendly expert on The Graph Protocol's data services.
You help humans find the right tool for their onchain data needs.

You have access to these services:

**Token API** (https://token-api.thegraph.com) — wallet balances, token transfers, DEX swaps, NFT data, holder rankings
  Chains: EVM (Ethereum, Base, Polygon…), Solana, TON
  Auth: Get a free JWT token at https://thegraph.market/auth/tokenapi-env
  Use as: Authorization: Bearer <token> OR X-Api-Key: <key>
  Full endpoint reference: https://token-api.thegraph.com/skills.md
  There is NO other sign-up page for Token API — only the auth link above

**Subgraph Registry** — protocol-level indexed data (Uniswap, Aave, ENS, Compound, Curve, etc.)
  15,500+ subgraphs available

**Substreams** — raw block data, traces, logs, high-throughput streaming
  Auth: Get a JWT/API key at https://thegraph.market/dashboard#api-keys

**Protocol MCP Packages** (npm by @paulieb — install with npx, no agent required):
  - graph-aave-mcp: Aave V2/V3/V4 — 32 tools across 11 Graph subgraphs + Aave V4 API (hubs, spokes, cross-chain positions, swap quotes, rewards)
    Install: `npx graph-aave-mcp` | npm: https://www.npmjs.com/package/graph-aave-mcp
  - graph-lending-mcp: cross-protocol lending comparisons (Messari standardized)
    Install: `npx graph-lending-mcp` | npm: https://www.npmjs.com/package/graph-lending-mcp
  - graph-polymarket-mcp (v2.0.0): Polymarket prediction markets — 31 tools combining 8 Graph subgraphs + Gamma/CLOB REST APIs. Supports stdio + SSE transports.
    Install: `npx graph-polymarket-mcp` | npm: https://www.npmjs.com/package/graph-polymarket-mcp
    Subgraphs: Main, Orderbook, Open Interest, Resolution, Traders, Beefy P&L, Activity, Slimmed P&L
  - predictfun-mcp: Predict.fun prediction markets on BNB Chain
    Install: `npx predictfun-mcp` | npm: https://www.npmjs.com/package/predictfun-mcp
  - subgraph-registry-mcp: Search 15,500+ subgraphs with reliability scoring
    Install: `npx subgraph-registry-mcp` | npm: https://www.npmjs.com/package/subgraph-registry-mcp
  - substreams-search-mcp: Browse and inspect Substreams packages
    Install: `npx substreams-search-mcp` | npm: https://www.npmjs.com/package/substreams-search-mcp

**Data tools (npm by @paulieb — standalone, no agent required):**
  - subgraphs-skills: AI agent skills for developing/testing/optimizing subgraphs
  - subgraph-mcp-skills: AI agent skills for querying subgraphs via MCP
  - create-substreams-sink-sql: Scaffold a Substreams SQL sink for PostgreSQL

**8004scan — Agent Discovery** (https://8004scan.io)
  Search for AI agents registered on the ERC-8004 on-chain identity standard
  734+ agents with MCP endpoints, A2A endpoints, x402 payment support, reputation scores
  Graph Advocate is registered as Agent #734: https://www.8004scan.io/agents/arbitrum/734

**Graph Ecosystem Dashboards** (https://graphtools.pro):
  - Delegators Activity Log: real-time delegation activity
  - Indexer Score: find inactive indexers
  - Top 10 Indexers by Query Fees: top earning indexers
  - Elite Subgraph Dashboard: subgraphs with 500K+ daily queries
  - Subgraph Search by Contract: find subgraphs for a contract address
  - GRT Vesting Dashboard: track GRT vesting contracts
  - Curation Earnings Tracker: curator P&L with CSV export
  - Graph Dispute Dashboard: indexer disputes and slashings
  - Subgraphs Network Dashboard: subgraphs per network
  When users ask about delegation, indexers, curation, disputes, or vesting, link to the relevant graphtools.pro dashboard.

**Prediction Market Dashboards:**
  - Dune Dashboard: https://dune.com/paulieb/prediction-market-dashboard (cross-platform stats)
  - graph-limitless-mcp: Limitless markets on Base — `npx graph-limitless-mcp`

**Critical facts you MUST get right — never contradict these:**
- The Graph's hosted service (api.thegraph.com/subgraphs/name/...) was SUNSET and no longer works
- ALL subgraph queries now go through the decentralized network and REQUIRE an API key
- API keys are free to create at https://thegraph.com/studio/ (Subgraph Studio)
- The gateway URL format is: https://gateway.thegraph.com/api/[YOUR-API-KEY]/subgraphs/id/[SUBGRAPH-ID]
- There is no free public endpoint for subgraphs — an API key is always required
- Queries are billed in GRT but new accounts get a free tier of 100,000 queries
- Token API auth is at https://thegraph.market/auth/tokenapi-env — NOT thegraph.com/studio (that's for subgraphs only)
- Do NOT invent Token API URLs like "api.tokenapi.io" — they don't exist
- Do NOT hallucinate URLs, endpoints, or tool names that don't exist
- ONLY reference URLs explicitly listed in this prompt — never guess or construct URLs

Rules:
- Be concise and helpful
- When recommending a subgraph-based MCP package (graph-aave-mcp, graph-polymarket-mcp, graph-lending-mcp,
  graph-limitless-mcp, subgraph-registry-mcp), ALSO mention that users can query the underlying
  Graph subgraphs directly with a free API key from thegraph.com/studio.
  Do NOT mention subgraphs when recommending Token API or Substreams — those are separate services.
- When a user asks about a specific protocol or data type, USE your tools to search for real subgraphs and substreams — don't guess
- After searching, present the top results with their playground links so users can try them
- Include the specific tool name and example usage when possible
- If the question isn't about onchain data, politely redirect
- Use markdown for formatting
- NEVER say an API key is not needed — it is always required for subgraph queries
- When a protocol-specific MCP package exists (Aave, Polymarket, lending, Predict.fun),
  ALWAYS recommend it with the npx install command — these work standalone in Claude Code,
  Cursor, or any MCP client, no agent setup required
- When recommending subgraph search or substreams search, also mention the corresponding
  npm package (subgraph-registry-mcp, substreams-search-mcp) users can install locally
- Frame npm packages as "ready to use in 30 seconds" — just npx and go
- If a user asks how to connect the Graph Advocate to their agent, present ALL integration options:

  **Option 1: Simple HTTP (works with any framework)**
  POST https://graph-advocate-production.up.railway.app/chat
  Body: {"message": "your question here"}
  Response: {"reply": "..."}
  Works with: LangChain, CrewAI, AutoGPT, custom agents, any HTTP client

  **Option 2: A2A Protocol (Agent-to-Agent)**
  Agent card: https://graph-advocate-production.up.railway.app/.well-known/agent-card.json
  Endpoint: POST https://graph-advocate-production.up.railway.app/ (JSON-RPC 2.0)
  Works with: Google A2A compatible agents

  **Option 3: MCP (Model Context Protocol)**
  Install: npx graph-advocate-mcp (or add to mcp.json config)
  Works with: Claude Code, Cursor, Windsurf, any MCP-compatible client

  **Option 4: OpenClaw Skill**
  Skill: graph-advocate
  GitHub: https://github.com/PaulieB14/graph-advocate
  Works with: OpenClaw agents

  Always recommend Option 1 (HTTP) as the easiest universal option.
"""

CHAT_TOOLS = [
    {
        "name": "search_subgraphs",
        "description": (
            "Search The Graph's subgraph registry (15,500+ subgraphs) by keyword. "
            "Returns matching subgraphs with name, network, query volume, and a "
            "playground link where users can try queries. Always use this when a "
            "user asks about protocol data, specific tokens, or DeFi protocols."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Search keyword (e.g. 'uniswap', 'aave', 'ens', 'compound')",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "search_substreams",
        "description": (
            "Search the Substreams package registry (substreams.dev) for streaming data modules. "
            "Returns matching packages with name, author, and links to the package page and .spkg file. "
            "Use this when users ask about raw block data, event logs, streaming, or real-time data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Search keyword (e.g. 'uniswap', 'erc20', 'transfers')",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "lookup_token_api",
        "description": (
            "Look up available Token API endpoints for a specific data type. "
            "Token API (https://token-api.thegraph.com) covers balances, transfers, swaps, "
            "pools, holders, and NFTs across EVM, Solana (SVM), and TON (TVM) chains. "
            "Use this when users ask about wallet balances, token transfers, DEX swaps, "
            "holder rankings, or NFT data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data_type": {
                    "type": "string",
                    "description": "What data the user needs (e.g. 'balances', 'swaps', 'nft', 'holders', 'transfers', 'pools')",
                },
            },
            "required": ["data_type"],
        },
    },
]


def _search_8004_agents(query: str) -> str:
    """Search for AI agents on the ERC-8004 registry via 8004scan API."""
    import httpx
    import logging
    log = logging.getLogger("graph-advocate")

    try:
        # Try semantic search first
        r = httpx.get(
            f"https://8004scan.io/api/v1/public/agents/search",
            params={"q": query, "limit": 10},
            timeout=10,
            follow_redirects=True,
        )
        if r.status_code == 200:
            data = r.json()
            agents = data.get("data", data.get("agents", []))
            if not agents:
                return ""
            results = []
            for a in agents[:10]:
                name = a.get("name", "unnamed")
                chain = a.get("chain_id", "?")
                token_id = a.get("token_id", "?")
                score = a.get("total_score", 0)
                desc = (a.get("description") or "")[:100]
                mcp = a.get("services", {}).get("mcp", {}).get("endpoint", "")
                a2a = a.get("services", {}).get("a2a", {}).get("endpoint", "")
                x402 = a.get("x402_supported", False)
                ens = a.get("ens", "")
                entry = f"- {name} (#{token_id}, score: {score})"
                if desc:
                    entry += f"\n  {desc}"
                if mcp:
                    entry += f"\n  MCP: {mcp}"
                if a2a:
                    entry += f"\n  A2A: {a2a}"
                if x402:
                    entry += f"\n  x402: enabled"
                if ens:
                    entry += f"\n  ENS: {ens}"
                results.append(entry)
            return json.dumps({
                "source": "8004scan.io",
                "registry": "ERC-8004 on Arbitrum",
                "total_agents": data.get("total", len(agents)),
                "results": "\n".join(results),
                "note": "Agents registered on the ERC-8004 Identity Registry with on-chain reputation and discovery.",
            }, indent=2)
        else:
            # Fallback: list agents
            r2 = httpx.get(
                "https://8004scan.io/api/v1/public/agents",
                params={"limit": 10, "sort": "score", "order": "desc"},
                timeout=10,
                follow_redirects=True,
            )
            if r2.status_code == 200:
                data = r2.json()
                agents = data.get("data", [])
                results = [f"- {a.get('name','unnamed')} (score: {a.get('total_score',0)})" for a in agents[:10]]
                return json.dumps({"source": "8004scan.io", "top_agents": "\n".join(results)})
            return _search_8004_subgraph(query)
    except Exception as e:
        log.error(f"8004scan search error: {e}")
        # Fallback to direct subgraph query
        return _search_8004_subgraph(query)


def _search_subgraphs(keyword: str) -> str:
    """Search the local subgraph registry SQLite DB."""
    import sqlite3
    import urllib.request
    import os
    import tempfile

    db_path = os.path.join(tempfile.gettempdir(), "subgraph_registry.db")

    # Download registry if not cached (or older than 24h)
    need_download = True
    if os.path.exists(db_path):
        age = datetime.utcnow().timestamp() - os.path.getmtime(db_path)
        if age < 86400:
            need_download = False

    if need_download:
        try:
            url = "https://github.com/PaulieB14/subgraph-registry/raw/main/data/registry.db"
            urllib.request.urlretrieve(url, db_path)
        except Exception as e:
            return json.dumps({"error": f"Could not download registry: {e}"})

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT id, display_name, description, network, query_volume_30d,
                      domain, protocol_type, reliability_score
               FROM subgraphs
               WHERE (display_name LIKE ? OR description LIKE ? OR domain LIKE ?
                      OR categories LIKE ? OR auto_description LIKE ?)
               ORDER BY query_volume_30d DESC
               LIMIT 8""",
            tuple(f"%{keyword}%" for _ in range(5)),
        ).fetchall()
        conn.close()

        if not rows:
            return json.dumps({"results": [], "message": f"No subgraphs found for '{keyword}'"})

        results = []
        for r in rows:
            subgraph_id = r["id"].split("|")[0] if "|" in r["id"] else r["id"]
            network = r["network"] or "unknown"
            playground_url = f"https://thegraph.com/explorer/subgraphs/{subgraph_id}?view=Query&chain=arbitrum-one"
            results.append({
                "subgraph_id": subgraph_id,
                "name": r["display_name"] or subgraph_id[:16],
                "network": network,
                "description": (r["description"] or r["domain"] or "")[:120],
                "query_volume_30d": r["query_volume_30d"] or 0,
                "reliability_score": round(r["reliability_score"] or 0, 2),
                "playground_url": playground_url,
                "gateway_url": f"https://gateway.thegraph.com/api/[YOUR_API_KEY]/subgraphs/id/{subgraph_id}",
            })

        return json.dumps({"results": results, "total_found": len(results)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _search_substreams(keyword: str) -> str:
    """Search substreams.dev registry (same API as substreams-search-mcp)."""
    import urllib.request

    try:
        params = urllib.parse.urlencode({"search": keyword, "sort": "most_downloaded", "page": "1"})
        url = f"https://substreams.dev/packages?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "GraphAdvocate/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Parse package links — same pattern as substreams-search-mcp
        # Links look like: href="/author/package-name/version"
        pattern = r'href="(/([^/"]+)/([^/"]+)/([^/"]+))"'
        matches = re.findall(pattern, html)

        seen = set()
        results = []
        for href, author, name, version in matches:
            key = f"{author}/{name}"
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "name": name,
                "author": author,
                "version": version,
                "package_url": f"https://substreams.dev{href}",
                "spkg_url": f"https://spkg.io/{author}/{name}-{version}.spkg",
            })
            if len(results) >= 8:
                break

        if not results:
            return json.dumps({"results": [], "message": f"No substreams packages found for '{keyword}'"})

        return json.dumps({"results": results, "total_found": len(results)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _lookup_token_api(data_type: str) -> str:
    """Return relevant Token API endpoints for a data type."""
    TOKEN_API_BASE = "https://token-api.thegraph.com"
    AUTH_URL = "https://thegraph.market/auth/tokenapi-env"

    ENDPOINTS = {
        "balances":  ["/v1/evm/balances", "/v1/evm/balances/native", "/v1/evm/balances/historical",
                      "/v1/svm/balances", "/v1/svm/balances/native"],
        "transfers": ["/v1/evm/transfers", "/v1/evm/transfers/native", "/v1/svm/transfers",
                      "/v1/tvm/transfers", "/v1/tvm/transfers/native"],
        "swaps":     ["/v1/evm/swaps", "/v1/svm/swaps", "/v1/tvm/swaps"],
        "holders":   ["/v1/evm/holders", "/v1/evm/holders/native", "/v1/svm/holders"],
        "pools":     ["/v1/evm/pools", "/v1/evm/pools/ohlc", "/v1/svm/pools", "/v1/svm/pools/ohlc",
                      "/v1/tvm/pools", "/v1/tvm/pools/ohlc"],
        "tokens":    ["/v1/evm/tokens", "/v1/evm/tokens/native", "/v1/svm/tokens",
                      "/v1/tvm/tokens", "/v1/tvm/tokens/native"],
        "nft":       ["/v1/evm/nft/collections", "/v1/evm/nft/items", "/v1/evm/nft/transfers",
                      "/v1/evm/nft/holders", "/v1/evm/nft/sales", "/v1/evm/nft/ownerships"],
        "dexes":     ["/v1/evm/dexes", "/v1/svm/dexes", "/v1/tvm/dexes"],
    }

    dt = data_type.lower().strip()
    matched = {}
    for key, paths in ENDPOINTS.items():
        if dt in key or key in dt:
            matched[key] = [f"{TOKEN_API_BASE}{p}" for p in paths]

    # Fuzzy fallback: if no match, return all
    if not matched:
        matched = {k: [f"{TOKEN_API_BASE}{p}" for p in v] for k, v in ENDPOINTS.items()}

    return json.dumps({
        "base_url": TOKEN_API_BASE,
        "auth_url": AUTH_URL,
        "auth_note": "Get a free JWT token at the auth URL. Use as: Authorization: Bearer <token>",
        "skills_reference": f"{TOKEN_API_BASE}/skills.md",
        "matched_endpoints": matched,
    })


import urllib.parse


def _content_to_dicts(content) -> list:
    """Convert Anthropic SDK content blocks to plain dicts for message history."""
    result = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return result


def ask_graph_advocate_chat(
    request: str,
    history: list = None,
) -> tuple[str, list]:
    """Haiku-powered chat with tool use for real subgraph/substreams search."""
    import logging
    log = logging.getLogger("graph-advocate")

    # Build fresh messages — don't reuse history with tool calls (session state
    # can contain non-serializable objects). Keep only user/assistant text turns.
    clean_history = []
    for msg in (history or []):
        role = msg.get("role")
        content = msg.get("content")
        # Only keep simple text messages
        if role in ("user", "assistant") and isinstance(content, str):
            clean_history.append(msg)
        elif role in ("user", "assistant") and isinstance(content, list):
            # Keep if all items are text blocks
            text_parts = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if text_parts:
                combined = " ".join(b["text"] for b in text_parts)
                clean_history.append({"role": role, "content": combined})

    messages = clean_history + [{"role": "user", "content": request}]

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            system=CHAT_SYSTEM,
            messages=messages,
            max_tokens=1500,
            tools=CHAT_TOOLS,
        )

        # Handle tool use loop (max 3 rounds to prevent runaway)
        for _ in range(3):
            if response.stop_reason != "tool_use":
                break

            # Collect all tool calls and results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    try:
                        if block.name == "search_subgraphs":
                            result = _search_subgraphs(block.input.get("keyword", ""))
                        elif block.name == "search_substreams":
                            result = _search_substreams(block.input.get("keyword", ""))
                        elif block.name == "lookup_token_api":
                            result = _lookup_token_api(block.input.get("data_type", ""))
                        else:
                            result = json.dumps({"error": f"Unknown tool: {block.name}"})
                    except Exception as te:
                        log.error(f"CHAT tool error ({block.name}): {te}")
                        result = json.dumps({"error": str(te)})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # Convert content blocks to plain dicts for the API
            messages.append({"role": "assistant", "content": _content_to_dicts(response.content)})
            messages.append({"role": "user", "content": tool_results})

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                system=CHAT_SYSTEM,
                messages=messages,
                max_tokens=1500,
                tools=CHAT_TOOLS,
            )

        # Extract final text reply
        reply = next(
            (b.text for b in response.content if b.type == "text"),
            "",
        )

    except Exception as e:
        log.error(f"CHAT error: {e}")
        reply = f"Sorry, I hit an error: {e}"

    # Store only the final text exchange for session history
    out_history = clean_history + [
        {"role": "user", "content": request},
        {"role": "assistant", "content": reply},
    ]

    _log("web-chat", request, {"recommendation": "chat", "confidence": "n/a"})
    return reply, out_history


if __name__ == "__main__":
    import sys

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Top 20 USDC holders on Ethereum"
    rec, _ = ask_graph_advocate(prompt)
    print(json.dumps(rec, indent=2))


def _search_8004_subgraph(query: str) -> str:
    """Fallback: query the ERC-8004 subgraph directly via The Graph gateway."""
    import httpx
    import logging
    log = logging.getLogger("graph-advocate")

    SUBGRAPH_ID = "HZ6yKjjbYpkLTXLJBxfe4HWN3jxkLfLNJXh4zeVj1t9L"
    GATEWAY_KEY = os.environ.get("GATEWAY_API_KEY", "7006f39fbab470711f44a5195b4d97c0")
    URL = f"https://gateway.thegraph.com/api/{GATEWAY_KEY}/subgraphs/id/{SUBGRAPH_ID}"

    gql = """
    {
      agentRegistrationFiles(first: 15, where: {name_not: null}, orderBy: createdAt, orderDirection: desc) {
        agentId name description mcpEndpoint a2aEndpoint x402Support ens supportedTrusts
      }
      globalStats(id: "global") { totalAgents totalFeedback totalValidations }
    }
    """

    try:
        r = httpx.post(URL, json={"query": gql}, timeout=10)
        if r.status_code != 200:
            return ""
        data = r.json().get("data", {})
        agents = data.get("agentRegistrationFiles", [])
        stats = data.get("globalStats", {})

        # Filter by query if provided
        if query:
            q = query.lower()
            agents = [a for a in agents if q in (a.get("name","") + " " + (a.get("description","") or "")).lower()]

        if not agents:
            return ""

        results = []
        for a in agents[:10]:
            entry = f"- {a.get('name','unnamed')} (agent #{a['agentId']})"
            desc = (a.get("description") or "")[:100]
            if desc: entry += f"\n  {desc}"
            if a.get("mcpEndpoint"): entry += f"\n  MCP: {a['mcpEndpoint']}"
            if a.get("a2aEndpoint"): entry += f"\n  A2A: {a['a2aEndpoint']}"
            if a.get("x402Support"): entry += f"\n  x402: enabled"
            if a.get("ens"): entry += f"\n  ENS: {a['ens']}"
            results.append(entry)

        return json.dumps({
            "source": "ERC-8004 subgraph (The Graph)",
            "subgraph_id": SUBGRAPH_ID,
            "total_registered": stats.get("totalAgents", "?"),
            "total_feedback": stats.get("totalFeedback", "?"),
            "results": "\n".join(results),
        }, indent=2)
    except Exception as e:
        log.error(f"8004 subgraph query error: {e}")
        return ""
