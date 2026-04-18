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
_db_init_lock = threading.Lock()
_DB_PATH = os.environ.get(
    "RECOMMENDATIONS_DB",
    "/data/recommendations.db" if os.path.isdir("/data") else "recommendations.db",
)
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
        with _db_init_lock:
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
Best for: wallet balances, token transfers, DEX swaps, NFT data, holder rankings, AND Polymarket prediction market data
Chains: EVM (Ethereum, Base, Polygon…), SVM (Solana), TVM (TON), plus Polymarket (Polygon)
Key tools: getV1EvmBalances, getV1EvmSwaps, getV1EvmNftSales, getV1SvmBalances, getV1EvmHolders, getV1EvmTransfers, getV1EvmPools, getV1EvmPoolsOhlc, getV1SvmNftSales, getV1EvmNftItems, getV1EvmNftHolders
Solana (SVM) native endpoints: getV1SvmTokensNative, getV1SvmTransfersNative, getV1SvmHoldersNative
Solana DEX coverage: Raydium (AMM v4, CLMM, CPMM, Launchpad), Pump.fun, Orca Whirlpool, Meteora DLLM, Jupiter (v4/v6), Boop, Darklake, Dumpfun
CRITICAL — Token API parameter names (use EXACTLY these, never alias):
  - "network" (REQUIRED): "mainnet", "base", "matic", "arbitrum-one", "optimism", "avalanche-mainnet", "bsc-mainnet"
  - "contract" (REQUIRED for holders/tokens): the token contract address
  - "address" (REQUIRED for balances): the wallet address
  - DO NOT use "chain", "token_address", "token", or "network_id" — these are WRONG
  Full reference: https://token-api.thegraph.com/skills.md
  Common contracts:
    USDC: mainnet=0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48, base=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
    WETH: mainnet=0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2, base=0x4200000000000000000000000000000000000006
    USDT: mainnet=0xdAC17F958D2ee523a2206206994597C13D831ec7
  Example: getV1EvmHolders with args: {"network": "base", "contract": "0x4200000000000000000000000000000000000006", "limit": 5}

  Polymarket Prediction Markets API (part of Token API):
  Production-grade Polymarket data — markets, prices, activity, and P&L — through REST endpoints.
  On-chain Polygon data enriched with Polymarket metadata. No npm install needed.
  Endpoints:
    GET /v1/polymarket/markets — market lookup by condition_id, slug, or token_id; discovery with sort/filter
    GET /v1/polymarket/markets/ohlc — OHLCV + fees per outcome token
    GET /v1/polymarket/markets/oi — open interest time-series (splits/merges that move USDC collateral)
    GET /v1/polymarket/markets/activity — trades, splits, merges, redemptions in chronological order
    GET /v1/polymarket/markets/positions — per-token leaderboard with cost basis, PNL, shares held
    GET /v1/polymarket/platform — platform-wide volume, open interest, fee aggregates
    GET /v1/polymarket/users — user discovery with volume/PNL/transaction counts
    GET /v1/polymarket/users/positions — user portfolio with realized/unrealized PNL per outcome token
  Docs: https://thegraph.com/docs/en/token-api/polymarket-markets/markets/
  PREFER Token API for Polymarket queries (markets, OHLCV, positions, P&L, activity, leaderboards).
  Use graph-polymarket-mcp only for advanced use cases: live orderbook depth, live spreads, disputed markets, UMA resolution lifecycle.

[SUBGRAPH REGISTRY]
Best for: protocol-level indexed data (Uniswap, Aave, ENS, Compound, Curve, Balancer, etc.)
Use when: the agent needs entities, relationships, or aggregations a subgraph tracks
Key tools: search_subgraphs_by_keyword, get_schema_by_subgraph_id, execute_query_by_subgraph_id
IMPORTANT — Common subgraph entity names (do NOT guess, use these):
  - Uniswap V2: pairs(orderBy: reserveUSD) { token0 { symbol } token1 { symbol } reserveUSD volumeUSD }
  - Uniswap V3: pools(orderBy: totalValueLockedUSD) { token0 { symbol } token1 { symbol } totalValueLockedUSD feeTier }
  - Aave V2/V3: markets(orderBy: totalDepositBalanceUSD) { name inputToken { symbol } totalDepositBalanceUSD totalBorrowBalanceUSD }
  - Compound: markets(orderBy: totalDepositBalanceUSD) { name inputToken { symbol } totalDepositBalanceUSD }
  - ENS: registrations(orderBy: registrationDate) { domain { name } registrant { id } registrationDate }
  - Curve: pools(orderBy: totalValueLockedUSD) { name totalValueLockedUSD coins }
  Always use the entity names from the search results or these hints — never invent field names.
npm: subgraph-registry-mcp (14,700+ classified subgraphs with domain/protocol/reliability scoring, bot-readable category files)
npm: subgraphs-skills (AI agent skills for developing/testing/optimizing subgraphs)
npm: subgraph-mcp-skills (AI agent skills for querying subgraphs via MCP tools)

[SUBSTREAMS]
Best for: raw block data, traces, logs, anything not yet in a subgraph, high-throughput streaming
Use when: the agent needs highly specific or real-time block-level data, custom transformations, or data not covered by existing subgraphs
Key tools: search_substreams, stream_data
Browse packages (no auth needed): https://substreams.dev
Auth: Substreams uses a JWT (not a plain API key like subgraphs). Sign up at https://thegraph.market → create an API key → generate a JWT → run `substreams auth` to use it. Docs: https://docs.substreams.dev
npm: substreams-search-mcp (search and inspect Substreams packages, browse registry, introspect .spkg modules)
npm: create-substreams-sink-sql (scaffold a Substreams SQL sink for PostgreSQL — zero custom code)

[PROTOCOL-SPECIFIC MCP SERVERS — npm packages by @paulieb]
Use these when the agent's request matches a specific protocol. Install via: npx <package-name>

- graph-aave-mcp: Aave V2/V3/V4 — 40 tools across 16 Graph subgraphs + Aave V4 API
  Use for: Aave liquidations, deposits, borrows, interest rates, governance votes, V4 hubs/spokes, cross-chain positions, exchange rates, swap quotes, rewards
  V2/V3: Powered by Graph subgraphs — Aave V3 on Ethereum, Arbitrum, Optimism, Polygon, Avalanche, Base, Metis + Aave V2 Ethereum + Governance
  V4: Powered by Aave V4 API (api.aave.com) — no API key needed. 16 tools: get_v4_hubs, get_v4_spokes, get_v4_reserves, get_v4_user_positions, get_v4_user_summary, get_v4_exchange_rate, get_v4_swap_quote, get_v4_claimable_rewards, and more
  V4 architecture: Hubs (Core, Plus, Prime) aggregate liquidity across Spokes (Main, Bluechip, Kelp, Lido, Ethena, EtherFi, Forex, Gold, Lombard) — cross-chain lending
- graph-lending-mcp: Unified tools over Messari standardized lending subgraphs (multi-protocol)
  Use for: cross-protocol lending comparisons, TVL, utilization rates
  Powered by Graph subgraphs: Messari-standardized subgraphs for Aave, Compound, MakerDAO, and other lending protocols
- graph-polymarket-mcp (v2.0.0): Polymarket prediction markets — 31 tools combining The Graph subgraphs + Polymarket REST APIs (Gamma + CLOB)
  NOTE: For common Polymarket queries (markets, OHLCV, positions, P&L, activity), PREFER Token API — simpler REST, no npm install.
  Use graph-polymarket-mcp ONLY for: live orderbook depth, live spreads, disputed markets, UMA resolution, subgraph-specific deep queries
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

For ecosystem questions, use recommendation="ecosystem-overview" with confidence="high".

Rules:
- Always respond in valid JSON — other agents parse your output programmatically
- ALWAYS include query_ready with tool name + args — NEVER return query_ready: null for data requests
  For subgraph queries: query_ready.args MUST include subgraph_id (from search results) and gql (GraphQL query using entity names from query_hint)
  For token-api queries: query_ready.args MUST include network and contract (use the exact param names, NOT chain/token_address)
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

CRITICAL — recommendation MUST be exactly one of these values (never invent new names):
  token-api, subgraph-registry, substreams, graph-aave-mcp, graph-polymarket-mcp,
  graph-lending-mcp, graph-limitless-mcp, predictfun-mcp, mcp8004, 8004scan,
  x402-analytics, introduction, out-of-scope, comparison
  Do NOT use names like "Uniswap V3 Ethereum Subgraph" or "subgraph-query-builder" — use "subgraph-registry" instead.

Response format — always valid JSON with these fields:
{
  "recommendation": "<MUST be one of the values listed above>",
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
- "Hottest Polymarket markets" → token-api (/v1/polymarket/markets)
- "Polymarket OHLCV for Bitcoin market" → token-api (/v1/polymarket/markets/ohlc)
- "Polymarket trader P&L for 0x..." → token-api (/v1/polymarket/users/positions)
- "Polymarket live orderbook depth" → graph-polymarket-mcp (get_live_orderbook) — advanced, needs npm
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
            "# 1. Search Substreams packages (no auth needed)\n"
            "npx substreams-search-mcp\n\n"
            "# Or browse the registry directly\n"
            "curl 'https://substreams.dev/packages?search=uniswap&sort=most_downloaded'\n\n"
            "# 2. To stream data, install the Substreams CLI:\n"
            "#    https://docs.substreams.dev/how-to-guides/installing-the-cli\n"
            "# 3. Auth: create an API key at https://thegraph.market, generate a JWT,\n"
            "#    then run:  substreams auth\n"
            "# 4. Run a package:  substreams run <spkg> module_name -e mainnet.eth.streamingfast.io:443"
        ),
        "get_started": (
            "Substreams uses a JWT (not a plain API key). "
            "Sign up at https://thegraph.market → create an API key → generate a JWT → "
            "use it with `substreams auth`. Docs: https://docs.substreams.dev"
        ),
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
            "  -H 'Authorization: Bearer YOUR_JWT'\n\n"
            "# Polymarket — browse active markets\n"
            "curl 'https://token-api.thegraph.com/v1/polymarket/markets?limit=10&sort=volume&order=desc' \\\n"
            "  -H 'Authorization: Bearer YOUR_JWT'\n\n"
            "# Polymarket — user portfolio P&L\n"
            "curl 'https://token-api.thegraph.com/v1/polymarket/users/positions?user=0xADDRESS' \\\n"
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


# ── Public capability metadata (consumed by /agents/capabilities.json) ────────
# Externalized so the routing surface is editable without touching code, and
# so other agents can discover Graph Advocate's coverage without parsing the
# system prompt. Mirrors Push Chain's /agents/capabilities.json pattern.
_SERVICE_METADATA: dict[str, dict] = {
    "token-api": {
        "summary": "Hosted REST API for token data — balances, holders, transfers, swaps, NFTs across EVM, Solana, and TON.",
        "best_for": [
            "Wallet balances on Ethereum / Base / Arbitrum / Solana / TON",
            "Top holders, biggest swaps, whale transfers",
            "NFT collections and ownership",
            "Current prices and 30-day balance history",
        ],
        "not_for": ["Custom GraphQL joins", "Historical pool mechanics that need protocol-specific entities"],
        "auth": "Free JWT — https://thegraph.market/auth/tokenapi-env",
        "interface": "REST",
        "example_prompts": [
            "Top 20 USDC holders on Ethereum",
            "Wallet balances on Base for 0xabc…",
            "Solana NFT sales last 7 days",
        ],
    },
    "subgraph-registry": {
        "summary": "Discover the right subgraph from 15,500+ indexed subgraphs and run GraphQL queries against it.",
        "best_for": [
            "Custom GraphQL with protocol-specific entities",
            "Historical state (TVL over time, positions, events)",
            "Joins not exposed by REST APIs",
        ],
        "not_for": ["One-shot 'current price/balance' lookups (use token-api)"],
        "auth": "Free Graph Network API key — https://thegraph.com/studio/",
        "interface": "GraphQL",
        "example_prompts": [
            "Uniswap V3 pool TVL and fee tiers",
            "Lens Protocol followers over time",
            "What subgraphs exist for NFT sales on Base?",
        ],
    },
    "substreams": {
        "summary": "Parallel, sub-block streaming of raw blockchain events, traces, and logs via the StreamingFast firehose.",
        "best_for": [
            "Custom indexing pipelines",
            "Raw event logs across large block ranges",
            "Streaming traces / receipts at full chain throughput",
        ],
        "not_for": ["Quick one-shot reads (subgraph or token-api are cheaper)"],
        "auth": "JWT from https://thegraph.market — used with `substreams auth`",
        "interface": "gRPC / CLI",
        "example_prompts": [
            "Raw decoded event logs, blocks 19000000 to 20000000",
            "Stream all ERC20 transfers on Base",
        ],
    },
    "graph-aave-mcp": {
        "summary": "MCP server with 40+ tools over Aave V2 / V3 / V4, including cross-chain liquidation risk.",
        "best_for": [
            "Aave market state, positions, liquidations",
            "Cross-chain Aave V4 hub/spoke topology",
            "Yield and rate analytics",
        ],
        "not_for": ["Non-Aave lending protocols (use graph-lending-mcp)"],
        "auth": "Free Graph Network API key",
        "interface": "MCP (Model Context Protocol)",
        "example_prompts": [
            "Top Aave V3 markets by TVL on Ethereum",
            "Recent Aave liquidations above $50K",
        ],
    },
    "graph-polymarket-mcp": {
        "summary": "MCP server with 31 tools over Polymarket prediction markets.",
        "best_for": ["Hottest markets", "Trader PnL", "Order book depth"],
        "not_for": ["Predict.fun (use predictfun-mcp)", "Limitless (use graph-limitless-mcp)"],
        "auth": "None for REST endpoints; Graph API key for subgraph queries",
        "interface": "MCP",
        "example_prompts": ["Hottest Polymarket markets right now", "Top traders on Polymarket by PnL"],
    },
    "graph-lending-mcp": {
        "summary": "Cross-protocol lending data via Messari standardized subgraphs (Aave, Compound, MakerDAO, etc.).",
        "best_for": ["Comparing TVL across lending protocols", "Standardized borrow/supply rates"],
        "not_for": ["Aave-specific deep features (use graph-aave-mcp)"],
        "auth": "Free Graph Network API key",
        "interface": "MCP",
        "example_prompts": ["Compare Aave vs Compound TVL on Ethereum", "Top lending markets by utilization"],
    },
    "graph-limitless-mcp": {
        "summary": "MCP server for Limitless prediction markets on Base.",
        "best_for": ["Limitless market state and trades on Base"],
        "auth": "Graph API key (env: GRAPH_API_KEY)",
        "interface": "MCP",
        "example_prompts": ["Active Limitless markets on Base"],
    },
    "predictfun-mcp": {
        "summary": "MCP server for Predict.fun on BNB Chain.",
        "best_for": ["Predict.fun markets and trader activity on BNB Chain"],
        "auth": "None (public REST API)",
        "interface": "MCP",
        "example_prompts": ["Top Predict.fun markets by volume"],
    },
    "8004scan": {
        "summary": "Discover and search ERC-8004 registered AI agents — identity, reputation, capabilities.",
        "best_for": ["Finding agents by capability", "Reputation/feedback lookup", "Agent registry browsing"],
        "auth": "None for public reads; register your own agent at 8004scan.io",
        "interface": "REST",
        "example_prompts": ["Find agents with MCP endpoints", "Agents with x402 support on Base"],
    },
    "mcp8004": {
        "summary": "Auth middleware (npm package) for adding ERC-8004 identity verification to any MCP server.",
        "best_for": ["Securing MCP server endpoints with on-chain agent identity", "Min-score gating"],
        "auth": "npm install mcp8004",
        "interface": "Library (TypeScript/JavaScript)",
        "example_prompts": ["How do I require ERC-8004 auth on my MCP server?"],
    },
}


_SERVICE_CHAINS: dict[str, list[str]] = {
    "token-api": ["Ethereum", "Base", "Arbitrum", "Optimism", "Polygon", "Avalanche", "BSC", "Solana", "TON"],
    "subgraph-registry": ["80+ chains (EVM, Solana, TON, Near, Starknet)"],
    "substreams": ["Ethereum", "Solana", "Near", "80+ firehose-enabled chains"],
    "graph-aave-mcp": ["Ethereum", "Arbitrum", "Optimism", "Polygon", "Avalanche", "Base", "Metis"],
    "graph-polymarket-mcp": ["Polygon"],
    "graph-lending-mcp": ["Ethereum", "Polygon", "Arbitrum", "Avalanche", "BSC", "Optimism", "Base", "Scroll", "Fantom", "Gnosis", "+ 5 more"],
    "graph-limitless-mcp": ["Base"],
    "predictfun-mcp": ["BNB Chain"],
    "mcp8004": ["Base", "Base Sepolia"],
    "8004scan": ["Base", "Base Sepolia", "Arbitrum"],
    "x402-analytics": ["Base"],
}


def build_capabilities() -> dict:
    """Build the /agents/capabilities.json payload by merging metadata with
    the curl/install examples already maintained in _SERVICE_CURL_EXAMPLES.

    Single source of truth: edit _SERVICE_METADATA and _SERVICE_CURL_EXAMPLES;
    the public capability doc regenerates automatically.
    """
    capabilities = []
    for service, meta in _SERVICE_METADATA.items():
        ex = _SERVICE_CURL_EXAMPLES.get(service, {})
        capabilities.append({
            "service": service,
            "summary": meta.get("summary", ""),
            "best_for": meta.get("best_for", []),
            "not_for": meta.get("not_for", []),
            "interface": meta.get("interface"),
            "auth": meta.get("auth"),
            "chains": _SERVICE_CHAINS.get(service, []),
            "install": ex.get("install"),
            "curl_example": ex.get("curl_example"),
            "get_started": ex.get("get_started"),
            "example_prompts": meta.get("example_prompts", []),
        })
    return {
        "agent": "graph-advocate",
        "version": "1.1",
        "endpoint": "https://graph-advocate-production.up.railway.app/",
        "protocol": "A2A (JSON-RPC 2.0)",
        "agent_card": "https://graph-advocate-production.up.railway.app/.well-known/agent-card.json",
        "identity": {
            "ens": "graphadvocate.eth",
            "erc8004_id": 734,
            "erc8004_chain": "Arbitrum",
            "wallet": "0x575267eED09c338FAE5716A486A7B58A5749A292",
        },
        "pricing": {
            "free_tier": "10 requests/day per sender (task_id)",
            "paid": "$0.01 USDC on Base after free tier",
            "payment_protocol": "x402 v2",
            "payment_network": "eip155:8453 (Base)",
            "usdc_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        },
        "endpoints": {
            "main": "POST /",
            "chat": "POST /chat",
            "agent_card": "GET /.well-known/agent-card.json",
            "capabilities": "GET /agents/capabilities.json",
            "mcp_catalog": "GET /mcp/catalog",
            "llms_txt": "GET /llms.txt",
            "feedback": "POST /feedback",
            "openapi": "GET /openapi.json",
        },
        "capabilities": capabilities,
        "how_to_use": (
            "Send a natural-language data question to POST / via A2A JSON-RPC. "
            "Graph Advocate routes the question to the best service in this list "
            "and returns a recommendation plus a ready-to-run curl/GraphQL/MCP example. "
            "For batch / programmatic use, see /agents/capabilities.json (this file) "
            "and the agent card."
        ),
    }


def build_mcp_catalog() -> dict:
    """Build /mcp/catalog — list of protocol-specific MCP servers agents can install.

    Unlike capabilities.json (all services), this focuses only on the MCP npm
    packages so agents can auto-discover installable tools.
    """
    MCP_SERVICES = [
        "graph-aave-mcp", "graph-polymarket-mcp", "graph-lending-mcp",
        "graph-limitless-mcp", "predictfun-mcp", "mcp8004",
    ]
    servers = []
    for service in MCP_SERVICES:
        meta = _SERVICE_METADATA.get(service, {})
        ex = _SERVICE_CURL_EXAMPLES.get(service, {})
        servers.append({
            "name": service,
            "summary": meta.get("summary", ""),
            "install": ex.get("install"),
            "chains": _SERVICE_CHAINS.get(service, []),
            "best_for": meta.get("best_for", []),
            "transport": "stdio",
            "example_prompts": meta.get("example_prompts", []),
            "get_started": ex.get("get_started"),
        })
    return {
        "catalog": "graph-advocate-mcp-servers",
        "version": "1.0",
        "updated": datetime.utcnow().isoformat() + "Z",
        "count": len(servers),
        "servers": servers,
        "how_to_discover": (
            "Agents can fetch this endpoint to discover protocol-specific MCP servers "
            "published under the Graph Advocate umbrella. Each entry includes the npm "
            "install command, supported chains, and example prompts. Route questions "
            "through POST / to Graph Advocate and it will recommend the right MCP "
            "server based on the question."
        ),
    }


def _compare_route(request: str) -> dict | None:
    """Detect 'X vs Y' / 'X or Y' comparison questions between two known services.

    These were ~100% of the historical 'unknown' bucket — one recurring probe
    ("Token API vs subgraph for Uniswap pool data?") that the regular router
    couldn't confidently classify. Return a direct answer instead of routing
    the agent somewhere wrong. Returns None if this isn't a comparison prompt.
    """
    req = request.lower()
    # Require a comparative connective AND two different service mentions
    if not any(sep in req for sep in (" vs ", " vs. ", " versus ", " or ")):
        return None

    mentions = []
    if any(w in req for w in ["token api", "token-api", "tokenapi"]):
        mentions.append("token-api")
    if any(w in req for w in ["subgraph", "the graph", "graphql"]):
        mentions.append("subgraph-registry")
    if "substream" in req:
        mentions.append("substreams")
    if "aave" in req:
        mentions.append("graph-aave-mcp")
    if "polymarket" in req:
        mentions.append("token-api")
    if "8004" in req:
        mentions.append("8004scan")
    mentions = list(dict.fromkeys(mentions))  # dedupe, preserve order
    if len(mentions) < 2:
        return None

    a, b = mentions[0], mentions[1]
    # Topic hint drives which side wins the "use X" recommendation
    wants_history = any(w in req for w in ["historical", "history", "over time", "time series", "trend"])
    wants_live = any(w in req for w in ["current", "live", "real-time", "realtime", "now", "latest"])

    if {a, b} == {"token-api", "subgraph-registry"}:
        answer = (
            "Use **Token API** for current prices, balances, holders, swaps, and NFT data — "
            "it's a prebuilt REST API with sub-second response and no schema work. "
            "Use a **subgraph** (via the registry) for historical pool mechanics, custom "
            "entity joins, protocol-specific state (TVL over time, positions, events), or "
            "anything that needs a GraphQL join the REST API doesn't expose."
        )
        if wants_history:
            pick = "subgraph-registry"
        elif wants_live:
            pick = "token-api"
        else:
            pick = "comparison"  # neutral — both are valid
    elif {a, b} == {"token-api", "substreams"}:
        answer = (
            "**Token API** for shaped application data (balances, transfers, swaps) as REST. "
            "**Substreams** for raw block/trace/event-log streaming when you need the firehose."
        )
        pick = "token-api" if wants_live else "comparison"
    elif {a, b} == {"subgraph-registry", "substreams"}:
        answer = (
            "**Subgraph** for queryable entities and relationships via GraphQL. "
            "**Substreams** for parallel raw-event processing, custom sinks, and "
            "sub-block streaming pipelines. Substreams feed subgraphs — they're complements."
        )
        pick = "comparison"
    else:
        answer = (
            f"**{a}** and **{b}** serve different use cases. Pick based on whether you need "
            f"shaped REST data ({a}) or custom GraphQL/streaming ({b}). See their docs for details."
        )
        pick = "comparison"

    # Borrow a concrete curl example from the more-actionable side (pick),
    # falling back to the first option so callers always have something to run.
    example = _SERVICE_CURL_EXAMPLES.get(
        pick if pick != "comparison" else a, {}
    ) or _SERVICE_CURL_EXAMPLES.get(a, {})

    return {
        "recommendation": pick,
        "confidence": "high",
        "answer": answer,
        "alternatives": [
            {"service": a, "confidence": "medium"},
            {"service": b, "confidence": "medium"},
        ],
        "curl_example": example.get("curl_example", ""),
        "install": example.get("install", ""),
        "get_started": example.get("get_started", ""),
        "reason": f"Comparison prompt between {a} and {b}",
    }


def _wants_query(request: str) -> bool:
    """Heuristic: is the user asking us to *write* a GraphQL/subgraph query?

    These prompts need a concrete query string, not just a routing decision.
    Fallback currently returns a generic curl example — which is worse than
    useless for a "write me a query" request.
    """
    r = request.lower()
    needles = (
        "write a query", "write a graphql", "graphql query",
        "subgraph query", "give me a query", "build a query",
        "show me a query", "query for", "generate a query",
    )
    return any(n in r for n in needles)


def _template_query(request: str) -> dict | None:
    """Return a pre-built subgraph query response for common request patterns.

    Used by _fallback_route when Claude couldn't produce one. Covers the
    high-value prompts we've seen land in the 'unknown' bucket. Returns None
    if no template matches — caller falls through to normal keyword routing.
    """
    if not _wants_query(request):
        return None
    r = request.lower()

    def _parse_threshold(req_lower: str, default: int = 50000) -> int:
        """Extract a USD threshold like '$50K', '1M', 'above 100000' from the request.

        Skips protocol version numbers (V2, V3, V4) which would otherwise match.
        """
        import re
        # Remove version tokens first so 'V3' doesn't get picked up as a number
        cleaned = re.sub(r"\bv\d+\b", " ", req_lower, flags=re.I).replace(",", "")
        # Prefer matches with a $ prefix or a k/m suffix (strong threshold signals);
        # fall back to a plain 4+ digit number.
        m = (re.search(r"\$\s*([\d]+(?:\.\d+)?)\s*([kKmM])?", cleaned)
             or re.search(r"\b([\d]+(?:\.\d+)?)\s*([kKmM])\b", cleaned)
             or re.search(r"\b(\d{4,}(?:\.\d+)?)\b", cleaned))
        if not m:
            return default
        try:
            n = float(m.group(1))
            suf = (m.group(2) or "").lower() if m.lastindex and m.lastindex >= 2 else ""
            if suf == "k": n *= 1_000
            elif suf == "m": n *= 1_000_000
            return max(int(n), 1)
        except Exception:
            return default

    # Aave liquidations (any version — Messari standardized schema works for V2/V3)
    if "aave" in r and ("liquidat" in r):
        threshold = _parse_threshold(r, default=50000)
        # Messari Aave V3 Ethereum — the standardized schema exposes `liquidates`
        subgraph_id = "JCNWRypm7FYwV8fx5HhzZPSFaMxgkPuw4TnR3Gpi81zk"
        query = (
            "{\n"
            "  liquidates(\n"
            "    first: 50\n"
            "    orderBy: amountUSD\n"
            "    orderDirection: desc\n"
            f"    where: {{ amountUSD_gt: \"{threshold}\" }}\n"
            "  ) {\n"
            "    id\n"
            "    hash\n"
            "    timestamp\n"
            "    amountUSD\n"
            "    liquidatee { id }\n"
            "    liquidator { id }\n"
            "    asset { symbol name }\n"
            "  }\n"
            "}"
        )
        endpoint = f"https://gateway.thegraph.com/api/<API_KEY>/subgraphs/id/{subgraph_id}"
        one_line = query.replace("\n", " ").replace('"', '\\"')
        curl = (
            f'curl -X POST {endpoint} \\\n'
            f'  -H "Content-Type: application/json" \\\n'
            f'  -d \'{{"query":"{one_line}"}}\''
        )
        return {
            "recommendation": "subgraph-registry",
            "confidence": "high",
            "reason": f"Templated Aave liquidations query (amountUSD > {threshold}) — Messari standardized schema",
            "query_ready": {
                "tool": "execute_query_by_subgraph_id",
                "args": {"subgraph_id": subgraph_id, "query": query},
            },
            "curl_example": curl,
            "endpoint": endpoint,
            "notes": "Messari standardized `liquidates` entity works for Aave V2/V3 across chains — swap the subgraph_id for V2 or a different chain (Arbitrum/Optimism/Polygon) as needed.",
        }

    # Uniswap V3 pools by TVL
    if "uniswap" in r and ("v3" in r or "v2" in r) and ("pool" in r or "tvl" in r or "liquidity" in r):
        subgraph_id = "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV"  # Uniswap V3 Ethereum
        query = (
            "{\n"
            "  pools(first: 20, orderBy: totalValueLockedUSD, orderDirection: desc) {\n"
            "    id\n"
            "    token0 { symbol }\n"
            "    token1 { symbol }\n"
            "    feeTier\n"
            "    totalValueLockedUSD\n"
            "    volumeUSD\n"
            "  }\n"
            "}"
        )
        endpoint = f"https://gateway.thegraph.com/api/<API_KEY>/subgraphs/id/{subgraph_id}"
        one_line = query.replace("\n", " ").replace('"', '\\"')
        return {
            "recommendation": "subgraph-registry",
            "confidence": "high",
            "reason": "Templated Uniswap V3 top-pools-by-TVL query",
            "query_ready": {
                "tool": "execute_query_by_subgraph_id",
                "args": {"subgraph_id": subgraph_id, "query": query},
            },
            "curl_example": (
                f'curl -X POST {endpoint} \\\n'
                f'  -H "Content-Type: application/json" \\\n'
                f'  -d \'{{"query":"{one_line}"}}\''
            ),
            "endpoint": endpoint,
        }

    return None


def _fallback_route(request: str) -> dict:
    """Keyword-based fallback router — fires when Claude's response can't be parsed
    or returns a JSON blob without a 'recommendation' field.

    Returns a minimal valid routing dict so the caller always gets a usable response.
    """
    # Comparison detector runs first — otherwise "X vs Y" gets routed to whichever
    # keyword happens to match earliest in the chain.
    cmp = _compare_route(request)
    if cmp is not None:
        return cmp

    # Query-template path — if the user explicitly asked us to *write* a query
    # for a known protocol, hand back a working templated query instead of a
    # generic service curl example.
    tpl = _template_query(request)
    if tpl is not None:
        return tpl

    req = request.lower()

    # Ordered from most-specific to least-specific
    if any(w in req for w in ["aave", "v4 hub", "v4 spoke", "aave v3", "aave v2", "liquidat"]):
        svc = "graph-aave-mcp"
    elif any(w in req for w in ["polymarket", "poly market"]):
        # Advanced CLOB features → MCP; everything else → Token API
        if any(w in req for w in ["orderbook", "order book", "spread", "dispute", "resolution", "uma",
                                    "winrate", "win rate", "drawdown", "profit factor",
                                    "ctf event", "split", "merge", "redemption"]):
            svc = "graph-polymarket-mcp"
        else:
            svc = "token-api"
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

    # For token-api fallbacks, generate a more specific response based on the
    # actual tokens/request instead of always returning the generic USDC example
    reason = f"Keyword-based fallback routing for: {request[:100]}"
    curl = example.get("curl_example", "")
    query_ready = None

    if svc == "token-api":
        # Resolve token symbols to contract addresses via TKN (tkn.xyz)
        # TKN is a decentralized token registry built on ENS — resolve
        # symbol.tkn.eth to get the mainnet contract address for any token.
        def _resolve_tkn(symbol: str) -> str | None:
            """Resolve a token symbol to a contract address via tkn.xyz ENS."""
            try:
                from web3 import Web3
                w3 = Web3(Web3.HTTPProvider(
                    "https://ethereum-rpc.publicnode.com",
                    request_kwargs={"timeout": 3},
                ))
                addr = w3.ens.address(f"{symbol.lower()}.tkn.eth")
                if addr and addr != "0x0000000000000000000000000000000000000000":
                    return addr
            except ImportError:
                pass
            except Exception:
                pass
            return None

        # Hardcoded fallback for common tokens (mainnet)
        _KNOWN_CONTRACTS = {
            "GRT": "0xc944E90C64B2c07662A292be6244BDC5Ee2F2d7e",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
            "LINK": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
            "UNI": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
            "AAVE": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
            "COMP": "0xc00e94Cb662C3520282E6f5717214004A7f26888",
            "MKR": "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2",
            "SNX": "0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F",
            "CRV": "0xD533a949740bb3306d119CC777fa900bA034cd52",
            "LDO": "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32",
            "ARB": "0x912CE59144191C1204E64559FE8253a0e49E6548",  # Arbitrum
            "OP": "0x4200000000000000000000000000000000000042",  # Optimism
            "ENS": "0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72",
            "BAL": "0xba100000625a3754423978a60c9317c58a424e3D",
            "SAFE": "0x5aFE3855358E112B5647B952709E6165e1c1eEEe",
            "RPL": "0xD33526068D116cE69F19A9ee46F0bd304F21A51f",
        }

        # Extract token symbols mentioned in the request
        import re as _re
        token_matches = _re.findall(r'\b[A-Z]{2,10}\b', request)
        tokens = [t for t in token_matches if t not in (
            "API", "GET", "POST", "FOR", "THE", "AND", "WITH", "TOP", "NFT",
            "EVM", "USD", "ETH", "BTC", "MCP", "URL", "JSON", "USDC", "USDT",
        )]
        if tokens:
            first = tokens[0]
            first_addr = _KNOWN_CONTRACTS.get(first)

            # Resolve addresses: TKN (live ENS) → hardcoded fallback → unknown
            known = {}
            unknown = []
            for t in tokens:
                if t in _KNOWN_CONTRACTS:
                    known[t] = _KNOWN_CONTRACTS[t]
                else:
                    # Try TKN resolution (live, covers thousands of tokens)
                    tkn_addr = _resolve_tkn(t)
                    if tkn_addr:
                        known[t] = tkn_addr
                    else:
                        unknown.append(t)

            addr_info = ""
            if known:
                addr_info = "Known addresses: " + ", ".join(f"{t}={a}" for t, a in known.items())
            if unknown:
                addr_info += (" | " if addr_info else "") + f"Need to look up: {', '.join(unknown)}"

            reason = (
                f"Use Token API's getV1EvmHolders endpoint for holder data. "
                f"{addr_info}. "
                f"Query each token separately with network=mainnet (or the chain it's on). "
                f"Token API returns the top holders with balances — use this for concentration analysis."
            )

            contract_display = first_addr or "CONTRACT_ADDRESS"
            contract_note = "" if first_addr else f" (replace with {first}'s contract address)"
            curl = (
                f"# Get holders for {first}{contract_note}\n"
                f"curl 'https://token-api.thegraph.com/v1/evm/holders?"
                f"contract={contract_display}&network=mainnet&limit=50&orderBy=balance&orderDirection=desc' \\\n"
                f"  -H 'Authorization: Bearer YOUR_JWT'\n\n"
                f"# Get a free JWT at https://thegraph.market/auth/tokenapi-env"
            )
            if len(tokens) > 1:
                curl += f"\n# Repeat for each token: {', '.join(tokens[1:8])}"

            query_ready = {
                "tool": "getV1EvmHolders",
                "args": {
                    "network": "mainnet",
                    "contract": first_addr or f"<{first} contract address>",
                    "limit": 50,
                    "orderBy": "balance",
                    "orderDirection": "desc",
                },
            }
            if len(tokens) > 1:
                query_ready["note"] = f"Run for each token. {addr_info}"

    return {
        "recommendation": svc,
        "reason": reason,
        "confidence": "medium",
        "query_ready": query_ready,
        "curl_example": curl,
        "install": example.get("install", ""),
        "get_started": example.get("get_started", "Free API key: https://thegraph.com/studio/"),
        "alternatives": [],
        "_fallback": True,
    }


def _normalize_service_name(svc: str) -> str:
    """Collapse Claude's free-form service labels into canonical short names.

    Example: 'graph-aave-mcp (easiest) OR direct Aave V3 subgraph query' → 'graph-aave-mcp'
             'Token API' → 'token-api'
             'SUBGRAPH_REGISTRY' → 'subgraph-registry'
    """
    if not svc:
        return svc
    s = svc.strip()
    s_lower = s.lower()

    # Canonical service names — first match wins (order matters)
    # Multi-service labels (combinations) collapse to the primary service
    CANONICAL = [
        ("graph-aave-mcp", "graph-aave-mcp"),
        ("graph-polymarket-mcp", "graph-polymarket-mcp"),
        ("graph-lending-mcp", "graph-lending-mcp"),
        ("graph-limitless-mcp", "graph-limitless-mcp"),
        ("predictfun-mcp", "predictfun-mcp"),
        ("subgraph-registry", "subgraph-registry"),
        ("subgraph_registry", "subgraph-registry"),
        ("subgraph-query", "subgraph-registry"),
        ("uniswap", "subgraph-registry"),
        ("aave v3 subgraph", "subgraph-registry"),
        ("aave v3 ethereum", "subgraph-registry"),
        ("ens subgraph", "subgraph-registry"),
        ("compound subgraph", "subgraph-registry"),
        ("curve subgraph", "subgraph-registry"),
        ("token-api", "token-api"),
        ("token api", "token-api"),
        ("substreams", "substreams"),
        ("8004scan", "8004scan"),
        ("mcp8004", "mcp8004"),
        ("x402-analytics", "x402-analytics"),
        ("x402 analytics", "x402-analytics"),
        ("x402", "x402-analytics"),
        ("operational-confirmation", "introduction"),
        ("registry-info", "introduction"),
        ("no-match", "out-of-scope"),
        ("unclear-request", "out-of-scope"),
        ("clarification-needed", "out-of-scope"),
    ]
    for needle, canonical in CANONICAL:
        if needle in s_lower:
            return canonical
    return s


def _inject_missing_fields(rec: dict, request: str) -> dict:
    """Ensure every recommendation has a curl_example and get_started URL.

    Called after Claude's response is parsed. Fills in fields that Claude
    frequently omits so agents always receive a working example to run.
    Also normalizes the service name to a canonical short label.
    """
    svc_raw = rec.get("recommendation", "")
    svc = _normalize_service_name(svc_raw)
    if svc != svc_raw:
        rec["recommendation"] = svc
    example = _SERVICE_CURL_EXAMPLES.get(svc, {})

    # Always inject get_started if missing
    if not rec.get("get_started") and example.get("get_started"):
        rec["get_started"] = example["get_started"]

    # Inject install command for npm-package services
    if not rec.get("install") and example.get("install"):
        rec["install"] = example["install"]

    # Always inject curl_example when missing — agents benefit from a copy-paste
    # probe even when query_ready is present, and the rubric scores it independently.
    if not rec.get("curl_example") and example.get("curl_example"):
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
        "limitless", "predict.fun",
        "resolution", "trader p&l", "indexer",
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
        "polymarket", "prediction market", "open interest",
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

    # Inject ecosystem/dashboard/reference context only when keywords match
    ECOSYSTEM_KEYWORDS = ["roadmap", "ecosystem", "what's new", "whats new", "horizon",
                          "tycho", "amp", "firehose", "2026", "new service"]
    DASHBOARD_KEYWORDS = ["indexer", "delegation", "delegator", "curation", "curator",
                          "vesting", "dispute", "slashing", "query fee", "reo",
                          "graphtools", "indexer score"]
    ETHSKILLS_KEYWORDS = ["contract address", "defi pattern", "gas cost", "l2", "flash loan"]

    if any(kw in req_lower for kw in ECOSYSTEM_KEYWORDS):
        results.append(
            "[THE GRAPH ECOSYSTEM CONTEXT]\n"
            "The Graph's 2026 roadmap: 6 products — Subgraphs (15,500+), Substreams, Token API, Tycho (DEX liquidity), Amp (SQL analytics), Firehose.\n"
            "Key themes: AI agents as first-class consumers via MCP, x402 pay-per-query, Horizon protocol unification, 80+ chains, 200+ indexers, $2B+ staked GRT.\n"
            "Roadmap blog: https://thegraph.com/blog/technical-roadmap/ | Core dev roadmap: https://thegraph.com/roadmap/\n"
            "Upcoming: Tycho (real-time DEX pricing, not yet MCP), Amp (SQL for institutions, coming 2026), x402 payments (USDC per-query, live on Base)."
        )

    if any(kw in req_lower for kw in DASHBOARD_KEYWORDS):
        results.append(
            "[GRAPH ECOSYSTEM DASHBOARDS — graphtools.pro]\n"
            "- Delegators Activity: https://graphtools.pro/delegators-activity\n"
            "- Indexer Score (find inactive): https://graphtools.pro/indexer-score\n"
            "- Top Indexers by Query Fees: https://graphtools.pro/top-indexers\n"
            "- Elite Subgraphs (500K+ daily): https://graphtools.pro/elite-subgraphs\n"
            "- Subgraph Search by Contract: https://graphtools.pro/subgraph-search\n"
            "- GRT Vesting: https://graphtools.pro/vesting\n"
            "- Curation Earnings: https://graphtools.pro/curation\n"
            "- Disputes/Slashings: https://graphtools.pro/disputes\n"
            "- Subgraphs by Network: https://graphtools.pro/subgraphs-network\n"
            "- REO Reward Eligibility: https://graphtools.pro/reo"
        )

    if any(kw in req_lower for kw in ETHSKILLS_KEYWORDS):
        results.append(
            "[ETHSKILLS — VERIFIED REFERENCE DATA]\n"
            "- Contract addresses: https://ethskills.com/addresses/SKILL.md\n"
            "- DeFi patterns: https://ethskills.com/building-blocks/SKILL.md\n"
            "- Indexing patterns: https://ethskills.com/indexing/SKILL.md\n"
            "- Gas costs: https://ethskills.com/gas/SKILL.md\n"
            "- L2 ecosystem: https://ethskills.com/l2s/SKILL.md"
        )

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

    def _call_claude(msgs):
        if is_complex:
            return client.messages.create(
                model="claude-opus-4-6",
                system=SYSTEM,
                messages=msgs,
                max_tokens=2000,
                thinking={"type": "adaptive"},
            )
        return client.messages.create(
            model="claude-haiku-4-5-20251001",
            system=SYSTEM,
            messages=msgs,
            max_tokens=2000,
        )

    log.info(f"MODEL    using {'Opus (complex query)' if is_complex else 'Haiku (simple routing)'}")
    response = _call_claude(messages)
    raw = next((b.text for b in response.content if b.type == "text"), "")
    messages.append({"role": "assistant", "content": response.content})
    rec = _extract_json(raw)

    # Retry once on parse failure before falling back. Most parse errors are
    # transient — truncation, a stray prose wrapper, a hallucinated trailing
    # comment. A single retry with a JSON-only nudge resolves the majority.
    if rec.get("parse_error"):
        log.warning(f"JSON parse failed on first try, retrying | raw[:120]={raw[:120]!r}")
        messages.append({
            "role": "user",
            "content": "Your previous response could not be parsed as JSON. Reply with ONLY a single valid JSON object matching the schema — no prose, no code fences, no explanation.",
        })
        try:
            response = _call_claude(messages)
            raw = next((b.text for b in response.content if b.type == "text"), "")
            messages.append({"role": "assistant", "content": response.content})
            rec = _extract_json(raw)
        except Exception as e:
            log.warning(f"Retry call failed: {e}")

    # If parse still failed or recommendation is missing, use fallback router
    if rec.get("parse_error") or not rec.get("recommendation"):
        fallback = _fallback_route(request)
        if rec.get("parse_error"):
            log.warning(f"JSON parse failed after retry, using fallback router | raw[:120]={raw[:120]!r}")
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

    # Execute the recommendation — run the first query as a demo
    query_ready = rec.get("query_ready")
    if not rec.get("parse_error") and query_ready:
        # If Claude returned multiple queries (list), execute just the first
        # as a free demo and hint that full execution requires x402 payment.
        if isinstance(query_ready, list) and len(query_ready) > 0:
            rec["query_ready"] = query_ready[0]  # executor expects a dict
            rec["additional_queries"] = len(query_ready) - 1
        try:
            execution_result = _execute_recommendation(rec)
            if execution_result:
                rec["execution_result"] = execution_result
                if isinstance(query_ready, list) and len(query_ready) > 1:
                    rec["execution_result"]["note"] = (
                        f"Showing results for the first token only. "
                        f"{len(query_ready) - 1} more queries available — "
                        f"pay $0.01 via x402 at POST /route for full results."
                    )
                    rec["remaining_queries"] = query_ready[1:]
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

        # Normalize arg keys and inject missing required params
        params = dict(args)
        if "network_id" in params and "network" not in params:
            params["network"] = params.pop("network_id")
        if "chain" in params and "network" not in params:
            params["network"] = params.pop("chain")
        if "token_address" in params and "contract" not in params:
            params["contract"] = params.pop("token_address")
        if "token" in params and "contract" not in params:
            params["contract"] = params.pop("token")

        # Default network to mainnet if missing
        if "network" not in params:
            # Try to infer from request text
            req_lower = rec.get("reason", "").lower() + rec.get("_original_request", "").lower()
            if "base" in req_lower:
                params["network"] = "base"
            elif "polygon" in req_lower or "matic" in req_lower:
                params["network"] = "matic"
            elif "arbitrum" in req_lower:
                params["network"] = "arbitrum-one"
            else:
                params["network"] = "mainnet"

        # Inject common contract addresses if missing
        if "contract" not in params and tool in ("getV1EvmHolders", "getV1EvmBalances"):
            KNOWN_CONTRACTS = {
                "usdc": {"mainnet": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
                "weth": {"mainnet": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "base": "0x4200000000000000000000000000000000000006"},
                "usdt": {"mainnet": "0xdAC17F958D2ee523a2206206994597C13D831ec7"},
                "dai": {"mainnet": "0x6B175474E89094C44Da98b954EedeAC495271d0F"},
                "wbtc": {"mainnet": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"},
            }
            reason = rec.get("reason", "").lower()
            for token, networks in KNOWN_CONTRACTS.items():
                if token in reason:
                    network = params.get("network", "mainnet")
                    if network in networks:
                        params["contract"] = networks[network]
                        break

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
    # ── x402 analytics subgraph — demonstrates Graph subgraph capabilities ──
    # Must come BEFORE generic subgraph handler to intercept x402 queries
    if service == "x402-analytics" or "x402" in service.lower():
        import httpx as _httpx
        # Claude puts the query in various places — check all of them
        gql = (
            args.get("gql") or args.get("query")
            or query_ready.get("gql") or query_ready.get("query")
        )
        # Also check if Claude put queries in a "queries" array
        if not gql and isinstance(query_ready.get("queries"), list) and query_ready["queries"]:
            gql = query_ready["queries"][0].get("query", "")
        # Last resort: build a default query
        if not gql:
            gql = '{ stats: x402DailyStats_collection(first: 3, orderBy: date, orderDirection: desc) { date totalPayments totalVolumeDecimal eip3009Payments permit2Payments } facilitators(first: 10, orderBy: totalSettlements, orderDirection: desc) { name address totalSettlements totalVolumeDecimal isActive } }'
        # Fix common query issues Claude generates for this subgraph
        if 'x402DailyStats(' in gql and '_collection' not in gql:
            gql = gql.replace('x402DailyStats(', 'x402DailyStats_collection(')
        if 'x402DailyStatses(' in gql:
            gql = gql.replace('x402DailyStatses(', 'x402DailyStats_collection(')
        if 'x402DailyStat(' in gql:
            gql = gql.replace('x402DailyStat(', 'x402DailyStats_collection(')
        if gql:
            x402_url = "https://api.studio.thegraph.com/query/1745687/x-402-base/version/latest"
            default_gql = '{ stats: x402DailyStats_collection(first: 3, orderBy: date, orderDirection: desc) { date totalPayments totalVolumeDecimal eip3009Payments permit2Payments } facilitators(first: 10, orderBy: totalSettlements, orderDirection: desc) { name address totalSettlements totalVolumeDecimal isActive } }'
            try:
                r = _httpx.post(x402_url, json={"query": gql}, timeout=15)
                data = r.json()
                # If Claude's query failed, retry with default
                if data.get("errors") and gql != default_gql:
                    log.info(f"EXECUTE  x402 query failed, retrying with default")
                    r = _httpx.post(x402_url, json={"query": default_gql}, timeout=15)
                    data = r.json()
                log.info(f"EXECUTE  x402-subgraph -> {r.status_code}")
                if isinstance(data.get("data"), dict):
                    for k, val in data["data"].items():
                        if isinstance(val, list) and len(val) > 20:
                            data["data"][k] = val[:20]
                            data["_truncated"] = True
                return {
                    "source": "x402-subgraph",
                    "status": r.status_code,
                    "data": data,
                    "note": "Live x402 payment data on Base, powered by The Graph.",
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
  Auth: Substreams uses a JWT (not a plain API key). Sign up at https://thegraph.market,
  create an API key, then generate a JWT from it. Use with `substreams auth` CLI command.
  Browse packages (no auth needed): https://substreams.dev
  Docs: https://docs.substreams.dev

**Protocol MCP Packages** (npm by @paulieb — install with npx, no agent required):
  - graph-aave-mcp: Aave V2/V3/V4 — 40 tools across 16 Graph subgraphs + Aave V4 API (hubs, spokes, cross-chain positions, swap quotes, rewards)
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
- Substreams auth is a JWT (not a plain API key) — sign up at https://thegraph.market, create an API key, then generate a JWT
- AUTH SYSTEMS DIFFER — never confuse them:
    • Subgraphs:   API key from thegraph.com/studio  → URL header: /api/{KEY}/subgraphs/id/{ID}
    • Token API:   JWT from thegraph.market           → Authorization: Bearer {JWT}
    • Substreams:  JWT from thegraph.market (via API key) → use with `substreams auth` CLI
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


_subgraph_search_cache: dict[str, tuple[float, str]] = {}
_SUBGRAPH_CACHE_TTL = 300  # 5 minutes — hot path for repeat keywords


def _search_subgraphs(keyword: str) -> str:
    """Search the local subgraph registry SQLite DB. In-memory cached for 5 min."""
    import sqlite3
    import urllib.request
    import os
    import tempfile
    import time

    key = keyword.lower().strip()
    if key in _subgraph_search_cache:
        cached_at, cached_result = _subgraph_search_cache[key]
        if time.time() - cached_at < _SUBGRAPH_CACHE_TTL:
            return cached_result

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
                      domain, protocol_type, reliability_score, query_hint
               FROM subgraphs
               WHERE (display_name LIKE ? OR description LIKE ? OR domain LIKE ?
                      OR categories LIKE ? OR auto_description LIKE ?)
               ORDER BY query_volume_30d DESC
               LIMIT 8""",
            tuple(f"%{keyword}%" for _ in range(5)),
        ).fetchall()
        conn.close()

        if not rows:
            empty = json.dumps({"results": [], "message": f"No subgraphs found for '{keyword}'"})
            _subgraph_search_cache[key] = (time.time(), empty)
            return empty

        results = []
        for r in rows:
            subgraph_id = r["id"].split("|")[0] if "|" in r["id"] else r["id"]
            network = r["network"] or "unknown"
            playground_url = f"https://thegraph.com/explorer/subgraphs/{subgraph_id}?view=Query&chain=arbitrum-one"
            entry = {
                "subgraph_id": subgraph_id,
                "name": r["display_name"] or subgraph_id[:16],
                "network": network,
                "description": (r["description"] or r["domain"] or "")[:120],
                "query_volume_30d": r["query_volume_30d"] or 0,
                "reliability_score": round(r["reliability_score"] or 0, 2),
                "playground_url": playground_url,
                "gateway_url": f"https://gateway.thegraph.com/api/[YOUR_API_KEY]/subgraphs/id/{subgraph_id}",
            }
            # Include query hint if available — gives Claude the exact fields to use
            try:
                hint = r["query_hint"]
                if hint:
                    entry["query_hint"] = hint
            except (IndexError, KeyError):
                pass
            results.append(entry)

        output = json.dumps({"results": results, "total_found": len(results)})
        _subgraph_search_cache[key] = (time.time(), output)
        # Evict stale entries if cache grows too large
        if len(_subgraph_search_cache) > 500:
            cutoff = time.time() - _SUBGRAPH_CACHE_TTL
            stale = [k for k, (t, _) in _subgraph_search_cache.items() if t < cutoff]
            for k in stale:
                del _subgraph_search_cache[k]
        return output
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
