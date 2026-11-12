"""End-to-end (mocked) paid POST /route: payment middleware bypassed, model + gateway mocked.
Verifies the buyer gets formatted rows in `result` (and the verified-query fallback)."""
import json
import os
import unittest
from unittest import mock

os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import live_preview as lp

POOLS = {"_meta": {"block": {"number": 26395665, "timestamp": 4102444800}}, "pools": [
    {"id": "0x88e6", "feeTier": "500", "volumeUSD": "609167447506.1830892627042412837456",
     "totalValueLockedUSD": "363095785.5150252058840355529469255",
     "token0": {"symbol": "USDC"}, "token1": {"symbol": "WETH"}},
    {"id": "0x11b8", "feeTier": "500", "volumeUSD": "136191979960.2224419516580473504387",
     "totalValueLockedUSD": "74372424.21175646766366485807997811",
     "token0": {"symbol": "WETH"}, "token1": {"symbol": "USDT"}}]}

REC = {"recommendation": "subgraph-registry", "reason": "Uniswap V3 Ethereum, ranked by volumeUSD.", "confidence": "high",
       "query_ready": {"tool": "execute_query_by_subgraph_id", "args": {
           "subgraph_id": lp.UNI_V3_ETH,
           "gql": "{ pools(first: 10, orderBy: volumeUSD, orderDirection: desc) { id feeTier volumeUSD totalValueLockedUSD token0 { symbol } token1 { symbol } } }"}}}


class _Resp:
    def __init__(self, p): self._p = p
    def raise_for_status(self): pass
    def json(self): return self._p


class _Client:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, *a, **k): return _Resp({"data": POOLS})


class TestPaidRouteResult(unittest.TestCase):
    def _client(self, rec):
        import x402.http.middleware.fastapi as mw
        import a2a_server
        from starlette.testclient import TestClient
        with mock.patch.object(mw, "PaymentMiddlewareASGI", lambda app, **kw: app):
            app = a2a_server.build_app()
        return a2a_server, TestClient(app)

    def test_paid_reply_has_formatted_result_rows(self):
        import httpx
        a2a, c = self._client(REC)
        with mock.patch.dict(os.environ, {"GRAPH_API_KEY": "test"}), \
             mock.patch.object(a2a, "ask_graph_advocate", return_value=(dict(REC), None)), \
             mock.patch.object(httpx, "AsyncClient", _Client):
            r = c.post("/route", json={"request": "top Uniswap V3 pools on Ethereum by volume"})
        if r.status_code == 404:
            self.skipTest("x402 route not mounted without CDP credentials")
        self.assertEqual(r.status_code, 200, r.text[:300])
        d = r.json()
        res = d["result"]
        self.assertEqual(res["rows_shown"], 2)
        self.assertEqual(res["rows"][0]["volumeUSD"], "$609.17B")
        self.assertEqual(res["rows"][0]["token0_symbol"], "USDC")
        self.assertEqual(res["source"]["subgraph_id"], lp.UNI_V3_ETH)
        self.assertEqual(res["indexed_block"], 26395665)
        self.assertIn("pools(first: 10", res["query"])
        self.assertEqual(d["executed"]["data"]["pools"][0]["volumeUSD"], "609167447506.1830892627042412837456")
        self.assertEqual(d["executed"]["data_display"]["pools"][1]["totalValueLockedUSD"], "$74.37M")
        self.assertIn("recommendation", d)

    def test_fallback_to_verified_query_when_model_gives_none(self):
        a2a, c = self._client({})
        bare = {"recommendation": "subgraph-registry", "reason": "x", "confidence": "high"}
        with mock.patch.object(a2a, "ask_graph_advocate", return_value=(dict(bare), None)), \
             mock.patch.object(lp, "_fetch", return_value=POOLS) as f:
            r = c.post("/route", json={"request": "top Uniswap V3 pools on Ethereum by volume"})
        if r.status_code == 404:
            self.skipTest("x402 route not mounted without CDP credentials")
        self.assertEqual(r.status_code, 200, r.text[:300])
        res = r.json()["result"]
        self.assertEqual(res["rows"][0]["volume_usd_lifetime"], "$609.17B")
        self.assertIn("first: 25", f.call_args[0][1])
        self.assertNotIn("pay $", json.dumps(res))

    def test_execute_false_skips_result(self):
        a2a, c = self._client({})
        with mock.patch.object(a2a, "ask_graph_advocate", return_value=({"recommendation": "x", "confidence": "high"}, None)):
            r = c.post("/route", json={"request": "top Uniswap V3 pools on Ethereum by volume", "execute": False})
        if r.status_code == 404:
            self.skipTest("x402 route not mounted without CDP credentials")
        self.assertNotIn("result", r.json())


if __name__ == "__main__":
    unittest.main()


class PaidRowsFormatLeafFields(unittest.TestCase):
    """Found on the real $0.01 settlement: feeTier came back raw '500' and txCount as a bare 12498203."""

    def test_feetier_and_txcount_are_readable_in_rows_and_data_display(self):
        import numfmt
        data = {"pools": [{"id": "0x88e6", "feeTier": "500", "txCount": "12498203",
                           "volumeUSD": "609167447506.18", "feesUSD": "304590000.5",
                           "token0": {"symbol": "USDC"}, "token1": {"symbol": "WETH"}}]}
        _k, rows = numfmt.table_rows(data)
        self.assertEqual(rows[0]["feeTier"], "0.05%")
        self.assertEqual(rows[0]["txCount"], "12,498,203")
        self.assertEqual(rows[0]["volumeUSD"], "$609.17B")
        disp = numfmt.humanize_data(data)
        self.assertEqual(disp["pools"][0]["feeTier"], "0.05%")
        self.assertEqual(data["pools"][0]["feeTier"], "500")  # raw input untouched
        self.assertEqual(numfmt.table_rows({"pools": [{"id": "1", "tick": "500"}]})[1][0]["tick"], "500")
