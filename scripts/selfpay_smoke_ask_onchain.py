"""
Self-pay smoke test: GA's outbound hot wallet pays graphadvocate.com's two
newest paid endpoints (/onchain-x402/address $0.01, /ask $0.05) and asserts
the response shapes look right.

Purpose:
- Re-runnable regression check after every deploy that touches a2a_server.py.
- Catches the two failure modes that bit us 2026-06-04/05:
    * RouteConfig description >500 chars → CDP facilitator 400 → handler 500.
    * Gateway routed to lagging Graph Network indexer → handler RuntimeError.
- Confirms the wallet is debited end-to-end (settle path, not just signing).

Run:
    set -a; . ~/.x402_wallets/ga_outbound.env; set +a
    python3 scripts/selfpay_smoke_ask_onchain.py             # /onchain only ($0.01)
    python3 scripts/selfpay_smoke_ask_onchain.py --with-ask  # both ($0.06)

Reads GA_BASE_WALLET_PK from env. Costs $0.01 USDC + tiny gas (or $0.06 with
--with-ask). Failure modes (5xx) skip settlement per x402 SDK behavior, so a
regression catches the bug without burning more money than necessary.

Exit code is 0 when all selected tests pass, 1 otherwise — wires into a
GH Action / cron without further glue.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time

TARGET_ONCHAIN = "https://graphadvocate.com/onchain-x402/address"
TARGET_ASK = "https://graphadvocate.com/ask"

# GA's first recurring x402 payer — known to have populated as_payer summary
# with at least ~500 payments. Stable address: don't change without verifying
# the new pick still returns non-null data.
REAL_ADDR = "0xac5a07c44a4f971667b3df4b6551fb6991b2142d"


def _summarize(label: str, status: int, ms: float, body, expected_ok_shape) -> dict:
    ok = status == 200 and expected_ok_shape(body)
    return {
        "label": label,
        "ok": ok,
        "http_status": status,
        "ms": round(ms, 1),
        "body_preview": (json.dumps(body)[:400]
                         if isinstance(body, (dict, list)) else str(body)[:400]),
    }


async def main() -> int:
    pk = os.environ.get("GA_BASE_WALLET_PK", "").strip()
    if not pk:
        print(json.dumps({"ok": False, "error": "GA_BASE_WALLET_PK not set"}))
        return 1

    with_ask = "--with-ask" in sys.argv

    from eth_account import Account
    from x402 import x402Client, prefer_network
    from x402.mechanisms.evm.signers import EthAccountSigner
    from x402.mechanisms.evm.exact import ExactEvmScheme
    from x402.http.clients.httpx import wrapHttpxWithPayment

    account = Account.from_key(pk)
    client = x402Client()
    client.register("eip155:8453", ExactEvmScheme(signer=EthAccountSigner(account)))
    client.register_policy(prefer_network("eip155:8453"))
    http = wrapHttpxWithPayment(client, timeout=90.0)

    print(f"# payer wallet:  {account.address}")
    print(f"# tests:         onchain{' + ask' if with_ask else ''}")
    print()

    results = []

    # --- Regression: /onchain with real address ---
    t0 = time.time()
    r = await http.post(TARGET_ONCHAIN, json={"address": REAL_ADDR})
    try:
        body = r.json()
    except Exception:
        body = r.text[:600]
    results.append(_summarize(
        "onchain-real-addr", r.status_code, (time.time() - t0) * 1000, body,
        # Real address means as_payer must be populated (it's a known payer).
        lambda b: (isinstance(b, dict)
                   and b.get("address") == REAL_ADDR
                   and isinstance(b.get("as_payer"), dict)
                   and int(b["as_payer"].get("totalPayments", 0)) > 0
                   and b.get("indexed_through_block") is not None),
    ))

    # --- /ask (optional, $0.05) ---
    if with_ask:
        t0 = time.time()
        r = await http.post(TARGET_ASK, json={
            "question": "How many x402 settlements were there on Base on 2026-05-15?",
        })
        try:
            body = r.json()
        except Exception:
            body = r.text[:600]
        results.append(_summarize(
            "ask-daily-stats", r.status_code, (time.time() - t0) * 1000, body,
            lambda b: (isinstance(b, dict)
                       and isinstance(b.get("answer"), str)
                       and len(b["answer"]) > 0
                       and isinstance(b.get("sql_trace"), list)
                       and len(b["sql_trace"]) > 0),
        ))

    all_ok = all(r["ok"] for r in results)
    print(json.dumps({"ok": all_ok, "tests": results}, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
