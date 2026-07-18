"""
One-off bazaar outreach v3 — input shapes corrected per each listing's
`outputSchema.input` declaration in CDP discovery.

Outbound from the GA hot wallet (`GA_BASE_WALLET_PK`). Each call is hard-
capped at $0.05 USDC and never raises; failures come back as structured
dicts so the operator can see what happened.
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

    targets = [
        # 0000402 donate — explicitly designed as a $0.01 live x402 integration test.
        # Listed as "the simplest possible x402 round-trip" — perfect first settlement.
        {
            "label": "donate-0000402",
            "method": "POST",
            "url": "https://donate.0000402.xyz/donate",
            "json": {
                "name": "Graph Advocate",
                "message": "GM from graphadvocate.eth — testing x402 outbound. Built x402-bazaar-intelligence today.",
            },
        },
        # blockrun polymarket activity — needs `wallet=` query param. Use a known
        # active Polymarket wallet (this one shows up in our memory as a recurring
        # x402 payer of GA — symbolic).
        {
            "label": "blockrun-polymarket-activity",
            "method": "GET",
            "url": "https://blockrun.ai/api/v1/pm/polymarket/activity?wallet=0xac5a07c44a4f971667b3df4b6551fb6991b2142d&limit=5",
        },
        # zapper token-balances — POST with addresses + first
        {
            "label": "zapper-token-balances",
            "method": "POST",
            "url": "https://public.zapper.xyz/x402/token-balances",
            "json": {
                "addresses": ["0x575267eED09c338FAE5716A486A7B58A5749A292"],
                "first": 5,
            },
        },
        # twit-by-id — use the example ID from the listing
        {
            "label": "twit-tweet-by-id",
            "method": "GET",
            "url": "https://x402.twit.sh/tweets/by/id?id=1110302988",
        },
    ]

    results = []
    for t in targets:
        print(f"\n## {t['label']} → {t['method']} {t['url']}")
        t0 = time.time()
        try:
            kwargs = {"headers": {"User-Agent": "Mozilla/5.0 (compatible; graph-advocate/x402)"}}
            if t.get("json") is not None:
                kwargs["json"] = t["json"]
            r = await http.request(t["method"], t["url"], **kwargs)

            settle = r.headers.get("x-payment-response", "")
            dt = int((time.time() - t0) * 1000)
            try:
                body_preview = json.dumps(r.json())[:500]
            except Exception:
                body_preview = (r.text or "")[:500]

            results.append({
                "label": t["label"],
                "url": t["url"],
                "status": r.status_code,
                "settled": bool(settle),
                "settlement": settle[:140] if settle else None,
                "ms": dt,
                "body_preview": body_preview,
            })
            print(f"   status={r.status_code}  ms={dt}  settled={bool(settle)}")
            if settle:
                print(f"   settlement: {settle[:160]}")
            print(f"   body: {body_preview[:280]}")
        except Exception as exc:
            results.append({
                "label": t["label"],
                "url": t["url"],
                "ok": False,
                "error": str(exc)[:300],
            })
            print(f"   FAIL: {str(exc)[:200]}")

    print("\n" + "=" * 60)
    settled = sum(1 for r in results if r.get("settled"))
    twohundred = sum(1 for r in results if str(r.get("status", "")).startswith("2"))
    print(f"settled: {settled}/{len(results)}, 2xx: {twohundred}/{len(results)}")
    print(json.dumps({"wallet": account.address, "results": results}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
