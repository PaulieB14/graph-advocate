#!/usr/bin/env python3
"""Peer outreach batch 4 (2026-06-19).

Targets identified by workflow wirrhinxv — mined live CDP Bazaar (500 listings)
across 6 verticals. Skipped Drip ($0.10) and Surplus Intelligence ($0.052) as
both blow the $0.05 batch cap individually.

NPB win-probability oracle is the standout: 1,106 calls in 30d is the densest
payer pool we've ever pitched.

Budget: $0.036 USDC total across 6 sends. Wallet 0xe121e3a8...F734 floor
post-send: ~$1.41.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


_ALL_TARGETS = [
    {
        "id": "npb_oracle",
        "target_url": "https://oracle-api-production-766f.up.railway.app/v1/npb/games/2026-06-10/win-prob",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "referral_pair_offer",
            "X-Pitch-Summary-1": "GA /kalshi/sports-live-edge $0.05 - live Kalshi sports contracts with mispricing scores vs implied fair value, JSON ranked by edge bps",
            "X-Pitch-Summary-2": "GA /kalshi-polymarket/spread $0.05 - cross-venue spread between matched Kalshi + Polymarket markets, closes the arb loop",
            "X-Pitch-Reason": "Your 1106 calls/30d are sportsbook arb bots. After NPB win-prob, the next call is comparing model edge to live US prediction-market consensus. GA surfaces the mispricing and cross-venue spread in one hop.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake",
        },
    },
    {
        "id": "hugen_fx_tick",
        "target_url": "https://tick.hugen.tokyo/tick/latest",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /hyperliquid/score $0.02 - ranks HL traders by edge (PnL, sharpe, hit-rate, vol-adj)",
            "X-Pitch-Summary-2": "GA /hyperliquid/fills $0.02 - live perps tape mirror for spread/funding arb",
            "X-Pitch-Reason": "Your 84 unique payers on 93 calls = densest arb-bot buyer pool. FX BBO callers extend natively to crypto perps; HL trader-edge + live fills are the complementary asset class for the same institutional arb stack.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake",
        },
    },
    {
        "id": "hyre_agent",
        "target_url": "https://orbisapi.com/proxy/hyre-agent",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "endpoint_resale_offer",
            "X-Pitch-Summary-1": "GA /route $0.01 - multichain subgraph proxy: Aave v3, Morpho Blue, Pendle, Yearn v3, Compound. Returns raw APY, TVL, utilization, supply/borrow rates per market",
            "X-Pitch-Summary-2": "GA /hyperliquid/vault $0.10 - vault APR, drawdown, sharpe, depositor count, leader PnL for HL strategy ranker overlay",
            "X-Pitch-Reason": "Your 23 payers buy yield-aggregator output; they need fresh source-of-truth APYs across EVM DeFi + HL vaults. GA resells subgraph reads at $0.01 = pure margin passthrough or differentiated bundle.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake",
        },
    },
    {
        "id": "allium_explorer",
        "target_url": "https://agents.allium.so/api/v1/explorer/queries/run-async",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /onchain-x402/address $0.05 - x402 settlement history per wallet: paid calls, USDC flows, counterparty agents, repeat-payer score. Not derivable from raw EVM/Solana SQL.",
            "X-Pitch-Summary-2": "GA /polymarket/risk $0.02 - per-address prediction-market PnL, open exposure, position concentration. Enriches Allium wallet rows with derived venue risk.",
            "X-Pitch-Reason": "Allium warehouse customers asking 'what is this address doing across venues' get base-layer chain data but miss x402 agent settlement and Polymarket derived exposure. GA fills both gaps.",
            "X-Reply-Via": "x402 payment to either GA endpoint = handshake",
        },
    },
    {
        "id": "stocktrends_stim",
        "target_url": "https://api.stocktrends.com/v1/stim/latest?symbol=AAPL&exchange=Q",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /kalshi/consensus-trend $0.05 - event-market consensus drift, multi-contract weighted prob, regime tag",
            "X-Pitch-Summary-2": "GA /predmarket/spread $0.05 - cross-venue Polymarket/Kalshi spread, liquidity-weighted mid, stale-quote flag",
            "X-Pitch-Reason": "Your sub-cent payers rank equities by forward-return distribution; next decision is regime-supportive yes/no. Event-market consensus is orthogonal to price-only STIM signal and layers cheap.",
            "X-Reply-Via": "x402 payment to either GA endpoint = handshake",
        },
    },
    {
        "id": "seerium_whale_radar",
        "target_url": "https://api.seerium.xyz/v1/prediction/whale-radar/top-10-recent-moves",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /polymarket/risk $0.02 - per-wallet exposure, concentration, position-size vs bankroll, liquidation-distance for any Polymarket trader address",
            "X-Pitch-Summary-2": "GA /polymarket/pnl $0.05 ranks whales by realized + unrealized edge, win-rate, sharpe; turns your radar pings into ranked alpha",
            "X-Pitch-Reason": "Your radar emits whale wallets. Buyers next ask: how risky is this whale right now, does their track record justify copying. GA enriches the exact entity you already surface, one hop deeper.",
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
