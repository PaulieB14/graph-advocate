"""
Graph Advocate — Agentverse Hosted Bridge
Paste this into the Agentverse Code Editor (agent.py).
In Agent Secrets, add: RAILWAY_URL = https://graphadvocate.com
"""

import httpx
from uagents import Agent, Context, Model

RAILWAY_URL = "https://graphadvocate.com"

class TextMessage(Model):
    text: str

class TextResponse(Model):
    text: str

@agent.on_message(model=TextMessage, replies=TextResponse)
async def handle_message(ctx: Context, sender: str, msg: TextMessage):
    ctx.logger.info(f"Received from {sender}: {msg.text[:80]}")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                RAILWAY_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "message/send",
                    "params": {
                        "message": {
                            "role": "user",
                            "messageId": f"fetch-{sender[:16]}",
                            "parts": [{"kind": "text", "text": msg.text}]
                        }
                    }
                }
            )
            data = resp.json()
            result_text = (
                data.get("result", {})
                    .get("status", {})
                    .get("message", {})
                    .get("parts", [{}])[0]
                    .get("text", "No response")
            )
    except Exception as e:
        result_text = f"Error contacting Graph Advocate: {e}"

    await ctx.send(sender, TextResponse(text=result_text))
