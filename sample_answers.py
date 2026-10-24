"""'Questions people ask' section for /llms.txt and /SKILL.md.

Built from the questions most often seen stopping at the 402 paywall. Each
entry: an example question, the shape of the paid answer (described from the
endpoint's catalog description - no invented numbers), the exact endpoint and
its price. Prices are looked up from `_PAID_CATALOG` by the caller so this
section can never quote a price the middleware does not charge.
"""
from __future__ import annotations

SITE = "https://graphadvocate.com"
ROUTE_PRICE = "$0.01"  # /route x402 price (live 402 challenge amount 10000 = $0.01)

# (topic, example question, path, request body, what the answer contains)
SAMPLES: list[tuple[str, str, str, str, str]] = [
    ("Uniswap V3 pools ranked by fee revenue",
     "Which Uniswap V3 pools on Ethereum earned the most fees this month?",
     "/route", '{"request": "Which Uniswap V3 pools on Ethereum earned the most fees this month?"}',
     "names the official Uniswap V3 Ethereum subgraph (5zvR82Qo…) and returns a ready-to-run "
     "GraphQL query ordering pools by fees, with field-trap warnings (e.g. TVL fields)."),
    ("Uniswap token liquidity / deepest pool",
     "Where is WETH's deepest Uniswap venue and is the flow two-way?",
     "/uniswap/pretrade", '{"token": "WETH", "chain": "ethereum"}',
     "real liquidity, deepest venue ranked by volume (not TVL), honeypot two-way-flow check "
     "and daily volume trend."),
    ("Hyperliquid wallet leverage and liquidation risk",
     "How risky is Hyperliquid wallet 0x…? Is it getting liquidated?",
     "/hyperliquid/risk", '{"user": "0x..."}',
     "counterparty risk for the wallet: liquidation rate, funding burn and a recent-outflow flag."),
    ("Hyperliquid wallet positions and PnL",
     "What positions does Hyperliquid wallet 0x… hold and what is its PnL?",
     "/hyperliquid/pnl", '{"user": "0x..."}',
     "full trader dossier: skill metrics plus open positions and recent fills."),
    ("Curve pools / which subgraph to use",
     "Which Curve subgraph should I query for pools on Arbitrum, and how?",
     "/route", '{"request": "Which Curve subgraph should I query for pools on Arbitrum?"}',
     "the right Curve / Messari-standard DEX deployment for that chain plus a working pool query."),
    ("Polymarket trader skill",
     "Is Polymarket wallet 0x… a skilled trader?",
     "/polymarket/pnl-quick", '{"wallet": "0x..."}',
     "skill score, classification, realized PnL and win rate for the wallet."),
    ("Top Polymarket traders",
     "Who are the top Polymarket traders by PnL today?",
     "/polymarket/leaders", '{"sort_by": "total_pnl", "interval": "1d", "limit": 10}',
     "leaderboard of top traders ranked by PnL or volume over the window."),
    ("Kalshi vs Polymarket",
     "Where do Kalshi and Polymarket disagree right now?",
     "/kalshi-polymarket/spread", "{}",
     "matched Kalshi and Polymarket markets on a topic with the price gap between venues."),
]


def render(price_for_path) -> str:
    """Markdown section. `price_for_path(path) -> '$0.0x' | ''`."""
    lines = [
        "## Questions people ask (and what the paid answer looks like)",
        "",
        "Every paid call settles in USDC on Base via x402: POST the body, get a 402,",
        "sign with any x402 SDK (x402-fetch / x402-axios) and retry. Unpaid real",
        "questions get a free one-line preview in the 402 body.",
        "",
    ]
    for topic, q, path, body, ans in SAMPLES:
        price = ROUTE_PRICE if path == "/route" else (price_for_path(path) or "see 402")
        lines += [
            f"### {topic}",
            f"- Ask: \"{q}\"",
            f"- Answer: {ans}",
            f"- Endpoint: POST {SITE}{path}  body {body}  price {price} USDC (x402, Base)",
            "",
        ]
    return "\n".join(lines)
