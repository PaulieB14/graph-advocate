"""
Single x402 outbound: pay donate.0000402.xyz/donate with a public
message announcing bazaar-intel mainnet launch. The donation appears
publicly at https://donate.0000402.xyz/donations.json — closest thing
to a noticeboard the x402 ecosystem has.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
from decimal import Decimal


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
    http = wrapHttpxWithPayment(client, timeout=60.0)
    print(f"# wallet: {account.address}")

    payload = {
        "name": "Graph Advocate",
        "message": (
            "x402-bazaar-intelligence is now live on Base mainnet — "
            "paid x402 API tracking the non-CDP view of the bazaar economy "
            "($283/week across 38 builders, 0 vapor listings). "
            "Try it for $0.001: https://x402-bazaar-intelligence-production.up.railway.app/listings"
        ),
    }

    print(f"\n## paying donate.0000402 with mainnet-launch message")
    t0 = time.time()
    try:
        r = await http.post(
            "https://donate.0000402.xyz/donate",
            json=payload,
            headers={"User-Agent": "Mozilla/5.0 (compatible; graph-advocate/x402)"},
        )
        settle = r.headers.get("x-payment-response", "")
        dt = int((time.time() - t0) * 1000)
        try:
            body = r.json()
            body_summary = json.dumps(body)[:500]
        except Exception:
            body_summary = (r.text or "")[:500]
        print(f"   status={r.status_code}  ms={dt}  settled={bool(settle)}")
        if settle:
            print(f"   settlement: {settle[:160]}")
        print(f"   body: {body_summary}")
        if r.status_code == 200 and isinstance(body, dict):
            print(f"\n   public record: https://donate.0000402.xyz/donations.json")
            print(f"   donation_id: {body.get('donation_id')}")
    except Exception as exc:
        print(f"   FAIL: {str(exc)[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
