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
    RECONCILE_MAX_DIVERGENCE,
    _event_epoch,
    _kalshi_ladder_buckets,
    _poly_delta_bounds,
    _reconcile_ladder,
)


def rung(strike, mid, strike_type="greater"):
    """One Kalshi ladder rung priced at `mid`, quoted in dollars."""
    return {
        "strike_type": strike_type,
        "floor_strike": strike,
        "yes_bid_dollars": round(mid - 0.005, 4),
        "yes_ask_dollars": round(mid + 0.005, 4),
    }


# The KXFED-26SEP ladder as it stood for activity 8561.
FED_LADDER = [rung(3.50, 0.99), rung(3.75, 0.595), rung(4.00, 0.015), rung(4.50, 0.005)]

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
        assert sum(b[2] for b in kb["buckets"]) == pytest.approx(1.0, abs=1e-9)
        assert kb["step"] == pytest.approx(0.25)

    def test_step_is_the_minimum_gap_not_the_first(self):
        # Rungs are not always evenly spaced; a bucket sized off the first gap
        # would mis-place every level above it.
        kb = _kalshi_ladder_buckets(
            [rung(3.0, 0.99), rung(4.0, 0.60), rung(4.25, 0.10), rung(4.5, 0.02)]
        )
        assert kb["step"] == pytest.approx(0.25)

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
        rec = _reconcile_ladder(kb, FED_POLY)
        assert rec is not None
        assert rec["anchor_level"] == pytest.approx(3.75)
        assert rec["total_abs_divergence"] < 0.10

    def test_reports_the_disagreement_the_customer_paid_for(self):
        kb = _kalshi_ladder_buckets(FED_LADDER)
        rec = _reconcile_ladder(kb, FED_POLY)
        by = {r["outcome"]: r for r in rec["outcomes"]}
        # Kalshi 0.395 vs Polymarket 0.425 on "no change" — the -300bp that the
        # old wording-based matcher discarded as "no trustworthy spread".
        assert by["No change"]["kalshi_prob"] == pytest.approx(0.395, abs=1e-4)
        assert by["No change"]["spread_bps"] == -300
        assert by["25 bps increase"]["spread_bps"] == 150
        # Sorted by magnitude so the largest disagreement reads first.
        assert abs(rec["outcomes"][0]["spread_bps"]) >= abs(rec["outcomes"][-1]["spread_bps"])

    def test_rejects_an_incomplete_distribution(self):
        kb = _kalshi_ladder_buckets(FED_LADDER)
        partial = [dict(FED_POLY[1]), dict(FED_POLY[2])]
        partial[0]["prob"] = 0.20
        partial[1]["prob"] = 0.20
        assert _reconcile_ladder(kb, partial) is None

    def test_rejects_a_distribution_that_cannot_align(self):
        kb = _kalshi_ladder_buckets(FED_LADDER)
        bad = [
            {"lo": 0.0, "hi": 0.0, "prob": 0.02, "label": "No change"},
            {"lo": 0.25, "hi": 0.25, "prob": 0.02, "label": "25 bps increase"},
            {"lo": -0.25, "hi": -0.25, "prob": 0.96, "label": "25 bps decrease"},
        ]
        assert _reconcile_ladder(kb, bad) is None

    def test_rejects_polymarket_finer_than_the_kalshi_grid(self):
        # A 25bp outcome against 50bp rungs lands between them. Reporting the
        # unrepresentable outcome as a 100% disagreement would invent an
        # arbitrage, so the whole fit is dropped.
        kb = _kalshi_ladder_buckets(
            [rung(3.0, 0.99), rung(3.5, 0.60), rung(4.0, 0.02), rung(4.5, 0.005)]
        )
        finer = [
            {"lo": 0.0, "hi": 0.0, "prob": 0.40, "label": "No change"},
            {"lo": 0.25, "hi": 0.25, "prob": 0.35, "label": "25 bps increase"},
            {"lo": 0.5, "hi": 0.5, "prob": 0.25, "label": "50 bps increase"},
        ]
        assert _reconcile_ladder(kb, finer) is None

    def test_accepts_a_matching_grid_when_the_extremes_are_open_ended(self):
        # Same granularity on both sides, with the outermost outcomes labelled
        # open ("50+ bps"), which is how Polymarket actually words them.
        kb = _kalshi_ladder_buckets(
            [rung(3.0, 0.99), rung(3.5, 0.60), rung(4.0, 0.02), rung(4.5, 0.005)]
        )
        coarse = [
            {"lo": 0.0, "hi": 0.0, "prob": 0.39, "label": "No change"},
            {"lo": 0.5, "hi": None, "prob": 0.58, "label": "50+ bps increase"},
            {"lo": None, "hi": -0.5, "prob": 0.03, "label": "50+ bps decrease"},
        ]
        rec = _reconcile_ladder(kb, coarse)
        assert rec is not None
        assert rec["anchor_level"] == pytest.approx(3.5)

    def test_a_closed_outcome_on_the_outermost_rung_is_not_matched(self):
        # Kalshi's bottom bucket is "<= 3.0"; Polymarket's closed "50 bps
        # decrease" is "exactly 3.0". Those are different events, and the
        # ladder cannot separate them, so no reconciliation is offered.
        kb = _kalshi_ladder_buckets(
            [rung(3.0, 0.99), rung(3.5, 0.60), rung(4.0, 0.02), rung(4.5, 0.005)]
        )
        closed = [
            {"lo": 0.0, "hi": 0.0, "prob": 0.39, "label": "No change"},
            {"lo": 0.5, "hi": 0.5, "prob": 0.58, "label": "50 bps increase"},
            {"lo": -0.5, "hi": -0.5, "prob": 0.03, "label": "50 bps decrease"},
        ]
        assert _reconcile_ladder(kb, closed) is None

    def test_divergence_cap_is_enforced(self):
        kb = _kalshi_ladder_buckets(FED_LADDER)
        rec = _reconcile_ladder(kb, FED_POLY)
        assert rec["total_abs_divergence"] <= RECONCILE_MAX_DIVERGENCE


class TestEventEpoch:
    def test_parses_both_venues_timestamp_flavours(self):
        k = _event_epoch("2026-09-16T17:55:00Z")        # Kalshi close_time
        p = _event_epoch("2026-09-16T00:00:00Z")        # Polymarket endDate
        assert k and p and abs(k - p) / 86400.0 < 1.0   # same day -> same event

    @pytest.mark.parametrize("ts", [None, "", "not-a-date", 12345, [], {}])
    def test_bad_timestamps_are_none_not_exceptions(self, ts):
        assert _event_epoch(ts) is None
