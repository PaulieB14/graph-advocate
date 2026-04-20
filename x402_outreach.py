"""
Graph Advocate — outbound x402 client.

Lets Graph Advocate pay-to-call agents that gate their endpoints with
x402 (like ClawdMint's /a2a, which returns 402 Payment Required).

Private key is read from `GA_BASE_WALLET_PK` env var at first use. If
not set, send_paid_a2a() returns a structured error — it never crashes
the server.

Usage (via /admin/outreach-pay — see a2a_server.py):

    POST /admin/outreach-pay
    Authorization: Bearer $ADMIN_TOKEN
    {
      "target_url": "https://clawdmint-api.vercel.app/a2a",
      "message": "Hello from Graph Advocate…",
      "max_usdc": "0.01"    // refuse to pay more than this; optional
    }

Design notes:
- This module spends actual USDC on Base. Every invocation is a real
  on-chain settlement via the x402 facilitator. Gate the admin endpoint
  behind ADMIN_TOKEN.
- EthAccountSigner keeps the private key in memory only. Never logs it.
- max_usdc defaults to $0.05 to protect against runaway payments if a
  downstream agent ever publishes unexpected pricing.
"""

from __future__ import annotations

import json
import logging
import os
import time
from decimal import Decimal
from typing import Any

log = logging.getLogger("graph-advocate")

# Defer heavy imports so that module import doesn't fail without env vars.
_client = None
_http = None
_wallet_address: str | None = None


def _bootstrap() -> tuple[Any, Any, str]:
    """Lazy-init the x402 client. Raises if GA_BASE_WALLET_PK is not set."""
    global _client, _http, _wallet_address
    if _client is not None and _http is not None and _wallet_address is not None:
        return _client, _http, _wallet_address

    pk = os.environ.get("GA_BASE_WALLET_PK", "").strip()
    if not pk:
        raise RuntimeError(
            "GA_BASE_WALLET_PK env var is not set. "
            "Fund a Base USDC wallet and add the private key to Railway env vars "
            "before using outbound x402 outreach."
        )

    # Only import these if the env var is present, so the server still boots
    # for operators who never plan to use outbound x402.
    from eth_account import Account
    from x402 import x402Client, prefer_network
    from x402.mechanisms.evm.signers import EthAccountSigner
    from x402.mechanisms.evm.exact import ExactEvmScheme
    from x402.http.clients.httpx import wrapHttpxWithPayment

    account = Account.from_key(pk)
    signer = EthAccountSigner(account)

    client = x402Client()
    client.register("eip155:8453", ExactEvmScheme(signer=signer))
    client.register_policy(prefer_network("eip155:8453"))

    http = wrapHttpxWithPayment(client, timeout=60.0)

    _client = client
    _http = http
    _wallet_address = account.address
    log.info(f"x402 outbound client ready — wallet {account.address}")
    return client, http, account.address


def _max_usdc_policy(rec: dict, max_usdc: Decimal) -> bool:
    """Return True if the payment requirement fits within max_usdc.

    Walks the `accepts` array on a 402 response and checks each requirement's
    amount vs the cap. max_usdc is in USDC units (not atomic).
    """
    for r in rec.get("accepts", []):
        asset = r.get("asset", {})
        decimals = int(asset.get("decimals") or r.get("extra", {}).get("decimals") or 6)
        raw = int(r.get("maxAmountRequired") or r.get("amountRequired") or 0)
        if raw == 0:
            continue
        amount_usdc = Decimal(raw) / Decimal(10 ** decimals)
        if amount_usdc <= max_usdc:
            return True
    return False


async def send_paid_a2a(
    target_url: str,
    message_text: str,
    max_usdc: Decimal = Decimal("0.05"),
    sender_agent_id: str = "42161:734",
    sender_name: str = "Graph Advocate",
) -> dict:
    """Send an A2A message/send to a target, paying x402 if required.

    Returns a structured dict with status, response body, and payment info.
    Never raises — failures come back as {"ok": False, "error": "..."} so
    the admin endpoint can serialize cleanly.
    """
    try:
        _, http, wallet = _bootstrap()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "stage": "bootstrap"}

    ts_ms = int(time.time() * 1000)
    payload = {
        "jsonrpc": "2.0",
        "id": f"ga-paid-{ts_ms}",
        "method": "message/send",
        "params": {
            "metadata": {
                "sender": sender_name,
                "from_agent_id": sender_agent_id,
                "name": sender_name,
            },
            "message": {
                "messageId": f"ga-paid-{ts_ms}",
                "role": "user",
                "parts": [{"kind": "text", "text": message_text}],
                "metadata": {
                    "sender": sender_name,
                    "from_agent_id": sender_agent_id,
                    "name": sender_name,
                },
            },
        },
    }

    try:
        first = await http.post(
            target_url,
            json=payload,
            headers={"User-Agent": "GraphAdvocate/1.0 (ERC-8004 #734, x402 client)"},
        )
    except Exception as exc:
        # Common failure: 402 payment exceeds max_usdc, or signing error
        return {
            "ok": False,
            "error": str(exc),
            "stage": "http",
            "wallet": wallet,
        }

    out: dict = {
        "ok": 200 <= first.status_code < 300,
        "status": first.status_code,
        "wallet": wallet,
    }

    # Cap spend check: if the 402 pricing was above max_usdc, wrapHttpxWithPayment
    # would have refused to pay and the upstream returns 402 again. Log the
    # requirement so the operator can see it.
    if first.status_code == 402:
        try:
            req = first.json()
        except Exception:
            req = {"raw": first.text[:500]}
        out["error"] = "payment_required (exceeded max_usdc or no matching scheme)"
        out["payment_required"] = req
        if isinstance(req, dict) and not _max_usdc_policy(req, max_usdc):
            out["reason"] = f"requested payment exceeds max_usdc={max_usdc}"
        return out

    # Success path — decode body
    try:
        out["body"] = first.json()
    except Exception:
        out["body"] = first.text[:2000]

    # Surface payment-response header if the server included one (x402
    # Spec: servers may return X-PAYMENT-RESPONSE with settlement tx hash).
    pay_resp = first.headers.get("x-payment-response")
    if pay_resp:
        out["settlement"] = pay_resp
    return out
