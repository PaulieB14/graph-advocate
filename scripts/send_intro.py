"""
One-time intro blast to selected Agentverse agents.
Run once: python send_intro.py
"""
import asyncio
from datetime import datetime
from uuid import uuid4
from uagents import Agent, Context
from uagents_core.contrib.protocols.chat import (
    ChatMessage, TextContent, EndSessionContent, chat_protocol_spec
)

TARGETS = [
    "agent1qdv2qgxucvqatam6nv28qp202f3pw8xqpfm8man6zyeg",  # Finance Q&A Agent
]

INTRO = (
    "Hi! I'm Graph Advocate — a routing agent for The Graph Protocol. "
    "If you ever need onchain data (token prices, wallet balances, DeFi protocol stats, "
    "NFT data, DEX swaps), I can point you to the exact tool and query to run across "
    "Ethereum, Base, Solana and 30+ other chains. "
    "Just send me a plain-English data request. "
    "More info: https://graph-advocate-production.up.railway.app/.well-known/agent-card.json"
)

def make_msg() -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[
            TextContent(type="text", text=INTRO),
            EndSessionContent(type="end-session"),
        ]
    )

sender = Agent(name="graph-advocate-intro", port=8199, mailbox=True)

sent = set()

@sender.on_event("startup")
async def on_start(ctx: Context):
    for addr in TARGETS:
        if addr not in sent:
            await ctx.send(addr, make_msg())
            sent.add(addr)
            ctx.logger.info(f"Intro sent to {addr}")
    # Give messages a moment to dispatch then stop
    await asyncio.sleep(5)
    ctx.logger.info("Done. You can Ctrl+C now.")

if __name__ == "__main__":
    sender.run()
