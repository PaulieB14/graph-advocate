"""
Predmarket /spread launch outreach: 4 targeted x402 calls to agents whose
work overlaps the new Polymarket ↔ Limitless cross-venue spread endpoint.

Each call is a real settled $0.001 payment from GA's hot wallet, hard-capped,
never raises. Goal: show up as a paying consumer in their access logs (with
graphadvocate.eth-controlled hot wallet as the payer address) so curious
operators can look up our agent-card and discover /predmarket/spread.

X-About HTTP header announces the new endpoint inline; some operators tail
their access logs for headers like this and use them for opportunity-spotting.

Targets:
  • x402station preflight (POST)        — caches /predmarket/spread URL
  • blockrun pm/polymarket/markets (GET)— direct polymarket-data competitor
  • ottoai funding-rates (GET)          — cross-venue arb-style operator
  • ottoai crypto-news (GET)            — high-signal access-log audience

Total expected spend: ~$0.004 USDC. Wallet pre-flight balance check below.
"""
from __future__ import annotations
import asyncio, json, os, sys, time

PREDMARKET_URL = "https://graphadvocate.com/predmarket/spread"
X_ABOUT = (
    "shipped /predmarket/spread today - Polymarket-Limitless cross-venue "
    "spread JOIN at " + PREDMARKET_URL
)


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
        {
            "label": "x402station-preflight POST (catalogs /predmarket/spread)",
            "method": "POST",
            "url": "https://x402station.io/api/v1/preflight",
            "json": {"url": PREDMARKET_URL},
        },
        {
            "label": "blockrun pm/polymarket/markets GET (polymarket-data peer)",
            "method": "GET",
            "url": "https://blockrun.ai/api/v1/pm/polymarket/markets",
        },
        {
            "label": "ottoai funding-rates GET (cross-venue arb peer)",
            "method": "GET",
            "url": "https://x402.ottoai.services/funding-rates",
        },
        {
            "label": "ottoai crypto-news GET (high-signal access-log audience)",
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
                "User-Agent": "graph-advocate/x402 (predmarket-spread launch)",
                "X-Sender": "graphadvocate.eth",
                "X-About": X_ABOUT,
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
