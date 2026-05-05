"""Self-pay smoke test for the three /polymarket/* endpoints not yet
verified end-to-end: /pnl ($0.05), /screen ($0.02), /risk ($0.02).
Total spend ~$0.09 USDC + tiny gas on Base.

Run:
    set -a; . ~/.x402_wallets/ga_outbound.env; set +a
    python3 scripts/selfpay_polymarket_all.py
"""
from __future__ import annotations
import asyncio, json, os, sys

WALLET = "0x38e598961dd0456a7fb2e758bd433d3e59fb8a4a"  # docs-sample trader, has positions
COND = "0x95b6c59b628f15a94e42e5fdd08909cae5760a5093777eceab53e9e4900326cf"  # btc-updown market

TARGETS = [
    ("POST", "/polymarket/pnl",    {"wallet": WALLET},                      "0.05"),
    ("POST", "/polymarket/screen", {"condition_id": COND, "n": 3},          "0.02"),
    ("POST", "/polymarket/risk",   {"wallet": WALLET},                      "0.02"),
]
BASE = "https://graphadvocate.com"


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
    http = wrapHttpxWithPayment(client, timeout=120.0)

    print(f"# payer: {account.address}")
    print()

    summary = []
    for method, path, body, price in TARGETS:
        url = f"{BASE}{path}"
        print(f"=== {method} {path}  (${price}) ===")
        try:
            resp = await http.request(method, url, json=body)
            ct = resp.headers.get("content-type", "")
            settled = bool(resp.headers.get("x-payment-response", ""))
            try:
                data = resp.json()
            except Exception:
                data = resp.text[:600]
            ok = resp.status_code == 200
            # Show a tight summary of body
            if ok and isinstance(data, dict):
                # interesting first-line summary per endpoint
                if path == "/polymarket/pnl":
                    s = data.get("scores", {})
                    summary_line = (
                        f"skill={s.get('skill_score')} class={s.get('classification')} "
                        f"positions={len(data.get('positions', []))}"
                    )
                elif path == "/polymarket/screen":
                    summary_line = (
                        f"market={data.get('market_slug')} "
                        f"holders={data.get('holders_screened')} "
                        f"sharp={data.get('sharp_count')} retail={data.get('retail_count')} "
                        f"risk={data.get('ghost_fill_risk_breakdown')}"
                    )
                elif path == "/polymarket/risk":
                    summary_line = (
                        f"type={data.get('wallet_type')} "
                        f"risk={data.get('ghost_fill_risk')}"
                    )
                else:
                    summary_line = "ok"
            else:
                summary_line = f"FAIL: {data if isinstance(data, str) else json.dumps(data)[:200]}"
            print(f"  http={resp.status_code}  settled={settled}  {summary_line}")
            summary.append({
                "endpoint": path, "ok": ok, "http": resp.status_code,
                "settled": settled, "summary": summary_line,
            })
            # Print full body for failures and for the most interesting success
            if not ok:
                print(f"  full: {json.dumps(data, indent=2, default=str)[:800]}")
        except Exception as e:
            print(f"  EXCEPTION: {type(e).__name__}: {str(e)[:300]}")
            summary.append({
                "endpoint": path, "ok": False, "exception": type(e).__name__,
                "msg": str(e)[:300],
            })
        print()

    print("=== RESULTS ===")
    for r in summary:
        status = "✓" if r.get("ok") else "✗"
        print(f"  {status}  {r['endpoint']:<22}  {r.get('summary') or r.get('msg','')}")


if __name__ == "__main__":
    asyncio.run(main())
