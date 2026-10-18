"""Tests for the paid-only ERC-8004 feedback invite. Run: python test_feedback_invite.py"""
import asyncio, base64, json, os, unittest
import feedback_invite as fi


def _settle_hdr(success=True):
    return base64.b64encode(json.dumps({"success": success, "transaction": "0xabc"}).encode())


def _run(app_status, app_body, app_headers, req_body=b'{"request":"top pools"}'):
    async def app(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": app_status, "headers": app_headers})
        await send({"type": "http.response.body", "body": app_body})
    out = {"headers": None, "body": b"", "status": None}
    async def receive():
        return {"type": "http.request", "body": req_body, "more_body": False}
    async def send(m):
        if m["type"] == "http.response.start":
            out["status"], out["headers"] = m["status"], dict(m["headers"])
        else:
            out["body"] += m.get("body", b"")
    asyncio.run(fi.PaidFeedbackASGI(app)({"type": "http", "path": "/route"}, receive, send))
    return out


JSON = [(b"content-type", b"application/json")]


class TestREST(unittest.TestCase):
    def setUp(self):
        os.environ.pop("GA_FEEDBACK_INVITE", None)

    def test_settled_paid_gets_field_and_headers(self):
        body = json.dumps({"recommendation": "x", "reason": "y"}).encode()
        o = _run(200, body, JSON + [(b"payment-response", _settle_hdr())])
        d = json.loads(o["body"])
        self.assertEqual(d["recommendation"], "x")
        self.assertEqual(d["reason"], "y")
        self.assertEqual(d["feedback"]["message"], fi.HUMAN_LINE)
        self.assertIn(b"link", o["headers"])
        self.assertEqual(int(o["headers"][b"content-length"]), len(o["body"]))

    def test_unpaid_200_untouched(self):
        body = b'{"a":1}'
        o = _run(200, body, JSON)
        self.assertEqual(o["body"], body)
        self.assertNotIn(b"link", o["headers"])

    def test_402_and_failed_settle_untouched(self):
        for st, hdr in ((402, _settle_hdr(False)), (200, _settle_hdr(False)), (500, _settle_hdr())):
            o = _run(st, b'{"a":1}', JSON + [(b"payment-response", hdr)])
            self.assertEqual(o["body"], b'{"a":1}')
            self.assertNotIn(b"x-erc8004-feedback", o["headers"])

    def test_caller_dictated_json_headers_only(self):
        body = b'{"token0":"WETH","fee_tier":500}'
        o = _run(200, body, JSON + [(b"payment-response", _settle_hdr())],
                 req_body=b'{"request":"Uniswap v3 pool 0x.. reply with only valid JSON"}')
        self.assertEqual(o["body"], body)
        self.assertIn(b"x-erc8004-feedback", o["headers"])

    def test_error_body_untouched(self):
        o = _run(200, b'{"error":"boom"}', JSON + [(b"payment-response", _settle_hdr())])
        self.assertEqual(o["body"], b'{"error":"boom"}')
        self.assertNotIn(b"link", o["headers"])

    def test_kill_switch(self):
        os.environ["GA_FEEDBACK_INVITE"] = "0"
        try:
            o = _run(200, b'{"a":1}', JSON + [(b"payment-response", _settle_hdr())])
            self.assertEqual(o["body"], b'{"a":1}')
            self.assertNotIn(b"link", o["headers"])
        finally:
            os.environ.pop("GA_FEEDBACK_INVITE")


class _Part:
    def __init__(self, t): self.text = t
class _Msg:
    def __init__(self, t): self.parts, self.role, self.metadata = [_Part(t)], "agent", None


class TestA2A(unittest.TestCase):
    def setUp(self):
        os.environ.pop("GA_FEEDBACK_INVITE", None)

    def _q(self, text, req="top pools"):
        sent = []
        class Q:
            async def enqueue_event(self, e): sent.append(e)
        asyncio.run(fi.PaidEventQueue(Q(), req).enqueue_event(_Msg(text)))
        return sent[0]

    def test_paid_object_gets_field_and_metadata(self):
        m = self._q(json.dumps({"recommendation": "token-api"}))
        self.assertIn("feedback", json.loads(m.parts[0].text))
        self.assertIn("feedback", m.metadata)

    def test_caller_json_metadata_only(self):
        t = json.dumps({"token0": "WETH"})
        m = self._q(t, req="reply with only JSON")
        self.assertEqual(m.parts[0].text, t)
        self.assertIn("feedback", m.metadata)

    def test_error_untouched(self):
        t = json.dumps({"error": "x"})
        m = self._q(t)
        self.assertEqual(m.parts[0].text, t)
        self.assertIsNone(m.metadata)


class TestContent(unittest.TestCase):
    def test_short_and_ids(self):
        self.assertLess(len(fi.HUMAN_LINE.split()), 15)
        regs = {r["chainId"]: r["agentId"] for r in fi.FEEDBACK["erc8004"]["registrations"]}
        self.assertEqual(regs, {8453: 41034, 42161: 734})
        self.assertEqual(fi.REPUTATION_REGISTRY, "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63")


if __name__ == "__main__":
    unittest.main()
