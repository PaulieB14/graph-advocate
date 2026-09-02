"""Reconciliation of a Kalshi threshold ladder against a Polymarket delta group.

These exist because `kalshi-poly-spread` returned zero pairs on every call in
its history — 14 calls, 12 of them paid — while a computable spread sat in the
data it was returning. The cause was matching on wording: Kalshi says "upper
bound above 3.75%", Polymarket says "25 bps increase", and the best Jaccard
overlap across every real Fed combination was 0.067 against a 0.25 threshold.

The numbers below are the real ones from the paid call on 2026-09-02 (activity
id 8561), so a regression here is a regression against a request a customer
actually paid for.

Offline by construction — no network, no venue APIs.
"""
import pytest

from kalshi import (
    FED_UPPER_BOUND_DEFAULT,
    _align_ladder,
    _event_epoch,
    _kalshi_ladder_buckets,
    _poly_delta_bounds,
    _viable_anchors,
)


def align(kb, items, anchor=None):
    """_align_ladder with the default origin, which is what the endpoint uses."""
    a = FED_UPPER_BOUND_DEFAULT if anchor is None else anchor
    return _align_ladder(kb, items, a, "assumed_default")


def rung(strike, mid, strike_type="greater"):
    """One Kalshi ladder rung priced at `mid`, quoted in dollars."""
    return {
        "strike_type": strike_type,
        "floor_strike": strike,
        "yes_bid_dollars": round(mid - 0.005, 4),
        "yes_ask_dollars": round(mid + 0.005, 4),
    }


# The KXFED-26SEP ladder as it stood for activity 8561. The full 11-rung grid,
# not a subset: the strike grid must be UNIFORM or the bucket arithmetic
# mis-places levels, so a 4-rung sample with a 0.50 gap in it is now correctly
# rejected and would be a misleading fixture. The four rungs the paid response
# actually quoted (3.50/3.75/4.00/4.50) carry their real prices; the untraded
# tails are filled monotonically as the live book has them.
FED_LADDER = [
    rung(2.75, 0.995), rung(3.00, 0.995), rung(3.25, 0.995), rung(3.50, 0.99),
    rung(3.75, 0.595), rung(4.00, 0.015), rung(4.25, 0.005), rung(4.50, 0.005),
    rung(4.75, 0.005), rung(5.00, 0.005), rung(5.25, 0.005),
]

# The fed-decision-in-september-762 group as it stood for the same call.
FED_POLY = [
    {"lo": -0.25, "hi": -0.25, "prob": 0.0055, "label": "25 bps decrease"},
    {"lo": 0.0, "hi": 0.0, "prob": 0.425, "label": "No change"},
    {"lo": 0.25, "hi": 0.25, "prob": 0.565, "label": "25 bps increase"},
    {"lo": 0.5, "hi": None, "prob": 0.0065, "label": "50+ bps increase"},
    {"lo": None, "hi": -0.5, "prob": 0.0015, "label": "50+ bps decrease"},
]


class TestLadder:
    def test_ladder_is_a_complete_distribution(self):
        kb = _kalshi_ladder_buckets(FED_LADDER)
        assert kb is not None
        assert sum(b["p"] for b in kb["buckets"]) == pytest.approx(1.0, abs=1e-9)
        assert kb["step"] == pytest.approx(0.25)

    def test_a_non_uniform_grid_is_rejected_outright(self):
        # Bucket membership is computed as `lo + step` with ONE step, so a wider
        # gap anywhere silently drops a partially-overlapping bucket and
        # fabricates a disagreement — reproduced at up to -2014bp during review.
        # Non-uniform ladders are live (KXUSDX-26 mixes 0.25 and 1.0), so this
        # rejection is load-bearing, not theoretical.
        assert _kalshi_ladder_buckets(
            [rung(3.0, 0.99), rung(4.0, 0.60), rung(4.25, 0.10), rung(4.5, 0.02)]
        ) is None

    def test_uniform_grid_is_accepted(self):
        kb = _kalshi_ladder_buckets(
            [rung(3.0, 0.99), rung(3.25, 0.60), rung(3.5, 0.10), rung(3.75, 0.02)]
        )
        assert kb is not None and kb["step"] == pytest.approx(0.25)

    @pytest.mark.parametrize("markets,why", [
        ([rung(3.5, 0.9), rung(3.75, 0.5)], "two rungs is not a ladder"),
        ([rung(3.5, 0.20), rung(3.75, 0.90), rung(4.0, 0.10)], "P(>s) must not rise with s"),
        ([{"strike_type": "greater", "floor_strike": s} for s in (3.5, 4.0, 4.5)], "no prices"),
        ([rung(3.5, 0.9, "less"), rung(4.0, 0.5, "less"), rung(4.5, 0.1, "less")], "wrong strike_type"),
        ([], "empty"),
    ])
    def test_rejects_what_is_not_a_ladder(self, markets, why):
        assert _kalshi_ladder_buckets(markets) is None, why


class TestDeltaLabels:
    @pytest.mark.parametrize("label,expected", [
        ("No change", (0.0, 0.0)),
        ("25 bps increase", (0.25, 0.25)),
        ("25 bps decrease", (-0.25, -0.25)),
        ("50+ bps increase", (0.5, None)),
        ("50+ bps decrease", (None, -0.5)),
        ("100 bps increase", (1.0, 1.0)),
    ])
    def test_parses_real_group_item_titles(self, label, expected):
        assert _poly_delta_bounds(label) == expected

    @pytest.mark.parametrize("label", [None, "", "Yes", "Will the Fed cut?", "bps", "25 bps"])
    def test_returns_none_rather_than_guessing(self, label):
        assert _poly_delta_bounds(label) is None


class TestReconcile:
    def test_solves_the_anchor_without_being_told_the_policy_rate(self):
        # The whole point: the origin for Polymarket's deltas is derived from
        # the fit, so there is no second source of truth to keep current.
        kb = _kalshi_ladder_buckets(FED_LADDER)
        rec = align(kb, FED_POLY)
        assert rec is not None
        assert rec["anchor_level"] == pytest.approx(3.75)
        assert rec["anchor_source"] == "assumed_default"
        assert rec["total_abs_difference"] < 0.10

    def test_reports_the_disagreement_the_customer_paid_for(self):
        kb = _kalshi_ladder_buckets(FED_LADDER)
        rec = align(kb, FED_POLY)
        by = {r["outcome"]: r for r in rec["outcomes"]}
        # Kalshi 0.395 vs Polymarket 0.425 on "no change" — the -300bp that the
        # old wording-based matcher discarded as "no trustworthy spread".
        assert by["No change"]["kalshi_prob_mid"] == pytest.approx(0.395, abs=1e-4)
        assert by["No change"]["difference_bps"] == -300
        assert by["25 bps increase"]["difference_bps"] == 150
        # Sorted by magnitude so the largest disagreement reads first.
        assert abs(rec["outcomes"][0]["difference_bps"]) >= abs(rec["outcomes"][-1]["difference_bps"])

    def test_rejects_an_incomplete_distribution(self):
        kb = _kalshi_ladder_buckets(FED_LADDER)
        partial = [dict(FED_POLY[1]), dict(FED_POLY[2])]
        partial[0]["prob"] = 0.20
        partial[1]["prob"] = 0.20
        assert align(kb, partial) is None

    def test_a_large_genuine_disagreement_is_reported_not_suppressed(self):
        # Polymarket at 96% on a cut against a ladder pricing it near zero is a
        # real disagreement, and the honest answer is to show it flagged as
        # outside the quote band. The earlier design rejected this as a "bad
        # fit", which conflated two different things: whether the two events are
        # the same (now decided by the resolution-date match) and how far apart
        # they are priced (the output).
        kb = _kalshi_ladder_buckets(FED_LADDER)
        wide = [
            {"lo": 0.0, "hi": 0.0, "prob": 0.02, "label": "No change"},
            {"lo": 0.25, "hi": 0.25, "prob": 0.02, "label": "25 bps increase"},
            {"lo": -0.25, "hi": -0.25, "prob": 0.96, "label": "25 bps decrease"},
        ]
        rec = align(kb, wide)
        assert rec is not None
        by = {r["outcome"]: r for r in rec["outcomes"]}
        assert by["25 bps decrease"]["difference_bps"] < -9000
        assert by["25 bps decrease"]["exceeds_quote_band"] is True

    def test_rejects_polymarket_finer_than_the_kalshi_grid(self):
        # A 25bp outcome against 50bp rungs lands between them. Reporting the
        # unrepresentable outcome as a 100% disagreement would invent an
        # arbitrage, so the whole fit is dropped.
        kb = _kalshi_ladder_buckets(
            [rung(3.0, 0.99), rung(3.5, 0.60), rung(4.0, 0.02), rung(4.5, 0.005), rung(5.0, 0.001)]
        )
        finer = [
            {"lo": 0.0, "hi": 0.0, "prob": 0.40, "label": "No change"},
            {"lo": 0.25, "hi": 0.25, "prob": 0.35, "label": "25 bps increase"},
            {"lo": 0.5, "hi": 0.5, "prob": 0.25, "label": "50 bps increase"},
        ]
        assert align(kb, finer) is None

    def test_accepts_a_matching_grid_when_the_extremes_are_open_ended(self):
        # Same granularity on both sides, with the outermost outcomes labelled
        # open ("50+ bps"), which is how Polymarket actually words them.
        kb = _kalshi_ladder_buckets(
            [rung(3.0, 0.99), rung(3.5, 0.60), rung(4.0, 0.02), rung(4.5, 0.005), rung(5.0, 0.001)]
        )
        coarse = [
            {"lo": 0.0, "hi": 0.0, "prob": 0.39, "label": "No change"},
            {"lo": 0.5, "hi": None, "prob": 0.58, "label": "50+ bps increase"},
            {"lo": None, "hi": -0.5, "prob": 0.03, "label": "50+ bps decrease"},
        ]
        rec = align(kb, coarse, 3.5)
        assert rec is not None
        assert rec["anchor_level"] == pytest.approx(3.5)

    def test_a_closed_outcome_on_the_outermost_rung_is_not_matched(self):
        # Kalshi's bottom bucket is "<= 3.0"; Polymarket's closed "50 bps
        # decrease" is "exactly 3.0". Those are different events, and the
        # ladder cannot separate them, so no reconciliation is offered.
        kb = _kalshi_ladder_buckets(
            [rung(3.0, 0.99), rung(3.5, 0.60), rung(4.0, 0.02), rung(4.5, 0.005), rung(5.0, 0.001)]
        )
        closed = [
            {"lo": 0.0, "hi": 0.0, "prob": 0.39, "label": "No change"},
            {"lo": 0.5, "hi": 0.5, "prob": 0.58, "label": "50 bps increase"},
            {"lo": -0.5, "hi": -0.5, "prob": 0.03, "label": "50 bps decrease"},
        ]
        assert align(kb, closed, 3.5) is None

    def test_the_anchor_is_reported_as_an_assumption_not_a_derivation(self):
        # The audit killed two attempts to derive it: minimising divergence
        # erased the signal being measured, and requiring a structurally forced
        # origin only looks unique on a narrow ladder — the real 11-rung Fed
        # ladder admits eight. So it is an input, and the response must say so.
        kb = _kalshi_ladder_buckets(FED_LADDER)
        rec = align(kb, FED_POLY)
        assert rec["anchor_source"] == "assumed_default"
        assert rec["anchor_as_of"]
        supplied = _align_ladder(kb, FED_POLY, 3.75, "caller_supplied")
        assert supplied["anchor_source"] == "caller_supplied"
        assert supplied["anchor_as_of"] is None

    def test_differences_are_bounded_by_the_quote_band(self):
        kb = _kalshi_ladder_buckets(FED_LADDER)
        rec = align(kb, FED_POLY)
        for row in rec["outcomes"]:
            assert row["kalshi_prob_low"] <= row["kalshi_prob_mid"] <= row["kalshi_prob_high"]
            assert row["kalshi_quote_band_bps"] >= 0
            expected = abs(row["difference_bps"]) > row["kalshi_quote_band_bps"]
            assert row["exceeds_quote_band"] is expected

    def test_viable_anchors_are_exposed_rather_than_silently_chosen(self):
        kb = _kalshi_ladder_buckets(FED_LADDER)
        viable = _viable_anchors(kb, FED_POLY)
        assert 3.75 in viable


class TestEventEpoch:
    def test_parses_both_venues_timestamp_flavours(self):
        k = _event_epoch("2026-09-16T17:55:00Z")        # Kalshi close_time
        p = _event_epoch("2026-09-16T00:00:00Z")        # Polymarket endDate
        assert k and p and abs(k - p) / 86400.0 < 1.0   # same day -> same event

    @pytest.mark.parametrize("ts", [None, "", "not-a-date", 12345, [], {}])
    def test_bad_timestamps_are_none_not_exceptions(self, ts):
        assert _event_epoch(ts) is None
