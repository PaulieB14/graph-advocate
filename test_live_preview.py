"""Tests for numfmt + live_preview + free_preview integration. Offline (gateway mocked).
Run: python test_live_preview.py"""
from __future__ import annotations

import os
import unittest
from unittest import mock

import free_preview as fp
import live_preview as lp
import numfmt

UNI_DATA = {
    "_meta": {"block": {"number": 26395637, "timestamp": 1794447671}},
    "pools": [
        {"id": "0x88e6", "feeTier": "500", "volumeUSD": "609167447506.1830892627042412837456",
         "totalValueLockedUSD": "363095785.5150252058840355529469255",
         "token0": {"symbol": "USDC"}, "token1": {"symbol": "WETH"}},
        {"id": "0x11b8", "feeTier": "500", "volumeUSD": "136191979960.2224419516580473504387",
         "totalValueLockedUSD": "74372424.21175646766366485807997811",
         "token0": {"symbol": "WETH"}, "token1": {"symbol": "USDT"}},
        {"id": "0x3416", "feeTier": "100", "volumeUSD": "108705671421.3672795998815573659846",
         "totalValueLockedUSD": "43545495.962435",
         "token0": {"symbol": "USDC"}, "token1": {"symbol": "USDT"}},
    ],
}


class TestNumfmt(unittest.TestCase):
    def test_format_usd(self):
        self.assertEqual(numfmt.format_usd("609167447506.1830892627042412837456"), "$609.17B")
        self.assertEqual(numfmt.format_usd("363095785.5150252058840355529469255"), "$363.10M")
        self.assertEqual(numfmt.format_usd("12345.678"), "$12,345.68")
        self.assertEqual(numfmt.format_usd("0.00421"), "$0.0042")
        self.assertEqual(numfmt.format_usd("-5000000"), "-$5.00M")
        self.assertEqual(numfmt.format_usd("2500000000000"), "$2.50T")

    def test_non_numeric(self):
        self.assertIsNone(numfmt.format_usd("abc"))
        self.assertIsNone(numfmt.format_usd(None))
        self.assertIsNone(numfmt.format_usd("NaN"))

    def test_round_decimal_no_float_drift(self):
        self.assertEqual(numfmt.round_decimal("609167447506.1830892627042412837456", 2), "609167447506.18")

    def test_fee_tier(self):
        self.assertEqual(numfmt.format_fee_tier("500"), "0.05%")
        self.assertEqual(numfmt.format_fee_tier("3000"), "0.3%")
        self.assertEqual(numfmt.format_fee_tier("100"), "0.01%")

    def test_humanize_data_only_usd_fields(self):
        d = {"pools": [{"id": "0xabc", "feeTier": "500", "volumeUSD": "609167447506.18308",
                        "txCount": "123456789", "token0": {"symbol": "USDC"}}]}
        h = numfmt.humanize_data(d)
        self.assertEqual(h["pools"][0]["volumeUSD"], "$609.17B")
        self.assertEqual(h["pools"][0]["txCount"], "123456789")
        self.assertEqual(h["pools"][0]["id"], "0xabc")
        # original untouched
        self.assertEqual(d["pools"][0]["volumeUSD"], "609167447506.18308")


class LiveBase(unittest.TestCase):
    def setUp(self):
        os.environ.pop("GA_FREE_PREVIEW", None)
        os.environ.pop("GA_LIVE_PREVIEW", None)
        with fp._lock:
            fp._hits.clear()
            fp._day.update(d="", n=0)
        with lp._cache_lock:
            lp._cache.clear()


class TestLivePreview(LiveBase):
    def test_uniswap_live_rows_formatted(self):
        with mock.patch.object(lp, "_fetch", return_value=UNI_DATA) as f:
            prev = fp.build("top Uniswap V3 pools on Ethereum by volume", "t1")
        self.assertEqual(f.call_count, 1)
        lv = prev["live_preview"]
        self.assertEqual(lv["row_count"], 3)
        r0 = lv["rows"][0]
        self.assertEqual(r0["pool"], "USDC/WETH")
        self.assertEqual(r0["fee"], "0.05%")
        self.assertEqual(r0["volume_usd_lifetime"], "$609.17B")
        self.assertEqual(r0["tvl_usd"], "$363.10M")
        self.assertEqual(r0["raw"]["volumeUSD"], "609167447506.18")
        self.assertEqual(lv["source"]["subgraph_id"], lp.UNI_V3_ETH)
        self.assertIn("first: 3", lv["query"])
        self.assertEqual(lv["indexed_block"], 26395637)
        self.assertIn("fetched_at", lv)
        self.assertIn("Top 3 live rows free; pay $0.01 for full list, other chains, and follow-ups", lv["note"])
        self.assertIn("real, live rows", prev["cta"])
        self.assertIn("full list", prev["cta"])
        # backward compat: example kept, relabelled
        self.assertEqual(prev["example"]["kind"], "graphql")
        self.assertNotEqual(prev["example"]["label"], "example (not live data)")
        self.assertIn("live_preview", prev["example"]["label"])
        self.assertIn("teaser", prev)

    def test_cache_avoids_second_gateway_call(self):
        with mock.patch.object(lp, "_fetch", return_value=UNI_DATA) as f:
            a = fp.build("top Uniswap V3 pools on Ethereum by volume", "c1")
            b = fp.build("biggest uniswap v3 pools by volume", "c2")
        self.assertEqual(f.call_count, 1)
        self.assertFalse(a["live_preview"]["cached"])
        self.assertTrue(b["live_preview"]["cached"])

    def test_failure_falls_back_to_example_and_is_negative_cached(self):
        with mock.patch.object(lp, "_fetch", return_value=None) as f:
            a = fp.build("top Uniswap V3 pools on Ethereum by volume", "f1")
            b = fp.build("top Uniswap V3 pools on Ethereum by volume", "f2")
        self.assertEqual(f.call_count, 1)  # failure cached briefly
        for p in (a, b):
            self.assertNotIn("live_preview", p)
            self.assertEqual(p["example"]["label"], "example (not live data)")
            self.assertNotIn("real, live rows", p["cta"])

    def test_exception_in_live_path_is_silent(self):
        with mock.patch.object(lp, "_cached_fetch", side_effect=RuntimeError("boom")):
            prev = fp.build("top Uniswap V3 pools on Ethereum by volume", "e1")
        self.assertIsNotNone(prev)
        self.assertNotIn("live_preview", prev)

    def test_empty_rows_falls_back(self):
        with mock.patch.object(lp, "_fetch", return_value={"pools": []}):
            prev = fp.build("top Uniswap V3 pools on Ethereum by volume", "z1")
        self.assertNotIn("live_preview", prev)

    def test_fallback_topic_never_runs_live(self):
        with mock.patch.object(lp, "_fetch", return_value=UNI_DATA) as f:
            prev = fp.build("what is the weather like in paris tomorrow", "n1")
        self.assertEqual(f.call_count, 0)
        self.assertNotIn("live_preview", prev)

    def test_other_chain_or_version_or_address_skips_live(self):
        with mock.patch.object(lp, "_fetch", return_value=UNI_DATA) as f:
            for i, q in enumerate([
                "top Uniswap V3 pools on Arbitrum by volume",
                "top Uniswap V4 pools by volume",
                "Uniswap pool 0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640 volume",
                "What is my Aave V3 health factor on Ethereum?",
                "Show the positions and realized P&L for Polymarket user 0x42eB1234abcd",
            ]):
                prev = fp.build(q, f"s{i}")
                self.assertNotIn("live_preview", prev, q)
        self.assertEqual(f.call_count, 0)

    def test_disabled_flag(self):
        os.environ["GA_LIVE_PREVIEW"] = "0"
        try:
            with mock.patch.object(lp, "_fetch", return_value=UNI_DATA) as f:
                prev = fp.build("top Uniswap V3 pools on Ethereum by volume", "d1")
            self.assertEqual(f.call_count, 0)
            self.assertNotIn("live_preview", prev)
        finally:
            os.environ.pop("GA_LIVE_PREVIEW", None)

    def test_no_api_key_falls_back(self):
        with mock.patch.object(lp, "_api_key", return_value=None):
            prev = fp.build("top Uniswap V3 pools on Ethereum by volume", "k1")
        self.assertNotIn("live_preview", prev)

    def test_inflight_cap_falls_back(self):
        sem = lp.threading.BoundedSemaphore(1)
        sem.acquire()
        with mock.patch.object(lp, "_inflight", sem), mock.patch.object(lp, "_api_key", return_value="k"):
            prev = fp.build("top Uniswap V3 pools on Ethereum by volume", "i1")
        self.assertNotIn("live_preview", prev)

    def test_aave_markets_and_liquidations(self):
        mk = {"_meta": {"block": {"number": 1, "timestamp": 1794447671}}, "markets": [
            {"name": "Aave Ethereum WETH", "inputToken": {"symbol": "WETH"},
             "totalValueLockedUSD": "4341479646.506991147463489406188",
             "totalDepositBalanceUSD": "4341479646.506991147463489406188",
             "totalBorrowBalanceUSD": "3586674519.66510221747009335813"}]}
        with mock.patch.object(lp, "_fetch", return_value=mk) as f:
            prev = fp.build("What are the top Aave V3 markets on Ethereum by TVL?", "a1")
        self.assertIn("markets(first: 3", f.call_args[0][1])
        r = prev["live_preview"]["rows"][0]
        self.assertEqual((r["asset"], r["tvl_usd"], r["borrows_usd"]), ("WETH", "$4.34B", "$3.59B"))
        liq = {"liquidates": [{"hash": "0xabc", "timestamp": "1794438035", "amountUSD": "82893.87167903692535988574096",
                               "asset": {"symbol": "AAVE"}, "market": {"name": "Aave Ethereum AAVE"}}]}
        with mock.patch.object(lp, "_fetch", return_value=liq) as f:
            prev = fp.build("Write a GraphQL query for Aave V3 liquidations above $50K on Ethereum", "a2")
        self.assertIn("liquidates(", f.call_args[0][1])
        self.assertEqual(prev["live_preview"]["rows"][0]["amount_usd"], "$82,893.87")

    def test_ens_name_lookup_and_injection_safe(self):
        d = {"domains": [{"name": "vitalik.eth", "createdAt": "1497775154", "expiryDate": "2471818424",
                          "owner": {"id": "0xd8da"}, "resolvedAddress": {"id": "0xd8da"}}]}
        with mock.patch.object(lp, "_fetch", return_value=d) as f:
            prev = fp.build("Who owns vitalik.eth and when does it expire?", "en1")
        self.assertIn('name: "vitalik.eth"', f.call_args[0][1])
        self.assertEqual(prev["live_preview"]["rows"][0]["name"], "vitalik.eth")
        spec = lp._ens('who owns x" }) { id } } {foo.eth')
        self.assertTrue(spec is None or '" }' not in spec["query"].split('name: "')[1].split('"')[0])

    def test_compound_and_polymarket(self):
        mk = {"markets": [{"name": "Compound V3 USDC", "inputToken": {"symbol": "USDC"},
                           "totalValueLockedUSD": "358086029.71", "totalDepositBalanceUSD": "358086029.71",
                           "totalBorrowBalanceUSD": "324339485.11"}]}
        with mock.patch.object(lp, "_fetch", return_value=mk) as f:
            prev = fp.build("Top Compound markets by TVL on Ethereum", "cm1")
        self.assertEqual(f.call_args[0][0], lp.COMPOUND_V3_ETH)
        self.assertEqual(prev["live_preview"]["rows"][0]["tvl_usd"], "$358.09M")
        pm = {"globals": [{"numTraders": "1234567", "tradesQuantity": "99999999", "scaledCollateralVolume": "5123456789.5",
                           "numConditions": "100", "numOpenConditions": "40"}]}
        with mock.patch.object(lp, "_fetch", return_value=pm):
            prev = fp.build("How big is Polymarket overall?", "pm1")
        self.assertEqual(prev["live_preview"]["rows"][0]["traders"], "1,234,567")
        self.assertEqual(prev["live_preview"]["rows"][0]["collateral_volume"], "$5.12B")

    def test_non_live_topic_unchanged(self):
        with mock.patch.object(lp, "_fetch", return_value=UNI_DATA) as f:
            prev = fp.build("Compare SOL token holder distribution vs ETH", "tk1")
        self.assertEqual(f.call_count, 0)
        self.assertNotIn("live_preview", prev)


class TestExecutedDisplay(unittest.TestCase):
    def test_execute_adds_data_display_and_keeps_raw(self):
        import asyncio
        import subgraph_exec as se

        class R:
            def raise_for_status(self): pass
            def json(self): return {"data": UNI_DATA}

        class C:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **k): return R()

        rec = {"query_ready": {"tool": "execute_query_by_subgraph_id",
                               "args": {"subgraph_id": lp.UNI_V3_ETH, "gql": "{ pools { id } }"}}}
        import httpx
        with mock.patch.dict(os.environ, {"GRAPH_API_KEY": "test"}), mock.patch.object(httpx, "AsyncClient", C):
            ex = asyncio.run(se.execute_query_ready(rec))
        self.assertTrue(ex["ok"], ex)
        self.assertEqual(ex["data"]["pools"][0]["volumeUSD"], "609167447506.1830892627042412837456")
        self.assertEqual(ex["data_display"]["pools"][0]["volumeUSD"], "$609.17B")
        self.assertEqual(ex["data_display"]["pools"][0]["totalValueLockedUSD"], "$363.10M")


if __name__ == "__main__":
    unittest.main()
