import unittest
import sample_answers as sa


class T(unittest.TestCase):
    def test_render_uses_lookup_prices(self):
        out = sa.render(lambda p: "$0.42" if p == "/hyperliquid/risk" else "$0.02")
        self.assertIn("POST https://graphadvocate.com/hyperliquid/risk", out)
        self.assertIn("$0.42 USDC", out)
        self.assertIn("/route", out)
        self.assertIn("$0.01 USDC", out)  # /route

    def test_unknown_price_not_invented(self):
        out = sa.render(lambda p: "")
        self.assertIn("see 402", out)


if __name__ == "__main__":
    unittest.main()
