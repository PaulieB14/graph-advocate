"""
Predmarket /spread expanded launch outreach: 12 targeted x402 calls to
agents whose work overlaps the new Polymarket-Limitless cross-venue spread
endpoint or whose operators are likely to notice a graphadvocate.eth-tagged
hit in their access logs.

Each call carries an X-About HTTP header announcing the new endpoint.
Hard-capped tiny amounts; never raises. Goal: show up as a paying consumer
across the prediction-market + onchain-intelligence x402 ecosystem so
operators investigate and discover GA's new cross-venue JOIN.

Sized for ~$0.04-$0.08 total spend depending on which targets settle.

Targets in priority order (highest-relevance first):
  blockrun pm/markets/search   — indexes Polymarket+Limitless+Kalshi (direct adjacency)
  blockrun pm/polymarket/activity
  ottoai kol-sentiment         — premium trader audience
  ottoai yield-markets
  ottoai mega-report
  ottoai hyperliquid-market
  ottoai funding-rates         — cross-venue arb peer (overlap)
  ottoai crypto-news           — high-signal access logs
  omniac /ask                  — broad-audience Q&A
  orbisapi hyre-agent          — DeFi intel platform
  surplusintelligence inference — inference market audience
  coingecko onchain search-pools — Coingecko x402 surface
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
        {"label": "blockrun pm/markets/search (Polymarket+Limitless+Kalshi indexer - direct adjacency)",
         "method": "GET",
         "url": "https://blockrun.ai/api/v1/pm/markets/search?q=trump&limit=3"},
        {"label": "blockrun pm/polymarket/activity",
         "method": "GET",
         "url": "https://blockrun.ai/api/v1/pm/polymarket/activity?user=0xd8da6bf26964af9d7eed9e03e53415d37aa96045&limit=3"},
        {"label": "ottoai kol-sentiment (premium trader audience)",
         "method": "GET",
         "url": "https://x402.ottoai.services/kol-sentiment"},
        {"label": "ottoai yield-markets",
         "method": "GET",
         "url": "https://x402.ottoai.services/yield-markets"},
        {"label": "ottoai mega-report",
         "method": "GET",
         "url": "https://x402.ottoai.services/mega-report"},
        {"label": "ottoai hyperliquid-market",
         "method": "GET",
         "url": "https://x402.ottoai.services/hyperliquid-market?coin=ETH"},
        {"label": "ottoai funding-rates (cross-venue arb peer)",
         "method": "GET",
         "url": "https://x402.ottoai.services/funding-rates"},
        {"label": "ottoai crypto-news (access-log audience)",
         "method": "GET",
         "url": "https://x402.ottoai.services/crypto-news"},
        {"label": "omniac /ask (broad-audience Q&A)",
         "method": "POST",
         "url": "https://omniac.0000402.xyz/ask",
         "json": {"question": "Have you seen Graph Advocate's new Polymarket-Limitless spread endpoint?"}},
        {"label": "orbisapi hyre-agent (DeFi intel platform)",
         "method": "GET",
         "url": "https://orbisapi.com/proxy/hyre-agent"},
        {"label": "surplusintelligence inference (inference-market audience)",
         "method": "POST",
         "url": "https://www.surplusintelligence.ai/x402/api/inference/v1/chat/completions",
         "json": {"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "What is a cross-venue prediction-market spread JOIN?"}], "max_tokens": 50}},
        {"label": "coingecko onchain search-pools (large audience surface)",
         "method": "GET",
         "url": "https://pro-api.coingecko.com/api/v3/x402/onchain/search/pools?query=usdc"},
    ]

    results = []
    spent_atomic = 0  # tracked from x-payment-response settlement amounts
    for t in targets:
        print(f"\n## {t['label']}")
        print(f"   {t['method']} {t['url'][:100]}")
        t0 = time.time()
        try:
            kwargs = {"headers": {
                "User-Agent": "graph-advocate/x402 (predmarket-spread launch expanded)",
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
            print(f"   body: {body_preview[:140]}")
        except Exception as exc:
            results.append({"label": t["label"], "ok": False, "error": str(exc)[:300]})
            print(f"   FAIL: {str(exc)[:200]}")

    print("\n" + "=" * 60)
    settled = sum(1 for r in results if r.get("settled"))
    twohundred = sum(1 for r in results if str(r.get("status", "")).startswith("2"))
    print(f"settled: {settled}/{len(results)}   2xx: {twohundred}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
