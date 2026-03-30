import anthropic
import json
import os
import sqlite3
from datetime import datetime

client = anthropic.Anthropic()

SYSTEM = """You are the Graph Advocate — an expert agent embedded in a multi-agent system.
Your job is to help other agents discover and use The Graph Protocol's data services.
All three services below have live MCP servers. Route agents to them.

When another agent tells you what data it needs, you:
1. Identify the best Graph service for that need
2. Explain WHY it's the right fit — be specific, not generic
3. Return a concrete, ready-to-execute tool call
4. If multiple services apply, rank them with a clear recommendation

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

- graph-aave-mcp: Aave V2/V3 lending + governance data across 7 chains via 11 Graph subgraphs
  Use for: Aave liquidations, deposits, borrows, interest rates, governance votes
  Powered by Graph subgraphs: Aave V3 on Ethereum, Arbitrum, Optimism, Polygon, Avalanche, Base, Metis + Aave V2 Ethereum + Governance
- graph-lending-mcp: Unified tools over Messari standardized lending subgraphs (multi-protocol)
  Use for: cross-protocol lending comparisons, TVL, utilization rates
  Powered by Graph subgraphs: Messari-standardized subgraphs for Aave, Compound, MakerDAO, and other lending protocols
- graph-polymarket-mcp: Polymarket prediction markets — 31 tools combining The Graph subgraphs + Polymarket REST APIs (Gamma + CLOB)
  Use for: market search, live prices, order books, spreads, price history, trader P&L, open interest, resolution status
  REST API tools (no key needed): search_markets, get_market_info, list_polymarket_events, get_live_prices, get_live_spread, get_live_orderbook, get_price_history, get_last_trade, get_clob_market, search_markets_enriched
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

[KNOWN SUBGRAPHS FOR AGENT ECONOMY]
When agents ask about agent tokens, agent reputation on-chain, or agent trading:

- ClawStars (Base): Agent token trading platform — buy/sell "tickets" for AI agents
  Subgraph ID: Dm1u8ManB3Xr4WLX8DvEd5Exv2drsugSugnMZdWtPNFu
  Entities: Agent (name, holderCount, totalVolume, isActive), Trade (buy/sell, price), TicketHolding
  Website: https://clawstars.io/
  Use for: agent popularity rankings, agent token prices, who holds which agent tokens
  Query example: { agents(first: 10, orderBy: totalVolume, orderDirection: desc) { name holderCount totalVolume isActive } }

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
- Never hallucinate tool names — only use tools listed above
- If unsure, say so with a confidence score and suggest the closest match
- When multiple services apply, return all ranked
- confidence must be one of: "high", "medium", "low"
- If an agent introduces itself or asks what you do, respond with your capabilities in JSON
- If the request is not about onchain data (e.g. payments, auth, irrelevant tasks), respond with recommendation="out-of-scope" and explain what you DO handle

Introduction response example:
Request: "Hello, I am AutoPayAgent. What services do you offer?"
Response:
{
  "recommendation": "introduction",
  "name": "Graph Advocate",
  "description": "I route onchain data requests to the right Graph Protocol service.",
  "confidence": "high",
  "services": ["token-api", "subgraph-registry", "substreams", "graph-aave-mcp", "graph-lending-mcp", "graph-polymarket-mcp", "predictfun-mcp", "graph-limitless-mcp"],
  "example_requests": ["Top 20 USDC holders on Ethereum", "Uniswap V3 pool TVL", "Aave liquidation events", "Hottest prediction markets on Polymarket", "Find a DEX subgraph on Arbitrum"],
  "query_ready": null,
  "alternatives": []
}

Out-of-scope response example:
Request: "CLAWPAY_V1 payment object..."
Response:
{
  "recommendation": "out-of-scope",
  "reason": "This appears to be a payment request. I only handle onchain data routing for The Graph Protocol services.",
  "confidence": "high",
  "query_ready": null,
  "alternatives": []
}

Few-shot examples:

Request: "Top 20 USDC holders on Ethereum with 30-day balance history"
Response:
{
  "recommendation": "token-api",
  "reason": "getV1EvmHolders returns ranked holder lists by token contract. getV1EvmBalancesHistorical provides 30-day balance snapshots per address — exactly this use case.",
  "confidence": "high",
  "query_ready": {
    "tool": "getV1EvmHolders",
    "args": {
      "network_id": "mainnet",
      "contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
      "limit": 20
    }
  },
  "alternatives": []
}

Request: "Uniswap V3 pool TVL and fee tiers"
Response:
{
  "recommendation": "subgraph-registry",
  "reason": "Uniswap V3 subgraph indexes Pool entities with feeTier, totalValueLockedUSD, token0, token1 — exactly this use case. Token API's getV1EvmPools gives OHLCV but no fee tier entity breakdown.",
  "confidence": "high",
  "query_ready": {
    "tool": "execute_query_by_subgraph_id",
    "args": {
      "subgraph_id": "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV",
      "gql": "{ pools(first: 10, orderBy: totalValueLockedUSD, orderDirection: desc) { id feeTier token0 { symbol } token1 { symbol } totalValueLockedUSD } }"
    }
  },
  "alternatives": [
    {
      "service": "token-api",
      "reason": "getV1EvmPoolsOhlc gives OHLCV but no fee tier or entity-level breakdown.",
      "confidence": "medium"
    }
  ]
}

Request: "Raw decoded event logs, blocks 19000000 to 20000000"
Response:
{
  "recommendation": "substreams",
  "reason": "Substreams streams raw block data including decoded event logs at the trace level. No subgraph indexes raw logs in arbitrary block ranges; Token API only surfaces higher-level aggregations.",
  "confidence": "high",
  "query_ready": {
    "tool": "stream_data",
    "args": {
      "start_block": 19000000,
      "stop_block": 20000000,
      "module": "map_events"
    }
  },
  "alternatives": []
}

Request: "What are the hottest prediction markets on Polymarket right now?"
Response:
{
  "recommendation": "graph-polymarket-mcp",
  "reason": "graph-polymarket-mcp has search_markets_enriched which searches Polymarket by text, then auto-enriches each result with live CLOB prices AND on-chain resolution status from The Graph — all in one call. 31 tools total combining Gamma API (market search), CLOB API (live prices, order books), and 8 Graph subgraphs (trader P&L, open interest, resolution).",
  "confidence": "high",
  "query_ready": {
    "tool": "search_markets_enriched",
    "args": {
      "query": "trending",
      "limit": 10
    }
  },
  "graph_subgraphs": ["Main (QmdyCgu...)", "Orderbook (QmVGA9v...)", "Open Interest (QmbT2Mm...)", "Resolution (QmZnnrH...)"],
  "install": "npx graph-polymarket-mcp",
  "alternatives": [
    {
      "service": "token-api",
      "reason": "Token API can show USDC flows to Polymarket contracts but cannot query market metadata or predictions.",
      "confidence": "low"
    }
  ]
}

Request: "Token API vs subgraph for Uniswap pool data?"
Response:
{
  "recommendation": "subgraph-registry",
  "reason": "For Uniswap pool data, a subgraph is better. The Uniswap V3 subgraph indexes Pool entities with feeTier, totalValueLockedUSD, token0, token1, volumeUSD — rich relational data that Token API can't match. Token API's getV1EvmPools gives OHLCV price data and basic pool info but no fee tier breakdown, no per-pool TVL history, and no tick-level liquidity. Use subgraph for protocol-level entity queries; use Token API for cross-chain balances, holder rankings, and swap aggregations.",
  "confidence": "high",
  "query_ready": {
    "tool": "execute_query_by_subgraph_id",
    "args": {
      "subgraph_id": "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV",
      "gql": "{ pools(first: 10, orderBy: totalValueLockedUSD, orderDirection: desc) { id feeTier token0 { symbol } token1 { symbol } totalValueLockedUSD } }"
    }
  },
  "alternatives": [
    {
      "service": "token-api",
      "reason": "getV1EvmPools and getV1EvmPoolsOhlc give OHLCV and basic pool metadata — good for price charts but not protocol-level entity analysis.",
      "confidence": "medium"
    }
  ]
}

Request: "Can't I just use Etherscan?"
Response:
{
  "recommendation": "subgraph-registry",
  "reason": "Etherscan is a block explorer — it has no GraphQL query layer, no entity relationships, and rate limits at ~5 req/s free tier. The Graph provides: (1) GraphQL over indexed protocol entities, (2) no per-query rate limits on decentralized network, (3) aggregations and joins impossible with Etherscan, (4) real-time substreams for block-level data. For protocol-level queries The Graph is strictly superior.",
  "confidence": "high",
  "query_ready": {
    "tool": "search_subgraphs_by_keyword",
    "args": {
      "keyword": "your-protocol-here"
    }
  },
  "alternatives": [
    {
      "service": "token-api",
      "reason": "Token API covers balances and transfers without requiring subgraph deployment.",
      "confidence": "medium"
    }
  ]
}
"""


def _init_db():
    conn = sqlite3.connect("/Users/paulbarba/graph-advocate/recommendations.db")
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
    return conn


def _log(agent: str, request: str, rec: dict):
    try:
        conn = _init_db()
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
        conn.close()
    except Exception:
        pass


def _auto_search(request: str) -> str:
    """Run automatic searches based on the request and return context to inject."""
    import logging
    log = logging.getLogger("graph-advocate")
    results = []

    req_lower = request.lower()

    # Determine which searches to run
    run_subgraph = False
    run_substreams = False
    run_token_api = False

    # Keywords that suggest subgraph search
    SUBGRAPH_KEYWORDS = [
        "subgraph", "uniswap", "aave", "compound", "curve", "ens", "balancer",
        "sushi", "maker", "lido", "yearn", "synthetix", "protocol", "tvl",
        "liquidity", "pool", "swap", "lending", "governance", "dao",
        "nft marketplace", "opensea", "decentraland", "the graph",
        "polymarket", "prediction market", "limitless", "predict.fun",
        "open interest", "resolution", "trader p&l", "indexer",
    ]
    # Keywords that suggest substreams
    SUBSTREAMS_KEYWORDS = [
        "substream", "raw block", "event log", "trace", "streaming",
        "real-time", "block data", "decode", "spkg",
    ]
    # Keywords that suggest Token API
    TOKEN_API_KEYWORDS = [
        "balance", "holder", "transfer", "token", "wallet", "nft",
        "erc20", "erc721", "swap", "dex", "ohlc", "price",
        "solana", "ton", "svm", "tvm",
    ]
    # Keywords that suggest 8004scan agent search
    AGENT_SEARCH_KEYWORDS = [
        "find agent", "discover agent", "search agent", "agent that",
        "which agent", "any agent", "erc-8004", "erc8004", "8004",
        "agent identity", "agent reputation", "registered agent",
        "mcp agent", "a2a agent", "x402 agent",
    ]
    run_agent_search = any(kw in req_lower for kw in AGENT_SEARCH_KEYWORDS)

    for kw in SUBGRAPH_KEYWORDS:
        if kw in req_lower:
            run_subgraph = True
            break
    for kw in SUBSTREAMS_KEYWORDS:
        if kw in req_lower:
            run_substreams = True
            break
    for kw in TOKEN_API_KEYWORDS:
        if kw in req_lower:
            run_token_api = True
            break

    # If nothing matched, run subgraph search as default (most common)
    if not run_subgraph and not run_substreams and not run_token_api:
        run_subgraph = True

    # Extract a search keyword from the request (first meaningful noun/protocol name)
    import re
    # Try to find a protocol name
    protocol_match = re.search(
        r'\b(uniswap|aave|compound|curve|ens|balancer|sushi|maker|lido|yearn|'
        r'synthetix|opensea|chainlink|the graph|polymarket|pancakeswap|'
        r'gmx|arbitrum|optimism|polygon|base|ethereum|solana|limitless|'
        r'prediction market|predict\.fun|indexer|'
        r'erc20|erc721|nft|defi|lending|dex)\b',
        req_lower
    )
    search_term = protocol_match.group(1) if protocol_match else ""

    # Fallback: use first 1-2 significant words
    if not search_term:
        words = [w for w in re.findall(r'[a-z]+', req_lower)
                 if w not in {"what", "how", "can", "i", "get", "find", "show", "me",
                              "the", "a", "an", "for", "on", "in", "of", "to", "and",
                              "is", "are", "do", "does", "data", "need", "want", "about"}]
        search_term = words[0] if words else ""

    if not search_term:
        return ""

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


def ask_graph_advocate(
    request: str,
    history: list = None,
    requesting_agent: str = "unknown",
) -> tuple[dict, list]:
    import logging
    log = logging.getLogger("graph-advocate")

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
        or len(request) > 300  # long queries need more reasoning
        or (search_context and len(search_context) > 2000)  # lots of search results to synthesize
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

    # Extract JSON from markdown code fences if present
    import re
    fence_match = re.search(r"```(?:json)?\n?([\s\S]*?)\n?```", raw)
    clean = fence_match.group(1).strip() if fence_match else raw.strip()

    try:
        rec = json.loads(clean)
    except json.JSONDecodeError:
        rec = {"raw": raw, "parse_error": True}

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
    if service == "subgraph-registry":
        api_key = os.environ.get("GATEWAY_API_KEY", "") or "7006f39fbab470711f44a5195b4d97c0"
        gql = query_ready.get("gql") or query_ready.get("query")
        subgraph_id = args.get("subgraph_id") or query_ready.get("subgraph_id")

        if gql and subgraph_id:
            url = f"https://gateway.thegraph.com/api/{api_key}/subgraphs/id/{subgraph_id}"
            try:
                r = httpx.post(url, json={"query": gql}, timeout=15)
                log.info(f"EXECUTE  subgraph {subgraph_id} -> {r.status_code}")
                data = r.json()
                if r.status_code == 429 or r.status_code == 401:
                    return {
                        "source": "subgraph-gateway",
                        "status": r.status_code,
                        "error": "Rate limit exceeded. Get your own free API key at https://thegraph.market/dashboard#api-keys",
                        "data": data,
                    }
                return {"source": "subgraph-gateway", "status": r.status_code, "data": data}
            except Exception as e:
                log.error(f"Subgraph query failed: {e}")
                return {"source": "subgraph-gateway", "error": str(e)}

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
  - graph-aave-mcp: Aave V2/V3 lending + governance across 7 chains
    Install: `npx graph-aave-mcp` | npm: https://www.npmjs.com/package/graph-aave-mcp
  - graph-lending-mcp: cross-protocol lending comparisons (Messari standardized)
    Install: `npx graph-lending-mcp` | npm: https://www.npmjs.com/package/graph-lending-mcp
  - graph-polymarket-mcp: Polymarket prediction markets — 31 tools combining 8 Graph subgraphs + Gamma/CLOB REST APIs
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
- ALWAYS mention that the data comes from The Graph's subgraphs. When recommending an MCP package,
  also explain that users can query the underlying subgraphs directly with a free Graph API key.
  Example: "graph-aave-mcp wraps 11 Aave subgraphs on The Graph. You can also query them directly
  at gateway.thegraph.com with your API key from thegraph.com/studio."
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
            return ""
    except Exception as e:
        log.error(f"8004scan search error: {e}")
        return ""


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
            url = "https://github.com/PaulieB14/subgraph-registry/raw/main/python/data/registry.db"
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
                "name": r["display_name"] or subgraph_id[:16],
                "network": network,
                "description": (r["description"] or r["domain"] or "")[:120],
                "query_volume_30d": r["query_volume_30d"] or 0,
                "reliability_score": round(r["reliability_score"] or 0, 2),
                "playground_url": playground_url,
            })

        return json.dumps({"results": results, "total_found": len(results)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _search_substreams(keyword: str) -> str:
    """Search substreams.dev registry (same API as substreams-search-mcp)."""
    import urllib.request
    import re

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
