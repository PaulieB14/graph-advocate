"""
Tests for discovery surfaces: robots/sitemap/MCP server.json/ARD, Bazaar
service metadata injection, agent-card icon, /tip in openapi.
Run: python test_discovery.py
"""

import base64
import json
import os
import re
import unittest

os.environ.setdefault("RECOMMENDATIONS_DB", "/tmp/test_advocate.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import discovery_files as d  # noqa: E402
from a2a_server import (  # noqa: E402
    _add_bazaar_service_metadata, _bazaar_service_metadata, agent_card,
    _encode_payment_required_header, _with_x402_cors_headers,
    X402_CORS_ALLOW_HEADERS, X402_CORS_EXPOSE_HEADERS,
    CDP_X402_FACILITATOR_URL,
)

ASCII = re.compile(r"^[\x20-\x7e]{1,32}$")


class TestStaticFiles(unittest.TestCase):
    def test_agent_registration_lists_both_chains(self):
        r = d.agent_registration_json()
        self.assertEqual(r["type"], "https://eips.ethereum.org/EIPS/eip-8004#registration-v1")
        regs = {(x["agentRegistry"], x["agentId"]) for x in r["registrations"]}
        reg = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
        self.assertIn((f"eip155:8453:{reg}", 41034), regs)
        self.assertIn((f"eip155:42161:{reg}", 734), regs)
        self.assertTrue(any(s["name"] == "MCP" for s in r["services"]))

    def test_robots(self):
        r = d.robots_txt()
        self.assertIn("User-agent: *", r)
        self.assertIn("Allow: /", r)
        self.assertIn("Sitemap: https://graphadvocate.com/sitemap.xml", r)
        self.assertIn("llms.txt", r)

    def test_sitemap_is_xml_with_canonical_urls(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(d.sitemap_xml())
        locs = [e.text for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        self.assertIn("https://graphadvocate.com/llms.txt", locs)
        self.assertTrue(all(l.startswith("https://graphadvocate.com/") for l in locs))

    def test_mcp_server_json_shape(self):
        s = d.mcp_server_json()
        self.assertRegex(s["name"], r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")
        self.assertTrue(s["name"].startswith("io.github.PaulieB14/"))
        self.assertLessEqual(len(s["description"]), 100)
        self.assertTrue(s["version"])
        types = {r["type"] for r in s["remotes"]}
        self.assertEqual(types, {"streamable-http", "sse"})
        self.assertIn("https://graphadvocate.com/mcp", [r["url"] for r in s["remotes"]])
        # The registry publisher validates against this schema when available.
        try:
            import jsonschema
            schema_path = "/tmp/mcpschema.json"
            if os.path.exists(schema_path):
                with open(schema_path) as f:
                    jsonschema.validate(s, json.load(f))
        except ImportError:
            pass

    def test_ard_entries(self):
        a = d.ard_json()
        for e in a["entries"]:
            for k in ("identifier", "displayName", "type"):
                self.assertTrue(e[k])
            self.assertTrue(e["identifier"].startswith("urn:air:graphadvocate.com:"))
            self.assertTrue(("url" in e) ^ ("data" in e))
            self.assertGreaterEqual(len(e["representativeQueries"]), 2)


class TestBazaarMetadata(unittest.TestCase):
    PATHS = ["/route", "/tip", "/ask", "/onchain-x402/address", "/polymarket/pnl",
             "/hyperliquid/fills", "/kalshi/consensus-trend", "/kalshi-polymarket/spread",
             "/predmarket/spread", "/narrative/divergence", "/uniswap/pretrade", "/agent/score"]

    def test_spec_limits_for_every_paid_prefix(self):
        for p in self.PATHS:
            m = _bazaar_service_metadata(p)
            self.assertEqual(m["serviceName"], "Graph Advocate")
            self.assertRegex(m["serviceName"], ASCII)
            self.assertLessEqual(len(m["tags"]), 5)
            for t in m["tags"]:
                self.assertRegex(t, ASCII)
            self.assertEqual(len({t.lower() for t in m["tags"]}), len(m["tags"]))
            self.assertTrue(m["iconUrl"].startswith("https://graphadvocate.com/"))

    def test_kalshi_polymarket_not_shadowed_by_kalshi(self):
        self.assertIn("arbitrage", _bazaar_service_metadata("/kalshi-polymarket/spread")["tags"])

    def test_header_injection_preserves_accepts(self):
        pr = {"x402Version": 2,
              "resource": {"url": "https://graphadvocate.com/uniswap/pretrade",
                           "description": "x", "mimeType": "application/json"},
              "accepts": [{"scheme": "exact", "amount": "20000", "payTo": "0xabc"}],
              "extensions": {"bazaar": {"info": {}}}}
        raw = base64.b64encode(json.dumps(pr).encode())
        out = json.loads(base64.b64decode(_add_bazaar_service_metadata(raw, "/uniswap/pretrade")))
        self.assertEqual(out["accepts"], pr["accepts"])
        self.assertEqual(out["extensions"], pr["extensions"])
        self.assertEqual(out["resource"]["url"], pr["resource"]["url"])
        self.assertEqual(out["resource"]["serviceName"], "Graph Advocate")
        self.assertIn("uniswap", out["resource"]["tags"])

    def test_bad_header_passthrough(self):
        self.assertEqual(_add_bazaar_service_metadata(b"not-base64!!", "/route"), b"not-base64!!")


class TestAgentCard(unittest.TestCase):
    def test_icon_and_transport(self):
        dumped = agent_card.model_dump(by_alias=True, exclude_none=True)
        self.assertTrue(dumped["iconUrl"].endswith("/graphadvocate.png"))
        self.assertEqual(dumped["preferredTransport"], "JSONRPC")


class TestRoutes(unittest.TestCase):
    """End-to-end through the real Starlette app."""

    @classmethod
    def setUpClass(cls):
        from starlette.testclient import TestClient
        import a2a_server
        cls.c = TestClient(a2a_server.build_app())

    def test_endpoints_served(self):
        for path, ctype in [("/robots.txt", "text/plain"), ("/sitemap.xml", "application/xml"),
                            ("/.well-known/mcp/server.json", "application/json"),
                            ("/.well-known/mcp.json", "application/json"),
                            ("/.well-known/ard.json", "application/json")]:
            r = self.c.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn(ctype, r.headers["content-type"], path)

    def test_openapi_has_tip(self):
        spec = self.c.get("/openapi.json").json()
        self.assertIn("/tip", spec["paths"])
        self.assertEqual(spec["paths"]["/tip"]["post"]["x-payment-info"]["price"]["amount"], "0.01")

    def test_agent_card_icon(self):
        card = self.c.get("/.well-known/agent-card.json").json()
        self.assertIn("iconUrl", card)

    def test_get_paid_routes_return_full_v2_challenge(self):
        """GET /route, /ask, /tip must be a 402 with accepts + payment-required header."""
        for path in ("/route", "/ask", "/tip"):
            r = self.c.get(path)
            self.assertEqual(r.status_code, 402, path)
            body = r.json()
            self.assertEqual(body.get("x402Version"), 2, path)
            accepts = body.get("accepts")
            self.assertTrue(isinstance(accepts, list) and accepts, f"{path} body missing accepts")
            acc = accepts[0]
            self.assertEqual(acc.get("scheme"), "exact")
            self.assertEqual(acc.get("network"), "eip155:8453")
            self.assertEqual(acc.get("asset"), "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
            self.assertEqual(acc.get("payTo").lower(), "0x0ff5a6ecef783bba35463ec2f8403b9b5e9e7c86")
            if path == "/route":
                self.assertEqual(str(acc.get("amount")), "10000")
            pr = r.headers.get("payment-required")
            self.assertTrue(pr, f"{path} missing payment-required header")
            decoded = json.loads(base64.b64decode(pr))
            self.assertEqual(decoded.get("x402Version"), 2, path)
            self.assertTrue(decoded.get("accepts"), f"{path} header missing accepts")
            expose = r.headers.get("access-control-expose-headers") or ""
            for h in ("PAYMENT-REQUIRED", "PAYMENT-RESPONSE", "PAYMENT-SIGNATURE", "X-PAYMENT"):
                self.assertIn(h, expose, f"{path} expose-headers missing {h}")

    def test_options_preflight_lists_v2_payment_headers(self):
        r = self.c.options("/route")
        self.assertEqual(r.status_code, 204)
        allow = r.headers.get("access-control-allow-headers") or ""
        for h in ("PAYMENT-SIGNATURE", "PAYMENT-REQUIRED", "PAYMENT-RESPONSE", "X-PAYMENT"):
            self.assertIn(h, allow, f"OPTIONS allow-headers missing {h}")


class TestPaymentRequiredHeaderHelpers(unittest.TestCase):
    def test_encode_roundtrip(self):
        doc = {"x402Version": 2, "accepts": [{"amount": "10000"}]}
        out = json.loads(base64.b64decode(_encode_payment_required_header(doc)))
        self.assertEqual(out, doc)

    def test_cors_header_helper_adds_expose(self):
        headers = _with_x402_cors_headers([(b"content-type", b"application/json")])
        as_dict = {
            (k.decode() if isinstance(k, (bytes, bytearray)) else k).lower():
            (v.decode() if isinstance(v, (bytes, bytearray)) else v)
            for k, v in headers
        }
        self.assertEqual(as_dict["access-control-allow-origin"], "*")
        for h in ("PAYMENT-REQUIRED", "PAYMENT-SIGNATURE", "X-PAYMENT"):
            self.assertIn(h, as_dict["access-control-expose-headers"])
        self.assertEqual(as_dict["access-control-expose-headers"], X402_CORS_EXPOSE_HEADERS)

    def test_cdp_facilitator_constant(self):
        self.assertEqual(
            CDP_X402_FACILITATOR_URL,
            "https://api.cdp.coinbase.com/platform/v2/x402",
        )
        self.assertIn("PAYMENT-SIGNATURE", X402_CORS_ALLOW_HEADERS)
        self.assertIn("X-PAYMENT", X402_CORS_ALLOW_HEADERS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
