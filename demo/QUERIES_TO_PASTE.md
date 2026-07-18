# Demo queries — copy/paste into /chat one at a time

When recording the demo segment (0:50–1:50), open
https://graphadvocate.com/chat in a browser tab,
and paste these queries one at a time. Wait ~10 seconds after each so the
response renders fully before pasting the next.

### Query 1 (Subgraph routing — Uniswap V3)
```
Top Uniswap V3 pools on Ethereum mainnet by TVL
```

### Query 2 (Token API routing — holders)
```
Top 20 USDC holders on Ethereum
```

### Query 3 (MCP package routing — Aave)
```
Aave liquidations above 25K USD on Ethereum last week
```

### Query 4 (Polymarket via Pinax — just-launched)
```
Top Polymarket prediction markets by 24h volume
```

Each query routes to a different service, demonstrating the agent's
multi-protocol awareness. The chat UI renders each response as a styled
card with the recommendation, query, and dry-run validation status.
