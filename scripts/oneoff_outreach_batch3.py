#!/usr/bin/env python3
"""Peer-to-peer outreach batch 3 (2026-06-18 PM).

Targets identified by workflow w8bj52hch — scored against GA's actual paid
endpoint catalog and verified x402-priced + l30DaysTotalCalls >= 5 on CDP
Bazaar. Skipped Molty 0xmesuthere A2A ($0.11) — over single-target budget.

Budget: $0.038 USDC total across 7 sends. Wallet 0xe121e3a8…F734 floor
post-send: ~$1.45.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


_ALL_TARGETS = [
    {
        "id": "otto_crypto_news",
        "target_url": "https://x402.ottoai.services/crypto-news",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /kalshi-polymarket/spread $0.02 - per-market mid_kalshi, mid_polymarket, spread_bps, lead_venue. Closes headline->priced loop",
            "X-Pitch-Summary-2": "GA /polymarket/screen $0.02 - ranked movers: yes_price, 1h_delta, 24h_vol, headline_match_score",
            "X-Pitch-Reason": "Your 204 unique 30d payers consume crypto news upstream of positioning. GA turns 'what happened' into 'what is mispriced' - 20x markup-friendly cross-sell.",
            "X-Reply-Via": "x402 payment to either GA endpoint = handshake",
        },
    },
    {
        "id": "otto_twitter_summary",
        "target_url": "https://x402.ottoai.services/twitter-summary",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /kalshi-polymarket/spread $0.02 - cross-venue mid, spread_bps, direction, last_update_ts",
            "X-Pitch-Summary-2": "GA /kalshi/consensus-trend $0.02 - consensus_score, trend_3h/24h, divergence_flag per market",
            "X-Pitch-Reason": "Your 48 payers buy twitter summaries to front-run predmarket mispricing. GA closes loop: spread tells WHICH venue, consensus tells WHEN.",
            "X-Reply-Via": "x402 payment to https://graphadvocate.com/kalshi-polymarket/spread = handshake",
        },
    },
    {
        "id": "orbis_address_labeler",
        "target_url": "https://orbisapi.com/proxy/crypto-address-labeler-api-79be80",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /onchain-x402/address $0.01 - x402 role labels (payer/recipient/facilitator), settlement count, first/last-seen",
            "X-Pitch-Summary-2": "Surfaces ERC-8004 agent-id linkage when address is a registered Trustless Agent - unique 'x402-agent' label not in pattern DBs",
            "X-Pitch-Reason": "Your 215 calls / 20 payers are forensics buyers chasing wallet provenance. x402 settlement traffic is invisible to standard labelers - GA adds the missing dimension.",
            "X-Reply-Via": "x402 payment to https://graphadvocate.com/onchain-x402/address = handshake",
        },
    },
    {
        "id": "orbis_scam_db",
        "target_url": "https://orbisapi.com/proxy/crypto-scam-database-fraud-pattern-api-036fbd",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "referral_pair_offer",
            "X-Pitch-Summary-1": "GA /polymarket/risk $0.02 - live behavioral score: ghost-fill rate, ERC-1967 deposit-wallet detection, POLY_1271 sig type",
            "X-Pitch-Summary-2": "GA /hyperliquid/risk $0.02 - actor-level: vault-vs-EOA, liquidation-cascade exposure, funding-rate behavior",
            "X-Pitch-Reason": "Your buyers match wallet to pattern, then need to score the live actor. Orbis = pattern (static fraud DB). GA = behavior (live actor signal). Two-call chain.",
            "X-Reply-Via": "x402 payment to https://graphadvocate.com/polymarket/risk = handshake",
        },
    },
    {
        "id": "usenami_funding",
        "target_url": "https://api.usenami.io/v1/funding/current",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "referral_pair_offer",
            "X-Pitch-Summary-1": "GA /hyperliquid/risk $0.02 - derived counterparty risk per HL address: liquidation_proximity, margin_health, position_concentration",
            "X-Pitch-Summary-2": "GA /hyperliquid/score $0.02 - 0-100 trader quality (sharpe-adj PnL, win rate, hold time, vault depositor overlap)",
            "X-Pitch-Reason": "Your 6 funding payers are perps arb/MM agents - they buy your $0.025 arb-signal tier, proving willingness to pay for derived signal. GA stacks counterparty-quality.",
            "X-Reply-Via": "x402 payment to https://graphadvocate.com/hyperliquid/risk = handshake",
        },
    },
    {
        "id": "otto_kol_sentiment",
        "target_url": "https://x402.ottoai.services/kol-sentiment",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "referral_pair_offer",
            "X-Pitch-Summary-1": "GA /hyperliquid/score $0.02 - skill_score 0-100 per address from realized PnL, Sharpe, drawdown, win-rate, hold-time",
            "X-Pitch-Summary-2": "GA /hyperliquid/fills $0.02 - per-fill ts, coin, side, px, sz, closedPnl for any KOL address - mirror agents replay/validate",
            "X-Pitch-Reason": "KOL sentiment without onchain skill_score = mirror-trade risk. Your 17 distinct payers are copy-bots; cost of mirroring losing whale >> $0.02 GA call.",
            "X-Reply-Via": "x402 payment to https://graphadvocate.com/hyperliquid/score = handshake",
        },
    },
    {
        "id": "anchor_wallet_intel",
        "target_url": "https://api.anchor-x402.com/v1/intel/wallet?wallet=0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "endpoint_resale_offer",
            "X-Pitch-Summary-1": "GA /hyperliquid/score $0.02 - skill_score 0-100 from perp PnL consistency, sharpe, drawdown, win-rate, hold-time",
            "X-Pitch-Summary-2": "GA /polymarket/pnl-quick $0.01 - realized+unrealized PnL, ROI, win-rate, market-count per wallet",
            "X-Pitch-Reason": "Your wallet bundle covers sanctions+identity (is-it-safe). Missing trader-quality axis (is-it-worth-mirroring). Copy-trade buyers stack GA on top.",
            "X-Reply-Via": "x402 payment to https://graphadvocate.com/hyperliquid/score = handshake",
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
            body_preview = r.text[:280]
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
    ok_count = sum(1 for r in results if r.get("ok"))
    for r in results:
        status = "OK" if r.get("ok") else "FAIL"
        print(f"  [{status}] {r['id']}: status={r.get('status','?')} settled={r.get('settled', False)}")
        if r.get("error"):
            print(f"    error: {r['error']}")
    print(f"\n{ok_count}/{len(results)} landed clean")


if __name__ == "__main__":
    asyncio.run(main())
