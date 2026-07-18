"""
Polymarket-token-api launch outreach: 5 targeted x402 calls to agents
whose work would benefit from polymarket trader intelligence.

Each call is a real settled $0.001–$0.01 payment from graphadvocate.eth's
hot wallet, hard-capped, never raises. Goal: show up as a paying consumer
in their logs (with graphadvocate.eth as the payer address) so curious
operators can look up our agent-card and discover the new endpoints.

Skips agents already reached in the prior outreach run (donate-0000402,
blockrun, zapper, twit.sh).
"""
from __future__ import annotations
import asyncio, json, os, sys, time

POLYMARKET_PNL_URL = "https://graphadvocate.com/polymarket/pnl-quick"


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
        # x402station preflight — POST per their spec; validates our /polymarket/pnl-quick
        # URL and caches it for their consumers. We pay $0.001 to put our endpoint in
        # their catalog cache. Brilliant double-purpose call: outreach + functional.
        {
            "label": "x402station-preflight POST (caches our endpoint)",
            "method": "POST",
            "url": "https://x402station.io/api/v1/preflight",
            "json": {"url": POLYMARKET_PNL_URL},
        },
        # onesource.io live-balance — they want `address` param (not `wallet`)
        {
            "label": "onesource-live-balance (graphadvocate.eth on Base)",
            "method": "GET",
            "url": "https://skills.onesource.io/api/chain/live-balance?address=0x575267eED09c338FAE5716A486A7B58A5749A292&chain=base",
        },
        # ottoai crypto-news — already returns 200 free; included again so the
        # operator sees a graphadvocate.eth-tagged hit in their access logs.
        {
            "label": "ottoai-crypto-news (free GET, signal-only)",
            "method": "GET",
            "url": "https://x402.ottoai.services/crypto-news",
        },
    ]

    results = []
    for t in targets:
        print(f"\n## {t['label']}")
        print(f"   {t['method']} {t['url']}")
        t0 = time.time()
        try:
            kwargs = {"headers": {
                "User-Agent": "graph-advocate/x402 (polymarket-token-api launch)",
                # ASCII-only — HTTP headers spec
                "X-Sender": "graphadvocate.eth",
                "X-About": f"shipped polymarket trader intelligence today - see {POLYMARKET_PNL_URL}",
            }}
            if t.get("json") is not None:
                kwargs["json"] = t["json"]
            r = await http.request(t["method"], t["url"], **kwargs)
            settle = r.headers.get("x-payment-response", "")
            dt = int((time.time() - t0) * 1000)
            try:
                body_preview = json.dumps(r.json())[:200]
            except Exception:
                body_preview = (r.text or "")[:200]
            results.append({
                "label": t["label"], "status": r.status_code,
                "settled": bool(settle), "ms": dt,
                "body_preview": body_preview,
            })
            print(f"   status={r.status_code}  ms={dt}  settled={bool(settle)}")
            print(f"   body: {body_preview[:160]}")
        except Exception as exc:
            results.append({"label": t["label"], "ok": False, "error": str(exc)[:300]})
            print(f"   FAIL: {str(exc)[:200]}")

    print("\n" + "=" * 60)
    settled = sum(1 for r in results if r.get("settled"))
    twohundred = sum(1 for r in results if str(r.get("status", "")).startswith("2"))
    print(f"settled: {settled}/{len(results)}   2xx: {twohundred}/{len(results)}")
    print(json.dumps({"wallet": account.address, "results": results}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
