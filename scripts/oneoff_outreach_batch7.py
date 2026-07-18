#!/usr/bin/env python3
"""Peer outreach batch 7 (2026-06-20) — twit.sh cluster.

Targets identified by workflow wbcrn1x3d. Pre-filter passed only 6 verified
live-probed candidates; 5 of 6 are twit.sh endpoints (Twitter/X data API,
same operator, same payTo 0x9dBA414637c611a16BEa6f0796BFcbcBdc410df8). The
6th (Exa /search) requires SIWE Worldcoin attestation our x402 client
doesn't have — skip per the batch 5 pattern (SIWX-gated = fail).

Strategy: pitch the SAME operator three times via three different endpoints,
each with a different GA-endpoint angle. Operator's access logs surface GA
3x with 3 distinct cross-sell pitches, more memorable than one isolated hit.

Picks (cheapest first per endpoint, all confirmed 402 EVM-exact eip155:8453):
  1. /users/by/username  $0.005  -> GA /hyperliquid/score pitch
  2. /tweets/search      $0.006  -> GA /polymarket/screen pitch
  3. /tweets             $0.01   -> GA /hyperliquid/screen pitch

Total: $0.021 USDC. Wallet 0xe121e3a8...F734 floor post-send: ~$1.41.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


_ALL_TARGETS = [
    {
        "id": "twitsh_users_by_username",
        "target_url": "https://x402.twit.sh/users/by/username?username=elonmusk",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /hyperliquid/score $0.02 - given a Twitter handle, derive their wallet's HL skill_score 0-100 (PnL, sharpe, win-rate). Closes the gap between social claim and onchain proof.",
            "X-Pitch-Summary-2": "GA /onchain-x402/address $0.05 - x402 settlement history per wallet: paid-call count, USDC volume, repeat-payer flag. Validates whether a cited account has agent-economy activity.",
            "X-Pitch-Reason": "Your 482 calls/30d on user-profile lookups are buyers asking 'is this user real?' The next call they want is 'are they actually a trader?' GA's skill_score answers it.",
            "X-Reply-Via": "x402 payment to https://graphadvocate.com/hyperliquid/score = handshake",
        },
    },
    {
        "id": "twitsh_tweets_search",
        "target_url": "https://x402.twit.sh/tweets/search?words=polymarket&minLikes=10",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /polymarket/screen $0.02 - ranked top holders per condition_id with skill_score + classification + ghost_fill_risk",
            "X-Pitch-Summary-2": "GA /predmarket/spread $0.05 - cross-venue Polymarket vs Kalshi divergence, lead_venue, spread_bps - turns tweet-discovered ticker into mispricing edge",
            "X-Pitch-Reason": "Your 1,102 calls/30d on tweet-search are narrative-discovery agents. They find the chatter, then need to know WHICH market is mispriced. GA closes that loop in one call.",
            "X-Reply-Via": "x402 payment to https://graphadvocate.com/polymarket/screen = handshake",
        },
    },
    {
        "id": "twitsh_tweets_bulk",
        "target_url": "https://x402.twit.sh/tweets?ids=1234567890",
        "method": "GET",
        "body": {},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "cross_link_offer",
            "X-Pitch-Summary-1": "GA /hyperliquid/screen $0.05 - top-N HL traders per coin ranked by skill_score with avg PnL + classification. Backtest-shaped JSON.",
            "X-Pitch-Summary-2": "GA /hyperliquid/fills $0.02 - HL fills feed with whale_fill flags - timestamp-aligned to tweet IDs for news-driven flow analysis",
            "X-Pitch-Reason": "Your 1,586 calls/30d on bulk tweet lookup are backtesting + news-pipeline agents. They need timestamp-matched HL positioning data at the moments they study. GA delivers it pre-ranked.",
            "X-Reply-Via": "x402 payment to https://graphadvocate.com/hyperliquid/screen = handshake",
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
