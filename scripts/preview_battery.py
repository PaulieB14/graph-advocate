"""Run a battery of realistic questions against the production free path (402 preview; no payment, no LLM).
Usage: python scripts/preview_battery.py [base_url]
expect = (topic_substring_or_None, live_expected True/False). topic is read from the teaser text."""
import json, sys, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://graphadvocate.com"
# (question, expected source keyword in teaser | None for generic fallback, live rows expected)
Q = [
 ("top Uniswap V3 pools on Ethereum by volume", "Uniswap", True),
 ("What are the biggest Uniswap v3 pools on Base?", "Uniswap", True),
 ("top uniswap pools on optimism by volume", "Uniswap", True),
 ("Which Uniswap V3 pools on Arbitrum have the most volume?", "Uniswap", False),
 ("most liquid uniswap pool for WETH", "Uniswap", True),
 ("Uniswap V4 hooks pools ranking by volume", "Uniswap", False),
 ("top Aave V3 markets on Ethereum by TVL", "Aave", True),
 ("largest Aave markets on Polygon by supply", "Aave", True),
 ("Aave V3 liquidations above $50K on Ethereum", "Aave", True),
 ("what is the health factor of 0x1234abcd5678ef90 on Aave", "Aave", False),
 ("top Compound V3 markets by TVL", "lending", True),
 ("who owns vitalik.eth and when does it expire", "ENS", True),
 ("show me recently registered ENS names", "ENS", True),
 ("resolve nick.eth", "ENS", True),
 ("How big is Polymarket overall, how many traders?", "Polymarket", True),
 ("Polymarket PnL for wallet 0x42eB1234abcd", "Polymarket", False),
 ("What is the Kalshi vs Polymarket spread on the fed rate market?", "Kalshi", False),
 ("top USDC holders on Ethereum", "Token API", False),
 ("show me wallet balances for 0xd8da6bf26964af9d7eed9e03e53415d37aa96045 on base", "Token API", False),
 ("how risky is Hyperliquid wallet 0x1234abcd5678ef90", "Hyperliquid", False),
 ("Curve pools by TVL on Ethereum", "Curve", False),
 ("Lido stETH staking stats", "lending", False),
 ("Morpho vault TVL", "lending", False),
 ("how many x402 payments settled on Base last week", "x402", False),
 ("find a subgraph for Balancer pools on Arbitrum", None, False),
 ("what is the best subgraph for GMX trades", None, False),
 ("Which indexers serve the Uniswap V3 subgraph", "Uniswap", False),
 ("what's the weather like in Paris tomorrow", None, False),
 ("write me a poem about the ocean and the moon", None, False),
 ("hi", "__NONE__", False),
 ("Uniswap", "__NONE__", False),
]

def call(i, q):
    req = urllib.request.Request(BASE + "/route", data=json.dumps({"request": q}).encode(),
                                 headers={"content-type": "application/json", "user-agent": f"battery-{i}"})
    try:
        urllib.request.urlopen(req, timeout=25)
        return 200, {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

ok = 0
for i, (q, topic, live_exp) in enumerate(Q):
    code, d = call(i, q)
    fp = d.get("free_preview")
    lv = bool(fp and fp.get("live_preview"))
    tease = (fp or {}).get("teaser", "")
    if topic == "__NONE__":
        good = fp is None and not lv
    elif topic is None:
        good = fp is not None and "15,500+" in tease and not lv
    else:
        good = fp is not None and topic.lower() in tease.lower() and lv == live_exp
    ok += good
    print(("PASS" if good else "FAIL"), code, f"live={lv}", "|", q[:60], "|", tease[:70].replace("\n", " "))
print(f"{ok}/{len(Q)} pass")
