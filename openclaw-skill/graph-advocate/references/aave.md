# Aave MCP Reference

`npx graph-aave-mcp` — 40 tools across 16 Graph subgraphs + Aave V4 API.

## V2/V3 Tools (Graph Subgraphs)
Requires GRAPH_API_KEY. 16 tools covering 7 chains.

| Tool | Description |
|------|-------------|
| list_aave_chains | Supported chains with subgraph IDs |
| get_aave_reserves | All active markets — TVL, APY, LTV |
| get_aave_reserve | Deep detail on one asset |
| get_reserve_rate_history | Historical APY, utilization |
| get_user_positions | User's deposits, borrows, health factor |
| get_liquidations | Recent liquidation events |
| get_flash_loans | Flash loan transactions |
| get_governance_proposals | Aave governance |

## V4 Tools (Aave API — no key needed)
16 tools via api.aave.com.

| Tool | Description |
|------|-------------|
| get_v4_hubs | Liquidity hubs (Core, Plus, Prime) |
| get_v4_spokes | Cross-chain spokes (9 types) |
| get_v4_reserves | Per-spoke reserves with APYs |
| get_v4_user_positions | Cross-chain positions, health factor |
| get_v4_user_summary | Aggregated portfolio |
| get_v4_exchange_rate | Token prices via Chainlink |
| get_v4_swap_quote | CoW Protocol swap pricing |
| get_v4_claimable_rewards | Merkl and points rewards |

## Install
```bash
claude mcp add graph-aave -- npx -y graph-aave-mcp
export GRAPH_API_KEY=your-key-here
```
