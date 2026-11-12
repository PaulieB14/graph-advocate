"""Tests for free_preview enrichment + spam filter. Run: python test_free_preview.py"""
from __future__ import annotations

import logging
import os
import unittest
from unittest import mock

import free_preview as fp


class TestFreePreview(unittest.TestCase):
    def setUp(self):
        os.environ.pop("GA_FREE_PREVIEW", None)
        os.environ["GA_LIVE_PREVIEW"] = "0"  # these tests cover the static preview; live is in test_live_preview.py
        # Reset in-memory rate limits between tests
        with fp._lock:
            fp._hits.clear()
            fp._day.update(d="", n=0)

    def test_uniswap_gets_example_graphql(self):
        prev = fp.build("top Uniswap V3 pools on Arbitrum by volume", "t-uni")
        self.assertIsNotNone(prev)
        self.assertTrue(prev["free"])
        self.assertIn("example", prev)
        self.assertEqual(prev["example"]["label"], "example (not live data)")
        self.assertEqual(prev["example"]["kind"], "graphql")
        self.assertIn("pools", prev["example"]["query"])
        self.assertIn("not live", prev["example"]["note"].lower())
        self.assertIn("feedback", prev)
        self.assertIn("8004scan", prev["feedback"]["message"])

    def test_aave_liquidations_full_answer_matches(self):
        prev = fp.build(
            "Write a GraphQL query for Aave V3 liquidations above $50K on Ethereum",
            "t-aave-liq",
        )
        self.assertIsNotNone(prev)
        self.assertIn("liquidation", prev["full_answer_includes"].lower())
        self.assertEqual(prev["example"]["kind"], "graphql")
        self.assertIn("liquidations", prev["example"]["query"])

    def test_aave_health_not_forced_liquidations(self):
        prev = fp.build("What is my Aave V3 health factor on Ethereum?", "t-aave-hf")
        self.assertIsNotNone(prev)
        self.assertIn("health", prev["full_answer_includes"].lower())
        self.assertNotIn("recent liquidation events", prev["full_answer_includes"].lower())

    def test_polymarket_http_example(self):
        prev = fp.build(
            "Show the positions and realized P&L for Polymarket user 0x42eB...",
            "t-poly",
        )
        self.assertEqual(prev["example"]["kind"], "http")
        self.assertEqual(prev["example"]["request"]["path"], "/polymarket/pnl-quick")

    def test_spam_pitch_no_preview(self):
        q = ("Ingravity Autonomous EVM Security Swarm v3.9.4 (Base Mainnet). "
             "Deterministic pre-sign protection: POST https://red-shape.workers.dev/api/v1/fast-ping")
        self.assertTrue(fp.is_spam_pitch(q))
        self.assertIsNone(fp.build(q, "t-spam"))

    def test_probe_no_preview(self):
        self.assertIsNone(fp.build("ping", "t-ping"))
        self.assertIsNone(fp.build("Taifoon onboarding probe: reply with the single word READY.", "t-tf"))

    def test_disabled(self):
        os.environ["GA_FREE_PREVIEW"] = "0"
        try:
            self.assertIsNone(fp.build("top Uniswap V3 pools on Arbitrum by volume", "t-off"))
        finally:
            os.environ.pop("GA_FREE_PREVIEW", None)

    def test_free_preview_served_log(self):
        records = []

        class H(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        h = H()
        fp.log.addHandler(h)
        fp.log.setLevel(logging.INFO)
        try:
            fp.build("Compare SOL token holder distribution vs ETH", "t-log")
        finally:
            fp.log.removeHandler(h)
        joined = "\n".join(records)
        self.assertIn("free_preview_served", joined)
        self.assertIn("topic=token-api", joined)
        self.assertIn("path=", joined)
        # No question text in the log line
        self.assertNotIn("SOL token holder", joined)


if __name__ == "__main__":
    unittest.main()
