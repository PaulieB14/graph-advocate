#!/usr/bin/env python3
"""CLI for agent_score.score_agent — batch score known wallets.

Calibration set:
  - 0x9dba414637c611a16bea6f0796bfcbcbdc410df8  twit.sh (active, recent payTo)
  - 0x6e007731870ede419cfb31889cd5c4493cecb04c  BlockRun (active outreach target)
  - 0xe69f9cc5e073b4a41d9e888a91159d0706161f18  wallet-behavior-score (ERC-8004 #55656, peer)
  - 0x575267eed09c338fae5716a486a7b58a5749a292  graphadvocate identity (self, ERC-8004 #734)
  - 0x0000000000000000000000000000000000000000  null address (control, should score 0)

Usage:
  python3 scripts/score_agent.py                      # run the calibration set
  python3 scripts/score_agent.py 0xWALLET             # score a specific wallet
  python3 scripts/score_agent.py --days 7 0xWALLET    # custom window
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

CALIBRATION_SET = [
    ("twit.sh",                          "0x9dba414637c611a16bea6f0796bfcbcbdc410df8"),
    ("BlockRun",                         "0x6e007731870ede419cfb31889cd5c4493cecb04c"),
    ("wallet-behavior-score (peer)",     "0xe69f9cc5e073b4a41d9e888a91159d0706161f18"),
    ("graphadvocate identity (self)",    "0x575267eed09c338fae5716a486a7b58a5749a292"),
    ("null address (control)",           "0x0000000000000000000000000000000000000000"),
]


def _fmt_score_card(label: str, result: dict) -> str:
    s = result["score"]
    bar = "█" * (s // 5) + "░" * (20 - s // 5)
    out = [f"\n=== {label} ({result['wallet']}) ==="]
    out.append(f"  Score:   {s:>3}/{result['max_score']} [{bar}]  tier: {result['tier']}")
    out.append(f"  Verdict: {result['verdict']}")
    awarded = result.get("awarded_points") or {}
    if awarded:
        out.append(f"  Points awarded:")
        for sig, pts in awarded.items():
            out.append(f"    +{pts:<3} {sig}")
    sig = result.get("signals") or {}
    if sig.get("usdc_received_30d_usdc", 0) > 0:
        out.append(f"  Senders sample: {', '.join((sig.get('sample_recent_payers') or [])[:3]) or 'n/a'}")
    if sig.get("erc8004_agent_count_for_owner", 0) > 1:
        out.append(f"  Owner runs {sig['erc8004_agent_count_for_owner']} registered agents (rep aggregated)")
    if sig.get("feedback_count", 0) > 0:
        out.append(
            f"  Reputation: {sig['feedback_count']} feedback / {sig['distinct_feedback_clients']} clients"
            + (f" / avg {sig['avg_feedback_value']}" if sig.get('avg_feedback_value') is not None else "")
        )
    return "\n".join(out)


async def main():
    import agent_score  # noqa: E402  (sys.path tweak above)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    days = 30
    for a in sys.argv[1:]:
        if a.startswith("--days="):
            days = int(a.split("=")[1])

    if args:
        targets = [(f"wallet {i+1}", a.lower()) for i, a in enumerate(args)]
    else:
        targets = CALIBRATION_SET

    print(f"Scoring {len(targets)} wallets ({days}d window)...")
    for label, wallet in targets:
        try:
            r = await agent_score.score_agent(wallet, days=days)
            print(_fmt_score_card(label, r))
        except Exception as e:
            print(f"\n=== {label} ({wallet}) ===")
            print(f"  ERROR: {type(e).__name__}: {e}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
