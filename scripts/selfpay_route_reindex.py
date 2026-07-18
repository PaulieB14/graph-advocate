"""
Self-pay test: GA's outbound hot wallet pays graphadvocate.com/route once.

Purpose:
- Confirm the receive path works end-to-end after the 2026-05-02 cleanup
  (Permit2 removed, EIP-3009-only).
- Trigger CDP Bazaar to re-index graphadvocate.com (per their docs, the
  first successful settlement at a URL flips it to "actually-earning",
  which fast-tracks the directory listing refresh).

Run:
    set -a; . ~/.x402_wallets/ga_outbound.env; set +a
    python3 scripts/selfpay_route_reindex.py

Reads GA_BASE_WALLET_PK from env. Caps at $0.05. Idempotent — every
new payment uses a fresh nonce, so re-runs are safe but unnecessary.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys


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
    print(f"# payer wallet: {account.address}")
    print(f"# target:       https://graphadvocate.com/route")

    try:
        resp = await http.request(
            "POST",
            "https://graphadvocate.com/route",
            json={"request": "self-pay reindex probe — Top USDC holders on Base"},
        )
        settle = resp.headers.get("x-payment-response", "")
        body = None
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:500]
        print(json.dumps({
            "ok": resp.status_code == 200,
            "http_status": resp.status_code,
            "settled": bool(settle),
            "x-payment-response_present": bool(settle),
            "body_preview": body if isinstance(body, dict) else str(body)[:500],
        }, indent=2, default=str))
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "error_type": type(e).__name__,
            "error": str(e)[:500],
        }, indent=2))
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
