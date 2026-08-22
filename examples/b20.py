"""B20 native token standard helpers for Base.

B20 ships in the Beryl hardfork (Base mainnet activation 2026-06-25 18:00 UTC,
Sepolia already activated 2026-06-18). It is Base's ERC-20-compatible token
standard implemented as Rust precompiles — Asset variant (configurable
decimals, rebase multiplier, announcements, batched issuance) and Stablecoin
variant (fixed 6 decimals, ISO currency code).

This module provides local O(1) classification helpers + async factory
queries for definitive verification. No RPC needed for the prefix/variant
check — the address encoding alone tells you which variant a token is.

Address layout (verified against B20Factory.getB20Address on Base Sepolia):
  bytes 0-9   : 10-byte B20 prefix  = 0xb2 + 9 zero bytes
  byte  10    : variant            = 0x00 ASSET, 0x01 STABLECOIN
  bytes 11-19 : 9-byte keccak256(deployer, salt)

Canonical precompile addresses (per Base StdPrecompiles.sol):
  B20_FACTORY         = 0xB20f000000000000000000000000000000000000
  POLICY_REGISTRY     = 0x8453000000000000000000000000000000000002
  ACTIVATION_REGISTRY = 0x8453000000000000000000000000000000000001
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx
from eth_utils import keccak

# ---- canonical precompile addresses (same on Sepolia + Mainnet) ----------
B20_FACTORY_ADDRESS = "0xB20f000000000000000000000000000000000000"
POLICY_REGISTRY_ADDRESS = "0x8453000000000000000000000000000000000002"
ACTIVATION_REGISTRY_ADDRESS = "0x8453000000000000000000000000000000000001"

# 10-byte address prefix shared by every B20 token. Verified by deriving
# addresses through B20Factory.getB20Address on Base Sepolia.
B20_PREFIX = "b200000000000000000000"  # 10 bytes / 20 hex chars (no 0x)

# Variant byte values (per IB20Factory.B20Variant enum)
VARIANT_ASSET = 0
VARIANT_STABLECOIN = 1
_VARIANT_NAMES = {VARIANT_ASSET: "ASSET", VARIANT_STABLECOIN: "STABLECOIN"}


def is_b20(addr: str) -> bool:
    """Returns True if `addr` matches the B20 address prefix.

    O(1) local check — does NOT verify the token was actually created by
    the factory (use is_b20_initialized for that). A prefix-matching
    address that's never been initialized will return True here but
    False from is_b20_initialized.
    """
    if not isinstance(addr, str) or not addr.startswith("0x") or len(addr) != 42:
        return False
    return addr[2:].lower().startswith(B20_PREFIX)


def b20_variant(addr: str) -> Optional[str]:
    """Returns 'ASSET', 'STABLECOIN', or None.

    Reads byte [10] of the address — no RPC call. Returns None for any
    non-B20 address. For B20 addresses with an unrecognized variant byte
    (future variants), returns 'UNKNOWN_<hex>'.
    """
    if not is_b20(addr):
        return None
    variant_byte = addr[2:].lower()[20:22]
    try:
        return _VARIANT_NAMES.get(int(variant_byte, 16), f"UNKNOWN_{variant_byte}")
    except ValueError:
        return None


# ---- async factory queries -------------------------------------------------


def _base_rpc(*, sepolia: bool = False) -> str:
    if sepolia:
        return os.environ.get("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")
    return os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")


async def is_b20_initialized(addr: str, *, sepolia: bool = False) -> bool:
    """Authoritative check — was this address created by the B20Factory?

    Calls B20Factory.isB20Initialized(addr) on Base. Returns False for any
    address whose prefix doesn't match (short-circuit, no RPC). Returns
    False on RPC error rather than raising — caller should treat None
    semantics as "unknown" if they need to distinguish.
    """
    if not is_b20(addr):
        return False
    sel = "0x" + keccak(text="isB20Initialized(address)")[:4].hex()
    data = sel + "0" * 24 + addr[2:].lower()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(_base_rpc(sepolia=sepolia), json={
                "jsonrpc": "2.0", "method": "eth_call",
                "params": [{"to": B20_FACTORY_ADDRESS, "data": data}, "latest"],
                "id": 1,
            })
            result = r.json().get("result") or "0x"
            return int(result, 16) == 1
    except Exception:
        return False


async def derive_b20_address(variant: int, deployer: str, salt: str = None, *, sepolia: bool = False) -> Optional[str]:
    """Compute the deterministic B20 address for (variant, deployer, salt).

    Useful for verifying a counterparty's anticipated B20 deployment, or
    pre-computing addresses for indexer registration. Calls the factory's
    getB20Address — no state-changing tx, no gas cost.
    """
    if variant not in (VARIANT_ASSET, VARIANT_STABLECOIN):
        return None
    salt_hex = (salt or "0x" + "0" * 64).removeprefix("0x").rjust(64, "0")
    sel = "0x" + keccak(text="getB20Address(uint8,address,bytes32)")[:4].hex()
    args = (
        f"{variant:064x}"
        + "0" * 24 + deployer.removeprefix("0x").lower()
        + salt_hex
    )
    data = sel + args
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(_base_rpc(sepolia=sepolia), json={
                "jsonrpc": "2.0", "method": "eth_call",
                "params": [{"to": B20_FACTORY_ADDRESS, "data": data}, "latest"],
                "id": 1,
            })
            result = r.json().get("result") or "0x"
            if result == "0x":
                return None
            return "0x" + result[-40:]
    except Exception:
        return None
