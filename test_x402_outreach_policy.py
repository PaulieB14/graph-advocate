import unittest
from decimal import Decimal

from x402_outreach import _max_usdc_policy

CAP = Decimal("0.05")
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


class TestMaxUsdcPolicy(unittest.TestCase):
    def test_v2_amount_within_cap(self):
        self.assertTrue(_max_usdc_policy({"accepts": [{"amount": "10000", "asset": USDC}]}, CAP))

    def test_v2_amount_over_cap(self):
        self.assertFalse(_max_usdc_policy({"accepts": [{"amount": "60000", "asset": USDC}]}, CAP))

    def test_v1_still_works(self):
        self.assertTrue(_max_usdc_policy({"accepts": [{"maxAmountRequired": "20000", "asset": {"decimals": 6}}]}, CAP))
        self.assertFalse(_max_usdc_policy({"accepts": [{"maxAmountRequired": "2000000", "asset": {"decimals": 6}}]}, CAP))

    def test_unreadable_amount_never_allowed(self):
        for rec in ({"accepts": [{"asset": USDC}]}, {"accepts": [{"amount": "abc", "asset": USDC}]},
                    {"accepts": [{"amount": "0"}]}, {"accepts": []}, {}, {"accepts": ["x"]}):
            self.assertFalse(_max_usdc_policy(rec, CAP), rec)

    def test_cheapest_option_counts(self):
        self.assertTrue(_max_usdc_policy({"accepts": [{"amount": "900000"}, {"amount": "10000"}]}, CAP))


if __name__ == "__main__":
    unittest.main()
