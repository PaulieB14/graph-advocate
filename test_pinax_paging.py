"""
Pinax plan caps `limit` at 10/request (403 above). Callers must clamp and page.
Run: python test_pinax_paging.py
"""

import asyncio
import os
import unittest
from unittest import mock

os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import pinax_paging as pp  # noqa: E402

LIMIT_403 = '{"status":403,"code":"forbidden","message":"Parameter \'limit\' exceeds maximum of 10 items."}'
HOLDERS = [{"address": f"0x{i:040x}", "value": 1000 - i} for i in range(1, 36)]  # 35 holders


class FakePinax:
    """Mimics /v1/evm/holders: 403 if limit>10, `page` 1-indexed, empty page = end."""

    def __init__(self, rows=HOLDERS, pages=True):
        self.rows, self.pages, self.calls = rows, pages, []

    def __call__(self, params):
        self.calls.append(dict(params))
        lim = int(params.get("limit", 10))
        if lim > 10:
            return 403, {"message": "limit"}, LIMIT_403
        page = int(params.get("page", 1)) if self.pages else 1
        chunk = self.rows[(page - 1) * lim: page * lim]
        return 200, {"data": chunk, "pagination": {"current_page": page}}, "ok"


class TestSync(unittest.TestCase):
    def test_n20_two_pages(self):
        f = FakePinax()
        st, body, _ = pp.fetch_sync(f, {"network": "arbitrum-one", "contract": "0xabc", "limit": 20})
        self.assertEqual(st, 200)
        self.assertEqual(len(f.calls), 2)
        self.assertEqual([c["page"] for c in f.calls], [1, 2])
        self.assertTrue(all(c["limit"] == 10 for c in f.calls))
        self.assertEqual(body["data"], HOLDERS[:20])          # merged in order
        self.assertEqual(body["_paging"]["returned"], 20)

    def test_n5_one_call(self):
        f = FakePinax()
        st, body, _ = pp.fetch_sync(f, {"contract": "0xabc", "limit": 5})
        self.assertEqual(len(f.calls), 1)
        self.assertEqual(f.calls[0]["limit"], 5)
        self.assertNotIn("page", f.calls[0])
        self.assertEqual(body["data"], HOLDERS[:5])

    def test_403_limit_retried_at_cap(self):
        calls = []

        def fixed_page_endpoint(params):   # caller passed page explicitly -> no paging
            calls.append(dict(params))
            if int(params["limit"]) > 10:
                return 403, None, LIMIT_403
            return 200, {"data": HOLDERS[:10]}, "ok"
        # Even if something upstream sends limit=50, we never send >10.
        st, body, _ = pp.fetch_sync(fixed_page_endpoint, {"limit": 50, "page": 1})
        self.assertEqual(st, 200)
        self.assertTrue(all(int(c["limit"]) <= 10 for c in calls))

        # And a raw 403 limit reply (e.g. plan cap lower than expected) is
        # retried once at 10 instead of failing.
        seq = [(403, None, LIMIT_403), (200, {"data": HOLDERS[:3]}, "ok")]
        st, body, _ = pp.fetch_sync(lambda p: seq.pop(0), {"limit": 7})
        self.assertEqual(st, 200)
        self.assertEqual(len(body["data"]), 3)

    def test_endpoint_without_paging_notes_cap(self):
        f = FakePinax(pages=False)
        st, body, _ = pp.fetch_sync(f, {"limit": 20})
        self.assertEqual(len(body["data"]), 10)
        self.assertTrue(any("capped at 10" in n for n in body["_paging"]["notes"]))

    def test_total_cap_and_short_source(self):
        f = FakePinax()
        st, body, _ = pp.fetch_sync(f, {"limit": 500})
        self.assertEqual(len(body["data"]), 35)              # source ran dry
        self.assertLessEqual(len(f.calls), 10)               # 100 cap / 10
        self.assertTrue(any("capped at 100" in n for n in body["_paging"]["notes"]))


class TestAsync(unittest.TestCase):
    def test_async_n20(self):
        f = FakePinax()

        async def af(p):
            return f(p)
        st, body, _ = asyncio.run(pp.fetch_async(af, {"limit": 20}))
        self.assertEqual(len(f.calls), 2)
        self.assertEqual(body["data"], HOLDERS[:20])


class TestAdvocateExecutor(unittest.TestCase):
    """End-to-end through advocate._execute_recommendation's token-api path."""

    def _run(self, limit):
        import advocate
        f = FakePinax()

        def fake_get(url, params=None, headers=None, timeout=None):
            st, body, text = f(params)
            return mock.Mock(status_code=st, json=lambda: body, text=text)
        rec = {"recommendation": "token-api",
               "query_ready": {"tool": "getV1EvmHolders",
                               "args": {"network": "arbitrum-one",
                                        "contract": "0x9623063377ad1b27544c965ccd7342f7ea7e88c7",
                                        "limit": limit}}}
        with mock.patch("httpx.get", side_effect=fake_get):
            return advocate._execute_recommendation(rec), f

    def test_top20_holders(self):
        out, f = self._run(20)
        self.assertEqual(out["status"], 200)
        self.assertNotIn("error", out)
        self.assertEqual(len(out["data"]["data"]), 20)
        self.assertEqual(len(f.calls), 2)

    def test_top5_holders(self):
        out, f = self._run(5)
        self.assertEqual(len(out["data"]["data"]), 5)
        self.assertEqual(len(f.calls), 1)


class TestIntelPinax(unittest.TestCase):
    def test_polymarket_pinax_pages(self):
        import polymarket_intel as pm
        f = FakePinax()

        class Client:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, headers=None, params=None):
                st, body, text = f(params)
                return mock.Mock(status_code=st, json=lambda: body, text=text)
        with mock.patch.object(pm.httpx, "AsyncClient", Client):
            body = asyncio.run(pm._pinax("/users", sort_by="total_pnl", limit=20))
        self.assertEqual(len(body["data"]), 20)
        self.assertTrue(all(c["limit"] <= 10 for c in f.calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
