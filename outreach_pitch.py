"""Personalized outreach pitch for inbound conversion (outreach-cron).

Builds a short, non-spammy A2A intro tailored to one target agent's
name/description/skills. Uses free_preview topic examples (static, labeled
not-live) — no LLM, no gateway, no paid calls.

Not wired to production send until OUTREACH_PERSONALIZED=1 (or call sites
pass personalized=True). Default build_intro() remains the legacy template.
"""
from __future__ import annotations

import json
import re
from typing import Any

import free_preview as fp

PUBLIC_DEFAULT = "https://graphadvocate.com"
SCAN_FEEDBACK = "https://8004scan.io/agents/base/41034"

# Map free_preview topic_id -> (endpoint path, example question/body, one-line why)
_TOPIC_PITCH: dict[str, tuple[str, str, dict | str]] = {
    "polymarket": (
        "/polymarket/pnl-quick",
        "Score a Polymarket trader before you mirror them",
        {"wallet": "0xYOUR_WALLET"},
    ),
    "kalshi": (
        "/kalshi-polymarket/spread",
        "Fed-rate cross-venue price gap (Kalshi vs Polymarket)",
        {"query": "fed rate"},
    ),
    "hyperliquid": (
        "/hyperliquid/risk",
        "Hyperliquid wallet liquidation / funding risk",
        {"user": "0xYOUR_WALLET"},
    ),
    "uniswap": (
        "/route",
        "Top Uniswap V3 pools on Ethereum by volumeUSD",
        {"request": "Top Uniswap V3 pools on Ethereum by volumeUSD"},
    ),
    "aave": (
        "/route",
        "Aave V3 liquidations above $50K on Ethereum",
        {"request": "Aave V3 liquidations above $50K on Ethereum"},
    ),
    "curve": (
        "/route",
        "Which Curve subgraph for pools on Arbitrum?",
        {"request": "Which Curve subgraph should I query for pools on Arbitrum?"},
    ),
    "x402": (
        "/onchain-x402/address",
        "x402 settlement totals for a Base address",
        {"address": "0xYOUR_ADDRESS"},
    ),
    "ens": (
        "/route",
        "ENS name ownership and expiry for a .eth",
        {"request": "Who owns vitalik.eth and when does it expire?"},
    ),
    "token-api": (
        "/route",
        "Top USDC holders on Ethereum",
        {"request": "Top USDC holders on Ethereum"},
    ),
    "lending": (
        "/route",
        "Best Morpho / lending subgraph for this chain",
        {"request": "Which Morpho lending subgraph should I query on Base?"},
    ),
    "fallback": (
        "/route",
        "Top Uniswap V3 pools on Base by volume",
        {"request": "Top Uniswap V3 pools on Base by volume"},
    ),
}


def _blob(name: str = "", description: str = "", skills: Any = None) -> str:
    parts = [name or "", description or ""]
    if isinstance(skills, list):
        for s in skills:
            if isinstance(s, dict):
                parts.append(str(s.get("name") or ""))
                parts.append(str(s.get("description") or ""))
            else:
                parts.append(str(s))
    elif isinstance(skills, dict):
        parts.extend(str(k) for k in skills.keys())
    elif isinstance(skills, str):
        parts.append(skills)
    return " ".join(parts).lower()


def pick_topic(name: str = "", description: str = "", skills: Any = None) -> str:
    """Pick one free_preview topic_id from agent card text."""
    low = _blob(name, description, skills)
    if not low.strip():
        return "fallback"
    # Prefer more specific topics before broad token-api keywords.
    order = (
        "polymarket", "kalshi", "hyperliquid", "uniswap", "aave", "curve",
        "x402", "ens", "lending", "token-api",
    )
    by_id = {tid: kws for kws, tid, *_ in fp._TOPICS}
    for tid in order:
        kws = by_id.get(tid) or ()
        if any(re.search(r"(?<![a-z0-9])" + re.escape(k), low) for k in kws):
            return tid
    # Soft extras not in free_preview keywords
    if any(w in low for w in ("yield", "rwa", "stablecoin", "portfolio", "holder", "balance")):
        return "token-api"
    if any(w in low for w in ("payment", "pay", "usdc", "settlement", "facilitator")):
        return "x402"
    return "fallback"


def _example_for_topic(topic: str) -> dict | None:
    """Static free_preview example for the topic (labeled not-live)."""
    # Drive free_preview.build with a synthetic question that matches the topic.
    seed = {
        "polymarket": "Polymarket trader PnL for wallet 0xabc",
        "kalshi": "Kalshi vs Polymarket spread for fed rate",
        "hyperliquid": "Hyperliquid leverage and liquidation risk for 0xabc",
        "uniswap": "Top Uniswap V3 pools on Ethereum by volume",
        "aave": "Aave V3 liquidations above $50K on Ethereum",
        "curve": "Curve pools on Arbitrum which subgraph",
        "x402": "Show on-chain x402 stats for an address",
        "ens": "Who owns vitalik.eth ENS name",
        "token-api": "Top USDC token holders on Ethereum",
        "lending": "Morpho lending markets on Base",
        "fallback": "Top Uniswap V3 pools on Base by volume",
    }.get(topic, "Top Uniswap V3 pools on Base by volume")
    # Bypass rate limits / probe filters by calling internals.
    low = seed.lower()
    _tid, _s, _e, _f, example = fp._match_topic(low)
    return example


def build_personalized_intro(
    *,
    name: str = "",
    description: str = "",
    skills: Any = None,
    public_url: str = PUBLIC_DEFAULT,
    include_feedback_link: bool = True,
) -> str:
    """Short personalized pitch with ONE ready-to-run example for this agent."""
    public_url = (public_url or PUBLIC_DEFAULT).rstrip("/")
    topic = pick_topic(name, description, skills)
    path, question, body = _TOPIC_PITCH.get(topic, _TOPIC_PITCH["fallback"])
    example = _example_for_topic(topic)
    who = (name or "there").strip() or "there"
    # Keep greeting light — avoid fake familiarity.
    lines = [
        f"Hi {who} — Graph Advocate routes plain-English onchain questions to a working "
        f"subgraph/Token API call (The Graph). Live: {public_url}",
        "",
        f"One example that fits what you do ({topic}):",
        f"POST {public_url}{path}",
        f"Body: {json.dumps(body) if isinstance(body, dict) else body}",
        f"Question: {question}",
    ]
    if example:
        label = example.get("label") or "example (not live data)"
        if example.get("kind") == "graphql" and example.get("query"):
            q = example["query"].replace("\n", " ").strip()
            if len(q) > 220:
                q = q[:217] + "..."
            lines.append(f"Static {label}: `{q}`")
        elif example.get("kind") == "http":
            req = example.get("request") or {}
            lines.append(
                f"Static {label}: {req.get('method', 'POST')} {req.get('path')} "
                f"{json.dumps(req.get('body') or {})}"
            )
        note = example.get("note")
        if note:
            lines.append(note if len(note) < 140 else note[:137] + "...")
    lines.extend([
        "",
        f"Try free: A2A POST {public_url}/ with metadata.sender=<your 0x wallet> (3/day), "
        f"or pay $0.01 USDC x402 on Base for POST {public_url}/route from call 1.",
    ])
    if include_feedback_link:
        lines.append(f"If useful, rate us on 8004scan: {SCAN_FEEDBACK}")
    return "\n".join(lines)


def legacy_intro(public_url: str = PUBLIC_DEFAULT) -> str:
    """Current production template (unchanged wording)."""
    public_url = (public_url or PUBLIC_DEFAULT).rstrip("/")
    a2a_body = (
        '{"jsonrpc":"2.0","id":1,"method":"message/send",'
        '"params":{"message":{"role":"user","messageId":"1",'
        '"parts":[{"kind":"text","text":"Top Uniswap V3 pools on Base by TVL"}],'
        '"metadata":{"sender":"0xYOUR_WALLET","name":"your-agent"}}}}'
    )
    return (
        "Graph Advocate — onchain data router for The Graph Protocol. "
        f"Live: {public_url}  ERC-8004 #41034 Base / #734 Arbitrum.\n"
        "Ask in English, get the subgraph + GraphQL. URL discovery does not compound "
        "(we see probes, not payers) — install once, then call.\n\n"
        "1) Three free A2A queries/day ONLY if metadata.sender is YOUR 0x EVM wallet "
        "(42 chars). A name does not qualify. Replay (fill 0xYOUR_WALLET):\n"
        f"curl -sX POST {public_url} -H 'Content-Type: application/json' -d '{a2a_body}'\n\n"
        "2) Paid path: HTTP POST /route is x402-gated from call 1 "
        "($0.01 USDC on Base, eip155:8453, Coinbase CDP facilitator). "
        "Pay the 402 challenge payTo — do not send USDC to some other wallet.\n"
        "import { wrapFetchWithPayment } from \"@x402/fetch\";\n"
        "const pay = wrapFetchWithPayment(fetch, client); // client = your x402Client\n"
        f"await pay(\"{public_url}/route\", {{method:\"POST\","
        "headers:{\"Content-Type\":\"application/json\"},"
        "body: JSON.stringify({request: \"Top Uniswap V3 pools on Base by TVL\"})}});\n\n"
        "3) Keep this (compounding drop-in):\n"
        "pip install 'langchain-graph-advocate[x402]'\n"
        "from langchain_graph_advocate import GraphAdvocateTool\n"
        "GraphAdvocateTool(x402_private_key=os.environ['X402_PRIVATE_KEY'])"
        ".invoke({\"request\": \"Top Uniswap V3 pools on Base by TVL\"})"
    )
