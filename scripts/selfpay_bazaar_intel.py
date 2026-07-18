"""
Self-pay test: GA's outbound hot wallet pays the bazaar-intelligence
service's /listings endpoint twice on Base mainnet. Two calls in case
one races with cold-cache or partial bazaar indexing.

This is the very first paid call that flips bazaar-intel from
"deployed paid endpoint" to "actually-earning service". Triggers CDP
Bazaar indexing per their docs ("first successful settlement is when
CDP catalogs it").
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
    http = wrapHttpxWithPayment(client, timeout=90.0)
    print(f"# wallet: {account.address}")

    base = "https://x402-bazaar-intelligence-production.up.railway.app"
    targets = [
        {"label": "listings #1 (sort=revenue_7d)", "url": f"{base}/listings?sort=revenue_7d&limit=3"},
        {"label": "listings #2 (sort=recency)",   "url": f"{base}/listings?sort=recency&limit=3"},
    ]

    results = []
    for t in targets:
        print(f"\n## {t['label']} → {t['url']}")
        t0 = time.time()
        try:
            r = await http.get(t["url"], headers={"User-Agent": "Mozilla/5.0 (compatible; graph-advocate/x402)"})
            settle = r.headers.get("x-payment-response", "")
            dt = int((time.time() - t0) * 1000)
            try:
                body = r.json()
                count = body.get("count")
                first_host = (body.get("listings") or [{}])[0].get("host")
                last_refresh = body.get("last_refresh_at")
                body_summary = f"count={count} first={first_host} refresh_at={last_refresh}"
            except Exception:
                body_summary = (r.text or "")[:200]

            results.append({
                "label": t["label"],
                "status": r.status_code,
                "settled": bool(settle),
                "settlement": settle[:160] if settle else None,
                "ms": dt,
                "body": body_summary,
            })
            print(f"   status={r.status_code}  ms={dt}  settled={bool(settle)}")
            if settle:
                print(f"   settlement: {settle[:160]}")
            print(f"   body: {body_summary}")
        except Exception as exc:
            results.append({"label": t["label"], "ok": False, "error": str(exc)[:300]})
            print(f"   FAIL: {str(exc)[:200]}")

    print("\n" + "=" * 60)
    settled = sum(1 for r in results if r.get("settled"))
    twohundred = sum(1 for r in results if str(r.get("status", "")).startswith("2"))
    print(f"settled: {settled}/{len(results)}, 2xx: {twohundred}/{len(results)}")
    print(json.dumps({"wallet": account.address, "results": results}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
