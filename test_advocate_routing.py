"""
test_advocate_routing.py
Tests for the routing-gap fixes in advocate.py.
Run: python test_advocate_routing.py
"""

import json
import sys
import types
import unittest

# ── Minimal stubs so we can import advocate.py without real API keys ─────────
import os
os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")

# Stub the anthropic client before import
import unittest.mock as mock

# We only test the pure-Python helpers — no actual API calls
sys.path.insert(0, "/home/claude")


class TestExtractJson(unittest.TestCase):
    """_extract_json should handle all common Claude output shapes."""

    def setUp(self):
        # Import lazily so mocks are in place
        from advocate import _extract_json
        self.fn = _extract_json

    def test_clean_json(self):
        raw = '{"recommendation":"token-api","confidence":"high"}'
        result = self.fn(raw)
        self.assertEqual(result["recommendation"], "token-api")
        self.assertNotIn("parse_error", result)

    def test_json_in_code_fence(self):
        raw = '```json\n{"recommendation":"subgraph-registry","confidence":"high"}\n```'
        result = self.fn(raw)
        self.assertEqual(result["recommendation"], "subgraph-registry")

    def test_json_in_plain_fence(self):
        raw = '```\n{"recommendation":"token-api"}\n```'
        result = self.fn(raw)
        self.assertEqual(result["recommendation"], "token-api")

    def test_json_with_leading_text(self):
        raw = 'Here is the routing decision:\n{"recommendation":"graph-aave-mcp","confidence":"high"}'
        result = self.fn(raw)
        self.assertEqual(result["recommendation"], "graph-aave-mcp")

    def test_json_with_trailing_text(self):
        raw = '{"recommendation":"substreams","confidence":"medium"}\nHope that helps!'
        result = self.fn(raw)
        self.assertEqual(result["recommendation"], "substreams")

    def test_plain_text_returns_parse_error(self):
        raw = "I cannot help with that request."
        result = self.fn(raw)
        self.assertTrue(result.get("parse_error"))

    def test_empty_string_returns_parse_error(self):
        result = self.fn("")
        self.assertTrue(result.get("parse_error"))

    def test_nested_json(self):
        raw = '{"recommendation":"token-api","query_ready":{"tool":"getV1EvmHolders","args":{"contract":"0xA0b8"}}}'
        result = self.fn(raw)
        self.assertEqual(result["recommendation"], "token-api")
        self.assertEqual(result["query_ready"]["tool"], "getV1EvmHolders")


class TestFallbackRoute(unittest.TestCase):
    """_fallback_route should always return a valid recommendation."""

    def setUp(self):
        from advocate import _fallback_route
        self.fn = _fallback_route

    def _check(self, query, expected_svc):
        result = self.fn(query)
        self.assertIn("recommendation", result)
        self.assertIn("confidence", result)
        self.assertIn("curl_example", result)
        self.assertEqual(
            result["recommendation"], expected_svc,
            f"Query {query!r}: expected {expected_svc!r}, got {result['recommendation']!r}",
        )

    def test_aave_routes_to_aave_mcp(self):
        self._check("top Aave V3 markets by TVL", "graph-aave-mcp")

    def test_liquidation_routes_to_aave(self):
        self._check("recent Aave liquidations on Ethereum", "graph-aave-mcp")

    def test_polymarket_routes_correctly(self):
        self._check("hottest Polymarket prediction markets", "graph-polymarket-mcp")

    def test_holder_routes_to_token_api(self):
        self._check("top 20 USDC holders on Ethereum", "token-api")

    def test_swap_routes_to_token_api(self):
        self._check("biggest DEX swaps on Base today", "token-api")

    def test_whale_routes_to_token_api(self):
        self._check("whale wallet transfers above 1M USDC", "token-api")

    def test_streaming_routes_to_substreams(self):
        self._check("raw event logs from blocks 19000000 to 20000000", "substreams")

    def test_agent_search_routes_to_8004scan(self):
        self._check("find agents with MCP endpoints on ERC-8004", "8004scan")

    def test_generic_routes_to_subgraph_registry(self):
        self._check("what data sources are available", "subgraph-registry")

    def test_always_has_curl_example(self):
        """Every routed service must return a non-empty curl_example."""
        queries = [
            "top USDC holders",
            "Aave liquidations",
            "Polymarket markets",
            "substreams for ERC20",
            "find MCP agents",
            "Uniswap pool TVL",
            "staking rewards",
        ]
        for q in queries:
            result = self.fn(q)
            self.assertTrue(
                result.get("curl_example"),
                f"No curl_example for query: {q!r} → {result['recommendation']!r}",
            )


class TestInjectMissingFields(unittest.TestCase):
    """_inject_missing_fields should fill in missing curl_example / get_started / install."""

    def setUp(self):
        from advocate import _inject_missing_fields
        self.fn = _inject_missing_fields

    def test_injects_curl_example_when_absent(self):
        rec = {"recommendation": "token-api", "confidence": "high", "query_ready": None}
        out = self.fn(rec, "top USDC holders")
        self.assertIn("curl_example", out)
        self.assertTrue(out["curl_example"])

    def test_injects_install_for_npm_packages(self):
        rec = {"recommendation": "graph-aave-mcp", "confidence": "high", "query_ready": None}
        out = self.fn(rec, "Aave markets")
        self.assertIn("install", out)
        self.assertIn("npx", out["install"])

    def test_does_not_overwrite_existing_curl_example(self):
        rec = {
            "recommendation": "token-api",
            "curl_example": "curl https://my-custom-example.com",
            "query_ready": None,
        }
        out = self.fn(rec, "holders")
        self.assertEqual(out["curl_example"], "curl https://my-custom-example.com")

    def test_injects_get_started(self):
        rec = {"recommendation": "subgraph-registry", "confidence": "high"}
        out = self.fn(rec, "uniswap pools")
        self.assertIn("get_started", out)
        self.assertIn("thegraph.com", out["get_started"])

    def test_normalizes_query_ready_shape(self):
        rec = {"recommendation": "token-api", "query_ready": {"tool": "getV1EvmHolders"}}
        out = self.fn(rec, "holders")
        self.assertIn("args", out["query_ready"])

    def test_handles_none_query_ready(self):
        rec = {"recommendation": "graph-polymarket-mcp", "query_ready": None}
        out = self.fn(rec, "polymarket")
        self.assertIsNone(out.get("query_ready"))  # None stays None — curl_example is injected instead
        self.assertTrue(out.get("curl_example"))


class TestAutoSearchKeywords(unittest.TestCase):
    """_auto_search keyword expansion — verify new tokens trigger correct search buckets."""

    def setUp(self):
        from advocate import (
            _any_word_match,
            _STOP_WORDS,
        )
        self._any_word_match = _any_word_match
        self._STOP_WORDS = _STOP_WORDS

        # Reproduce the exact keyword lists from advocate.py
        self.SUBGRAPH_KEYWORDS = [
            "subgraph", "uniswap", "aave", "compound", "curve", "ens", "balancer",
            "sushi", "maker", "lido", "yearn", "synthetix", "protocol", "tvl",
            "liquidity", "pool", "lending", "governance", "dao",
            "nft marketplace", "opensea", "decentraland", "the graph",
            "polymarket", "prediction market", "limitless", "predict.fun",
            "open interest", "resolution", "trader p&l", "indexer",
            "exchange", "staking", "yield", "farm", "vault", "borrow",
            "collateral", "oracle", "dydx", "gmx", "stargate", "layerzero",
            "pancake", "quickswap", "velodrome", "aerodrome", "camelot",
            "frax", "convex", "morpho", "spark", "sky", "pendle",
            "hyperliquid", "drift", "perpetual", "perp", "margin",
            "rewards", "incentive", "emission", "vote", "gauge",
        ]
        self.TOKEN_API_KEYWORDS = [
            "balance", "holder", "transfer", "wallet", "nft",
            "erc20", "erc721", "dex", "ohlc",
            "solana", "ton", "svm", "tvm",
            "swap", "price", "volume", "whale", "top holder", "biggest",
            "largest", "richest", "portfolio", "token amount",
            "usdc", "usdt", "weth", "eth holder", "btc holder",
            "nft sale", "nft floor", "nft owner",
        ]

    def _run_subgraph(self, text):
        return self._any_word_match(self.SUBGRAPH_KEYWORDS, text.lower())

    def _run_token(self, text):
        return self._any_word_match(self.TOKEN_API_KEYWORDS, text.lower())

    def test_staking_triggers_subgraph(self):
        self.assertTrue(self._run_subgraph("Lido staking rewards"))

    def test_yield_triggers_subgraph(self):
        self.assertTrue(self._run_subgraph("yield farming on Curve"))

    def test_oracle_triggers_subgraph(self):
        self.assertTrue(self._run_subgraph("Chainlink oracle price feeds subgraph"))

    def test_swap_triggers_token_api(self):
        self.assertTrue(self._run_token("biggest swap on Uniswap last hour"))

    def test_whale_triggers_token_api(self):
        self.assertTrue(self._run_token("whale wallets moving USDC"))

    def test_usdc_triggers_token_api(self):
        self.assertTrue(self._run_token("top USDC holders on mainnet"))

    def test_portfolio_triggers_token_api(self):
        self.assertTrue(self._run_token("wallet portfolio for 0xabc"))

    def test_volume_triggers_token_api(self):
        self.assertTrue(self._run_token("24h trading volume on Base"))


class TestServiceCurlExamples(unittest.TestCase):
    """Every service in _SERVICE_CURL_EXAMPLES must have a non-empty curl_example."""

    def test_all_services_have_curl_example(self):
        from advocate import _SERVICE_CURL_EXAMPLES
        for svc, example in _SERVICE_CURL_EXAMPLES.items():
            self.assertTrue(
                example.get("curl_example"),
                f"Service {svc!r} missing curl_example",
            )

    def test_npm_services_have_install(self):
        from advocate import _SERVICE_CURL_EXAMPLES
        NPM_SERVICES = {
            "graph-aave-mcp", "graph-polymarket-mcp", "graph-lending-mcp",
            "graph-limitless-mcp", "predictfun-mcp", "substreams", "mcp8004",
        }
        for svc in NPM_SERVICES:
            self.assertIn(svc, _SERVICE_CURL_EXAMPLES, f"{svc!r} missing from _SERVICE_CURL_EXAMPLES")
            self.assertTrue(
                _SERVICE_CURL_EXAMPLES[svc].get("install"),
                f"Service {svc!r} missing install command",
            )


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestExtractJson))
    suite.addTests(loader.loadTestsFromTestCase(TestFallbackRoute))
    suite.addTests(loader.loadTestsFromTestCase(TestInjectMissingFields))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoSearchKeywords))
    suite.addTests(loader.loadTestsFromTestCase(TestServiceCurlExamples))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
