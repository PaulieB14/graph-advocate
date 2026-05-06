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

    def test_polymarket_routes_to_token_api(self):
        self._check("hottest Polymarket prediction markets", "token-api")

    def test_polymarket_orderbook_routes_to_mcp(self):
        self._check("Polymarket live orderbook depth", "graph-polymarket-mcp")

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

    def test_comparison_token_api_vs_subgraph(self):
        """The recurring 'Token API vs subgraph' prompt must not fall through to 'unknown'."""
        result = self.fn("Token API vs subgraph for Uniswap pool data?")
        self.assertIn(result["recommendation"], {"comparison", "subgraph-registry", "token-api"})
        self.assertTrue(result.get("answer"), "comparison route should return an answer")

    def test_comparison_with_historical_prefers_subgraph(self):
        result = self.fn("Token API vs subgraph for historical Uniswap pool TVL")
        self.assertEqual(result["recommendation"], "subgraph-registry")

    def test_comparison_with_current_prefers_token_api(self):
        result = self.fn("Token API vs subgraph for current USDC holder count")
        self.assertEqual(result["recommendation"], "token-api")

    def test_aave_liquidations_query_template(self):
        """The prompt from the live feed miss must now return a real query, not just a service tag."""
        result = self.fn("Write a GraphQL query for Aave V3 liquidations above $50K")
        self.assertEqual(result["recommendation"], "subgraph-registry")
        qr = result.get("query_ready") or {}
        self.assertEqual(qr.get("tool"), "execute_query_by_subgraph_id")
        q = qr.get("args", {}).get("query", "")
        self.assertIn("liquidates", q, "query should target the Messari `liquidates` entity")
        self.assertIn("50000", q, "threshold must be parsed from '$50K'")
        self.assertIn("amountUSD_gt", q, "filter must use amountUSD_gt")

    def test_aave_liquidations_default_threshold(self):
        """No threshold mentioned → default applied, query still shape-correct."""
        result = self.fn("Give me a subgraph query for Aave liquidations")
        qr = result.get("query_ready") or {}
        q = qr.get("args", {}).get("query", "")
        self.assertIn("liquidates", q)
        self.assertIn("amountUSD_gt", q)

    def test_uniswap_v3_pool_template(self):
        result = self.fn("Write a GraphQL query for Uniswap V3 pools by TVL")
        qr = result.get("query_ready") or {}
        q = qr.get("args", {}).get("query", "")
        self.assertEqual(result["recommendation"], "subgraph-registry")
        self.assertIn("pools", q)
        self.assertIn("totalValueLockedUSD", q)

    def test_query_template_skipped_when_not_asking_for_query(self):
        """Plain 'aave liquidations' without 'write a query' should route normally, not hit template."""
        result = self.fn("recent Aave liquidations on Ethereum")
        # Non-template path for this still goes to graph-aave-mcp via keyword router
        self.assertEqual(result["recommendation"], "graph-aave-mcp")
        # Template path wouldn't have fired, so no templated query_ready
        # (but curl_example still exists from the MCP service entry)
        self.assertTrue(result.get("curl_example"))

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
            "limitless", "predict.fun",
            "resolution", "trader p&l", "indexer",
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
            "polymarket", "prediction market", "open interest",
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


class TestGreetingDetection(unittest.TestCase):
    """Verify _is_greeting handles common patterns."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")
        from a2a_server import _is_greeting
        self.fn = _is_greeting

    def test_basic_greetings(self):
        for g in ["hi", "hello", "hey", "yo", "howdy", "hola"]:
            self.assertTrue(self.fn(g), f"{g!r} should be a greeting")

    def test_greetings_case_insensitive(self):
        self.assertTrue(self.fn("Hello"))
        self.assertTrue(self.fn("HI"))

    def test_data_queries_not_greetings(self):
        for q in ["top USDC holders", "Aave liquidations", "Polymarket markets"]:
            self.assertFalse(self.fn(q), f"{q!r} should NOT be a greeting")


class TestBenchmarkMatching(unittest.TestCase):
    """Verify _match_benchmark_query catches known bot queries."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")
        from a2a_server import _match_benchmark_query
        self.fn = _match_benchmark_query

    def test_known_benchmarks_match(self):
        self.assertIsNotNone(self.fn("Which npm package should I use for Aave data?"))
        self.assertIsNotNone(self.fn("Token API vs subgraph for Uniswap pool data?"))
        self.assertIsNotNone(self.fn("Top 20 USDC holders on Ethereum"))

    def test_case_insensitive(self):
        self.assertIsNotNone(self.fn("TOP 20 USDC HOLDERS ON ETHEREUM"))

    def test_unknown_queries_dont_match(self):
        self.assertIsNone(self.fn("What is the weather?"))
        self.assertIsNone(self.fn("Aave liquidations above 50K"))

    def test_returns_correct_service(self):
        r = self.fn("Which npm package should I use for Aave data?")
        self.assertEqual(r["recommendation"], "graph-aave-mcp")
        r = self.fn("Top 20 USDC holders on Ethereum")
        self.assertEqual(r["recommendation"], "token-api")


class TestPolymarketRouting(unittest.TestCase):
    """Polymarket should route to token-api by default, MCP for advanced queries."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")
        from advocate import _fallback_route
        self.fn = _fallback_route

    def test_basic_polymarket_to_token_api(self):
        for q in ["Polymarket markets", "Polymarket OHLCV", "Polymarket user P&L"]:
            r = self.fn(q)
            self.assertEqual(r["recommendation"], "token-api", f"{q!r} should route to token-api")

    def test_advanced_polymarket_to_mcp(self):
        # CLOB-specific advanced features (orderbook depth, spread, disputes, resolution,
        # drawdown) still route to the MCP wrapper.
        for q in ["Polymarket live orderbook", "Polymarket spread", "Polymarket disputed markets",
                   "Polymarket resolution status", "Polymarket drawdown stats"]:
            r = self.fn(q)
            self.assertEqual(r["recommendation"], "graph-polymarket-mcp",
                             f"{q!r} should route to graph-polymarket-mcp")

    def test_polymarket_trader_intel_to_own_endpoints(self):
        # Trader-intelligence queries route to GA's own /polymarket/* paid endpoints
        # (skill scoring, ghost-fill risk, screening) instead of upstream wrappers.
        for q in ["Score Polymarket wallet 0xabc",
                   "Is this Polymarket trader sharp money or retail?",
                   "Polymarket trader winrate",  # win-rate IS a derived metric in /pnl-quick
                   "Will this Polymarket maker's fill settle?",
                   "Screen top 10 holders of Polymarket market 0x...",
                   "Polymarket ghost-fill counterparty risk for 0x..."]:
            r = self.fn(q)
            self.assertEqual(r["recommendation"], "polymarket-token-api",
                             f"{q!r} should route to polymarket-token-api")


class TestCompareRoute(unittest.TestCase):
    """_compare_route should detect multi-service comparison requests."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")
        from advocate import _compare_route
        self.fn = _compare_route

    def test_detects_comparison(self):
        result = self.fn("Token API vs subgraph for Uniswap")
        self.assertIsNotNone(result)
        self.assertEqual(result["recommendation"], "comparison")

    def test_no_comparison_single_service(self):
        result = self.fn("top USDC holders")
        self.assertIsNone(result)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestExtractJson))
    suite.addTests(loader.loadTestsFromTestCase(TestFallbackRoute))
    suite.addTests(loader.loadTestsFromTestCase(TestInjectMissingFields))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoSearchKeywords))
    suite.addTests(loader.loadTestsFromTestCase(TestServiceCurlExamples))
    suite.addTests(loader.loadTestsFromTestCase(TestGreetingDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestBenchmarkMatching))
    suite.addTests(loader.loadTestsFromTestCase(TestPolymarketRouting))
    suite.addTests(loader.loadTestsFromTestCase(TestCompareRoute))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
