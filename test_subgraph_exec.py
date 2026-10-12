"""
Tests for subgraph_exec row counting (single-entity lookups were rows=0).
Run: python test_subgraph_exec.py
"""

import asyncio
import os
import unittest
from unittest import mock

import subgraph_exec as se

POOL = {
    "id": "0xd0b53d9277642d899df5c87a3966a349a798f224",
    "feeTier": "500",
    "token0": {"id": "0x4200000000000000000000000000000000000006", "symbol": "WETH"},
    "token1": {"id": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "symbol": "USDC"},
}
META = {"block": {"number": 52468720, "timestamp": 1791738000},
        "deployment": "Qm", "hasIndexingErrors": False}


class TestCountRows(unittest.TestCase):
    def test_single_entity_is_one_row(self):
        self.assertEqual(se._count_rows({"pool": POOL}), (1, 0))

    def test_null_entity_is_zero(self):
        self.assertEqual(se._count_rows({"pool": None}), (0, 0))

    def test_meta_not_counted(self):
        self.assertEqual(se._count_rows({"pool": POOL, "_meta": META})[0], 1)

    def test_aliases(self):
        self.assertEqual(se._count_rows({"a": POOL, "b": POOL})[0], 2)

    def test_list_and_nested(self):
        d = {"pools": [{"id": "1", "swaps": [{"id": "s1"}, {"id": "s2"}]},
                       {"id": "2", "swaps": []}]}
        self.assertEqual(se._count_rows(d), (2, 2))

    def test_nested_truncation(self):
        d = {"pool": {"id": "1", "swaps": [{"id": str(i)} for i in range(250)]}}
        out, rows, truncated = se._truncate(d, 100)
        self.assertEqual((rows, truncated, len(out["pool"]["swaps"])), (1, True, 100))


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def _run(rec, responses):
    client = mock.AsyncMock()
    client.post.side_effect = [_Resp(r) for r in responses]
    client.__aenter__.return_value = client
    with mock.patch.dict(os.environ, {"GRAPH_API_KEY": "test"}), \
         mock.patch("httpx.AsyncClient", return_value=client):
        return asyncio.run(se.execute_query_ready(rec))


REC = {"query_ready": {"tool": "execute_query_by_subgraph_id", "args": {
    "subgraph_id": "43Hwfi3dJSoGpyas9VwNoDAv55yjgGrPpNSmbQZArzMG",
    "query": '{ pool(id: "0xd0b53d9277642d899df5c87a3966a349a798f224") '
             '{ id feeTier token0 { id symbol } token1 { id symbol } } }'}}}


class TestExecuteRegression(unittest.TestCase):
    """2026-10-11 production case: real pool data came back, GA logged rows=0."""

    def test_base_univ3_pool_lookup(self):
        ex = _run(REC, [{"data": {"pool": POOL}}, {"data": {"_meta": META}}])
        self.assertTrue(ex["ok"])
        self.assertEqual(ex["row_count"], 1)
        self.assertNotIn("empty_result_note", ex)
        self.assertEqual(ex["data"]["pool"]["token1"]["symbol"], "USDC")
        self.assertEqual(ex["indexed_block"], 52468720)

    def test_missing_pool_says_no_entity(self):
        ex = _run(REC, [{"data": {"pool": None}}, {"data": {"_meta": META}}])
        self.assertEqual(ex["row_count"], 0)
        self.assertIn("no entity with that id", ex["empty_result_note"])


if __name__ == "__main__":
    unittest.main()
