#!/usr/bin/env python3
"""One-shot outreach to 3 proven x402 payers — BlockRun, Otto HL Market, Otto Funding.

Pay-then-pitch pattern: GA calls each target's $0.001 x402 endpoint with the
pitch as JSON body + custom X-* headers identifying GA + the relevant paid
endpoint. The fact of payment lands them in our access logs; their dev sees
graphadvocate.com + pitch headers in their access logs.

Run via:
    railway run python3 scripts/oneoff_outreach_blockrun_otto.py

Reads GA_BASE_WALLET_PK from Railway env. Budget: ~$0.003 USDC total.
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


_ALL_TARGETS = [
    {
        "id": "blockrun",
        "target_url": "https://blockrun.ai/api/v1/pm/polymarket/activity?wallet=0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
        "body": {"_outreach": "pre-flight"},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "endpoint_resale_offer",
            "X-Pitch-Summary-1": "GA /polymarket/screen $0.02 - top-N holders with skill_score + classification + ghost_fill_risk",
            "X-Pitch-Summary-2": "GA /polymarket/risk $0.02 - wallet_type + ghost_fill_risk + 24h collateral_outflow",
            "X-Pitch-Reason": "You sell raw Polymarket activity at $0.001. GA sells the derived layer above. Same buyers, one tier up.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake, or A2A POST to https://graphadvocate.com/",
        },
    },
    {
        "id": "otto_hl_market",
        "target_url": "https://x402.ottoai.services/hyperliquid-market?asset=BTC",
        "body": {"_outreach": "pre-flight"},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "endpoint_resale_offer",
            "X-Pitch-Summary-1": "GA /hyperliquid/vault $0.10 - vault_quality_score + redemption_pressure + top_depositor_share",
            "X-Pitch-Summary-2": "GA /hyperliquid/score $0.02 - skill_score 0-100 + classification + liquidation_count",
            "X-Pitch-Reason": "Your 81 HL payers need trader+vault scoring downstream of your mark/funding feed. GA ships the scoring layer.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake; no A2A endpoint detected on your side",
        },
    },
    {
        "id": "otto_funding",
        "target_url": "https://x402.ottoai.services/funding-rates",
        "body": {"_outreach": "pre-flight"},
        "pitch_headers": {
            "X-From-Agent": "graphadvocate.eth",
            "X-Agent-Card": "https://graphadvocate.com/.well-known/agent-card.json",
            "X-Pitch-Intent": "endpoint_resale_offer",
            "X-Pitch-Summary-1": "GA /hyperliquid/screen $0.05 - top sharp HL traders per coin",
            "X-Pitch-Summary-2": "GA /polymarket/pnl-quick $0.01 - Polymarket sentiment cross-venue for your funding arb",
            "X-Pitch-Reason": "Your cross-venue funding/OI/liquidation aggregator gains Polymarket sentiment as orthogonal signal.",
            "X-Reply-Via": "x402 payment to GA endpoint = handshake",
        },
    },
]


async def main():
    import sys as _sys
    only = _sys.argv[1] if len(_sys.argv) > 1 else None
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
        print(f"=== {t['id']} → {t['target_url']} ===")
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
            body_preview = r.text[:400]
            print(f"  status: {r.status_code}")
            if settled:
                print(f"  settlement: {settled[:120]}")
            print(f"  body: {body_preview}")
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

    # Exit non-zero only if ALL failed (lets a partial success still report)
    if not any(r.get("ok") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
