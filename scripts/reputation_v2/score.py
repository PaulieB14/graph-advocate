"""reputation_v2 prototype — combines ERC-8004 feedback with payment-style
diversity weighting. Operates on the saved Base mainnet feedback sample.

Per-agent score components (each 0..100, weighted into composite):
  - payer_diversity:   1 - HHI on raters     (higher = more unique raters)
  - mean_rating:       avg of rater values, normalized to 0..100
  - volume_signal:     log1p(distinct_raters) / log(8)  (caps near 8 raters)
  - noise_penalty:     fraction of entries with `test`-like tags

Composite (suggested initial weights):
  score = 0.45 * payer_diversity
        + 0.25 * mean_rating
        + 0.20 * volume_signal
        + (-0.10) * noise_penalty

Tag noise list is data-driven from the sample we observed:
  - test, tip, liveness (single-wallet flooding), starred
Real-signal tags kept: trust, quality, usefulness, financial, research,
  rating, booking, trustScore, longevity, activity, counterparty,
  contractRisk, collaboration, communication
"""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).parent / "base_feedback_sample.json"

NOISE_TAGS = {"test", "starred", "synmerco-outreach"}


def hhi(counts):
    total = sum(counts.values())
    if total == 0:
        return 1.0
    return sum((c / total) ** 2 for c in counts.values())


def score_agent(rows):
    by_rater = defaultdict(int)
    values = []
    noise = 0
    for r in rows:
        if r.get("isRevoked"):
            continue
        by_rater[r["clientAddress"]] += 1
        try:
            v = float(r["value"])
            values.append(min(100, max(0, v)))
        except (TypeError, ValueError):
            pass
        if (r.get("tag1") or "").lower() in NOISE_TAGS:
            noise += 1
    if not by_rater:
        return None
    distinct = len(by_rater)
    payer_diversity = (1.0 - hhi(by_rater)) * 100
    mean_rating = (sum(values) / len(values)) if values else 0
    volume_signal = min(100.0, math.log1p(distinct) / math.log(8) * 100)
    noise_penalty = (noise / len(rows)) * 100
    composite = (
        0.45 * payer_diversity
        + 0.25 * mean_rating
        + 0.20 * volume_signal
        - 0.10 * noise_penalty
    )
    return {
        "agent_id": rows[0]["agent"]["id"],
        "feedback_count": len(rows),
        "distinct_raters": distinct,
        "payer_diversity": round(payer_diversity, 1),
        "mean_rating": round(mean_rating, 1),
        "volume_signal": round(volume_signal, 1),
        "noise_penalty": round(noise_penalty, 1),
        "composite": round(composite, 1),
    }


def main():
    if not DATA.exists():
        sys.exit(f"missing {DATA}")
    raw = json.loads(DATA.read_text())
    feedbacks = raw.get("feedbacks") or raw
    by_agent = defaultdict(list)
    for r in feedbacks:
        by_agent[r["agent"]["id"]].append(r)
    scores = [s for s in (score_agent(rows) for rows in by_agent.values()) if s]
    scores.sort(key=lambda s: -s["composite"])

    print(f"{'AGENT':<14} {'FB':>3} {'DIST':>4} {'DIV':>5} {'MEAN':>5} {'VOL':>5} {'NOISE':>5} {'SCORE':>6}")
    print("-" * 60)
    for s in scores:
        print(
            f"{s['agent_id']:<14} "
            f"{s['feedback_count']:>3} "
            f"{s['distinct_raters']:>4} "
            f"{s['payer_diversity']:>5} "
            f"{s['mean_rating']:>5} "
            f"{s['volume_signal']:>5} "
            f"{s['noise_penalty']:>5} "
            f"{s['composite']:>6}"
        )
    print(f"\nscored {len(scores)} agents from {len(feedbacks)} feedback entries")


if __name__ == "__main__":
    main()
