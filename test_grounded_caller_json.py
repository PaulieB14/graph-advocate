"""
Caller-dictated JSON lookups must be answered from an executed query, never
from model memory (Taifoon Base Uniswap V3 pool cases, 2026-10-11..14).
Run: python test_grounded_caller_json.py
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import advocate  # noqa: E402
import grounded_lookup as gl  # noqa: E402

BASE_V3 = "HMuAwufqZ1YCRmzL2SfHTVkzZovC9VL2UAKhjvRqKiR1"
WETH = "0x4200000000000000000000000000000000000006"
AERO = "0x940181a94a35a4569e4529a3cdfb74e38fd98631"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
CBBTC = "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"

# Real subgraph rows (Uniswap V3 Base, verified 2026-10-14).
POOLS = {
    "0x3d5d143381916280ff91407febeb52f2b60f33cf": ("3000", (WETH, "WETH"), (AERO, "AERO")),
    "0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef": ("500", (USDC, "USDC"), (CBBTC, "cbBTC")),
    "0xd0b53d9277642d899df5c87a3966a349a798f224": ("500", (WETH, "WETH"), (USDC, "USDC")),
}


def taifoon(pool: str) -> str:
    # Verbatim shape of the production request (sender 0x3574999d…).
    return (
        f"data.onchain_query: on Base (chain 8453), which tokens does the Uniswap V3 pool {pool} "
        f"hold? Read it from the chain or from the Uniswap V3 subgraph on Base, e.g. "
        f'{{ pool(id: "{pool}") {{ id feeTier token0 {{ id symbol }} token1 {{ id symbol }} }} }}, '
        f"and return the token0 and token1 contract addresses and the fee tier. Reply with only a "
        f'JSON object {{"token0": "0x...", "token1": "0x...", "fee_tier": 0, "query_used": "..."}}'
    )


class FakeGateway:
    def __init__(self):
        self.calls = []

    def __call__(self, sid, query):
        self.calls.append((sid, query))
        for pid, (fee, t0, t1) in POOLS.items():
            if pid in query:
                return {"pool": {"id": pid, "feeTier": fee,
                                 "token0": {"id": t0[0], "symbol": t0[1], "decimals": "18"},
                                 "token1": {"id": t1[0], "symbol": t1[1], "decimals": "6"}}}
        return {"pool": None}


def _no_model(*a, **k):
    raise AssertionError("model must not be called for a grounded pool lookup")


class TestTaifoonPools(unittest.TestCase):
    def run_case(self, pool):
        gw = FakeGateway()
        with mock.patch.object(gl, "run_gql", gw), \
             mock.patch.object(advocate.client.messages, "create", side_effect=_no_model), \
             mock.patch.object(advocate, "_auto_search", side_effect=_no_model):
            rec, _ = advocate.ask_graph_advocate(taifoon(pool), requesting_agent="taifoon")
        self.assertEqual(len(gw.calls), 1)
        self.assertEqual(gw.calls[0][0], BASE_V3)
        return rec, gw.calls[0][1]

    def test_weth_aero_03(self):
        rec, q = self.run_case("0x3d5d143381916280ff91407febeb52f2b60f33cf")
        self.assertEqual((rec["token0"], rec["token1"], rec["fee_tier"]), (WETH, AERO, 3000))
        self.assertEqual((rec["token0_symbol"], rec["token1_symbol"]), ("WETH", "AERO"))
        self.assertEqual(rec["query_used"], q)

    def test_usdc_cbbtc_500(self):
        rec, _ = self.run_case("0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef")
        self.assertEqual((rec["token0"], rec["token1"], rec["fee_tier"]), (USDC, CBBTC, 500))

    def test_token_order_preserved(self):
        # token0 is WETH (0x42… < 0x83…), not USDC — order comes from the subgraph.
        rec, _ = self.run_case("0xd0b53d9277642d899df5c87a3966a349a798f224")
        self.assertEqual(rec["token0"], WETH)
        self.assertEqual(rec["token1"], USDC)
        self.assertEqual(rec["fee_tier"], 500)


class TestQueryUsedOnlyWhenExecuted(unittest.TestCase):
    def test_gateway_failure_is_honest(self):
        def boom(sid, q):
            raise RuntimeError("gateway 503")
        with mock.patch.object(gl, "run_gql", boom), \
             mock.patch.object(advocate.client.messages, "create", side_effect=_no_model):
            rec, _ = advocate.ask_graph_advocate(taifoon("0x3d5d143381916280ff91407febeb52f2b60f33cf"))
        self.assertEqual(rec["status"], "could_not_determine")
        self.assertNotIn("query_used", rec)
        self.assertIsNone(rec["token0"])
        self.assertFalse(rec["_grounding"]["executed"])

    def test_unknown_pool_is_honest(self):
        with mock.patch.object(gl, "run_gql", FakeGateway()):
            rec = gl.answer(taifoon("0x" + "ab" * 20))
        self.assertEqual(rec["status"], "could_not_determine")
        self.assertNotIn("query_used", rec)

    def test_unsupported_chain_runs_nothing(self):
        gw = FakeGateway()
        with mock.patch.object(gl, "run_gql", gw):
            rec = gl.answer(taifoon(list(POOLS)[0]).replace("Base (chain 8453)", "Zora")
                            .replace("subgraph on Base", "subgraph on Zora"))
        self.assertEqual(gw.calls, [])
        self.assertNotIn("query_used", rec)

    def test_model_claimed_query_stripped_on_non_lookup(self):
        # A caller-JSON request that is NOT a data lookup still goes to the model,
        # but any query it claims is removed because nothing was executed.
        fake = mock.Mock()
        fake.content = [mock.Mock(type="text", text='{"steps": ["a", "b"], "query_used": "{ pools { id } }"}')]
        fake.usage = None
        with mock.patch.object(advocate.client.messages, "create", return_value=fake) as m, \
             mock.patch.object(advocate, "_auto_search", return_value=""):
            rec, _ = advocate.ask_graph_advocate(
                'plan.steps: plan the goal "set up a shared calendar". Reply with only a JSON '
                'object {"steps": []}')
        self.assertEqual(rec["steps"], ["a", "b"])
        self.assertNotIn("query_used", rec)
        # Caller-JSON composition is at least Sonnet.
        self.assertNotIn("haiku", m.call_args.kwargs["model"])

    def test_generic_lookup_without_execution_is_honest(self):
        # Non-pool lookup: routed normally; if nothing executes, no invented data.
        with mock.patch.object(advocate, "ask_graph_advocate", wraps=advocate.ask_graph_advocate) as w:
            def inner(req, *a, **k):
                if advocate._CALLER_JSON_ONLY_RE.search(req):
                    return w._mock_wraps(req, *a, **k)
                return {"recommendation": "unknown"}, []
            w.side_effect = inner
            rec, _ = advocate.ask_graph_advocate(
                "on Base, what is the USDC balance of 0x" + "11" * 20 + "? Reply with only a JSON "
                'object {"balance": "0", "query_used": "..."}')
        self.assertEqual(rec["status"], "could_not_determine")
        self.assertIsNone(rec["balance"])
        self.assertNotIn("query_used", rec)

    def test_generic_lookup_with_execution_sets_real_query(self):
        q = '{ account(id:"0x1") { balance } }'
        executed = {"recommendation": "subgraph-registry",
                    "query_ready": {"tool": "execute_query_by_subgraph_id",
                                    "args": {"subgraph_id": "X", "query": q}},
                    "execution_result": {"source": "subgraph-gateway",
                                         "data": {"account": {"balance": "42"}},
                                         "routing": {"subgraph_id": "X"}}}
        fake = mock.Mock()
        fake.content = [mock.Mock(type="text", text='{"balance": "42", "query_used": "made up"}')]
        orig = advocate.ask_graph_advocate

        def inner(req, *a, **k):
            if advocate._CALLER_JSON_ONLY_RE.search(req):
                return orig(req, *a, **k)
            return executed, []
        with mock.patch.object(advocate, "ask_graph_advocate", side_effect=inner), \
             mock.patch.object(advocate.client.messages, "create", return_value=fake) as m:
            rec, _ = orig("on Base, what is the USDC balance of 0x" + "11" * 20 +
                          '? Reply with only a JSON object {"balance": "0", "query_used": "..."}')
        self.assertEqual(rec["balance"], "42")
        self.assertEqual(rec["query_used"], q)       # the executed one, not the model's
        self.assertIn("sonnet", m.call_args.kwargs["model"])


class TestHelpers(unittest.TestCase):
    def test_requested_keys(self):
        self.assertEqual(gl.requested_keys(taifoon(list(POOLS)[0])),
                         ["token0", "token1", "fee_tier", "query_used"])

    def test_chain_id(self):
        self.assertEqual(gl.detect_chain("on chain 8453"), "base")


if __name__ == "__main__":
    unittest.main(verbosity=2)
