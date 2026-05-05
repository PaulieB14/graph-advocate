"""
Self-pay test: GA's outbound hot wallet pays graphadvocate.com/polymarket/pnl-quick once.

Purpose:
- Verify end-to-end that the new /polymarket/pnl-quick endpoint settles correctly,
  Pinax responds with the user's trade history, and the lot reconstruction +
  scoring produce a sensible JSON response.
- Trigger CDP Bazaar to index the new endpoint (first successful settlement at a
  URL fast-tracks discovery).

Run:
    set -a; . ~/.x402_wallets/ga_outbound.env; set +a
    python3 scripts/selfpay_polymarket_pnl.py

Reads GA_BASE_WALLET_PK from env. Costs $0.01 USDC on Base + tiny gas.
Pays once against a known Polymarket trader from the Pinax docs sample.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys

TARGET_URL = "https://graphadvocate.com/polymarket/pnl-quick"
# Docs-sample Polymarket trader — confirmed has trade activity per the docs page.
TARGET_WALLET = "0x38e598961dd0456a7fb2e758bd433d3e59fb8a4a"


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
    print(f"# payer wallet:  {account.address}")
    print(f"# target:        {TARGET_URL}")
    print(f"# pnl-of:        {TARGET_WALLET}")
    print()

    try:
        resp = await http.request(
            "POST",
            TARGET_URL,
            json={"wallet": TARGET_WALLET},
        )
        settle = resp.headers.get("x-payment-response", "")
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:600]

        # Verify the response shape matches what compute_scores produces.
        # Field names track polymarket_intel.compute_scores().
        expected_fields = {
            "wallet", "skill_score", "classification", "sharpe_like",
            "win_rate", "sample_size_markets", "sample_size_trades",
            "confidence", "worst_position_pnl_usdc",
            "realized_pnl_usdc", "unrealized_pnl_usdc", "total_pnl_usdc",
            "open_positions_count", "generated_at",
        }
        missing = (
            sorted(expected_fields - set(body.keys()))
            if isinstance(body, dict) else list(expected_fields)
        )

        print(json.dumps({
            "ok": resp.status_code == 200 and not missing,
            "http_status": resp.status_code,
            "settled": bool(settle),
            "x-payment-response_present": bool(settle),
            "missing_fields": missing,
            "body": body,
        }, indent=2, default=str))
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "error_type": type(e).__name__,
            "error": str(e)[:600],
        }, indent=2))
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
