"""
Cache the 5 new /hyperliquid/* endpoints in x402station's discovery catalog.

Why: x402station became paid (~$0.001/call as of 2026-05-07). Their preflight
caches the URL into a downstream-agent service catalog; landing there is the
cheapest possible "ping" for new x402 endpoints beyond passive Bazaar crawl.

Cost: 5 × $0.001 = $0.005 USDC on Base + tiny gas. Reads GA_BASE_WALLET_PK.

Run:
    set -a; . ~/.x402_wallets/ga_outbound.env; set +a
    python3 scripts/preflight_hyperliquid.py
"""
from __future__ import annotations
import asyncio
import json
import os
import sys

PREFLIGHT_URL = "https://x402station.io/api/v1/preflight"
HYPERLIQUID_URLS = [
    "https://graphadvocate.com/hyperliquid/score",
    "https://graphadvocate.com/hyperliquid/pnl",
    "https://graphadvocate.com/hyperliquid/screen",
    "https://graphadvocate.com/hyperliquid/vault",
    "https://graphadvocate.com/hyperliquid/risk",
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
    for url in HYPERLIQUID_URLS:
        try:
            resp = await http.request(
                "POST",
                PREFLIGHT_URL,
                json={"url": url},
            )
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
