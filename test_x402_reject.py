"""
Tests for facilitator-rejection handling (fake/insufficient payments -> 402, not 500).
Run: python test_x402_reject.py
"""

import os
import unittest

os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from a2a_server import _facilitator_rejection  # noqa: E402

# Verbatim shape of the 2026-10-11 production error (payer 0x…dEaD probe).
PROD = ('Facilitator verify failed (400): {"invalidMessage":"invalid signature: public key '
        'recovery code 211 is not in the valid range [27, 34]","invalidReason":'
        '"invalid_exact_evm_payload_signature","isValid":false,'
        '"payer":"0x000000000000000000000000000000000000dEaD"}')


class TestFacilitatorRejection(unittest.TestCase):
    def test_production_verify_failure(self):
        self.assertEqual(
            _facilitator_rejection(ValueError(PROD)),
            ("verify", "invalid_exact_evm_payload_signature",
             "0x000000000000000000000000000000000000dEaD"))

    def test_insufficient_funds_settle(self):
        exc = ValueError('Facilitator settle failed (400): {"errorReason":"insufficient_funds",'
                         '"payer":"0xabc"}')
        self.assertEqual(_facilitator_rejection(exc), ("settle", "insufficient_funds", "0xabc"))

    def test_non_json_body(self):
        self.assertEqual(_facilitator_rejection(ValueError("Facilitator verify failed (400): nope")),
                         ("verify", "invalid_payment", "?"))

    def test_facilitator_outage_still_raises(self):
        self.assertIsNone(_facilitator_rejection(ValueError("Facilitator verify failed (502): bad gateway")))

    def test_unrelated_errors_still_raise(self):
        self.assertIsNone(_facilitator_rejection(ValueError("something else")))
        self.assertIsNone(_facilitator_rejection(RuntimeError(PROD)))


if __name__ == "__main__":
    unittest.main()
