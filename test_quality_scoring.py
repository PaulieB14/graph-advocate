"""
test_quality_scoring.py
Tests for the delivery rubric in a2a_server.py — the scale that grades answers
which ARE the result, as opposed to answers that hand back a query to run.

a2a_server.py is a 600KB module that opens real resources on import, so this
lifts the scorer out by AST instead of importing it.

Run: python test_quality_scoring.py
"""

import ast
import json
import re
import unittest
from pathlib import Path

SERVER = Path(__file__).with_name("a2a_server.py")

# Names the delivery rubric is made of. Pulled out by source segment so the test
# exercises the shipping code, not a copy of it.
_WANTED = {
    "_DELIVERY_ENVELOPE_KEYS", "_EMPTY_STATUS_RE",
    "_delivery_leaves", "_delivery_filled", "_score_delivery",
}


def _load_scorer():
    src = SERVER.read_text()
    tree = ast.parse(src)
    ns = {"re": re}
    found = set()
    for node in tree.body:
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and node.targets and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        if name in _WANTED:
            exec(compile(ast.Module([node], []), str(SERVER), "exec"), ns)
            found.add(name)
    missing = _WANTED - found
    assert not missing, f"could not lift from a2a_server.py: {sorted(missing)}"
    return ns


NS = _load_scorer()
score_delivery = NS["_score_delivery"]


def is_routing_answer(rec):
    """The shape discriminator used by _score_response."""
    return bool(rec.get("query_ready") or rec.get("curl_example"))


class TestShapeDiscriminator(unittest.TestCase):
    """Rubric is chosen by shape, never by service name."""

    def test_routing_answer_detected(self):
        self.assertTrue(is_routing_answer({
            "recommendation": "subgraph-registry",
            "query_ready": {"args": {"subgraph_id": "abc"}},
        }))

    def test_direct_data_answer_detected(self):
        self.assertFalse(is_routing_answer({
            "recommendation": "hyperliquid-token-api", "coin": "BTC", "traders": [1, 2],
        }))

    def test_one_service_can_emit_both_shapes(self):
        """subgraph-registry does exactly this — 46 routing / 3 direct-data
        historically — which is why a service-name allowlist gets it wrong."""
        routing = {"recommendation": "subgraph-registry", "curl_example": "curl ..."}
        direct = {"recommendation": "subgraph-registry", "token": {"symbol": "WETH"},
                  "best_venue": {"pool": "0x88e6", "tvl_usd": 417463121.65}}
        self.assertTrue(is_routing_answer(routing))
        self.assertFalse(is_routing_answer(direct))


class TestDeliveryScoring(unittest.TestCase):

    def test_full_payload_scores_top(self):
        rec = {"recommendation": "hyperliquid-token-api", "coin": "BTC",
               "traders_screened": 10, "sharp_count": 0, "retail_count": 0,
               "neutral_count": 10,
               "traders": [{"rank": 1, "user": "0xc6ac", "skill_score": 50.8}]}
        score, fill, _ = score_delivery(rec)
        self.assertEqual(score, 5)
        self.assertEqual(fill, 1.0)

    def test_empty_sentinel_scores_below_full(self):
        """The bug this rubric exists for: an empty result used to score the
        same 4/5 as a full one. 13 keys, but the analytics are all null."""
        rec = {"recommendation": "kalshi-consensus-trend",
               "status": "no_forecast_history_yet",
               "kalshi_event_ticker": "KXELONMARS-99",
               "event_title": "Will Elon Musk visit Mars in his lifetime?",
               "category": "World",
               "consensus_probability_now": None, "slope_per_hour_24h": None,
               "slope_per_hour_3d": None, "acceleration_signal": None,
               "volatility_24h_stdev": None, "days_to_resolve": None,
               "interpretation": "insufficient-history",
               "markets_in_event": 1, "history_points_analyzed": 0}
        empty_score, _, sig = score_delivery(rec)
        self.assertTrue(sig["empty_sentinel"])

        full = {"recommendation": "kalshi-consensus-trend", "status": "ok",
                "kalshi_event_ticker": "KXABC", "event_title": "Something",
                "category": "World", "consensus_probability_now": 0.42,
                "slope_per_hour_24h": 0.01, "markets_in_event": 3,
                "history_points_analyzed": 288}
        full_score, _, _ = score_delivery(full)
        self.assertLess(empty_score, full_score,
                        "an empty result must score below a real one")

    def test_status_ok_is_not_an_empty_sentinel(self):
        rec = {"recommendation": "predmarket-spread", "status": "ok",
               "topic_keyword": "fed", "pairs": [{"a": 1}],
               "polymarket_candidates": [1], "limitless_candidates": [2]}
        _, _, sig = score_delivery(rec)
        self.assertFalse(sig["empty_sentinel"])

    def test_partial_result_is_not_an_empty_sentinel(self):
        """`limitless_only` means one venue matched — degraded, not empty.
        Fill rate grades it; the sentinel rule must not swallow it."""
        _, _, sig = score_delivery({
            "recommendation": "predmarket-spread", "status": "limitless_only",
            "topic_keyword": "fed", "limitless_candidates": [1, 2]})
        self.assertFalse(sig["empty_sentinel"])

    def test_no_match_variants_are_sentinels(self):
        for status in ("no_matches", "no_semantic_match",
                       "matched_no_common_condition",
                       "milestone_exists_but_no_plays_yet",
                       "no_market_ticker_supplied"):
            with self.subTest(status=status):
                _, _, sig = score_delivery({"recommendation": "x", "status": status})
                self.assertTrue(sig["empty_sentinel"], f"{status} should be empty")

    def test_error_payload_loses_a_point(self):
        clean = {"recommendation": "kalshi-consensus-trend", "a": 1, "b": 2, "c": 3, "d": 4}
        errored = {**clean, "error": "upstream 500"}
        self.assertLess(score_delivery(errored)[0], score_delivery(clean)[0])

    def test_key_count_does_not_buy_a_score(self):
        """Many keys, all null — the failure mode that fooled key-based rubrics."""
        rec = {"recommendation": "svc", **{f"f{i}": None for i in range(12)}}
        score, fill, _ = score_delivery(rec)
        self.assertEqual(fill, 0.0)
        self.assertLessEqual(score, 3)

    def test_envelope_keys_do_not_inflate_fill(self):
        """reason/confidence are envelope, not answer — they must not pad the
        fill ratio of an otherwise empty payload."""
        bare = {"recommendation": "svc", "result": None}
        padded = {**bare, "reason": "because", "confidence": "high", "tool": "x"}
        self.assertEqual(score_delivery(bare)[1], score_delivery(padded)[1])

    def test_long_arrays_do_not_dominate_fill(self):
        rec = {"recommendation": "svc", "rows": [{"v": i} for i in range(500)],
               "summary": None}
        _, fill, _ = score_delivery(rec)
        self.assertGreater(fill, 0.0)
        self.assertLessEqual(fill, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
