"""
Tests for model tiering, prompt caching blocks and indexer-aware ranking.
Run: python test_model_tiers.py
"""

import os
import sqlite3
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import advocate  # noqa: E402

TAIFOON_JOB = (
    'plan.steps: plan the goal "rotate the passwords of four shared accounts" in exactly '
    '5 steps. Reply with only a JSON object {"ref":"p1","goal":"<the goal>","steps":'
    '[{"n":1,"action":"<what to do>","depends_on":[]}]}: ' + "x" * 600
)


class TestPickTier(unittest.TestCase):
    def setUp(self):
        os.environ.pop("GA_PAID_TIER", None)

    def test_paid_long_caller_schema_is_sonnet(self):
        self.assertEqual(advocate._pick_tier(TAIFOON_JOB, paid=True), "sonnet")

    def test_paid_comparison_is_opus(self):
        self.assertEqual(advocate._pick_tier("compare aave vs compound on base", paid=True), "opus")

    def test_free_comparison_is_sonnet(self):
        self.assertEqual(advocate._pick_tier("aave versus compound", paid=False), "sonnet")

    def test_design_substring_no_longer_escalates(self):
        self.assertEqual(advocate._pick_tier("designated pool address on base"), "haiku")

    def test_free_simple_is_haiku(self):
        self.assertEqual(advocate._pick_tier("top uniswap pools"), "haiku")

    def test_premium_is_opus(self):
        self.assertEqual(advocate._pick_tier("top uniswap pools", paid=True, premium=True), "opus")

    def test_env_override(self):
        with mock.patch.dict(os.environ, {"GA_PAID_TIER": "opus"}):
            self.assertEqual(advocate._pick_tier("top pools", paid=True), "opus")

    def test_thinking_only_on_opus(self):
        self.assertIn("thinking", advocate._MODEL_TIERS["opus"])
        self.assertNotIn("thinking", advocate._MODEL_TIERS["sonnet"])
        self.assertNotIn("thinking", advocate._MODEL_TIERS["haiku"])


class TestPromptCaching(unittest.TestCase):
    def test_system_blocks_cached(self):
        for blocks, text in ((advocate.SYSTEM_BLOCKS, advocate.SYSTEM),
                             (advocate.CHAT_SYSTEM_BLOCKS, advocate.CHAT_SYSTEM)):
            self.assertEqual(blocks[0]["text"], text)
            self.assertEqual(blocks[0]["cache_control"], {"type": "ephemeral"})

    def test_call_uses_cached_system_and_sonnet_for_paid(self):
        captured = {}

        class _Block:
            type = "text"
            text = '{"recommendation":"subgraph-registry","confidence":"high","reason":"r"}'

        class _Resp:
            content = [_Block()]
            usage = None
            stop_reason = "end_turn"

        def fake_create(**kw):
            captured.update(kw)
            return _Resp()

        with mock.patch.object(advocate.client.messages, "create", side_effect=fake_create), \
             mock.patch.object(advocate, "_auto_search", return_value=""), \
             mock.patch.object(advocate, "_validate_and_fix_query", side_effect=lambda r: r):
            advocate.ask_graph_advocate("top uniswap v3 pools on base", priority=True)
        self.assertEqual(captured["model"], advocate._MODEL_TIERS["sonnet"]["model"])
        self.assertIs(captured["system"], advocate.SYSTEM_BLOCKS)
        self.assertNotIn("thinking", captured)
        self.assertEqual(captured["max_tokens"], 2500)


class TestIndexerRanking(unittest.TestCase):
    def test_more_indexers_ranks_first(self):
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "subgraph_registry.db")
        conn = sqlite3.connect(db)
        conn.execute("""CREATE TABLE subgraphs (id TEXT, display_name TEXT, description TEXT,
            network TEXT, query_volume_30d INTEGER, domain TEXT, protocol_type TEXT,
            reliability_score REAL, active_allocation_count INTEGER, categories TEXT,
            auto_description TEXT)""")
        rows = [("ONEIDX", "Uniswap V3 Base", "uniswap v3", "base", 9_000_000, "dex", "", 0, 1, "", ""),
                ("FIVEIDX", "UniV3-Base", "uniswap v3", "base", 1_000_000, "dex", "", 0, 5, "", "")]
        conn.executemany("INSERT INTO subgraphs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
        conn.close()
        advocate._subgraph_search_cache.clear()
        with mock.patch("tempfile.gettempdir", return_value=tmp):
            out = advocate._search_subgraphs("uniswap v3", "on base")
        import json
        ids = [r["subgraph_id"] for r in json.loads(out)["results"]]
        self.assertEqual(ids[0], "FIVEIDX")


if __name__ == "__main__":
    unittest.main()
