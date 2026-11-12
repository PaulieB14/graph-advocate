import json
import unittest

import pay_snippets as ps


class TestPaySnippets(unittest.TestCase):
    def test_how_to_pay_fields(self):
        h = ps.how_to_pay("https://graphadvocate.com/route", {"request": "q"}, "$0.01")
        for k in ("one_step", "javascript_x402_fetch", "python_x402_httpx", "curl", "mcp", "free", "price"):
            self.assertTrue(h[k], k)
        self.assertIn("https://graphadvocate.com/route", h["javascript_x402_fetch"])
        self.assertIn("eip155:8453", h["javascript_x402_fetch"])
        self.assertIn('{"request": "q"}', h["curl"])
        self.assertIn("PAYMENT-SIGNATURE", h["curl"])
        self.assertNotIn("0x" + "a" * 64, json.dumps(h))  # never a key

    def test_html_escapes_and_shows_rows(self):
        payload = {
            "resource": {"url": "https://graphadvocate.com/route"},
            "how_to_pay": ps.how_to_pay("https://graphadvocate.com/route", {"request": "<script>"}, "$0.01"),
            "free_preview": {"live_preview": {"scope": "Top pools", "fetched_at": "t", "note": "n",
                                              "rows": [{"rank": 1, "pool": "USDC/<b>WETH", "raw": {"x": 1}}]}},
        }
        out = ps.render_html(payload)
        self.assertIn("402", out)
        self.assertIn("USDC/&lt;b&gt;WETH", out)
        self.assertNotIn("<script>", out.replace("&lt;script&gt;", ""))
        self.assertIn("x402-fetch", out)


if __name__ == "__main__":
    unittest.main()
