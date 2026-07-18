#!/usr/bin/env python3
"""Peer outreach batch 5 (2026-06-19 — fresh verticals).

Targets from workflow wjcyi8s96 — mined CDP Bazaar for verticals we hadn't
touched: NFT, Solana, stablecoin flows, AMM/LP. Deduped from 6 to 4 unique
endpoints (2 were the same endpoint with different methods).

Budget: ~$0.02 USDC total. Wallet 0xe121e3a8...F734 floor: ~$1.42.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


_ALL_TARGETS = [
    {
        "id": "deepnets_flagged_tokens",
        "target_url": "https://api.deepnets.ai/api/flagged-tokens",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "referral_pair_offer",
            "X-Pitch-Summary-1": "GA /route $0.01 - fan Solana mint to holders+pools+lock subgraphs in one call, returns holder concentration, LP composition, token-program version",
            "X-Pitch-Summary-2": "GA /onchain-x402/address $0.05 - x402 settlement layer for any address: payer/recipient/facilitator label + counterparty graph",
            "X-Pitch-Reason": "Your DANGEROUS verdict ships without on-chain evidence. Pair each flagged row with GA /route to attach holder concentration + LP composition - buyers pay more for verdict+why than verdict alone.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake",
        },
    },
    {
        "id": "deepnets_token_safety",
        "target_url": "https://api.deepnets.ai/api/token-safety",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "endpoint_resale_offer",
            "X-Pitch-Summary-1": "GA /route $0.01 - multichain subgraph proxy with topHolderOwnership, topNetworkWalletCount, totalHolders, transfers, mint metadata",
            "X-Pitch-Summary-2": "GA /onchain-x402/address $0.05 - per-address risk signals (age, tx count, x402 cluster) enriches wallet-network concentration scoring",
            "X-Pitch-Reason": "Your safety schema is exactly what a Solana holders subgraph emits. Use /route as your cache-miss tier on long-tail mints - $0.01 per refresh beats re-indexing.",
            "X-Reply-Via": "x402 payment to GA /route = handshake",
        },
    },
    {
        "id": "slamai_trending_tokens",
        "target_url": "https://api.slamai.dev/chain/tokens/trending",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "endpoint_resale_offer",
            "X-Pitch-Summary-1": "GA /route $0.01 - multichain token->subgraph resolver, returns Graph subgraph ID + query URL for any token/chain pair",
            "X-Pitch-Summary-2": "GA api/x402/<subgraph-id> $0.01 - gateway query for active-wallet transfers, holders, deltas",
            "X-Pitch-Reason": "Your trending rank = delta active wallets per token per chain. GA /route replaces per-chain Goldsky/Allium contracts: pass contract+chain, get the right subgraph, query wallet transfers.",
            "X-Reply-Via": "x402 payment to GA /route = handshake",
        },
    },
    {
        "id": "quicknode_solana_rpc",
        "target_url": "https://x402.quicknode.com/solana-mainnet",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "referral_pair_offer",
            "X-Pitch-Summary-1": "GA /route $0.01 - decoded subgraph queries: top holders, LP balances over time, swap history, holder churn across 50+ chains incl Solana",
            "X-Pitch-Summary-2": "GA /onchain-x402/address $0.05 - x402 settlement score on Base: call_count, usdc_volume, repeat_pay_ratio, first_seen",
            "X-Pitch-Reason": "QN agents calling getAccountInfo/getProgramAccounts immediately need decoded views (top holders of mint X, LP history). GA /route is the indexed companion to your raw RPC - zero overlap, pure upsell.",
            "X-Reply-Via": "x402 payment to https://graphadvocate.com/route = handshake",
        },
    },
]


async def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    TARGETS = [t for t in _ALL_TARGETS if not only or t["id"] == only]
    if not TARGETS:
        print(f"No target with id={only!r}. Available: {[t['id'] for t in _ALL_TARGETS]}")
        sys.exit(2)
    from x402_outreach import _bootstrap

    print("Bootstrapping x402 client...")
    try:
        _client, http, wallet = _bootstrap()
    except Exception as e:
        print(f"FAIL bootstrap: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"Sender wallet: {wallet}")
    print(f"Targets: {len(TARGETS)}\n")

    results = []
    for t in TARGETS:
        print(f"=== {t['id']} -> {t['target_url']} ===")
        try:
            method = t.get("method", "GET").upper()
            req_kwargs = {
                "headers": {
                    "User-Agent": "graph-advocate/1.0 (+https://graphadvocate.com)",
                    **t["pitch_headers"],
                },
                "timeout": 60.0,
            }
            if method == "POST":
                req_kwargs["headers"]["Content-Type"] = "application/json"
                req_kwargs["json"] = t["body"]
                r = await http.post(t["target_url"], **req_kwargs)
            else:
                r = await http.get(t["target_url"], **req_kwargs)
            settled = r.headers.get("x-payment-response", "")
            body_preview = r.text[:260]
            print(f"  status:   {r.status_code}")
            if settled:
                print(f"  settled:  {settled[:80]}...")
            print(f"  body:     {body_preview}")
            results.append({
                "id": t["id"],
                "ok": 200 <= r.status_code < 300,
                "status": r.status_code,
                "settled": bool(settled),
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"id": t["id"], "ok": False, "error": str(e)})
        print()

    print("=== SUMMARY ===")
    ok = sum(1 for r in results if r.get("ok"))
    for r in results:
        s = "OK" if r.get("ok") else "FAIL"
        print(f"  [{s}] {r['id']}: status={r.get('status','?')} settled={r.get('settled', False)}")
        if r.get("error"):
            print(f"    error: {r['error']}")
    print(f"\n{ok}/{len(results)} landed clean")


if __name__ == "__main__":
    asyncio.run(main())
