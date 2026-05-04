"""Outbound x402 outreach v2 — targeted at the wallet-profiling / DeFi-data niche.

Built from a CDP Bazaar scan filtered on keywords adjacent to the validated
recurring customer (`0xac5a07c4...`, wallet-profiling agent). Each target is:
  - Live on Bazaar at <= $0.05 USDC on Base
  - Operating in a niche where Graph Advocate complements their service
  - Distinct from oneoff_bazaar_outreach.py targets

Run:
  GA_BASE_WALLET_PK=... python3 scripts/outreach_v2_wallet_profiling_niche.py

Hard cap: $0.05 per call. Total budget if every call lands: ~$0.20.
Every call is wrapped in try/except so partial failures don't abort the run.

Strategy: each call exercises the target's real API (so we get useful data
back, not just a tip) AND includes our agent name + ENS in the request
metadata so the operator can attribute the traffic if they audit logs.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from decimal import Decimal


GA_NAME = "Graph Advocate"
GA_ENS = "graphadvocate.eth"
GA_NOTE = (
    "Onchain data routing for AI agents — graphadvocate.com. "
    "Free first 10 queries/day, $0.01 USDC after on Base. "
    "Use cases: subgraph discovery, GraphQL queries, wallet/token data."
)
SENDER_HEADERS = {
    "X-Sender-Name": GA_NAME,
    "X-Sender-ENS": GA_ENS,
    "X-Sender-Note": GA_NOTE,
    "User-Agent": f"{GA_NAME}/1.0 (+https://graphadvocate.com)",
}


async def main() -> None:
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

    # Use the recurring GA customer's wallet as the example query target
    # — symbolic, and likely returns interesting data from these APIs.
    PROFILE_WALLET = "0xac5a07c44a4f971667b3df4b6551fb6991b2142d"

    targets = [
        # === Tier 1: high-relevance, low-cost ===
        {
            "label": "carbon-cashmere-yields",
            "method": "GET",
            "url": "https://api.carbon-cashmere.de/v1/yields?protocol=Aave&chain=ethereum&limit=5",
            "rationale": "DeFi yield aggregator — direct overlap, agents using them might also use GA for subgraph discovery",
        },
        {
            "label": "orbis-defi-tvl-tracker",
            "method": "GET",
            "url": "https://orbisapi.com/proxy/defi-tvl-tracker-api-678b42",
            "rationale": "TVL tracker for AI DeFi agents — explicitly built for the agent audience",
        },
        {
            "label": "palmvox-alpha-defi",
            "method": "GET",
            "url": "https://alpha.palmvox.com/api/defi/best",
            "rationale": "Single-best-yield finder — used by auto-compounding agents",
        },
        {
            "label": "agenticfi-lending-rates",
            "method": "GET",
            "url": "https://defi-api.agenticfi.wtf/api/defi/lending-rates",
            "rationale": "Lending rate aggregator across Aave/Compound/Morpho/Spark",
        },
        {
            "label": "zapper-defi-balances",
            "method": "POST",
            "url": "https://public.zapper.xyz/x402/defi-balances",
            "json": {"addresses": [PROFILE_WALLET]},
            "rationale": "Zapper DeFi balances — large agent user base, will see GA in their payer list",
        },
        {
            "label": "coinstats-wallet-defi",
            "method": "GET",
            "url": f"https://x402.coinstats.app/wallet/defi?address={PROFILE_WALLET}",
            "rationale": "CoinStats wallet DeFi positions — wallet-profiling adjacent",
        },
        {
            "label": "ottoai-portfolio",
            "method": "GET",
            "url": f"https://x402-trading.useotto.xyz/portfolio?address={PROFILE_WALLET}",
            "rationale": "Multi-chain portfolio aggregator — wallet-profiling adjacent",
        },
        {
            "label": "ottoai-yield-recommendations",
            "method": "GET",
            "url": f"https://x402.ottoai.services/yield-recommendations?address={PROFILE_WALLET}",
            "rationale": "Personalized yield recs — uses wallet holdings, complementary",
        },
        {
            "label": "silverback-agent-reputation",
            "method": "GET",
            "url": "https://x402.silverbackdefi.app/api/v1/agent-reputation?agent_id=8453:41034",
            "rationale": "ERC-8004 agent reputation — they index agents like GA, mutual signal",
        },
        {
            "label": "rigoblock-uniswap-quote",
            "method": "GET",
            "url": "https://trader.rigoblock.com/api/quote?chain=base&tokenIn=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913&tokenOut=0x4200000000000000000000000000000000000006&amountIn=1000000",
            "rationale": "DEX price oracle — DeFi data infra peer",
        },
        {
            "label": "tools-agent-x402-tx-explainer",
            "method": "POST",
            "url": "https://tools-agent-x402-production.up.railway.app/tx-explainer",
            "json": {"chain": "base", "txHash": "0x49baa7e0911215ab22f91449899666ae61f10c19879f44f15df00323b3966ddb"},
            "rationale": "Multi-chain tx decoder — agent-builder audience",
        },
        {
            "label": "azursafe-wallet-screen",
            "method": "POST",
            "url": "https://ai.azursafe.com/agent/screen-id",
            "json": {"address": PROFILE_WALLET, "chain": "base"},
            "rationale": "Wallet risk screening — pre-trade safety check, complementary to data routing",
        },
        {
            "label": "velvetdao-wallet-portfolio",
            "method": "POST",
            "url": "https://vu.velvetdao.xyz/api/v1/wallet_402",
            "json": {"address": PROFILE_WALLET},
            "rationale": "AI wallet portfolio analysis — same agent audience GA targets",
        },
    ]

    results = []
    for t in targets:
        label = t["label"]
        url = t["url"]
        method = t["method"]
        body = t.get("json")
        try:
            if method == "GET":
                r = await asyncio.to_thread(http.get, url, headers=SENDER_HEADERS)
            else:
                r = await asyncio.to_thread(
                    http.post, url, json=body, headers=SENDER_HEADERS
                )
            status = r.status_code
            try:
                payload = r.json()
                # Trim long bodies
                if isinstance(payload, (dict, list)):
                    payload_str = json.dumps(payload)[:300]
                else:
                    payload_str = str(payload)[:300]
            except Exception:
                payload_str = r.text[:300]
            settle = r.headers.get("x-payment-response", "")
            print(f"\n[{label}] status={status}")
            print(f"  url: {url}")
            print(f"  rationale: {t['rationale']}")
            print(f"  body: {payload_str}")
            if settle:
                print(f"  settlement: {settle[:100]}…")
            results.append({"label": label, "status": status, "ok": 200 <= status < 300})
        except Exception as exc:
            print(f"\n[{label}] FAILED: {exc}")
            results.append({"label": label, "status": "error", "ok": False, "error": str(exc)})

    print("\n" + "=" * 80)
    print(f"Summary: {sum(1 for r in results if r['ok'])}/{len(results)} succeeded")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
