#!/usr/bin/env python3
"""
Three Agent Exchange actions in one run:

1. REGISTER GA under multiple capability slots so we show up in
   discover-and-hire matches. Their top capabilities include
   `wallet-intel` and `prediction-markets` — both align with GA
   endpoints. Register one slot per category.

2. PAY $0.01 USDC to /a2a discover-and-hire with a query crafted
   to surface paki-curator's marketplace offer (the commons_post
   event we just saw fire on our webhook).

3. List bots in the network if there's a directory we can read.

Run: source venv/bin/activate && python3 scripts/agentexchange_register_and_discover.py
Log: /tmp/ga-agentexchange-actions-<timestamp>.jsonl
"""
import asyncio, json, pathlib, time

import httpx
from eth_account import Account
from x402 import x402Client, prefer_network
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.mechanisms.evm.exact import ExactEvmScheme
from x402.http.clients.httpx import wrapHttpxWithPayment

TS = int(time.time())
LOG = pathlib.Path(f"/tmp/ga-agentexchange-actions-{TS}.jsonl")
ENV = pathlib.Path.home() / ".x402_wallets/ga_outbound.env"

PK = None
for line in ENV.read_text().splitlines():
    line = line.strip()
    if line and "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if "KEY" in k.upper() or "PK" in k.upper():
            PK = v.strip().strip('"').strip("'")
            break
assert PK

account = Account.from_key(PK)
signer = EthAccountSigner(account)
client = x402Client()
client.register("eip155:8453", ExactEvmScheme(signer=signer))
try:
    from x402.mechanisms.evm.upto import UptoEvmClientScheme
    client.register("eip155:*", UptoEvmClientScheme(signer=signer))
except ImportError:
    pass
client.register_policy(prefer_network("eip155:8453"))
paid_http = wrapHttpxWithPayment(client, timeout=60.0)

print(f"== Agent Exchange actions ==  wallet={account.address}  log={LOG}\n")


def _log(e):
    with LOG.open("a") as f: f.write(json.dumps(e, default=str) + "\n")


# ── 1. REGISTER under multiple capability slots ──────────────────────────
# Their top 10 capabilities include wallet-intel + prediction-markets. We
# register one entry per category so discover-and-hire surfaces GA in any
# of those buckets. Price per slot reflects our actual /route or specialty
# endpoint pricing.
GA_REGISTRATIONS = [
    {
        "name": "graph-advocate",
        "endpoint": "https://graphadvocate.com",
        "capability": "on-chain-data-routing",
        "price_per_call": 0.01,
    },
    {
        "name": "graph-advocate-wallet",
        "endpoint": "https://graphadvocate.com",
        "capability": "wallet-intel",
        "price_per_call": 0.01,
    },
    {
        "name": "graph-advocate-prediction",
        "endpoint": "https://graphadvocate.com",
        "capability": "prediction-markets",
        "price_per_call": 0.05,
    },
    {
        "name": "graph-advocate-subgraph",
        "endpoint": "https://graphadvocate.com",
        "capability": "subgraph-discovery",
        "price_per_call": 0.01,
    },
    {
        "name": "graph-advocate-hyperliquid",
        "endpoint": "https://graphadvocate.com",
        "capability": "hyperliquid-data",
        "price_per_call": 0.05,
    },
]


async def register_all():
    print("[1] REGISTER GA in 5 capability slots\n")
    async with httpx.AsyncClient(timeout=15.0) as c:
        for reg in GA_REGISTRATIONS:
            try:
                r = await c.post("https://agentexchange.work/register",
                                  json=reg)
                try: body = r.json()
                except: body = r.text[:500]
                ok = 200 <= r.status_code < 300
                tag = "✓" if ok else "⚠"
                print(f"    {tag} {reg['capability']:<22} (${reg['price_per_call']:.2f})  "
                      f"status={r.status_code}  body={json.dumps(body, default=str)[:200]}")
                _log({"action": "register", "reg": reg, "status": r.status_code, "body": body})
            except Exception as e:
                print(f"    ✗ {reg['capability']}: {e}")
                _log({"action": "register", "reg": reg, "error": str(e)})


# ── 2. PAY $0.01 to discover-and-hire to surface paki-curator's offer ────
async def discover_paki_offer():
    print("\n[2] PAID discover-and-hire to surface paki-curator's offer ($0.01)\n")
    url = "https://agentexchange.work/a2a"
    payload = {
        "id": f"ga-disco-{TS}",
        "skill": "discover-and-hire",
        "input": {
            "query": "paki-curator marketplace offer",
            "budget": "0.05",
        },
    }
    try:
        r = await paid_http.post(url, json=payload,
                                  headers={"User-Agent": "graph-advocate/1.0"})
        pay_resp = r.headers.get("x-payment-response")
        try: body = r.json()
        except: body = r.text[:1500]
        print(f"    status={r.status_code}")
        if pay_resp:
            print(f"    ✓ PAID — settlement header: {pay_resp[:80]}…")
        print(f"    body: {json.dumps(body, default=str)[:1200]}")
        _log({"action": "discover_paki", "status": r.status_code,
              "x_payment_response": pay_resp, "body": body})
    except Exception as e:
        print(f"    ✗ {type(e).__name__}: {e}")
        _log({"action": "discover_paki", "error": str(e)})


# ── 3. Look up bots directory ────────────────────────────────────────────
async def list_bots():
    print("\n[3] BOT directory probes\n")
    candidates = ["/bots", "/api/bots", "/agents", "/api/agents",
                  "/directory", "/api/directory", "/network/bots",
                  "/list", "/api/list"]
    async with httpx.AsyncClient(timeout=8.0) as c:
        for path in candidates:
            try:
                r = await c.get(f"https://agentexchange.work{path}",
                                  follow_redirects=False)
                ct = r.headers.get("content-type", "")
                ok = 200 <= r.status_code < 300
                tag = "✓" if ok else " "
                preview = r.text[:80].replace("\n", " ") if ok else ""
                print(f"    {tag} {path:<24} {r.status_code}  {preview}")
                if ok:
                    _log({"action": "directory_probe", "path": path,
                          "status": r.status_code, "body": r.text[:1500]})
            except Exception as e:
                print(f"    ✗ {path}: {e}")


async def main():
    await register_all()
    await asyncio.sleep(1)
    await discover_paki_offer()
    await list_bots()
    print(f"\n== Done == log={LOG}")


if __name__ == "__main__":
    asyncio.run(main())
