"""Static discovery documents for crawlers, MCP registries and ARD consumers.

Served by a2a_server.py at /robots.txt, /sitemap.xml,
/.well-known/mcp/server.json (and /.well-known/mcp.json alias) and
/.well-known/ard.json. Pure functions so they can be unit-tested without
booting the server. URLs are pinned to the canonical public domain.
"""
from __future__ import annotations

SITE = "https://graphadvocate.com"
MCP_SERVER_NAME = "io.github.PaulieB14/graph-advocate"
MCP_SERVER_VERSION = "1.0.0"
MCP_SCHEMA = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
ICON_URL = f"{SITE}/graphadvocate.png"

SITEMAP_PATHS = (
    "/", "/chat", "/polymarket", "/hyperliquid", "/x402", "/copytrade",
    "/llms.txt", "/SKILL.md", "/openapi.json",
    "/.well-known/agent-card.json", "/.well-known/x402",
    "/.well-known/mcp/server.json", "/.well-known/ard.json",
    "/agents/index.json", "/agents/capabilities.json", "/mcp/catalog",
)


def robots_txt() -> str:
    return (
        "# Graph Advocate - onchain data router for AI agents\n"
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "\n"
        f"Sitemap: {SITE}/sitemap.xml\n"
        f"# LLM-readable index: {SITE}/llms.txt\n"
        f"# A2A agent card: {SITE}/.well-known/agent-card.json\n"
        f"# x402 resources: {SITE}/.well-known/x402\n"
    )


def sitemap_xml() -> str:
    urls = "".join(f"  <url><loc>{SITE}{p}</loc></url>\n" for p in SITEMAP_PATHS)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n"
    )


def mcp_server_json() -> dict:
    """server.json per the official MCP registry schema (2025-12-11)."""
    return {
        "$schema": MCP_SCHEMA,
        "name": MCP_SERVER_NAME,
        "title": "Graph Advocate",
        "description": "Routes plain-English onchain data questions to the right subgraph or API, with a query.",
        "version": MCP_SERVER_VERSION,
        "websiteUrl": SITE,
        "repository": {"url": "https://github.com/PaulieB14/graph-advocate", "source": "github"},
        "icons": [{"src": ICON_URL, "mimeType": "image/png", "sizes": ["1024x1024"]}],
        "remotes": [
            {"type": "streamable-http", "url": f"{SITE}/mcp"},
            {"type": "sse", "url": f"{SITE}/mcp/sse"},
        ],
    }


def ard_json() -> dict:
    """ARD manifest (agenticresourcediscovery.org spec v0.91)."""
    pub = "graphadvocate.com"
    queries = [
        "which subgraph has Uniswap v3 swaps on Base",
        "write a GraphQL query for Aave borrow rates",
        "Polymarket trader PnL for a wallet",
        "Hyperliquid trader risk score",
        "wallet token balances on Ethereum",
    ]
    return {
        "specVersion": "0.91",
        "host": {
            "displayName": "Graph Advocate",
            "identifier": f"did:web:{pub}",
            "documentationUrl": "https://docs.graphadvocate.com/",
        },
        "entries": [
            {
                "identifier": f"urn:air:{pub}:agent:graph-advocate",
                "displayName": "Graph Advocate (A2A)",
                "type": "application/a2a-agent-card+json",
                "url": f"{SITE}/.well-known/agent-card.json",
                "description": "Onchain data router for AI agents: plain-English to a working subgraph query or REST call; paid trader-intel endpoints via x402 on Base.",
                "representativeQueries": queries,
            },
            {
                "identifier": f"urn:air:{pub}:server:graph-advocate",
                "displayName": "Graph Advocate MCP server",
                "type": "application/mcp-server+json",
                "url": f"{SITE}/.well-known/mcp/server.json",
                "description": "Remote MCP server: route_data_request, recommend_npm_package, compare_graph_services.",
                "representativeQueries": queries[:3],
            },
            {
                "identifier": f"urn:air:{pub}:api:x402",
                "displayName": "Graph Advocate x402 API",
                "type": "application/openapi+json",
                "url": f"{SITE}/openapi.json",
                "description": "Pay-per-call onchain data endpoints (USDC on Base via x402): Polymarket, Hyperliquid, Uniswap, Kalshi, agent reputation.",
                "representativeQueries": queries[2:],
            },
        ],
    }
