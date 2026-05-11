"""Self-pay every paid GA endpoint once to refresh CDP Bazaar listings.

Why: as of 2026-05-10 only /route is on CDP Bazaar (last updated 2026-05-04
with the OLD pricing description). All 9 trader-intel endpoints
(/polymarket/*, /hyperliquid/*) shipped May 7-8 but were never paid by
external clients, so CDP's discovery never crawled+indexed them.

Each successful x402 payment forces CDP to re-index the resource with the
current 402 challenge metadata (extensions.bazaar block + description).

Cost: $0.35 USDC total + tiny gas on Base.

Run:
    set -a; . ~/.x402_wallets/ga_outbound.env; set +a
    python3 scripts/selfpay_refresh_bazaar_all.py
"""
from __future__ import annotations
import asyncio, json, os, sys, time

# Docs-sample / well-known data so the underlying compute returns sensible JSON.
WALLET_PM   = "0x38e598961dd0456a7fb2e758bd433d3e59fb8a4a"  # Polymarket trader
WALLET_HL   = "0xac5a07c46b6987f8db7b8b69f0e9ab9683e07734"  # Hyperliquid trader
COND_PM     = "0x95b6c59b628f15a94e42e5fdd08909cae5760a5093777eceab53e9e4900326cf"
VAULT_HL    = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
COIN_HL     = "BTC"

BASE = "https://graphadvocate.com"
TARGETS = [
    # method, path, body, advertised_price_usd, purpose
    ("POST", "/route",              {"question": "Top 20 USDC holders on Ethereum"},          "0.01", "refresh /route w/ new pricing desc"),
    ("POST", "/polymarket/pnl-quick", {"wallet": WALLET_PM},                                  "0.01", "register /polymarket/pnl-quick"),
    ("POST", "/polymarket/pnl",     {"wallet": WALLET_PM},                                    "0.05", "register /polymarket/pnl"),
    ("POST", "/polymarket/screen",  {"condition_id": COND_PM, "n": 3},                        "0.02", "register /polymarket/screen"),
    ("POST", "/polymarket/risk",    {"wallet": WALLET_PM},                                    "0.02", "register /polymarket/risk"),
    ("POST", "/hyperliquid/score",  {"user": WALLET_HL},                                      "0.02", "register /hyperliquid/score"),
    ("POST", "/hyperliquid/pnl",    {"user": WALLET_HL},                                      "0.05", "register /hyperliquid/pnl"),
    ("POST", "/hyperliquid/screen", {"coin": COIN_HL, "n": 5},                                "0.05", "register /hyperliquid/screen"),
    ("POST", "/hyperliquid/vault",  {"vault": VAULT_HL},                                      "0.10", "register /hyperliquid/vault"),
    ("POST", "/hyperliquid/risk",   {"user": WALLET_HL},                                      "0.02", "register /hyperliquid/risk"),
]


async def main():
    pk = os.environ.get("GA_BASE_WALLET_PK", "").strip()
    if not pk:
        print(json.dumps({"ok": False, "error": "GA_BASE_WALLET_PK not set"}))
        sys.exit(1)
    if not pk.startswith("0x"):
        pk = "0x" + pk

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
    http = wrapHttpxWithPayment(client, timeout=120.0)

    print(f"# payer: {account.address}")
    expected_total = sum(float(t[3]) for t in TARGETS)
    print(f"# total expected spend: ${expected_total:.2f}")
    print()

    summary = []
    for method, path, body, price, purpose in TARGETS:
        url = f"{BASE}{path}"
        print(f"=== {method} {path}  (${price})  — {purpose} ===")
        t0 = time.time()
        try:
            resp = await http.request(method, url, json=body)
            settled = bool(resp.headers.get("x-payment-response"))
            try:
                snippet = json.dumps(resp.json())[:200]
            except Exception:
                snippet = resp.text[:200]
            elapsed = time.time() - t0
            print(f"  HTTP {resp.status_code}  settled={settled}  latency={elapsed:.2f}s")
            print(f"  body: {snippet}")
            summary.append({
                "path": path, "status": resp.status_code, "settled": settled,
                "price_usd": price, "ok": resp.status_code == 200 and settled,
            })
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {str(e)[:200]}")
            summary.append({"path": path, "ok": False, "error": str(e)[:200]})
        print()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    ok = sum(1 for s in summary if s.get("ok"))
    print(f"  {ok}/{len(summary)} succeeded with settlement")
    actual_spent = sum(float(s["price_usd"]) for s in summary if s.get("ok") and "price_usd" in s)
    print(f"  total spent on settled calls: ${actual_spent:.2f}")
    print()
    print(f"  failures:")
    for s in summary:
        if not s.get("ok"):
            err = s.get("error")
            if not err:
                status = s.get("status")
                settled = s.get("settled")
                err = f"status={status} settled={settled}"
            print(f"    - {s['path']}: {err}")


if __name__ == "__main__":
    asyncio.run(main())
