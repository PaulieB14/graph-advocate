import os
import time
import unittest
from unittest import mock

os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import free_preview as fp
import live_preview as lp

UNI = {"_meta": {"block": {"number": 1, "timestamp": 0}},
       "pools": [{"id": "0x1", "feeTier": "500", "volumeUSD": "1000000", "totalValueLockedUSD": "5000",
                  "token0": {"symbol": "A"}, "token1": {"symbol": "B"}}]}


class TestPreviewEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import a2a_server
        from starlette.testclient import TestClient
        cls.client = TestClient(a2a_server.build_app())

    def setUp(self):
        os.environ.pop("GA_LIVE_PREVIEW", None)
        os.environ.pop("GA_FREE_PREVIEW", None)
        with fp._lock:
            fp._hits.clear()
        with lp._cache_lock:
            lp._cache.clear()
        UNI["_meta"]["block"]["timestamp"] = int(time.time())

    def test_preview_200_with_live_rows(self):
        with mock.patch.object(lp, "_fetch", return_value=UNI):
            r = self.client.get("/preview?q=top uniswap v3 pools by volume")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["live_preview"]["rows"][0]["volume_usd_lifetime"], "$1.00M")
        self.assertEqual(r.headers["access-control-allow-origin"], "*")

    def test_missing_q_400_and_unknown_topic_200_without_live(self):
        self.assertEqual(self.client.get("/preview").status_code, 400)
        r = self.client.get("/preview?q=write a poem about the moon tonight")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("live_preview", r.json())

    def test_route_402_carries_how_to_pay_and_html_view(self):
        with mock.patch.object(lp, "_fetch", return_value=UNI):
            r = self.client.post("/route", json={"request": "top uniswap v3 pools by volume"})
            if r.status_code != 402:
                self.skipTest("x402 middleware not initialised in this environment (no CDP credentials)")
            j = r.json()
            self.assertIn("javascript_x402_fetch", j["how_to_pay"])
            self.assertIn("live_preview", j["free_preview"])
            self.assertTrue(r.headers.get("payment-required"))
            h = self.client.get("/route", headers={"accept": "text/html,application/xhtml+xml"})
        self.assertEqual(h.status_code, 402)
        self.assertIn("text/html", h.headers["content-type"])
        self.assertIn("x402-fetch", h.text)
        self.assertTrue(h.headers.get("payment-required"))


if __name__ == "__main__":
    unittest.main()
