"""Send a 1-wei ETH "correction notice" tx on Base from GA's outbound hot
wallet to the EIP-7702 buyer who paid GA for two wrong answers at 23:48-23:50
UTC on 2026-06-21.

The buyer scored their OWN wallet via /hyperliquid/score and /polymarket/risk
back-to-back (counterparty reconnaissance pattern) and walked away with:
  - "never interacted with Hyperliquid" - they had 22 fills on HL native
  - "Smart contract wallet, likely Gnosis Safe" - they're EIP-7702 delegated EOA

Both fixed in commit 2401d04. This script sends a tiny ETH tx on Base with
ASCII memo in calldata announcing the fix + delegate they can re-query. No
ERC-8004 / ENS / agent-registry profile for this wallet, so onchain calldata
is the only address-targetable channel.

Reads GA_BASE_WALLET_PK from env. Caps at 1 wei + ~0.000005 ETH gas budget.
Idempotent in spirit - re-running just sends another (cheap) tx with a fresh
nonce.
"""
from __future__ import annotations

import json
import os
import sys

from eth_account import Account
from web3 import Web3

TARGET = "0x5c3d61167d9dfa2e4171416d08484220f1374456"
DELEGATE = "0x5a7fc11397e9a8ad41bf10bf13f22b0a63f96f6d"
MEMO = (
    "graphadvocate.com - wallet vetting bugs fixed (commit 2401d04). "
    "Your wallet is EIP-7702 delegated EOA (delegate " + DELEGATE + ", "
    "ghost_fill_risk depends on whether delegate implements ERC-1271), "
    "NOT a Gnosis Safe. HL: 22 fills exist, classification=insufficient_data, "
    "not 'never interacted' - re-query /agent/score for the corrected answer."
)
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
    print(f"# sender:   {sender}  (eth balance {bal_eth})")
    print(f"# target:   {target}")
    print(f"# memo len: {len(MEMO)} ASCII chars")
    print(f"# memo:     {MEMO!r}")

    if bal_wei < 5_000_000_000_000:  # ~0.000005 ETH floor for gas
        print(json.dumps({"ok": False, "error": "balance too low for gas"}))
        return 3

    data = MEMO.encode("ascii")
    if len(data) > 1024:
        print(json.dumps({"ok": False, "error": "memo too long"}))
        return 4

    nonce = w3.eth.get_transaction_count(sender)
    gas_price = w3.eth.gas_price
    # Estimate gas with the memo data
    tx_for_estimate = {
        "from": sender,
        "to": target,
        "value": 1,
        "data": "0x" + data.hex(),
    }
    gas_est = w3.eth.estimate_gas(tx_for_estimate)
    gas_cost_eth = w3.from_wei(gas_est * gas_price, "ether")
    print(f"# gas est:  {gas_est} @ {gas_price} wei  ≈ {gas_cost_eth} ETH")

    if input("\nSend? [y/N]: ").strip().lower() != "y":
        print(json.dumps({"ok": False, "aborted_by_user": True}))
        return 0

    tx = {
        "from": sender,
        "to": target,
        "value": 1,
        "data": "0x" + data.hex(),
        "gas": gas_est + 2000,  # small buffer
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": 8453,
    }
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hash_hex = tx_hash.hex()
    print(json.dumps({
        "ok": True,
        "tx_hash": tx_hash_hex,
        "basescan": f"https://basescan.org/tx/0x{tx_hash_hex}",
        "sender": sender,
        "target": target,
        "memo": MEMO,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
