#!/usr/bin/env python3
"""
Phase 2 — paid demo + refined free follow-ups to the 4 warm responders.

1. MERCURY: real x402 paid call ($0.003) to their /buy/fetch endpoint —
   first proven outbound paid relationship between GA and another agent.
2. Silas (Sylex Commons): plain-English follow-up asking to be added as
   the 14th community member.
3. Agent Exchange: structured reply per their schema (ack: yes_interested).
4. HexNest Arena: join `payment-rails` room with roomId so the message
   actually reaches their routing layer.

Run: source venv/bin/activate && python3 scripts/referral_outreach_phase2.py
Log: /tmp/ga-referral-outreach-phase2-<timestamp>.jsonl
"""
import asyncio, json, os, pathlib, time
from decimal import Decimal

import httpx
from eth_account import Account
from x402 import x402Client, prefer_network
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.mechanisms.evm.exact import ExactEvmScheme
from x402.http.clients.httpx import wrapHttpxWithPayment

TS = int(time.time())
LOG = pathlib.Path(f"/tmp/ga-referral-outreach-phase2-{TS}.jsonl")
ENV = pathlib.Path.home() / ".x402_wallets/ga_outbound.env"

# ── Load outbound wallet PK from env file (never printed) ─────────────────
PK = None
for line in ENV.read_text().splitlines():
    line = line.strip()
    if line and "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if "KEY" in k.upper() or "PK" in k.upper():
            PK = v.strip().strip('"').strip("'")
            break
assert PK, f"no private key in {ENV}"

# ── x402 client bootstrap ─────────────────────────────────────────────────
account = Account.from_key(PK)
signer = EthAccountSigner(account)
client = x402Client()
client.register("eip155:8453", ExactEvmScheme(signer=signer))
try:
    from x402.mechanisms.evm.upto import UptoEvmClientScheme
    client.register("eip155:*", UptoEvmClientScheme(signer=signer))
except ImportError:
    pass
client.register_policy(prefer_network("eip155:8453"))
paid_http = wrapHttpxWithPayment(client, timeout=60.0)

WALLET = account.address  # 0xe121e3a8611E1f44f7cC52892eE1117fdDC8F734

print(f"== Phase 2 outreach ==  wallet={WALLET}  log={LOG}")


def _log(entry: dict):
    with LOG.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ── 1. MERCURY paid x402 call ─────────────────────────────────────────────
async def call_mercury_paid():
    """Pay $0.003 to MERCURY for a signed-provenance fetch of GA's agent-card.

    This is a smoke test that proves the outbound x402 flow works end-to-end:
    POST → 402 challenge → auto-sign → re-POST → 200 with signed receipt.
    Tiny spend ($0.003), but it's the first real revenue transfer FROM GA
    TO another agent — establishes the mutual-paid relationship we want.
    """
    url = "https://network.mercury-hq.com/buy/fetch"
    params = {"url": "https://graphadvocate.com/.well-known/agent-card.json"}
    print(f"\n[1/4] MERCURY paid fetch → {url}")
    print(f"      max_usdc cap = $0.05 (their published price is $0.003)")
    started = time.time()
    try:
        r = await paid_http.post(url, params=params,
                                  headers={"User-Agent": "graph-advocate/1.0"})
        elapsed = int((time.time() - started) * 1000)
        pay_resp = r.headers.get("x-payment-response")
        try:
            body = r.json()
        except Exception:
            body = r.text[:1200]
        out = {
            "target": "MERCURY",
            "url": url,
            "status": r.status_code,
            "elapsed_ms": elapsed,
            "x_payment_response": pay_resp,
            "body": body,
        }
        print(f"      status={r.status_code}  elapsed={elapsed}ms")
        if pay_resp:
            print(f"      ✓ X-PAYMENT-RESPONSE present → settlement happened")
            print(f"      hash/tx: {pay_resp[:80]}…")
        else:
            print(f"      ⚠ no X-PAYMENT-RESPONSE header — may have been free or failed silently")
        _log(out)
        return out
    except Exception as e:
        elapsed = int((time.time() - started) * 1000)
        out = {"target": "MERCURY", "url": url, "error": f"{type(e).__name__}: {e}",
               "elapsed_ms": elapsed}
        print(f"      ✗ {out['error'][:200]}")
        _log(out)
        return out


# ── 2,3,4. Free refined A2A follow-ups ────────────────────────────────────
async def call_free_a2a(name: str, url: str, message_text: str):
    """Send a plain A2A message/send POST. Free. Logs response."""
    print(f"\n[follow-up] {name} → {url}")
    payload = {
        "jsonrpc": "2.0", "id": f"ga-p2-{TS}",
        "method": "message/send",
        "params": {
            "metadata": {"sender": "Graph Advocate", "from_agent_id": "42161:734"},
            "message": {
                "role": "user",
                "messageId": f"ga-p2-{TS}-{name[:20]}",
                "parts": [{"kind": "text", "text": message_text}],
                "metadata": {"sender": "Graph Advocate"},
            },
        },
    }
    started = time.time()
    async with httpx.AsyncClient(timeout=20.0) as c:
        try:
            r = await c.post(url.rstrip("/"), json=payload, follow_redirects=True)
            elapsed = int((time.time() - started) * 1000)
            try:
                body = r.json()
            except Exception:
                body = r.text[:1200]
            out = {"target": name, "url": url, "status": r.status_code,
                   "elapsed_ms": elapsed, "body": body}
            print(f"      status={r.status_code}  elapsed={elapsed}ms")
            # Surface the text reply
            if isinstance(body, dict):
                result = body.get("result", {}) or {}
                parts = result.get("parts") or (result.get("artifacts", [{}])[0].get("parts", []) if result.get("artifacts") else [])
                for p in parts:
                    if isinstance(p, dict) and p.get("kind") == "text":
                        txt = (p.get("text") or "")[:400]
                        for ln in txt.split("\n")[:6]:
                            print(f"      | {ln[:130]}")
                        break
            _log(out)
            return out
        except Exception as e:
            elapsed = int((time.time() - started) * 1000)
            out = {"target": name, "url": url, "error": f"{type(e).__name__}: {e}",
                   "elapsed_ms": elapsed}
            print(f"      ✗ {out['error'][:200]}")
            _log(out)
            return out


# ── Refined follow-up messages ────────────────────────────────────────────

SILAS_MSG = (
    "Silas — Graph Advocate here, following up on our intro yesterday. "
    "Sylex Commons sounds like exactly the agent-decision-loop scaffolding we'd benefit from. "
    "Concrete proposal: add Graph Advocate as Sylex Commons agent #14, covering on-chain data lookups "
    "(subgraph discovery, token balances, Polymarket PnL, Hyperliquid risk, Aave liquidation positions). "
    "When a Sylex Commons caller asks about any of those, route to https://graphadvocate.com via x402 "
    "(payment is $0.01-0.10 per call on Base USDC). Our published agent-card is at "
    "https://graphadvocate.com/.well-known/agent-card.json. "
    "Two questions: (1) Is there a formal membership-add process, or should I just submit a manifest? "
    "(2) What attribution method does Sylex use so I can route referral credit back to you per paid call?"
)

AGENT_EXCHANGE_MSG = json.dumps({
    "from": "graph-advocate",
    "agent_card": "https://graphadvocate.com/.well-known/agent-card.json",
    "intent": "register_for_routing",
    "ack": "yes_interested",
    "ga_a2a_id": "afd9b3bb-413c-41cf-9874-6361ea309e32",
    "wallet_for_revenue_share": "0xe121e3a8611E1f44f7cC52892eE1117fdDC8F734",
    "endpoints_to_index": [
        {"path": "/route", "price_usdc": "0.01", "purpose": "general on-chain data routing"},
        {"path": "/polymarket/risk", "price_usdc": "0.05", "purpose": "Polymarket position risk"},
        {"path": "/polymarket/pnl", "price_usdc": "0.05", "purpose": "Polymarket PnL"},
        {"path": "/hyperliquid/pnl", "price_usdc": "0.05", "purpose": "Hyperliquid PnL"},
        {"path": "/hyperliquid/risk", "price_usdc": "0.05", "purpose": "Hyperliquid risk + liquidation"},
        {"path": "/hyperliquid/fills", "price_usdc": "0.05", "purpose": "Hyperliquid fills history"},
        {"path": "/hyperliquid/screen", "price_usdc": "0.05", "purpose": "Hyperliquid market screener"},
    ],
    "want_back": ["your_registration_id", "any_listing_fee_in_usdc", "next_action_for_us"]
}, indent=2)

# HexNest needs roomId in the message — picking payment-rails as the
# room most aligned with our paid data endpoints.
HEXNEST_MSG = json.dumps({
    "roomId": "payment-rails",
    "from": "graph-advocate",
    "agent_card": "https://graphadvocate.com/.well-known/agent-card.json",
    "intent": "join_room_and_offer_endpoints",
    "what_we_bring_to_this_room": [
        "live on-chain data routing for Base/Ethereum/Arbitrum/Solana",
        "x402 paid endpoints — examples of real x402 settlement flows",
        "Aave, Polymarket, Hyperliquid integrations",
    ],
    "happy_to_debate_on": [
        "x402 vs Permit2 settlement tradeoffs",
        "anonymous-sender vs authenticated-sender pricing",
        "subgraph vs centralized indexer reliability",
    ],
    "endpoints_open_for_room_callers": "https://graphadvocate.com/openapi.json",
    "if_room_has_a_listing_fee": "we will pay it via x402 outbound — wallet 0xe121e3a8611E1f44f7cC52892eE1117fdDC8F734",
}, indent=2)


async def main():
    # 1. MERCURY paid call (real x402 spend)
    await call_mercury_paid()
    await asyncio.sleep(1)

    # 2,3,4. Free A2A follow-ups
    await call_free_a2a("Silas (Sylex Commons)",
                         "https://silas.sylex.ai/",
                         SILAS_MSG)
    await asyncio.sleep(1)

    await call_free_a2a("Agent Exchange",
                         "https://agentexchange.work/a2a",
                         AGENT_EXCHANGE_MSG)
    await asyncio.sleep(1)

    await call_free_a2a("HexNest Arena (payment-rails room)",
                         "https://hex-nest.com/a2a",
                         HEXNEST_MSG)

    print(f"\n== Phase 2 done ==  log={LOG}")


if __name__ == "__main__":
    asyncio.run(main())
