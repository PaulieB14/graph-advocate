"""Tests for personalized outreach pitch. Run: python3 test_outreach_pitch.py"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

# Stub httpx so importing outreach.py does not require the dep in this env.
if "httpx" not in sys.modules:
    sys.modules["httpx"] = types.ModuleType("httpx")

import outreach_pitch as op


def _load_outreach():
    # Already stubbed httpx.
    import outreach
    return outreach


class TestPitch(unittest.TestCase):
    def test_tokenbank_maps_to_token_api(self):
        tid = op.pick_topic(
            "TokenBank",
            "Information desk for tokenized real-world assets, stablecoins and crypto yield",
            ["Find buyable offers", "Yield picks of the week", "Build portfolio"],
        )
        self.assertEqual(tid, "token-api")
        msg = op.build_personalized_intro(
            name="TokenBank",
            description="tokenized real-world assets, stablecoins and crypto yield",
            skills=["Yield picks of the week"],
        )
        self.assertIn("TokenBank", msg)
        self.assertIn("graphadvocate.com", msg)
        self.assertIn("/route", msg)
        self.assertIn("8004scan", msg)
        self.assertIn("example (not live data)", msg)
        self.assertLess(len(msg), 1800)

    def test_beggar_bot_maps_to_x402(self):
        tid = op.pick_topic(
            "Beggar Bot utilities",
            "Base mainnet USDC payment verification, x402 seller health checks",
            ["/v1/portfolio", "/v1/erc20balances"],
        )
        self.assertEqual(tid, "x402")
        msg = op.build_personalized_intro(
            name="Beggar Bot utilities",
            description="x402 seller health checks and USDC payment verification",
            skills=["/v1/portfolio"],
        )
        self.assertIn("/onchain-x402/address", msg)
        self.assertIn("x402", msg.lower())

    def test_polymarket_agent(self):
        tid = op.pick_topic("PolyScout", "Tracks Polymarket traders and PnL", [])
        self.assertEqual(tid, "polymarket")
        msg = op.build_personalized_intro(name="PolyScout", description="Polymarket traders and PnL")
        self.assertIn("/polymarket/pnl-quick", msg)

    def test_legacy_unchanged_flag_off(self):
        os.environ.pop("OUTREACH_PERSONALIZED", None)
        outreach = _load_outreach()
        legacy = outreach.build_intro("https://graphadvocate.com")
        self.assertIn("langchain-graph-advocate", legacy)
        self.assertIn("Top Uniswap V3 pools on Base by TVL", legacy)

    def test_flag_on_personalizes(self):
        outreach = _load_outreach()
        os.environ["OUTREACH_PERSONALIZED"] = "1"
        try:
            msg = outreach.build_intro(
                "https://graphadvocate.com",
                agent={
                    "name": "TokenBank",
                    "description": "stablecoins and crypto yield products",
                    "skills": ["Yield picks"],
                },
            )
            self.assertIn("TokenBank", msg)
            self.assertNotIn("langchain-graph-advocate", msg)
        finally:
            os.environ.pop("OUTREACH_PERSONALIZED", None)


if __name__ == "__main__":
    unittest.main()
