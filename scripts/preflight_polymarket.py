"""
Cache the paid /polymarket/* endpoints in x402station's discovery catalog.

Companion to preflight_hyperliquid.py — same mechanism (a small x402 payment
per URL that lands the endpoint in x402station's downstream-agent catalog).
Includes the new /polymarket/leaders top-traders endpoint.

Cost: 5 × ~$0.001 = ~$0.005 USDC on Base + tiny gas. Reads GA_BASE_WALLET_PK.

Run (from a machine with open network — not the sandboxed agent shell):
    cd ~/graph-advocate
    set -a; . ~/.x402_wallets/ga_outbound.env; set +a
    venv/bin/python scripts/preflight_polymarket.py
"""
from __future__ import annotations
import asyncio
import json
import os
import sys

PREFLIGHT_URL = "https://x402station.io/api/v1/preflight"
POLYMARKET_URLS = [
    "https://graphadvocate.com/polymarket/leaders",
    "https://graphadvocate.com/polymarket/pnl-quick",
    "https://graphadvocate.com/polymarket/pnl",
    "https://graphadvocate.com/polymarket/screen",
    "https://graphadvocate.com/polymarket/risk",
]


async def main():
    pk = os.environ.get("GA_BASE_WALLET_PK", "").strip()
    if not pk:
        print(json.dumps({"ok": False, "error": "GA_BASE_WALLET_PK not set"}))
        sys.exit(1)

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
    http = wrapHttpxWithPayment(client, timeout=90.0)

    print(f"# payer wallet: {account.address}")
    print(f"# preflight:    {PREFLIGHT_URL}")
    print()

    results = []
    for url in POLYMARKET_URLS:
        try:
            resp = await http.request("POST", PREFLIGHT_URL, json={"url": url})
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:300]
            results.append({
                "url": url,
                "http_status": resp.status_code,
                "settled": bool(resp.headers.get("x-payment-response")),
                "warnings": (body.get("warnings") if isinstance(body, dict) else None),
                "service_id": (body.get("metadata", {}).get("service_id")
                               if isinstance(body, dict) else None),
                "price_usdc": (body.get("metadata", {}).get("price_usdc")
                               if isinstance(body, dict) else None),
            })
        except Exception as e:
            results.append({
                "url": url,
                "error_type": type(e).__name__,
                "error": str(e)[:300],
            })

    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
