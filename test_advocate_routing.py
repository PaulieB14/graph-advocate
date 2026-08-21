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

    # Regression: "swap" inside "uniswap" (sushiswap, pancakeswap…) used to hijack
    # subgraph-discovery questions to token-api via a naive substring match.
    def test_subgraph_discovery_uniswap_not_token_api(self):
        self._check("What subgraphs are available for Uniswap?", "subgraph-registry")

    def test_subgraph_discovery_sushiswap_not_token_api(self):
        self._check("which subgraph indexes Sushiswap?", "subgraph-registry")

    def test_standalone_swap_still_token_api(self):
        self._check("swap volume on ethereum", "token-api")

    def test_plural_holders_still_token_api(self):
        self._check("USDC holders on Base", "token-api")

    # B20 — Base's enshrined token standard, shipping with the Beryl hardfork
    # on 2026-06-25. Drop-in ERC-20 selector parity, so balance/holder reads
    # belong on token-api; the rebase-multiplier and Asset-variant nuances
    # surface via the reason text rather than a separate route.
    def test_b20_balance_routes_to_token_api(self):
        self._check("show me my USDB balance on Base", "token-api")

    def test_b20_holders_routes_to_token_api(self):
        self._check("top B20 stablecoin holders", "token-api")

    def test_b20_scaled_balance_routes_to_token_api(self):
        self._check("scaledBalanceOf for a B20 Asset variant", "token-api")

    # B20 compliance metadata — PolicyRegistry + ActivationRegistry precompiles.
    # Same routing target as B20 token reads (token-api over precompile addrs),
    # but a different gotcha surface (isAuthorized never reverts; isActive must
    # be checked per-feature even post-Beryl).
    def test_policy_registry_routes_to_token_api(self):
        self._check("is account 0xabc on the PolicyRegistry allowlist", "token-api")

    def test_blocklist_routes_to_token_api(self):
        self._check("which addresses are on the B20 blocklist", "token-api")

    def test_freeze_and_seize_routes_to_token_api(self):
        self._check("freeze and seize events for B20 Asset variant", "token-api")

    # Basenames — ENS-on-Base. Subgraph routing for "list names owned by X" and
    # for "who owns alice.base.eth" (resolver indexed by subgraphs).
    def test_basenames_owner_routes_to_subgraph(self):
        self._check("who owns alice.base.eth", "subgraph-registry")

    def test_basenames_list_routes_to_subgraph(self):
        self._check("list basenames owned by 0xabc", "subgraph-registry")

    # L2 EAS attestations — predeployed at 0x4200…0020/0021. Routes to a Base
    # EAS subgraph for "what attestations does wallet X have?".
    def test_eas_attestations_routes_to_subgraph(self):
        self._check("attestations issued to wallet 0xabc on Base", "subgraph-registry")

    def test_sign_in_with_base_routes_to_subgraph(self):
        self._check("Sign In With Base verification status for 0xabc", "subgraph-registry")

    # EIP-7702 EOA delegation — tx-level data via substreams; token-api can't
    # surface authorization_list field on transactions.
    def test_eip7702_delegation_routes_to_substreams(self):
        self._check("is EOA 0xabc using EIP-7702 delegation", "substreams")

    def test_authorization_list_routes_to_substreams(self):
        self._check("show me transactions with authorization list on Base", "substreams")

    # Beryl multi-proof withdrawal finalization — token-api can read L1
    # OptimismPortal + DisputeGameFactory state.
    def test_withdrawal_finalization_routes_to_token_api(self):
        self._check("when will my Base withdrawal finalize", "token-api")

    def test_multi_proof_routes_to_token_api(self):
        self._check("multi-proof status for my pending withdrawal", "token-api")

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
        """The template must rank by volumeUSD and must NOT select TVL.

        This assertion was inverted on 2026-08-19. It previously required
        totalValueLockedUSD in the generated query, encoding the very behaviour
        that shipped wrong numbers: on the native V3 deployment that field is
        accumulated from per-event deltas and measured 22.7x above real on-chain
        balances (USDC/WETH 0.3%, 6.1M USDC on chain vs 138.9M reported). The
        caller runs query_ready verbatim, so selecting it put an order-of-
        magnitude error into the machine-readable payload.

        Note the request still says "by TVL" — the anti-TVL rule deliberately
        overrides the caller's wording and the answer explains the substitution.
        """
        result = self.fn("Write a GraphQL query for Uniswap V3 pools by TVL")
        qr = result.get("query_ready") or {}
        q = qr.get("args", {}).get("query", "")
        self.assertEqual(result["recommendation"], "subgraph-registry")
        self.assertIn("pools", q)
        self.assertIn("orderBy: volumeUSD", q)
        self.assertNotIn("totalValueLockedUSD", q)

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
            # Base ecosystem primitives — Basenames + L2 EAS attestations.
            "basename", "basenames", "base.eth",
            "attestation", "attestations", "ethereum attestation",
            "sign in with base", "base verify", "coinbase verification",
        ]
        self.TOKEN_API_KEYWORDS = [
            "balance", "holder", "transfer", "wallet", "nft",
            "erc20", "erc721", "dex", "ohlc",
            "solana", "ton", "svm", "tvm",
            "swap", "price", "volume", "whale", "top holder", "biggest",
            "largest", "richest", "portfolio", "token amount",
            "usdc", "usdt", "weth", "eth holder", "btc holder",
            # B20 — Base's enshrined token standard (Beryl hardfork, 2026-06-25)
            # plus compliance metadata (PolicyRegistry / ActivationRegistry)
            # and Beryl multi-proof withdrawal status.
            "b20", "usdb", "scaledbalanceof",
            "policyregistry", "policy registry", "allowlist", "blocklist",
            "freeze and seize", "activationregistry", "activation registry",
            "withdrawal finalization", "withdrawal status", "multi-proof",
            "multiproof", "dispute game", "optimismportal",
            "nft sale", "nft floor", "nft owner",
            "polymarket", "prediction market", "open interest",
        ]
        self.SUBSTREAMS_KEYWORDS = [
            "substream", "raw block", "event log", "trace", "streaming",
            "block data", "decode", "spkg",
            "real-time", "realtime", "firehose", "sink", "pipeline",
            "eip-7702", "eip7702", "7702 delegation", "7702 authorization",
            "authorization list",
        ]

    def _run_subgraph(self, text):
        return self._any_word_match(self.SUBGRAPH_KEYWORDS, text.lower())

    def _run_token(self, text):
        return self._any_word_match(self.TOKEN_API_KEYWORDS, text.lower())

    def _run_substreams(self, text):
        return self._any_word_match(self.SUBSTREAMS_KEYWORDS, text.lower())

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

    def test_basename_triggers_subgraph(self):
        self.assertTrue(self._run_subgraph("resolve alice.base.eth"))

    def test_attestation_triggers_subgraph(self):
        self.assertTrue(self._run_subgraph("attestations on Base for 0xabc"))

    def test_policy_registry_triggers_token_api(self):
        self.assertTrue(self._run_token("PolicyRegistry allowlist check"))

    def test_withdrawal_finalization_triggers_token_api(self):
        self.assertTrue(self._run_token("withdrawal finalization on Base"))

    def test_eip7702_triggers_substreams(self):
        self.assertTrue(self._run_substreams("EIP-7702 delegation on Base"))


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

    def test_agent_intros_are_greetings(self):
        """As of 2026-05-11: Agentverse-discovered agents (e.g. Sylex Commons)
        broadcast intros with patterns like 'I am an AI agent' that have no
        Graph routing intent but used to fall through to the Claude classifier
        (paid path). Catching them at the greeting fast-path saves a Claude
        call and gives the agent ecosystem a friendly first impression."""
        agent_intros = [
            "I am an AI agent. What do you do?",
            "Hello Graph Advocate! I am Silas from Sylex Commons, a community of 14 AI agents.",
            "Hi! We are a community of AI agents who communicate through shared memory.",
            "Hey from Silas, another AI agent. When you route onchain data...",
            "I'm Silas from the Sylex Commons — a community of 10 AI agents.",
        ]
        for q in agent_intros:
            self.assertTrue(self.fn(q), f"{q!r} should be detected as an agent intro greeting")

    def test_real_queries_with_ai_keyword_still_not_greetings(self):
        """Sanity: queries about AI-related onchain data should still route
        normally, not get bounced to the introduction handler."""
        real_queries = [
            "Top 10 USDC holders on Ethereum",
            "Find me an Aave V3 subgraph for Arbitrum",
            "GraphQL query for Uniswap V3 pools by TVL on Base",
        ]
        for q in real_queries:
            self.assertFalse(self.fn(q), f"{q!r} should NOT be flagged as a greeting")


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


class TestHyperliquidRouting(unittest.TestCase):
    """Hyperliquid: raw market data → token-api; trader/vault/risk intel → hyperliquid-token-api."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")
        from advocate import _fallback_route
        self.fn = _fallback_route

    def test_raw_hyperliquid_to_token_api(self):
        for q in ["Top Hyperliquid markets",
                   "Hyperliquid BTC perp open interest",
                   "List builder-deployed DEXs on Hyperliquid",
                   "Hyperliquid platform 24h volume"]:
            r = self.fn(q)
            self.assertEqual(r["recommendation"], "token-api",
                             f"{q!r} should route to token-api")

    def test_hyperliquid_trader_intel_to_own_endpoints(self):
        for q in ["Score Hyperliquid trader 0xabc",
                   "Is this Hyperliquid perps trader sharp or retail?",
                   "Evaluate Hyperliquid vault 0xabc",
                   "Liquidation risk for Hyperliquid trader 0xabc",
                   "Funding burn for Hyperliquid wallet 0xabc",
                   "Should I deposit into this Hyperliquid vault?"]:
            r = self.fn(q)
            self.assertEqual(r["recommendation"], "hyperliquid-token-api",
                             f"{q!r} should route to hyperliquid-token-api")

    def test_hip4_outcomes_to_token_api(self):
        """HIP-4 outcome market queries → token-api (Pinax v3.21.0-pre1)."""
        for q in ["Hyperliquid HIP-4 outcome leaderboard",
                  "Show settle_fraction for outcome 42",
                  "Outcome leg OHLC for question 7",
                  "Outcome composition mint redeem activity",
                  "Outcome positions for wallet 0xabc on Hyperliquid",
                  "Top traders on Hyperliquid outcome markets"]:
            r = self.fn(q)
            self.assertEqual(r["recommendation"], "token-api",
                             f"{q!r} should route to token-api")

    def test_hip4_outcomes_without_hyperliquid_keyword(self):
        """HIP-4 keywords alone (no 'hyperliquid') still route to token-api."""
        for q in ["outcome leaderboard",
                  "settle_fraction analysis",
                  "outcome composition flow"]:
            r = self.fn(q)
            self.assertEqual(r["recommendation"], "token-api",
                             f"{q!r} should route to token-api via HIP-4 fallback")


class TestPayerCapture(unittest.TestCase):
    """_extract_payer_addr should pull the EVM 'from' address from a verified
    x402 PaymentPayload regardless of how the SDK shapes the payload tree
    (dict, dataclass with model_dump, dataclass with dict()). The middleware
    contract is: payer never blocks the request — return None on structural
    mismatch, never raise."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ.setdefault("ACTIVITY_DB_PATH", "/tmp/test_paid_payer.db")
        import a2a_server as _srv
        self._srv = _srv

    def test_dict_payload_with_authorization_from(self):
        # The shape PaymentMiddlewareASGI sets on request.state today for
        # the exact EVM scheme — a pydantic model whose .payload is a dict
        # containing "authorization" with a "from" address.
        class _PP:
            payload = {"authorization": {"from": "0xAaBbCc11223344556677889900AaBbCc11223344"}}
        out = self._srv._extract_payer_addr(_PP())
        self.assertEqual(out, "0xaabbcc11223344556677889900aabbcc11223344")

    def test_pydantic_payload_with_model_dump(self):
        class _Auth:
            def model_dump(self): return {"from": "0xDDee00ff11223344556677889900aaBbCcDD00ff"}
        class _Payload:
            def model_dump(self): return {"authorization": _Auth()}
        class _PP:
            payload = _Payload()
        out = self._srv._extract_payer_addr(_PP())
        self.assertEqual(out, "0xddee00ff11223344556677889900aabbccdd00ff")

    def test_permit2_authorization_path(self):
        # Permit2 scheme stores signer under permit2_authorization.from
        class _PP:
            payload = {"permit2_authorization": {"from_address": "0xFEdcba9876543210FEDCBA9876543210FEDCBA98"}}
        out = self._srv._extract_payer_addr(_PP())
        self.assertEqual(out, "0xfedcba9876543210fedcba9876543210fedcba98")

    def test_returns_none_on_malformed_payload(self):
        # Each of these is structurally wrong somewhere — must NOT raise.
        cases = [
            None,
            {"payload": None},
            {"payload": "not-a-dict"},
            type("X", (), {"payload": None})(),
            type("X", (), {"payload": {}})(),
            type("X", (), {"payload": {"authorization": None}})(),
            type("X", (), {"payload": {"authorization": {}}})(),
            type("X", (), {"payload": {"authorization": {"from": ""}}})(),
        ]
        for case in cases:
            self.assertIsNone(
                self._srv._extract_payer_addr(case),
                f"expected None for malformed payload {case!r}",
            )


class TestPaymentPayloadFromScope(unittest.TestCase):
    """_payment_payload_from_scope must find the payload the way Starlette
    ACTUALLY stores it.

    Regression test for the 2026-08-18 finding: TestPayerCapture above passed
    the whole time while production attribution was dead, because it tested
    _extract_payer_addr in isolation and never exercised the scope read. The
    middleware did getattr() on scope["state"], which Starlette makes a plain
    dict — so payment_payload was invisible on every paid request for two
    months. Assert against real Starlette, not a hand-built stand-in."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ.setdefault("ACTIVITY_DB_PATH", "/tmp/test_paid_payer.db")
        import a2a_server as _srv
        self._srv = _srv

    def test_reads_payload_written_via_real_starlette_request_state(self):
        # The exact mechanism x402 2.8.0 uses: request.state.payment_payload = X
        from starlette.requests import Request
        scope = {"type": "http", "headers": [], "method": "POST", "path": "/route"}
        req = Request(scope)
        class _PP:
            payload = {"authorization": {"from": "0xAaBbCc11223344556677889900AaBbCc11223344"}}
        req.state.payment_payload = _PP()
        got = self._srv._payment_payload_from_scope(scope)
        self.assertIsNotNone(
            got, "payload written via request.state must be readable from the raw scope",
        )
        # And it must survive the full path into an address.
        self.assertEqual(
            self._srv._extract_payer_addr(got),
            "0xaabbcc11223344556677889900aabbcc11223344",
        )

    def test_reads_object_style_state_too(self):
        # A State instance (or any future object-shaped state) still works.
        class _State:
            payment_payload = "SENTINEL"
        self.assertEqual(
            self._srv._payment_payload_from_scope({"state": _State()}), "SENTINEL",
        )

    def test_returns_none_on_free_traffic(self):
        # No payment → None, never a raise. Free traffic is the common case.
        for scope in ({}, {"state": None}, {"state": {}}, {"state": "nonsense"},
                      {"state": {"other_key": 1}}):
            self.assertIsNone(
                self._srv._payment_payload_from_scope(scope),
                f"expected None for unpaid scope {scope!r}",
            )


class TestLogPaidFailureNormalization(unittest.TestCase):
    """_log_paid_failure should normalize non-Exception args so the row never
    silently shows exception_type='str' (bug observed 2026-06-18T05:33Z on the
    onchain-x402-address handler, which passed the literal string 'timeout')."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        # Avoid touching the real activity DB
        os.environ["LOG_PATH"] = "/tmp/test_paid_failure_logs.json"
        os.environ["ACTIVITY_DB_PATH"] = "/tmp/test_paid_failure_activity.db"
        self.captured = []

        # Monkeypatch _log_request inside a2a_server so we can capture args
        import a2a_server as _srv
        self._srv = _srv
        self._orig = _srv._log_request
        def _capture(*args, **kwargs):
            self.captured.append({"args": args, "kwargs": kwargs})
        _srv._log_request = _capture

    def tearDown(self):
        self._srv._log_request = self._orig

    def _row(self):
        self.assertEqual(len(self.captured), 1)
        c = self.captured[0]
        # signature: (task_id, request, service, confidence, tool, response=...)
        return c["args"][4], c["kwargs"].get("response", {})

    def test_exception_arg_records_class_and_message(self):
        self._srv._log_paid_failure("desc", TimeoutError("upstream took too long"))
        tool, resp = self._row()
        self.assertEqual(tool, "TimeoutError")
        self.assertEqual(resp["exception_type"], "TimeoutError")
        self.assertEqual(resp["message"], "upstream took too long")

    def test_string_arg_does_not_leak_str_to_exception_type(self):
        # The historical bug: callers passing 'timeout' made exception_type='str'.
        # The normalized contract: exception_type becomes 'unknown', message
        # preserves the string content.
        self._srv._log_paid_failure("desc", "timeout")
        tool, resp = self._row()
        self.assertEqual(tool, "unknown")
        self.assertEqual(resp["exception_type"], "unknown")
        self.assertEqual(resp["message"], "timeout")

    def test_none_arg_does_not_crash(self):
        self._srv._log_paid_failure("desc", None)
        tool, resp = self._row()
        self.assertEqual(tool, "unknown")
        self.assertEqual(resp["exception_type"], "unknown")
        self.assertIn("no message", resp["message"])


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


class TestSubgraphExecExtraction(unittest.TestCase):
    """Pure-logic guards for subgraph_exec. Live behaviour lives in
    eval_delivery.py; these run offline so they stay in the fast suite."""

    def setUp(self):
        from subgraph_exec import extract_runnable, strip_false_capability_claims
        self.extract = extract_runnable
        self.strip = strip_false_capability_claims

    def _rec(self, **args):
        return {"query_ready": {"tool": "execute_query_by_subgraph_id", "args": args}}

    def test_extracts_subgraph_id_and_gql(self):
        got = self.extract(self._rec(subgraph_id="Abc123", gql="{ pools { id } }"))
        self.assertEqual(got, ("Abc123", "{ pools { id } }"))

    def test_accepts_query_alias_for_gql(self):
        got = self.extract(self._rec(subgraph_id="Abc123", query="{ pools { id } }"))
        self.assertEqual(got, ("Abc123", "{ pools { id } }"))

    def test_rejects_non_subgraph_tools(self):
        # REST services must never be "executed" as subgraph queries.
        self.assertIsNone(self.extract(
            {"query_ready": {"tool": "getV1EvmBalances", "args": {"network": "base"}}}))

    def test_rejects_incomplete_and_malformed(self):
        for bad in (None, "not a dict", {}, {"query_ready": None},
                    self._rec(subgraph_id="Abc123"), self._rec(gql="{ a }"),
                    self._rec(subgraph_id="  ", gql="{ a }")):
            self.assertIsNone(self.extract(bad), f"should reject: {bad!r}")

    def test_strips_false_capability_claims(self):
        reason = ("The Aave subgraph is purpose-built for this. "
                  "I cannot make live HTTP calls myself. "
                  "Use the curl below.")
        out = self.strip(reason)
        self.assertNotIn("cannot make live", out.lower())
        self.assertIn("purpose-built", out)
        self.assertIn("curl", out)

    def test_strip_never_returns_empty(self):
        # If every sentence was a false claim, keep the original rather than
        # handing the caller a blank reason.
        self.assertTrue(self.strip("I cannot execute queries."))
        self.assertEqual(self.strip(""), "")

    def test_strip_leaves_clean_prose_alone(self):
        clean = "The ENS subgraph indexes Domain entities with registrationDate."
        self.assertEqual(self.strip(clean), clean)


class TestUniswapTvlOverride(unittest.TestCase):
    """Uniswap subgraph TVL is inflated by spam pools (a single fake pool
    reports $1.1T TVL against $0 volume), so every Uniswap ranking must sort
    by volumeUSD. The prompt used to say both things in two places and the
    model coin-flipped; these pin the surfaces that must agree."""

    def test_static_benchmark_ranks_by_volume(self):
        import a2a_server
        gql = a2a_server._BENCHMARK_UNI_V3_ETH_POOLS["query_ready"]["args"]["gql"]
        self.assertIn("orderBy: volumeUSD", gql)
        self.assertNotIn("orderBy: totalValueLockedUSD", gql)

    def test_static_benchmark_discloses_the_substitution(self):
        import a2a_server
        reason = a2a_server._BENCHMARK_UNI_V3_ETH_POOLS["reason"].lower()
        self.assertIn("volumeusd", reason)
        self.assertIn("tvl", reason)

    def test_prompt_hint_agrees_with_the_anti_tvl_rule(self):
        import advocate
        hint = [l for l in advocate.SYSTEM.splitlines()
                if l.strip().startswith("- Uniswap V3:")]
        self.assertTrue(hint, "Uniswap V3 entity hint missing from prompt")
        self.assertIn("orderBy: volumeUSD", hint[0])


class TestPublishedPricesMatchTheCatalog(unittest.TestCase):
    """Every document that quotes a price must quote the one that is charged.

    The 2026-08-12 audit found four endpoints whose advertised price was 2x-2.5x
    what the x402 middleware actually takes, spread across llms.txt, SKILL.md,
    the README and the Mintlify docs. /llms.txt is `start_here` in
    /agents/index.json, so it is the first thing an autonomous agent reads to
    budget a run; quoting $0.05 and charging $0.02 is not a rounding error to a
    caller deciding whether it can afford you.

    `_PAID_CATALOG` is the single source - openapi.json and /.well-known/x402
    already derive from it, and it was verified against all 22 live 402
    challenges. These tests hold the hand-written surfaces to it.
    """

    def test_llms_txt_price_table_is_generated_not_typed(self):
        """The price column must come from the catalog, not from a literal."""
        import a2a_server as srv
        rows = srv._render_paid_price_rows()
        for key, entry in srv._PAID_CATALOG.items():
            price = entry.get("price")
            if not price or key in ("route", "tip"):
                continue
            match = [r for r in rows.split("\n") if f"POST {entry['path']} " in r]
            self.assertTrue(match, f"{entry['path']} missing from the rendered table")
            self.assertIn(
                price, match[0],
                f"{entry['path']} renders a price other than the catalog's {price}",
            )

    def test_openapi_entries_carry_what_the_spec_builder_reads(self):
        """`openapi: True` without `op_id`/`desc` returns 500 for the whole spec.

        Setting agent/score to `openapi: True` — to fix it being *absent* from
        openapi.json — shipped an entry with neither key, and the builder read
        `c["op_id"]` unguarded. The result was a KeyError out of a list
        comprehension and a 500 on the entire document, so one incomplete entry
        made all 22 endpoints undiscoverable to exactly the crawlers that file
        exists to serve. It stayed broken for a day.
        """
        import a2a_server as srv
        offenders = {
            key: [f for f in ("op_id", "desc", "price") if not entry.get(f)]
            for key, entry in srv._PAID_CATALOG.items()
            if entry.get("openapi")
        }
        offenders = {k: v for k, v in offenders.items() if v}
        self.assertEqual({}, offenders, f"openapi=True but missing required keys: {offenders}")

    def test_every_paid_endpoint_appears_on_the_agent_card(self):
        """A2A directories read the skills list to learn what GA sells.

        Four priced endpoints — /polymarket/leaders and all three /kalshi/*
        routes — were live and absent from it, so 8004scan, Agentverse and the
        A2A registry all under-reported the catalogue. An endpoint nobody can
        discover earns nothing.
        """
        import a2a_server as srv
        src = open("a2a_server.py", encoding="utf-8").read()
        start = src.find("AgentSkill(")
        block = src[start:src.find("\ndef ", start)]
        missing = [
            v["path"] for v in srv._PAID_CATALOG.values()
            if v.get("price") and v["path"] not in block
        ]
        self.assertEqual([], missing, f"priced but undiscoverable on the agent card: {missing}")

    def test_revenue_case_prices_match_the_catalog(self):
        """Reported revenue must use the prices actually charged.

        The hand-typed SQL ladders counted pm-pnl-quick at $0.02 (charges $0.01)
        and onchain-x402-address at $0.05 (charges $0.01, so five times over),
        and omitted uniswap/*, narrative, predmarket and agent/score entirely.
        Also pins the ordering trap: `pm-pnl%` matches `pm-pnl-quick…`, and SQL
        takes the first matching WHEN, so the longer prefix must come first.
        """
        import a2a_server as srv
        sql = srv._revenue_case_sql()
        for key, entry in srv._PAID_CATALOG.items():
            prefix, price = entry.get("log_prefix"), entry.get("price")
            if not (prefix and price):
                continue
            expected = f"WHEN request LIKE '{prefix}%' THEN {float(price.lstrip('$')):.2f}"
            self.assertIn(expected, sql, f"{key} priced wrongly in the revenue CASE")
        lines = [l.strip() for l in sql.split("\n")]
        quick = next(i for i, l in enumerate(lines) if "'pm-pnl-quick%'" in l)
        full = next(i for i, l in enumerate(lines) if "'pm-pnl%'" in l)
        self.assertLess(quick, full, "pm-pnl% would shadow pm-pnl-quick%")

    def test_get_signpost_can_quote_a_price_for_every_paid_path(self):
        """A GET on a paid path must be able to name its price.

        Paid routes are POST-only (a GET used to hang ~10s on `request.body()`),
        so Starlette answered every GET with 18 bytes of text/plain "Method Not
        Allowed". Discovery bots GET a URL before they POST one, and that reply
        carries no price, no verb and no body shape — a working priced endpoint
        reads as broken to the exact crawlers that would send it customers.

        The 405 handler now renders the catalog entry instead. It resolves the
        two deliberately-blank entries — `/route` bills the flat
        `X402_PRICE_CENTS` query price, `/tip` takes any amount — and this test
        pins that list closed: a NEW blank-price endpoint would otherwise
        silently emit `"price": ""` and a message quoting no price at all, which
        is worse than the bare 405 it replaced.
        """
        import a2a_server as srv
        dynamic = {"/route", "/tip"}
        blank = [
            v["path"] for v in srv._PAID_CATALOG.values()
            if not v.get("price") and v["path"] not in dynamic
        ]
        self.assertEqual(
            [], blank,
            f"priced-endpoint GET would quote an empty price for: {blank}. "
            "Give it a catalog price, or teach the 405 handler how to resolve it.",
        )

    def test_no_markdown_surface_contradicts_the_catalog(self):
        """README, SKILL.md and docs/*.mdx must not quote a different price."""
        import a2a_server as srv
        import glob, os, re
        catalog = {v["path"]: v.get("price") for v in srv._PAID_CATALOG.values()}
        targets = (
            glob.glob("docs/**/*.mdx", recursive=True)
            + glob.glob("docs/**/*.md", recursive=True)
            + ["README.md", "openclaw-skill/graph-advocate/SKILL.md"]
        )
        offenders = []
        path_re = re.compile(
            r"(/(?:polymarket|hyperliquid|kalshi[\w-]*|uniswap|predmarket|narrative|onchain-x402|agent)/[a-z-]+)"
        )
        for f in targets:
            if not os.path.exists(f):
                continue
            for i, line in enumerate(open(f, encoding="utf-8"), 1):
                p = path_re.search(line)
                money = re.search(r"\$0\.\d\d", line)
                if not (p and money):
                    continue
                real = catalog.get(p.group(1))
                if real and money.group(0) != real:
                    offenders.append(f"{f}:{i} {p.group(1)} says {money.group(0)}, charges {real}")
        self.assertEqual([], offenders, "published prices disagree with the catalog:\n" + "\n".join(offenders))


class TestNoUnpublishedPackagesRecommended(unittest.TestCase):
    """GA must never hand an agent an install command that 404s.

    Three packages GA recommended were unpublished from npm inside two weeks —
    predictfun-mcp (2026-08-05), substreams-search-mcp (2026-08-11) and
    create-substreams-sink-sql (2026-08-17) — and GA kept emitting `npx <name>`
    for all three. GA's entire value is "the right tool, and how to run it";
    an uninstallable recommendation burns the caller's call and teaches them
    the answers are stale.

    Offline by design: this is a denylist, not a live npm probe, so the suite
    stays hermetic. When a package is unpublished, add it here — the test then
    points at every surface still advertising it."""

    UNPUBLISHED = {
        "predictfun-mcp": "2026-08-05",
        "substreams-search-mcp": "2026-08-11",
        "create-substreams-sink-sql": "2026-08-17",
    }

    def test_no_npx_install_line_for_an_unpublished_package(self):
        import advocate
        haystacks = {"SYSTEM prompt": advocate.SYSTEM,
                     "CHAT_SYSTEM prompt": advocate.CHAT_SYSTEM}
        for name, meta in (getattr(advocate, "_SERVICE_CURL_EXAMPLES", {}) or {}).items():
            for key in ("install", "curl_example", "get_started"):
                val = (meta or {}).get(key)
                if isinstance(val, str):
                    haystacks[f"_SERVICE_CURL_EXAMPLES[{name}].{key}"] = val
        self._assert_clean(haystacks)

    def test_no_markdown_surface_advertises_an_unpublished_package(self):
        """README, REFERENCE, SKILL.md and docs/*.mdx are read by humans and
        crawled by LLM tooling — a dead `npx` line there outlives the prompt fix.
        Mirrors test_no_markdown_surface_contradicts_the_catalog."""
        import glob
        root = os.path.dirname(os.path.abspath(__file__))
        targets = ["README.md", "REFERENCE.md", "CLAUDE.md",
                   "openclaw-skill/graph-advocate/SKILL.md"]
        targets += [os.path.relpath(p, root) for p in glob.glob(os.path.join(root, "docs", "*.mdx"))]
        haystacks = {}
        for rel in targets:
            path = os.path.join(root, rel)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    haystacks[rel] = fh.read()
        self.assertTrue(haystacks, "found no markdown surfaces to check")
        self._assert_clean(haystacks)

    def _assert_clean(self, haystacks):
        for pkg, when in self.UNPUBLISHED.items():
            for where, text in haystacks.items():
                for cmd in (f"npx {pkg}", f"npx -y {pkg}", f"npm install {pkg}"):
                    self.assertNotIn(
                        cmd, text,
                        f"{where} still tells agents to run `{cmd}`, but {pkg} was "
                        f"unpublished from npm on {when} — the command 404s.",
                    )


class TestSubstreamsRegistryFieldNames(unittest.TestCase):
    """The Substreams registry response shape must be stated, not guessed.

    Observed live 2026-08-19: GA answered a substreams question with the right
    tool and the right install command, then a jq filter of
    `.results[] | {name, network, version, spkg_url}` — three wrong names. The
    API returns {"hasMore":…, "packages":[{name, slug, repository, downloads,
    releaseCount, latestVersion, network, spkg, reference}]}, so that filter
    returns NOTHING. Silent-empty is worse than an error: the caller concludes
    the registry has no Uniswap packages.

    Root cause was omission, not misstatement — the prompt named `spkg` and
    `reference` and said nothing about the envelope, so the model filled the gap
    with plausible names. The fix is stating the shape; this test guards it."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        import advocate
        self.advocate = advocate
        self.haystack = advocate.SYSTEM + (
            (advocate._SERVICE_CURL_EXAMPLES.get("substreams") or {}).get("curl_example") or "")

    def test_prompt_states_the_real_envelope_and_field_names(self):
        for token in ("packages", "latestVersion", "spkg"):
            self.assertIn(token, self.haystack,
                          f"routing prompt never names `{token}`, so the model has to guess it")

    def test_prompt_warns_off_the_names_the_model_invented(self):
        # Naming the wrong forms explicitly is what stops them recurring — the
        # model reached for these exact three when left to improvise.
        for wrong in ("results", "spkg_url"):
            self.assertIn(wrong, self.haystack,
                          f"prompt should explicitly warn that `{wrong}` is NOT the right name")

    def test_static_example_uses_a_filter_that_would_actually_match(self):
        ex = (self.advocate._SERVICE_CURL_EXAMPLES.get("substreams") or {}).get("curl_example") or ""
        self.assertIn(".packages[]", ex,
                      "the canned example is the template the model copies — it must use .packages[]")
        self.assertNotIn(".results[]", ex)


class TestExtractJsonAlwaysReturnsDict(unittest.TestCase):
    """_extract_json must return a dict for ANY model output.

    Reproduced live 2026-08-19: a question ending "give me runnable calls for
    both" makes the model answer with a top-level ARRAY. Four json.loads paths
    passed it straight through, callers did rec.get(...), and the paid /route
    handler raised AttributeError AFTER payment settled — the caller was charged
    and got a 500."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        import advocate
        self.advocate = advocate

    def test_every_shape_coerces_to_dict(self):
        cases = [
            '[{"recommendation":"comparison"}]',
            '```json\n[{"a":1}]\n```',
            '{"recommendation":"token-api"}',
            'not json at all',
            '"a bare string"',
            '42',
            '[]',
            '[1,2,3]',
            '```\n[{"recommendation":"x"}]\n```',
        ]
        for raw in cases:
            out = self.advocate._extract_json(raw)
            self.assertIsInstance(
                out, dict, f"_extract_json({raw[:40]!r}) returned {type(out).__name__}")
            out.get("parse_error")   # must not raise

    def test_list_answer_keeps_the_first_and_demotes_the_rest(self):
        out = self.advocate._extract_json(
            '[{"recommendation":"token-api","reason":"a"},'
            ' {"recommendation":"subgraph-registry","reason":"b"}]')
        self.assertEqual(out["recommendation"], "token-api")
        self.assertTrue(out.get("_unwrapped_from_list"))
        self.assertIn("subgraph-registry", [a["service"] for a in out["alternatives"]])


class TestGreetingDoesNotSwallowDataQuestions(unittest.TestCase):
    """A data question is never a greeting.

    `"ai agent"` was a bare greeting phrase, so "Which subgraph tracks USDC
    transfers for AI agent wallets on Base?" returned the canned intro — and
    because _is_greeting feeds is_canned_path, which gates the x402 check, it
    was served free as well. GA sells to the agent economy; that phrase is the
    most common noun in its market's vocabulary."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ.setdefault("ACTIVITY_DB_PATH", "/tmp/test_greeting.db")
        import a2a_server
        self.srv = a2a_server

    def test_data_questions_mentioning_ai_agents_are_not_greetings(self):
        for q in [
            "Which subgraph tracks USDC transfers for AI agent wallets on Base? Give me the subgraph id and a GraphQL query.",
            "How do I look up an AI agent registered under ERC-8004? Give me a runnable API call.",
            "What service should I use to get wallet balances for an AI agent?",
        ]:
            self.assertFalse(self.srv._is_greeting(q), f"treated as a greeting: {q[:60]}")

    def test_real_greetings_still_classified(self):
        for q in ["hi", "ping", "hello", "Hello! What can you do?",
                  "I am an AI agent exploring the ecosystem",
                  "We are a community of agents saying hello"]:
            self.assertTrue(self.srv._is_greeting(q), f"missed greeting: {q[:60]}")

    def test_bare_ai_agent_is_not_a_greeting_phrase(self):
        self.assertNotIn("ai agent", self.srv._GREETING_PHRASES)
        self.assertNotIn("ai agents", self.srv._GREETING_PHRASES)


class TestBillingEventsNeverCached(unittest.TestCase):
    """402 bodies must never be servable as answers.

    Logging the 402 challenge (2026-08-18, for auditability) armed a latent bug:
    the cache SELECT excluded several services but not 'payment-required', and
    was protected only by `response_json IS NOT NULL` — which had been true of
    all 762 such rows until that day. Within hours 13 live 402s sat in the
    200-row cache window inside the 1h TTL, replayable to a PAYING caller."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ.setdefault("ACTIVITY_DB_PATH", "/tmp/test_cache.db")
        import a2a_server
        self.srv = a2a_server
        import inspect
        self.src = inspect.getsource(a2a_server._get_cached_response)

    def test_billing_services_excluded_from_the_cache_query(self):
        for svc in ("payment-required", "x402-failed", "blocked"):
            self.assertIn(f"'{svc}'", self.src,
                          f"cache SELECT does not exclude {svc}")

    def test_content_filter_backstops_rows_already_written(self):
        # A service-name filter cannot retract rows already in the table, so the
        # loop must also reject on the parsed recommendation.
        self.assertIn("_NEVER_CACHE_RECS", self.src)
        for rec in ("payment-required", "payment-failed"):
            self.assertIn(f'"{rec}"', self.src)

    def test_paid_requests_bypass_the_cache_entirely(self):
        import inspect
        exec_src = inspect.getsource(self.srv.GraphAdvocateExecutor)
        self.assertIn("None if _is_paid_request else _get_cached_response", exec_src,
                      "a paid call must never be answered from cache")


class TestSubstreamsInjectorMirrorsUpstream(unittest.TestCase):
    """GA's own search injection must not rename upstream fields.

    _search_substreams read `latestVersion`/`spkg`/`hasMore` correctly and
    re-emitted them as `version`/`spkg_url`/`results`. That JSON goes into the
    model's context, so the model's `jq '.results[] | {version, spkg_url}'` was
    an accurate description of what GA handed it — and matched nothing against
    the real API. Concrete JSON beats prompt prose, so the prompt rule alone
    would have looked landed and stayed broken."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        import advocate, inspect
        self.src = inspect.getsource(advocate._search_substreams)

    def test_emits_upstream_names(self):
        for good in ('"packages"', '"latestVersion"', '"spkg"', '"hasMore"'):
            self.assertIn(good, self.src, f"injector no longer emits {good}")

    def test_does_not_emit_the_renamed_vocabulary(self):
        for bad in ('"results":', '"spkg_url"', '"has_more"'):
            self.assertNotIn(bad, self.src,
                             f"injector still emits {bad}, which the model will copy into jq")


class TestNativeUniswapTvlNeverEmitted(unittest.TestCase):
    """Never select totalValueLockedUSD from a native Uniswap V3 deployment.

    Measured 2026-08-19 on the canonical USDC/WETH 0.3% pool
    0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8:
        native 5zvR82…  138,939,548 USDC / 61,692 WETH  ($267.2M)
        Messari 4cKy6QQ…  6,350,287 USDC /  5,455 WETH  ($17.7M)
        on-chain          6,110,083 USDC /  5,337 WETH
    The native deployment accumulates locked balances from per-event deltas and
    drifts — 22.7x and 11.6x high on a blue-chip pool, so the pre-existing
    "spam pools" rule does not explain it and did not prevent it. GA was
    returning that column AND vouching for it in `reason`.

    Note the two rules stack rather than cancel: the Messari fork is accurate
    per-pool but still must not be ranked by TVL (a fake Wrapped Ether/Yescoin
    pair reports $94B there), which is why the anti-ranking rule stays."""

    NATIVE_V3 = "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV"
    MESSARI = "4cKy6QQMc5tpfdx8yxfYeb9TLZmgLQe44ddW1G7NwkA6"

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        import advocate
        self.advocate = advocate

    def test_uniswap_curl_example_does_not_select_native_tvl(self):
        ex = (self.advocate._SERVICE_CURL_EXAMPLES.get("subgraph-registry") or {}).get("curl_example") or ""
        self.assertIn(self.NATIVE_V3, ex, "example should still show the native deployment")
        # Assert on the GraphQL PAYLOAD, not the surrounding prose — the comments
        # deliberately name the field in order to explain why it is absent.
        native_section = ex.split(self.MESSARI)[0]
        queries = [ln for ln in native_section.splitlines()
                   if '-d ' in ln and '"query"' in ln]
        self.assertTrue(queries, "no runnable query found in the native example")
        for q in queries:
            self.assertNotIn("totalValueLockedUSD", q,
                             f"native-deployment query still selects TVL: {q[:120]}")

    def test_messari_alternative_is_offered_and_looked_up_by_id(self):
        ex = (self.advocate._SERVICE_CURL_EXAMPLES.get("subgraph-registry") or {}).get("curl_example") or ""
        self.assertIn(self.MESSARI, ex, "no accurate TVL source offered")
        self.assertIn("liquidityPool(id:", ex,
                      "must look the pool up BY ID — ranking the Messari fork by TVL "
                      "surfaces the same spam pools")

    def test_prompt_states_the_value_is_wrong_not_just_the_ranking(self):
        s = self.advocate.SYSTEM
        self.assertIn("22.7x", s, "prompt should carry the measured magnitude")
        self.assertIn(self.MESSARI, s, "prompt should name the accurate source")

    def test_generated_pool_query_omits_tvl(self):
        # The query builder feeds query_ready, which callers execute verbatim.
        import inspect
        src = inspect.getsource(self.advocate)
        marker = 'entity, extra = "pools", "feeTier"'
        self.assertIn(marker, src,
                      "the V3/V4 query builder must not append totalValueLockedUSD")


class TestTokenApiBalancesPagination(unittest.TestCase):
    """Never call one /v1/evm/balances request "all balances".

    Verified 2026-08-19 against the live API with a free-tier JWT: no `limit`
    returns 10 rows; `limit=100` and `limit=500` return HTTP 403. Vitalik's
    wallet holds hundreds of tokens, so a bare call is ~1% of the portfolio —
    returned with HTTP 200 and no error. The caller's next move is summing it
    into a net worth, which is then silently wrong. `&page=N` works at 10/page
    and the response carries no total, so 'page until short' is the only stop
    condition."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        import advocate
        self.advocate = advocate

    def test_prompt_states_the_page_size_and_the_403(self):
        s = self.advocate.SYSTEM
        self.assertIn("403", s, "prompt must warn that raising limit is forbidden on free tier")
        for token in ("page", "10"):
            self.assertIn(token, s)

    def test_prompt_forbids_calling_it_all_balances(self):
        s = self.advocate.SYSTEM
        self.assertIn('"all balances"', s,
                      "prompt should explicitly forbid the phrase that misleads callers")

    def test_curl_example_shows_the_pagination_loop(self):
        ex = (self.advocate._SERVICE_CURL_EXAMPLES.get("token-api") or {}).get("curl_example") or ""
        self.assertIn("/v1/evm/balances", ex, "balances call missing from the example")
        self.assertIn("page=", ex, "example must demonstrate pagination, not a single call")


class TestQueryReadyUsesToolParameterName(unittest.TestCase):
    """query_ready.args must key the GraphQL document as `query`, not `gql`.

    execute_query_by_subgraph_id's published schema is
    {"subgraph_id": str, "query": str}, both required — confirmed against the
    live tool definition 2026-08-19. query_ready exists so a caller can pass
    `args` straight to that tool, so a payload keyed `gql` fails validation with
    "missing required parameter: query" for every MCP consumer.

    It survived because GA's own executor reads
    `args.get("gql") or args.get("query")` — it worked everywhere except the
    integration it is published for. Normalizing on the way out (rather than
    only instructing the model) means a slip can't reach a caller."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        import advocate
        self.advocate = advocate

    def _norm(self, rec):
        return self.advocate._inject_missing_fields(rec, "give me a subgraph query")

    def test_gql_key_is_rewritten_to_query(self):
        rec = {"recommendation": "subgraph-registry",
               "query_ready": {"tool": "execute_query_by_subgraph_id",
                               "args": {"subgraph_id": "abc", "gql": "{ pools { id } }"}}}
        args = self._norm(rec)["query_ready"]["args"]
        self.assertIn("query", args, "GraphQL document must be published under `query`")
        self.assertNotIn("gql", args, "`gql` must not survive into the published payload")
        self.assertIn("pools", args["query"])

    def test_already_correct_payload_is_left_alone(self):
        rec = {"recommendation": "subgraph-registry",
               "query_ready": {"tool": "execute_query_by_subgraph_id",
                               "args": {"subgraph_id": "abc", "query": "{ pools { id } }"}}}
        args = self._norm(rec)["query_ready"]["args"]
        self.assertIn("query", args)
        self.assertNotIn("gql", args)

    def test_prompt_teaches_the_tool_parameter_name(self):
        s = self.advocate.SYSTEM
        self.assertIn("The key is `query`, NOT `gql`", s)


class TestFreeTierCopyMatchesTheGate(unittest.TestCase):
    """Never tell a caller that a `name` earns the free tier. It does not.

    The gate is wallet-only by construction: a2a_server.py ~2734 accepts a sender
    only if it is 42 chars starting with 0x, and ~2834 sets
    `sender_is_anonymous = not sender_wallet`. `name` is never consulted, because
    the daily allowance is counted per wallet and only an address can hold one.

    Four published surfaces said otherwise, and on 2026-08-21 that cost a real
    sale: activity row 8427, "Who are the biggest WETH holders on Base right
    now?" — an answerable question from a live agent — was told to "include a
    `sender` (wallet address) or `name` field ... to claim the 3 free
    queries/day". An agent that complies by adding `name` is re-402'd and retries
    into the same wall forever instead of paying. This is not a monetization
    question; the gate is correct. The COPY was lying about it."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ.setdefault("ACTIVITY_DB_PATH", "/tmp/test_freetier.db")
        import a2a_server
        self.srv = a2a_server

    def test_no_surface_offers_the_free_tier_for_a_name(self):
        import inspect
        src = inspect.getsource(self.srv)
        for bad in ("wallet address) or `name`", "wallet or `name`", "or `name` field"):
            self.assertNotIn(bad, src,
                             f"a published surface still claims a `name` earns the free tier: {bad!r}")

    def test_the_402_body_names_the_wallet_requirement(self):
        body = self.srv._x402_payment_required_response(anonymous=True, user_text="test")
        reason = body.get("reason") or ""
        self.assertIn("metadata.sender", reason,
                      "the 402 must say WHICH field to set")
        self.assertIn("0x", reason, "the 402 must say it has to be an address")
        self.assertIn("does NOT qualify", reason,
                      "the 402 must rule the `name` shortcut out explicitly — an agent that "
                      "tries it burns a round-trip and may never reach the pay path")
        # The pay rail itself was never broken; keep it that way.
        pv = body.get("pay_via_http") or {}
        self.assertTrue(pv.get("url") and pv.get("payment_header") == "X-PAYMENT",
                        "the 402 must still hand over a directly payable endpoint")


class TestRefusalScoring(unittest.TestCase):
    def test_headline_filter_is_a_superset_of_the_write_skip(self):
        """The read-side filter must cover everything the write-side skips.

        Skipping the write only protects rows created from now on. Any row
        written before a service joined the skip list keeps counting toward the
        headline average forever. On 2026-08-07 `blocked` had 2 such rows at
        score 1.00 — and tip / no-match / clarification-needed / unclear-request
        had 6 more between them, all scoring ~1.
        """
        import a2a_server as srv

        missing = srv._NON_ROUTING_SERVICES - srv._META_SERVICES_EXCLUDED_FROM_HEADLINE
        assert not missing, (
            f"services skipped at write time but still counted in the headline "
            f"average: {sorted(missing)}"
        )

    def test_refusal_services_are_not_quality_scored(self):
        """Refusals must never enter the quality metric.

        The 5-point rubric grades on query_ready / subgraph_id / curl / install. A
        correct refusal has none of them by construction, so scoring one records a 1
        and drags the average down for doing the right thing. On 2026-08-07 the new
        `blocked` service did exactly that: two MetaVision solicitations were dropped
        correctly and scored 1 each, pulling the 24h average to 2.33 against a 7-day
        4.09.

        This asserts on the write itself rather than on the constant, so adding a new
        refusal service and forgetting to exclude it fails here instead of showing up
        as a phantom quality drop days later.
        """
        import sqlite3
        import a2a_server as srv

        writes = []
        real_connect = sqlite3.connect

        class _Spy:
            def __init__(self, *a, **k):
                self._c = None

            def execute(self, sql, params=()):
                writes.append((sql, params))
                return self

            def commit(self):
                pass

            def close(self):
                pass

        sqlite3.connect = lambda *a, **k: _Spy()
        try:
            for service in ("blocked", "out-of-scope", "payment-required",
                            "introduction", "rate-limited", "chat"):
                writes.clear()
                srv._score_response("MetaVision offer - AI Inference",
                                    {"recommendation": service, "reason": "solicitor"})
                assert not writes, f"{service!r} was quality-scored; refusals must be skipped"

            # A real routing answer must still be scored, or the exclusion is too broad.
            writes.clear()
            srv._score_response("Top Aave V3 markets by TVL", {
                "recommendation": "subgraph-registry",
                "query_ready": {"tool": "execute_query_by_subgraph_id", "args": {}},
            })
            assert writes, "a routing answer was not scored"
        finally:
            sqlite3.connect = real_connect


if __name__ == "__main__":
    loader = unittest.TestLoader()
    # DISCOVER the module's TestCases instead of listing them by hand.
    #
    # This was a hand-maintained roster of 16 classes, and on 2026-08-18 two
    # newly added classes silently never ran — including the very regression
    # test written to catch a bug that had survived because its own coverage
    # was illusory. A test suite whose membership is typed rather than derived
    # fails exactly like the code it guards: quietly, and looking green.
    suite = loader.loadTestsFromModule(sys.modules[__name__])

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
