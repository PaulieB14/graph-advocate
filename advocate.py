import anthropic
import json
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

The services you represent — MCP servers and npm packages:

[TOKEN API]
Best for: wallet balances, token transfers, DEX swaps, NFT data, holder rankings
Chains: EVM (Ethereum, Base, Polygon…), SVM (Solana), TVM (TON)
Key tools: getV1EvmBalances, getV1EvmSwaps, getV1EvmNftSales, getV1SvmBalances, getV1EvmHolders, getV1EvmTransfers, getV1EvmPools, getV1EvmPoolsOhlc, getV1SvmNftSales, getV1EvmNftItems, getV1EvmNftHolders

[SUBGRAPH REGISTRY]
Best for: protocol-level indexed data (Uniswap, Aave, ENS, Compound, Curve, Balancer, etc.)
Use when: the agent needs entities, relationships, or aggregations a subgraph tracks
Key tools: search_subgraphs_by_keyword, get_schema_by_subgraph_id, execute_query_by_subgraph_id
npm: subgraph-registry-mcp (15,500+ classified subgraphs, reliability scoring)
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

- graph-aave-mcp: Aave V2/V3 lending + governance data across 7 chains, 11 subgraphs
  Use for: Aave liquidations, deposits, borrows, interest rates, governance votes
- graph-lending-mcp: Unified tools over Messari standardized lending subgraphs (multi-protocol)
  Use for: cross-protocol lending comparisons, TVL, utilization rates
- graph-polymarket-mcp: Polymarket prediction market data via The Graph subgraphs
  Use for: market prices, positions, volumes, resolution data on Polymarket
- predictfun-mcp: Predict.fun prediction market data on BNB Chain
  Use for: BNB Chain prediction markets, outcomes, trader positions

When recommending a protocol-specific npm package, include install instructions:
  "install": "npx graph-aave-mcp" or "npm install -g graph-aave-mcp"

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
  "services": ["token-api", "subgraph-registry", "substreams", "graph-aave-mcp", "graph-lending-mcp", "graph-polymarket-mcp", "predictfun-mcp"],
  "example_requests": ["Top 20 USDC holders on Ethereum", "Uniswap V3 pool TVL", "Aave liquidation events"],
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
            confidence TEXT
        )
    """)
    conn.commit()
    return conn


def _log(agent: str, request: str, rec: dict):
    try:
        conn = _init_db()
        conn.execute(
            "INSERT INTO recommendations VALUES (NULL, ?, ?, ?, ?, ?)",
            (
                datetime.utcnow().isoformat(),
                agent,
                request,
                rec.get("recommendation", "unknown"),
                rec.get("confidence", "unknown"),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def ask_graph_advocate(
    request: str,
    history: list = None,
    requesting_agent: str = "unknown",
) -> tuple[dict, list]:
    messages = (history or []) + [{"role": "user", "content": request}]

    response = client.messages.create(
        model="claude-opus-4-6",
        system=SYSTEM,
        messages=messages,
        max_tokens=2000,
        thinking={"type": "adaptive"},
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
    return rec, messages


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

**Protocol MCP Packages** (npm by @paulieb):
  - graph-aave-mcp: Aave V2/V3 lending + governance
  - graph-lending-mcp: cross-protocol lending comparisons
  - graph-polymarket-mcp: Polymarket prediction markets
  - predictfun-mcp: Predict.fun on BNB Chain

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
- When a user asks about a specific protocol or data type, USE your tools to search for real subgraphs and substreams — don't guess
- After searching, present the top results with their playground links so users can try them
- Include the specific tool name and example usage when possible
- If the question isn't about onchain data, politely redirect
- Use markdown for formatting
- NEVER say an API key is not needed — it is always required for subgraph queries
- If a user asks how to connect the Graph Advocate to their agent, explain the A2A endpoint:
  POST https://graph-advocate-production.up.railway.app/ with JSON-RPC 2.0
  Agent card: https://graph-advocate-production.up.railway.app/.well-known/agent-card.json
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

        # Map network names to Graph Explorer chain param
        CHAIN_MAP = {
            "mainnet": "mainnet",
            "arbitrum-one": "arbitrum-one",
            "base": "base",
            "polygon": "matic",
            "optimism": "optimism",
            "bsc": "bsc",
            "avalanche": "avalanche",
            "celo": "celo",
            "gnosis": "gnosis",
            "fantom": "fantom",
            "linea": "linea",
            "scroll": "scroll",
            "blast-mainnet": "blast-mainnet",
        }

        results = []
        for r in rows:
            subgraph_id = r["id"].split("|")[0] if "|" in r["id"] else r["id"]
            network = r["network"] or "unknown"
            chain_param = CHAIN_MAP.get(network, "arbitrum-one")
            playground_url = f"https://thegraph.com/explorer/subgraphs/{subgraph_id}?view=playground&chain={chain_param}"
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


def ask_graph_advocate_chat(
    request: str,
    history: list = None,
) -> tuple[str, list]:
    """Haiku-powered chat with tool use for real subgraph/substreams search."""
    messages = (history or []) + [{"role": "user", "content": request}]

    # Initial call — may trigger tool use
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
                if block.name == "search_subgraphs":
                    result = _search_subgraphs(block.input.get("keyword", ""))
                elif block.name == "search_substreams":
                    result = _search_substreams(block.input.get("keyword", ""))
                elif block.name == "lookup_token_api":
                    result = _lookup_token_api(block.input.get("data_type", ""))
                else:
                    result = json.dumps({"error": f"Unknown tool: {block.name}"})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        messages.append({"role": "assistant", "content": response.content})
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
    messages.append({"role": "assistant", "content": response.content})

    _log("web-chat", request, {"recommendation": "chat", "confidence": "n/a"})
    return reply, messages


if __name__ == "__main__":
    import sys

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Top 20 USDC holders on Ethereum"
    rec, _ = ask_graph_advocate(prompt)
    print(json.dumps(rec, indent=2))
