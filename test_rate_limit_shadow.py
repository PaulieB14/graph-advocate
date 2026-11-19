"""Regression: a second module-level `_is_rate_limited(exc)` (log-scan backoff helper)
shadowed the per-sender limiter, so the A2A handler called the exception checker with a
task id and blocked any request whose UUID contained "429" (~1% of traffic). That is how a
Taifoon onboarding probe got 'rate-limited' instead of READY on 2026-11-19."""
import ast
import unittest

import a2a_server


class RateLimitShadow(unittest.TestCase):
    def test_no_duplicate_top_level_functions(self):
        tree = ast.parse(open(a2a_server.__file__).read())
        names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        dups = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual(dups, [], f"duplicate top-level defs shadow each other: {dups}")

    def test_task_id_containing_429_is_not_rate_limited(self):
        for tid in ("2585429e-a80c-4b7a-b904-26d12fcbeb47", "00000000-0000-4429-8000-000000000000"):
            self.assertFalse(a2a_server._is_rate_limited(tid), tid)

    def test_provider_backoff_helper_still_detects_429(self):
        self.assertTrue(a2a_server._is_provider_rate_limited(Exception("HTTP 429 Too Many Requests")))
        self.assertFalse(a2a_server._is_provider_rate_limited(Exception("boom")))

    def test_taifoon_probe_word(self):
        self.assertEqual(a2a_server._liveness_reply_word(
            "Taifoon onboarding probe: reply with the single word READY."), "READY")


if __name__ == "__main__":
    unittest.main()
