#!/usr/bin/env python3
"""
TKN Bulk Token Submitter
========================
Takes a list of token symbols, looks up their data from CoinGecko,
and outputs a TKN-compatible dataset JSON ready to submit as a PR
to https://github.com/tickerdao/tkn-cli

Usage:
    python3 tkn-bulk-add.py ONDO PEAQ ZKL MLN AZERO
    python3 tkn-bulk-add.py --file tokens.txt
    python3 tkn-bulk-add.py ONDO PEAQ --output my-submission.json

The output file can be used with:
    tkn generate --file output.json
    tkn upload --file output.json
Or submitted as a PR to tickerdao/tkn-cli/data/
"""

import argparse
import json
import sys
import time
import urllib.request


COINGECKO_API = "https://api.coingecko.com/api/v3"


def search_coingecko(symbol: str) -> dict | None:
    """Search CoinGecko for a token by symbol and return its data."""
    try:
        url = f"{COINGECKO_API}/search?query={symbol}"
        req = urllib.request.Request(url, headers={"User-Agent": "tkn-bulk-add/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        # Find exact symbol match (case-insensitive)
        for coin in data.get("coins", []):
            if coin.get("symbol", "").upper() == symbol.upper():
                return coin
    except Exception as e:
        print(f"  Warning: CoinGecko search failed for {symbol}: {e}", file=sys.stderr)
    return None


def get_coin_details(coin_id: str) -> dict | None:
    """Get detailed coin data from CoinGecko including contract addresses."""
    try:
        url = f"{COINGECKO_API}/coins/{coin_id}?localization=false&tickers=false&market_data=false&community_data=false&developer_data=false"
        req = urllib.request.Request(url, headers={"User-Agent": "tkn-bulk-add/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  Warning: CoinGecko details failed for {coin_id}: {e}", file=sys.stderr)
    return None


def build_tkn_entry(symbol: str, details: dict) -> dict:
    """Build a TKN dataset entry from CoinGecko data."""
    # Get the mainnet (Ethereum) contract address
    platforms = details.get("platforms", {})
    eth_address = platforms.get("ethereum", "")

    # Try other common chain mappings for TKN
    entry = {}

    if eth_address:
        entry["token_address"] = eth_address

    # Basic metadata
    entry["name"] = details.get("name", symbol)

    # Decimals from detail_platforms
    detail_platforms = details.get("detail_platforms", {})
    eth_detail = detail_platforms.get("ethereum", {})
    if isinstance(eth_detail, dict) and eth_detail.get("decimal_place") is not None:
        entry["decimals"] = str(eth_detail["decimal_place"])

    # Avatar / logo
    image = details.get("image", {})
    logo = image.get("large") or image.get("small") or image.get("thumb")
    if logo:
        entry["avatar"] = logo

    homepage = (details.get("links", {}).get("homepage", [None]) or [None])[0]
    if homepage:
        entry["website"] = homepage

    twitter = details.get("links", {}).get("twitter_screen_name")
    if twitter:
        entry["twitter"] = twitter

    github_repos = details.get("links", {}).get("repos_url", {}).get("github", [])
    if github_repos:
        entry["github"] = github_repos[0]

    description = details.get("description", {}).get("en", "")
    if description:
        # Truncate to first sentence
        first_sentence = description.split(". ")[0]
        if len(first_sentence) > 200:
            first_sentence = first_sentence[:200] + "..."
        entry["description"] = first_sentence

    # Multi-chain addresses — maps CoinGecko platform names to TKN field names
    # TKN supports: arb1, avaxc, base, bsc, cro, ftm, gno, matic, near, op, sol, trx, zil
    chain_map = {
        "arbitrum-one": "arb1_address",
        "avalanche": "avaxc_address",
        "base": "base_address",
        "binance-smart-chain": "bsc_address",
        "cronos": "cro_address",
        "fantom": "ftm_address",
        "xdai": "gno_address",
        "gnosis": "gno_address",
        "polygon-pos": "matic_address",
        "near-protocol": "near_address",
        "optimistic-ethereum": "op_address",
        "solana": "sol_address",
        "tron": "trx_address",
        "zilliqa": "zil_address",
    }
    for platform, tkn_field in chain_map.items():
        addr = platforms.get(platform, "")
        if addr:
            entry[tkn_field] = addr

    # Also capture any chains CoinGecko has that TKN doesn't map yet
    # (store as extra_chains for reference)
    unmapped = {}
    for platform, addr in platforms.items():
        if addr and platform != "ethereum" and platform not in chain_map:
            unmapped[platform] = addr
    if unmapped:
        entry["_extra_chains"] = unmapped

    return entry


def main():
    parser = argparse.ArgumentParser(description="Bulk lookup tokens and generate TKN dataset")
    parser.add_argument("symbols", nargs="*", help="Token symbols to look up (e.g. ONDO PEAQ ZKL)")
    parser.add_argument("--file", help="File with one symbol per line")
    parser.add_argument("--output", default="tkn-submission.json", help="Output JSON file (default: tkn-submission.json)")
    args = parser.parse_args()

    symbols = list(args.symbols)
    if args.file:
        with open(args.file) as f:
            symbols.extend(line.strip().upper() for line in f if line.strip())

    if not symbols:
        print("No symbols provided. Usage: python3 tkn-bulk-add.py ONDO PEAQ ZKL")
        sys.exit(1)

    print(f"Looking up {len(symbols)} tokens on CoinGecko...\n")

    dataset = {}
    found = 0
    missing = []

    for symbol in symbols:
        print(f"  {symbol}...", end=" ", flush=True)

        # Search for the coin
        coin = search_coingecko(symbol)
        if not coin:
            print("NOT FOUND on CoinGecko")
            missing.append(symbol)
            time.sleep(1.5)  # CoinGecko rate limit
            continue

        # Get details
        details = get_coin_details(coin["id"])
        if not details:
            print("DETAILS FAILED")
            missing.append(symbol)
            time.sleep(1.5)
            continue

        entry = build_tkn_entry(symbol, details)
        dataset[symbol.upper()] = entry
        found += 1

        addr = entry.get("token_address", "no mainnet address")
        chains = sum(1 for k in entry if k.endswith("_address"))
        print(f"OK — {addr[:20]}... ({chains} chains)")

        time.sleep(1.5)  # CoinGecko rate limit (30 req/min free tier)

    # Build output
    output = {"dataset": dataset}

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Found: {found}/{len(symbols)}")
    if missing:
        print(f"Missing: {', '.join(missing)}")
    print(f"Output: {args.output}")
    print(f"\nNext steps:")
    print(f"  1. Review {args.output} for accuracy")
    print(f"  2. Submit as PR to https://github.com/tickerdao/tkn-cli")
    print(f"     Or use tkn-cli: tkn generate --file {args.output}")


if __name__ == "__main__":
    main()
