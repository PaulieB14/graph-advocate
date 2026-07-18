"""Demo script: pay $0.01 USDC via x402 to Graph Advocate's /route endpoint
and print the routed query response. Used as the HOOK shot in the demo.

Set X402_TIP_PK in env to the sender wallet's private key (graphadvocate.eth
works fine for the demo).
"""
from __future__ import annotations
import os
import sys
import asyncio
import json

import httpx
from eth_account import Account
from x402.client import x402Client
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.http.clients.httpx import x402HttpxClient


async def main() -> None:
    pk = os.environ.get("X402_TIP_PK", "")
    if not pk:
        print("set X402_TIP_PK env var (sender wallet's PK)")
        sys.exit(1)

    account = Account.from_key(pk)
    print(f"  payer:  {account.address}")
    print(f"  url:    https://graphadvocate.com/route")
    print(f"  query:  Top Uniswap V3 pools on Ethereum by TVL")
    print(f"")

    client = x402Client()
    client.register("eip155:8453", ExactEvmClientScheme(signer=account))

    payload = {
        "request": "Top Uniswap V3 pools on Ethereum by TVL",
    }

    async with x402HttpxClient(client, timeout=60.0) as http:
        resp = await http.post(
            "https://graphadvocate.com/route",
            json=payload,
        )

    print(f"  status: {resp.status_code}")
    if resp.status_code == 200:
        try:
            data = resp.json()
            print(f"  service: {data.get('recommendation')}")
            print(f"  confidence: {data.get('confidence')}")
            qr = data.get("query_ready", {})
            print(f"  subgraph_id: {qr.get('args', {}).get('subgraph_id', 'n/a')}")
            qv = data.get("query_validation", {})
            print(f"  query_validation.ok: {qv.get('ok')}")
            print(f"")
            print(f"  ✓ paid $0.01 USDC, got verified routing recommendation")
        except Exception as e:
            print(f"  raw: {resp.text[:300]}")
    else:
        print(f"  body: {resp.text[:300]}")


if __name__ == "__main__":
    asyncio.run(main())
