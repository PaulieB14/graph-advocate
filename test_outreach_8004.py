import outreach, outreach_8004 as o


def test_mode_defaults_off(monkeypatch):
    monkeypatch.delenv("OUTREACH_8004_SOURCE", raising=False)
    assert outreach.erc8004_mode() == "off"
    for v, want in (("dry-run", "dry-run"), ("DRYRUN", "dry-run"), ("on", "on"), ("garbage", "off")):
        monkeypatch.setenv("OUTREACH_8004_SOURCE", v)
        assert outreach.erc8004_mode() == want


def test_spam_and_self():
    assert o.is_spam({"name": "Agent #155170", "description": "x" * 40})
    assert o.is_spam({"name": "Real", "description": ""})
    assert not o.is_spam({"name": "Swapper", "description": "Executes token swaps on Base via x402"})
    assert o.is_self(8453, "41034", [])
    assert o.is_self(1, "1", ["https://graphadvocate.com/a2a"])
    assert not o.is_self(8453, "5", ["https://example.com/a2a"])


def test_endpoints_and_fit():
    d = {"services": {"a2a": {"endpoint": "https://x.io/.well-known/agent-card.json"},
                      "mcp": {"endpoint": "https://x.io/mcp"}}}
    assert o.endpoints(d) == ("https://x.io/.well-known/agent-card.json", "https://x.io/mcp")
    assert o.fit("DexBot", "token swap executor")[0] == "/uniswap/pretrade"
    assert o.fit("PM", "Polymarket copy trader")[0] == "/polymarket/pnl-quick"
    assert o.fit("Helper", "general assistant")[0] == "/route"


def test_drop_farms():
    mk = lambda t, e: {"agent_id": f"8453:{t}", "endpoint": e}
    c = [mk(100, "https://a-api.vercel.app"), mk(130, "https://b-api.vercel.app"),
         mk(160, "https://c-api.vercel.app"), mk(9000, "https://solo.vercel.app"),
         mk(120, "https://real.example.com/a2a")]
    assert [x["agent_id"] for x in o.drop_farms(c)] == ["8453:9000", "8453:120"]
