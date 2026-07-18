#!/usr/bin/env python3
"""Peer-to-peer outreach batch 2 (2026-06-18).

Tuesday's batch (BlockRun + Otto Market + Otto Funding) confirmed the
pay-then-pitch pattern lands — BlockRun returned a settlement tx hash,
both Otto endpoints settled cleanly. Today's batch extends to adjacent
verticals from yesterday's scout (workflow ws1s6e0ft):

  1. OneSource     — chain RPC primitives (1,500+ unique 30d payers)
                     natural referral pair: their raw RPC → GA's derived
  2. Otto Yield    — completes the Otto family (3rd of 3 endpoints)
                     adds Aave V3 + Morpho APYs on Base / Polygon
  3. Anchor Price  — token pricing (39 unique payers, $0.001)
                     cross-link: their price + GA's pool-depth context
  4. Anchor Screen — wallet screening (16 unique payers, $0.001)
                     cross-link: their compliance + GA's behavior signal
  5. CoinGecko     — DEX pool search ($0.01, 19 payers)
                     cross-link: their pool metadata + GA's signals

Same pay-then-pitch pattern: pay each target's $0.001-$0.01 x402 endpoint
and embed pitch headers (X-From-Agent, X-Pitch-*) that land in their
access logs as a paying customer signal + GA endpoint summaries.

Wallet: 0xe121e3a8...F734 (currently ~$1.50 USDC, refilled 2026-06-18).
Budget cap: $0.05 for the whole batch (5x$0.001 + 1x$0.01).

Run via:
    railway run --service graph-advocate python3 scripts/oneoff_outreach_batch2.py [target_id]
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


_ALL_TARGETS = [
    {
        "id": "onesource_contract",
        "target_url": "https://api.onesource.io/api/chain/contract?address=0x6E007731870EDe419CfB31889Cd5C4493CEcb04c&chainId=8453",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "referral_pair_offer",
            "X-Pitch-Summary-1": "GA /route $0.01 - subgraph routing across 15500+ subgraphs",
            "X-Pitch-Summary-2": "GA /polymarket/risk $0.02 + /hyperliquid/score $0.02 - wallet-type detection + trader profiling",
            "X-Pitch-Reason": "You sell raw RPC primitives (contract / nonce / tx receipt). GA sells one layer up - subgraph routing + derived wallet signals. Natural referral chain: contract read -> profile that wallet.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake",
        },
    },
    {
        "id": "otto_yield",
        "target_url": "https://x402.ottoai.services/yield-markets",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "endpoint_resale_offer",
            "X-Pitch-Summary-1": "GA /route $0.01 - canonical Aave V3 / Morpho subgraph IDs with reliability scores",
            "X-Pitch-Summary-2": "GA hyperliquid + polymarket trader scoring complements your yield feed",
            "X-Pitch-Reason": "Your yield-markets feed surfaces APYs - GA surfaces position-level signals (liquidation distance, health-factor distribution) one layer above. Completes the Otto family pitch (HL Market + Funding pinged 2026-06-17).",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake",
        },
    },
    {
        "id": "anchor_price",
        "target_url": "https://api.anchor-x402.com/v1/price/token?symbol=ETH",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /route $0.01 - token-api routing for pool depth, holder concentration, whale flows",
            "X-Pitch-Summary-2": "Per-contract enriched context (top holders, recent flows, DEX depth) one tier above price",
            "X-Pitch-Reason": "Your token-symbol -> price API is upstream of any pre-trade decision. GA fills the next call - depth + concentration signal for that contract.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake",
        },
    },
    {
        "id": "anchor_screen",
        "target_url": "https://api.anchor-x402.com/v1/screen?wallet=0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /polymarket/risk $0.02 - wallet_type + ghost_fill_risk + 24h outflow",
            "X-Pitch-Summary-2": "GA /hyperliquid/score $0.02 - trader skill_score 0-100 + classification",
            "X-Pitch-Reason": "Your screen does compliance/AML. GA profiles wallet behavior for trading. Compliance + alpha in two hops - direct upsell for your payer cohort.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake",
        },
    },
    {
        "id": "coingecko_pools",
        "target_url": "https://pro-api.coingecko.com/api/v3/x402/onchain/search/pools?query=WETH",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /route $0.01 - canonical pool subgraph IDs for any chain with reliability data",
            "X-Pitch-Summary-2": "Per-pool derived signals (TVL trajectory, LP concentration, swap-flow toxicity)",
            "X-Pitch-Reason": "Your pool search returns metadata. GA can return pool-level derived signals via Token API endpoints. Same payer cohort, one tier up.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake",
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
            body_preview = r.text[:300]
            print(f"  status:   {r.status_code}")
            if settled:
                print(f"  settled:  {settled[:80]}...")
            print(f"  body:     {body_preview}")
            results.append({
                "id": t["id"],
                "ok": 200 <= r.status_code < 300,
                "status": r.status_code,
                "settled": bool(settled),
                "settlement": settled[:200] if settled else None,
                "body_preview": body_preview,
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"id": t["id"], "ok": False, "error": str(e)})
        print()

    print("=== SUMMARY ===")
    for r in results:
        status = "OK" if r.get("ok") else "FAIL"
        print(f"  [{status}] {r['id']}: status={r.get('status','?')} settled={r.get('settled', False)}")
        if r.get("error"):
            print(f"    error: {r['error']}")

    if not any(r.get("ok") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
