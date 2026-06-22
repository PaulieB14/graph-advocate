"""Send a 1-wei ETH correction notice on Base to GA's Ampersend repeat
customer (0x9cc42f3d…) after their 2 /onchain-x402/address calls timed
out at 04:54-04:55 UTC on 2026-06-22.

They paid GA $0.07 today via hl-score + hl-pnl (those succeeded). The
2 failed /onchain-x402/address calls hit Graph Network's load-balancing
to slow indexers — fixed in commit fd385ea (query split + 20s→30s timeout).

The address they queried (0x8ba1f109551bd432803012645ac136ddd64dba72) has
zero x402 activity in the index, so the answer is simple: not_in_index.
Memo embeds the answer + endpoint-now-fixed signal so they can retry
with confidence.
"""
from __future__ import annotations
import json, os, sys
from eth_account import Account
from web3 import Web3

TARGET = "0x9cc42f3d9245b867acccd630b43f906c1665b176"
MEMO = (
    "graphadvocate.com - /onchain-x402/address ReadTimeout fixed (commit fd385ea, "
    "deployed 2026-06-22). Your two failed calls at 04:54/04:55 UTC: target wallet "
    "0x8ba1f109551bd432803012645ac136ddd64dba72 has ZERO x402 activity in the index "
    "(is_in_index=false, indexed_through_block=47668057, no recent payments either "
    "direction). Endpoint now returns in ~3s; safe to retry."
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
    print(f"# sender:   {sender} (eth {w3.from_wei(bal_wei,'ether')})")
    print(f"# target:   {target}")
    print(f"# memo len: {len(MEMO)} ASCII chars")
    print(f"# memo:     {MEMO!r}")
    if bal_wei < 5_000_000_000_000:
        print(json.dumps({"ok": False, "error": "balance too low"}))
        return 3
    data = MEMO.encode("ascii")
    nonce = w3.eth.get_transaction_count(sender)
    gas_price = w3.eth.gas_price
    tx_for_estimate = {"from": sender, "to": target, "value": 1, "data": "0x"+data.hex()}
    gas_est = w3.eth.estimate_gas(tx_for_estimate)
    print(f"# gas est:  {gas_est} @ {gas_price} wei  ≈ {w3.from_wei(gas_est * gas_price,'ether')} ETH")
    if input("\nSend? [y/N]: ").strip().lower() != "y":
        print(json.dumps({"ok": False, "aborted_by_user": True}))
        return 0
    tx = {
        "from": sender, "to": target, "value": 1,
        "data": "0x"+data.hex(), "gas": gas_est + 2000,
        "gasPrice": gas_price, "nonce": nonce, "chainId": 8453,
    }
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    th = tx_hash.hex()
    print(json.dumps({
        "ok": True, "tx_hash": th,
        "basescan": f"https://basescan.org/tx/0x{th}",
        "sender": sender, "target": target, "memo": MEMO,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
