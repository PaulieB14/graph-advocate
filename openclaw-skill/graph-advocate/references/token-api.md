# Token API Reference

Base URL: `https://token-api.thegraph.com`
Auth: `Authorization: Bearer <JWT>` or `X-Api-Key: <key>`
Get key: https://thegraph.market/auth/tokenapi-env

## Parameter Rules (CRITICAL)
- Use `network` (NOT chain, NOT network_id)
- Use `contract` (NOT token_address, NOT token)
- Networks: mainnet, base, matic, arbitrum-one, optimism, avalanche-mainnet, bsc-mainnet

## Common Contracts
| Token | Mainnet | Base |
|-------|---------|------|
| USDC | 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 | 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 |
| WETH | 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 | 0x4200000000000000000000000000000000000006 |
| USDT | 0xdAC17F958D2ee523a2206206994597C13D831ec7 | — |

## Key Endpoints
| Tool | Endpoint | Required Params |
|------|----------|-----------------|
| getV1EvmHolders | GET /v1/evm/holders | network, contract |
| getV1EvmBalances | GET /v1/evm/balances | network, address |
| getV1EvmSwaps | GET /v1/evm/swaps | network |
| getV1EvmTransfers | GET /v1/evm/transfers | network |
| getV1EvmPools | GET /v1/evm/pools | network |
| getV1EvmPoolsOhlc | GET /v1/evm/pools/ohlc | network, pool |
| getV1EvmNftSales | GET /v1/evm/nft/sales | network |
| getV1SvmBalances | GET /v1/svm/balances | network, owner |
| getV1SvmSwaps | GET /v1/svm/swaps | network |

## Full Specification
Fetch the complete endpoint reference (all params, response schemas, examples):
**https://token-api.thegraph.com/skills.md**

This skills.md is the authoritative source — if anything in this reference conflicts, trust skills.md.
