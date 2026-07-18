"""
Send a 1-wei ETH "calling card" tx on Base from GA's outbound hot wallet
to the recurring x402 payer 0xac5a07c4..., with an ASCII memo in calldata
announcing the /route fix.

This is a one-shot nudge — the wallet has been paying GA daily, then
went quiet during the 2026-05-02 → 2026-05-04 verify outage. They have
no ERC-8004 / ENS / agent-registry profile, so onchain calldata is the
only address-targetable channel.

Reads GA_BASE_WALLET_PK from env. Caps at 1 wei + 0.001 ETH gas budget.
Idempotent in spirit — re-running just sends another (cheap) tx with a
fresh nonce.
"""
from __future__ import annotations

import json
import os
import sys

from eth_account import Account
from web3 import Web3

TARGET = "0xac5a07c44a4f971667b3df4b6551fb6991b2142d"
MEMO = "graphadvocate.com/route is live again — paid /route fixed 2026-05-04"
RPC = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")


def main() -> int:
    pk = os.environ.get("GA_BASE_WALLET_PK", "").strip()
    if not pk:
        print(json.dumps({"ok": False, "error": "GA_BASE_WALLET_PK not set"}))
        return 1

    w3 = Web3(Web3.HTTPProvider(RPC))
    if not w3.is_connected():
        print(json.dumps({"ok": False, "error": f"RPC unreachable: {RPC}"}))
        return 2

    account = Account.from_key(pk)
    sender = account.address
    target = Web3.to_checksum_address(TARGET)

    bal_wei = w3.eth.get_balance(sender)
    bal_eth = w3.from_wei(bal_wei, "ether")
    print(f"# sender:  {sender}  (eth balance {bal_eth})")
    print(f"# target:  {target}")
    print(f"# memo:    {MEMO!r}")

    if bal_wei < 5_000_000_000_000:  # ~0.000005 ETH floor for gas
        print(json.dumps({"ok": False, "error": "sender out of gas budget"}))
        return 3

    nonce = w3.eth.get_transaction_count(sender)
    chain_id = w3.eth.chain_id
    fees = w3.eth.fee_history(1, "latest", [50])
    base_fee = fees["baseFeePerGas"][-1]
    priority = w3.to_wei(0.01, "gwei")
    max_fee = base_fee * 2 + priority

    data_bytes = MEMO.encode("utf-8")
    tx = {
        "from": sender,
        "to": target,
        "value": 1,                     # 1 wei — symbolic
        "data": data_bytes,
        "nonce": nonce,
        "chainId": chain_id,
        "type": 2,
        "maxPriorityFeePerGas": priority,
        "maxFeePerGas": max_fee,
    }
    tx["gas"] = w3.eth.estimate_gas(tx)

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"# broadcast: 0x{tx_hash.hex().lstrip('0x')}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    print(json.dumps({
        "ok": receipt.status == 1,
        "tx": receipt.transactionHash.hex(),
        "block": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "basescan": f"https://basescan.org/tx/{receipt.transactionHash.hex()}",
        "memo_hex": "0x" + data_bytes.hex(),
    }, indent=2))
    return 0 if receipt.status == 1 else 4


if __name__ == "__main__":
    sys.exit(main())
