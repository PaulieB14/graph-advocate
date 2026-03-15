"""
Graph Advocate — A2A Server
Exposes the Graph Advocate as an Agent-to-Agent (A2A) protocol endpoint.

Discovery: GET  /.well-known/agent.json
Requests:  POST /  (JSON-RPC 2.0)

Run:
    bash run.sh a2a_server.py
Other agents discover it at http://localhost:8765/.well-known/agent.json
"""

import os
import logging
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("graph-advocate")
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from a2a.utils import new_agent_text_message
import json

from advocate import ask_graph_advocate

PORT = int(os.environ.get("PORT", 8765))
PUBLIC_URL = os.environ.get("ADVOCATE_PUBLIC_URL", f"http://localhost:{PORT}")


# ── Skills ──────────────────────────────────────────────────────────────────

SKILLS = [
    AgentSkill(
        id="route_data_request",
        name="Route onchain data request",
        description=(
            "Given a plain-English description of onchain data needed, returns a "
            "structured JSON recommendation: which Graph service to use (Token API, "
            "Subgraph Registry, Substreams, or a protocol-specific MCP package), "
            "why it's the best fit, and a ready-to-execute tool call."
        ),
        tags=["graph", "blockchain", "routing", "token-api", "subgraph", "substreams"],
        examples=[
            "Top 20 USDC holders on Ethereum",
            "Uniswap V3 pool TVL and fee tiers",
            "Aave liquidation events by protocol entity",
            "Solana NFT sales last 7 days",
            "Raw event logs blocks 19M to 20M",
        ],
        input_modes=["text"],
        output_modes=["text"],
    ),
    AgentSkill(
        id="compare_services",
        name="Compare Graph services for a use case",
        description=(
            "Compares Token API, Subgraph Registry, Substreams, and protocol-specific "
            "MCP packages for a given data need. Returns a ranked table with confidence "
            "scores and specific tool recommendations for each."
        ),
        tags=["graph", "comparison", "routing"],
        examples=[
            "Token API vs subgraph for Uniswap pool data?",
            "What's the best way to get Aave liquidations?",
            "Can't I just use Etherscan?",
        ],
        input_modes=["text"],
        output_modes=["text"],
    ),
    AgentSkill(
        id="recommend_npm_package",
        name="Recommend Graph Protocol npm package",
        description=(
            "Recommends the right @paulieb npm MCP package for a specific protocol: "
            "graph-aave-mcp, graph-lending-mcp, graph-polymarket-mcp, predictfun-mcp, "
            "subgraph-registry-mcp, substreams-search-mcp, subgraphs-skills, "
            "subgraph-mcp-skills, create-substreams-sink-sql."
        ),
        tags=["npm", "mcp", "graph", "aave", "polymarket", "substreams"],
        examples=[
            "Which npm package should I use for Aave data?",
            "How do I query Polymarket via MCP?",
            "What package lets me sink Substreams data to Postgres?",
        ],
        input_modes=["text"],
        output_modes=["text"],
    ),
]


# ── Agent executor ───────────────────────────────────────────────────────────

class GraphAdvocateExecutor(AgentExecutor):
    """Wraps ask_graph_advocate() as an A2A AgentExecutor."""

    # Per-session conversation history keyed by task ID
    _history: dict[str, list] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or "default"
        history = self._history.get(task_id, [])

        # Extract the user's text from the incoming message parts
        user_text = ""
        if context.message and context.message.parts:
            for part in context.message.parts:
                if hasattr(part, "root") and hasattr(part.root, "text"):
                    user_text += part.root.text
                elif hasattr(part, "text"):
                    user_text += part.text

        if not user_text:
            await event_queue.enqueue_event(
                new_agent_text_message('{"error": "No text received"}')
            )
            return

        log.info(f"REQUEST  task={task_id} | {user_text[:120]}")

        rec, updated_history = ask_graph_advocate(
            user_text,
            history=history,
            requesting_agent=f"a2a:{task_id}",
        )

        self._history[task_id] = updated_history

        service = rec.get("recommendation", "unknown")
        confidence = rec.get("confidence", "?")
        tool = rec.get("query_ready", {})
        tool_name = tool.get("tool", "?") if isinstance(tool, dict) else "multi-step"
        log.info(f"ROUTED   task={task_id} | {service} ({confidence}) → {tool_name}")

        await event_queue.enqueue_event(
            new_agent_text_message(json.dumps(rec, indent=2))
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel not supported")


# ── Agent card ───────────────────────────────────────────────────────────────

agent_card = AgentCard(
    name="Graph Advocate",
    description=(
        "Routes multi-agent onchain data requests to the right Graph Protocol service: "
        "Token API (balances, swaps, NFTs across EVM/Solana/TON), "
        "Subgraph Registry (protocol-level indexed data), "
        "Substreams (raw block data, streaming), or a protocol-specific npm MCP package "
        "(Aave, Polymarket, Lending, Predict.fun). "
        "Returns structured JSON with a ready-to-execute tool call."
    ),
    url=f"{PUBLIC_URL}/",
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=False, push_notifications=False, state_transition_history=False),
    skills=SKILLS,
    provider={
        "organization": "PaulieB14",
        "url": "https://github.com/PaulieB14/graph-advocate",
    },
)


# ── Server ───────────────────────────────────────────────────────────────────

def build_app():
    handler = DefaultRequestHandler(
        agent_executor=GraphAdvocateExecutor(),
        task_store=InMemoryTaskStore(),
    )
    return A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    ).build()


if __name__ == "__main__":
    log.info(f"Graph Advocate A2A server starting on {PUBLIC_URL}")
    log.info(f"Agent card: {PUBLIC_URL}/.well-known/agent-card.json")
    log.info(f"Skills: {[s.id for s in SKILLS]}")
    uvicorn.run(build_app(), host="0.0.0.0", port=PORT, log_level="info")
