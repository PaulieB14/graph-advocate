#!/usr/bin/env python3
"""
Update on-chain `agentWallet` for Graph Advocate (Base agent #41034)
from graphadvocate.eth -> the actual x402 payTo wallet 0x0FF5A6...

Why this is needed: the agent0 subgraph indexes `agentWallet` from the
on-chain MetadataSet event. Today it points at the identity wallet, not
the wallet that actually receives x402 USDC, so revenue cannot be joined
to the registered agent.

The contract enforces that the new wallet authorize itself via an
EIP-712 signature (AgentWalletSet typehash). Submitting the tx requires
the owner of agent #41034 (graphadvocate.eth).

Run:
    PK_OWNER=0x... PK_NEW_WALLET=0x... python scripts/fix_agent_wallet.py
    PK_OWNER=0x... PK_NEW_WALLET=0x... python scripts/fix_agent_wallet.py --send
"""
import argparse
import os
import sys
import time

from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

CHAIN_ID = 8453
AGENT_ID = 41034
IDENTITY_REGISTRY = Web3.to_checksum_address("0x8004A169FB4a3325136EB29fA0ceB6D2e539a432")
NEW_WALLET = Web3.to_checksum_address("0x0FF5A6ecef783BBA35463ec2F8403B9B5e9e7C86")
EXPECTED_OWNER = Web3.to_checksum_address("0x575267eED09c338FAE5716A486A7B58A5749A292")
DEFAULT_RPC = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")

ABI = [
    {"type": "function", "name": "ownerOf", "stateMutability": "view",
     "inputs": [{"name": "tokenId", "type": "uint256"}],
     "outputs": [{"name": "", "type": "address"}]},
    {"type": "function", "name": "getAgentWallet", "stateMutability": "view",
     "inputs": [{"name": "agentId", "type": "uint256"}],
     "outputs": [{"name": "", "type": "address"}]},
    {"type": "function", "name": "setAgentWallet", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "agentId", "type": "uint256"},
         {"name": "newWallet", "type": "address"},
         {"name": "deadline", "type": "uint256"},
         {"name": "signature", "type": "bytes"},
     ],
     "outputs": []},
]

EIP712_DOMAIN = {
    "name": "ERC8004IdentityRegistry",
    "version": "1",
    "chainId": CHAIN_ID,
    "verifyingContract": IDENTITY_REGISTRY,
}
EIP712_TYPES = {
    "AgentWalletSet": [
        {"name": "agentId", "type": "uint256"},
        {"name": "newWallet", "type": "address"},
        {"name": "owner", "type": "address"},
        {"name": "deadline", "type": "uint256"},
    ],
}


def build_signature(new_wallet_pk: str, owner_addr: str, deadline: int) -> bytes:
    new_wallet_acct = Account.from_key(new_wallet_pk)
    if Web3.to_checksum_address(new_wallet_acct.address) != NEW_WALLET:
        raise SystemExit(
            f"PK_NEW_WALLET is for {new_wallet_acct.address}, expected {NEW_WALLET}"
        )

    typed = {
        "domain": EIP712_DOMAIN,
        "types": EIP712_TYPES,
        "primaryType": "AgentWalletSet",
        "message": {
            "agentId": AGENT_ID,
            "newWallet": NEW_WALLET,
            "owner": Web3.to_checksum_address(owner_addr),
            "deadline": deadline,
        },
    }
    encoded = encode_typed_data(full_message=typed)
    signed = new_wallet_acct.sign_message(encoded)
    return signed.signature


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--send", action="store_true",
                   help="Broadcast the tx (default is dry-run: prints calldata only)")
    p.add_argument("--rpc", default=DEFAULT_RPC)
    args = p.parse_args()

    pk_owner = os.environ.get("PK_OWNER")
    pk_new = os.environ.get("PK_NEW_WALLET")
    if not pk_owner or not pk_new:
        sys.exit("Set PK_OWNER (graphadvocate.eth) and PK_NEW_WALLET (0x0FF5A6...) env vars")

    w3 = Web3(Web3.HTTPProvider(args.rpc))
    if not w3.is_connected():
        sys.exit(f"Could not connect to {args.rpc}")

    owner_acct = Account.from_key(pk_owner)
    if Web3.to_checksum_address(owner_acct.address) != EXPECTED_OWNER:
        sys.exit(f"PK_OWNER is for {owner_acct.address}, expected {EXPECTED_OWNER}")

    contract = w3.eth.contract(address=IDENTITY_REGISTRY, abi=ABI)
    on_chain_owner = contract.functions.ownerOf(AGENT_ID).call()
    current_wallet = contract.functions.getAgentWallet(AGENT_ID).call()
    print(f"agent #{AGENT_ID} owner on-chain: {on_chain_owner}")
    print(f"current agentWallet:        {current_wallet}")
    print(f"target agentWallet:         {NEW_WALLET}")
    if current_wallet.lower() == NEW_WALLET.lower():
        print("Already set. Nothing to do.")
        return

    deadline = int(time.time()) + 240
    sig = build_signature(pk_new, owner_acct.address, deadline)
    print(f"deadline:    {deadline} (now+240s)")
    print(f"signature:   0x{sig.hex()}")

    tx = contract.functions.setAgentWallet(AGENT_ID, NEW_WALLET, deadline, sig).build_transaction({
        "from": owner_acct.address,
        "nonce": w3.eth.get_transaction_count(owner_acct.address),
        "chainId": CHAIN_ID,
    })
    gas_est = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas_est * 12 // 10)
    fees = w3.eth.fee_history(1, "latest")
    base_fee = fees["baseFeePerGas"][-1]
    tx["maxPriorityFeePerGas"] = w3.to_wei(0.001, "gwei")
    tx["maxFeePerGas"] = base_fee * 2 + tx["maxPriorityFeePerGas"]
    print(f"gas estimate: {gas_est} (sending with {tx['gas']})")
    print(f"maxFeePerGas: {tx['maxFeePerGas']} wei")

    if not args.send:
        print("\nDry-run only. Re-run with --send to broadcast.")
        return

    signed = owner_acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"\nbroadcast: 0x{tx_hash.hex()}")
    print(f"  https://basescan.org/tx/0x{tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    print(f"status: {'success' if receipt.status == 1 else 'FAILED'} in block {receipt.blockNumber}")


if __name__ == "__main__":
    main()
