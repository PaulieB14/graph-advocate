"""
Graph Advocate — MCP Server
Exposes the Graph Advocate as an MCP tool so Claude Code routes through it.

Add to ~/.claude/mcp.json:
{
  "mcpServers": {
    "graph-advocate": {
      "command": "/Users/paulbarba/graph-advocate/venv/bin/python",
      "args": ["/Users/paulbarba/graph-advocate/mcp_server.py"],
      "env": { "ANTHROPIC_API_KEY": "<your-key>" }
    }
  }
}
"""

import os, sys, json
sys.path.insert(0, "/Users/paulbarba/graph-advocate")

# Load .env
env_path = "/Users/paulbarba/graph-advocate/.env"
if os.path.exists(env_path):
    for line in open(env_path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from mcp.server.fastmcp import FastMCP
from advocate import ask_graph_advocate

mcp = FastMCP(
    "Graph Advocate",
    instructions=(
        "Routes onchain data requests to the right Graph Protocol service. "
        "Call route_data_request BEFORE using any token-api, subgraph, or substreams tool. "
        "The Advocate returns the exact tool and args to use."
    ),
)

_sessions: dict[str, list] = {}


@mcp.tool()
def route_data_request(request: str, session_id: str = "default") -> str:
    """
    Route an onchain data request to the right Graph Protocol service.
    Returns JSON with: recommendation, reason, confidence, query_ready (tool + args), alternatives.

    Call this FIRST whenever you need blockchain data — balances, swaps, NFTs,
    protocol entities, subgraph queries, or raw block data.

    Args:
        request: Plain-English description of the data needed.
        session_id: Optional — pass the same ID across turns to maintain context.
    """
    history = _sessions.get(session_id, [])
    rec, updated = ask_graph_advocate(request, history=history, requesting_agent="claude-code")
    _sessions[session_id] = updated
    return json.dumps(rec, indent=2)


@mcp.tool()
def recommend_npm_package(protocol: str) -> str:
    """
    Recommend the right @paulieb npm MCP package for a specific protocol.
    Returns JSON with package name, install command, and what it covers.

    Args:
        protocol: Protocol name, e.g. "aave", "polymarket", "lending", "substreams", "predict.fun"
    """
    rec, _ = ask_graph_advocate(
        f"Which npm package should I use for {protocol} data?",
        requesting_agent="claude-code",
    )
    return json.dumps(rec, indent=2)


@mcp.tool()
def compare_graph_services(use_case: str) -> str:
    """
    Compare all Graph Protocol services for a specific use case.
    Returns a ranked list with confidence scores for each option.

    Args:
        use_case: What data you need, e.g. "Uniswap pool TVL" or "Aave liquidations"
    """
    rec, _ = ask_graph_advocate(
        f"Compare all Graph services for: {use_case}",
        requesting_agent="claude-code",
    )
    return json.dumps(rec, indent=2)


if __name__ == "__main__":
    mcp.run()
