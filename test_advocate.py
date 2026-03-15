"""Validation test suite — 7 cases from the build plan."""
import json
from advocate import ask_graph_advocate

TESTS = [
    {
        "name": "USDC holders + 30-day history",
        "request": "Top 20 USDC holders on Ethereum with 30-day balance history",
        "expect_service": "token-api",
        "expect_tool_contains": "Holder",
    },
    {
        "name": "Uniswap V3 TVL + fee tiers",
        "request": "Uniswap V3 pool TVL and fee tiers",
        "expect_service": "subgraph-registry",
        "expect_tool_contains": "query",
    },
    {
        "name": "Raw event logs block range",
        "request": "Raw decoded event logs, blocks 19000000 to 20000000",
        "expect_service": "substreams",
        "expect_tool_contains": "stream",
    },
    {
        "name": "Multi-chain wallet balances",
        "request": "Wallet balances on Ethereum AND Solana",
        "expect_service": "token-api",
        "expect_tool_contains": "Balances",
    },
    {
        "name": "Aave liquidation events",
        "request": "Aave liquidation events by protocol entity",
        "expect_service": "subgraph-registry",
        "expect_tool_contains": "query",
    },
    {
        "name": "Etherscan objection",
        "request": "Can't I just use Etherscan?",
        "expect_service": None,  # just check it responds with Graph advantages
        "expect_tool_contains": None,
    },
    {
        "name": "Solana NFT sales",
        "request": "Solana NFT sales last 7 days",
        "expect_service": "token-api",
        "expect_tool_contains": "Svm",
    },
]


def run():
    passed = 0
    failed = 0

    for t in TESTS:
        print(f"\n{'='*60}")
        print(f"TEST: {t['name']}")
        print(f"REQUEST: {t['request']}")

        rec, _ = ask_graph_advocate(t["request"], requesting_agent="test-suite")

        if rec.get("parse_error"):
            print(f"  FAIL — JSON parse error: {rec.get('raw', '')[:200]}")
            failed += 1
            continue

        service = rec.get("recommendation", "")
        tool = json.dumps(rec.get("query_ready", {}))

        service_ok = t["expect_service"] is None or service == t["expect_service"]
        tool_ok = (
            t["expect_tool_contains"] is None
            or t["expect_tool_contains"].lower() in tool.lower()
        )

        qr = rec.get("query_ready", {})
        tool_name = qr.get("tool") if isinstance(qr, dict) else str(qr)

        if service_ok and tool_ok:
            print(f"  PASS — service={service}, confidence={rec.get('confidence')}")
            print(f"  tool={tool_name}")
            passed += 1
        else:
            print(f"  FAIL")
            if not service_ok:
                print(f"    expected service={t['expect_service']}, got={service}")
            if not tool_ok:
                print(f"    expected tool containing '{t['expect_tool_contains']}', got: {tool[:200]}")
            print(f"  FULL RESPONSE: {json.dumps(rec, indent=2)}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{len(TESTS)} passed, {failed} failed")


if __name__ == "__main__":
    run()
