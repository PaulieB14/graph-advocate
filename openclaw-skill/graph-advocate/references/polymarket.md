# Polymarket MCP Reference

`npx graph-polymarket-mcp` — 31 tools combining 8 Graph subgraphs + REST APIs.

## REST API Tools (no key needed)
| Tool | Description |
|------|-------------|
| search_markets | Search markets by text |
| get_market_info | Market metadata |
| list_polymarket_events | Browse events |
| get_live_prices | Current token prices |
| get_live_spread | Bid/ask spread |
| get_live_orderbook | Full order book |
| get_price_history | Historical prices |
| get_last_trade | Most recent trade |
| get_clob_market | CLOB market details |
| search_markets_enriched | Search + auto-enrich with prices and resolution |

## Graph Subgraph Tools (needs GRAPH_API_KEY)
| Tool | Subgraph | Description |
|------|----------|-------------|
| get_market_data | Main | Markets, conditions, trader counts |
| get_account_pnl | Beefy P&L | Trader winRate, profitFactor, maxDrawdown |
| get_top_traders | Beefy P&L | Top traders by profit |
| get_market_open_interest | Open Interest | USDC locked per market |
| get_market_resolution | Resolution | UMA oracle lifecycle, disputes |
| get_trader_profile | Traders | Per-trader CTF events |
| get_orderbook_trades | Orderbook | Order fills, volume |

## Install
```bash
claude mcp add graph-polymarket -- npx -y graph-polymarket-mcp
export GRAPH_API_KEY=your-key-here
```

## Note
Polymarket is migrating to CTF Exchange V2 + new collateral token (Polymarket USD).
Some subgraph tools may need updating after migration completes (~late April 2026).
