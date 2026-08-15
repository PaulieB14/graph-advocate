"""Self-pay every paid GA endpoint once to refresh CDP Bazaar listings.

Why: as of 2026-05-10 only /route is on CDP Bazaar (last updated 2026-05-04
with the OLD pricing description). All 9 trader-intel endpoints
(/polymarket/*, /hyperliquid/*) shipped May 7-8 but were never paid by
external clients, so CDP's discovery never crawled+indexed them.

Each successful x402 payment forces CDP to re-index the resource with the
current 402 challenge metadata (extensions.bazaar block + description).

That mechanism is the whole point, and it cuts both ways: an endpoint nobody has
paid for is never indexed, so agents browsing Bazaar never find it, so nobody
pays for it. Registration is the only way out of that loop.

The target list is now derived from `_PAID_CATALOG` rather than typed here — see
`_load_targets`. The hand-written version was stuck at the 10 endpoints that
existed on 2026-05-10 while the catalogue grew to 24, so as of 2026-08-15 Bazaar
indexed 18 of 23 registerable paths.

Cost: ~$0.81 USDC for a full refresh, or use --only-missing to pay for just the
unindexed ones (5 paths / $0.16 as of 2026-08-15) + tiny gas on Base.

Run:
    set -a; . ~/.x402_wallets/ga_outbound.env; set +a
    python3 scripts/selfpay_refresh_bazaar_all.py --only-missing --dry-run  # preview, free
    python3 scripts/selfpay_refresh_bazaar_all.py --only-missing            # pay
"""
from __future__ import annotations
import asyncio, json, os, sys, time

# Docs-sample / well-known data so the underlying compute returns sensible JSON.
WALLET_PM   = "0x38e598961dd0456a7fb2e758bd433d3e59fb8a4a"  # Polymarket trader
WALLET_HL   = "0xac5a07c46b6987f8db7b8b69f0e9ab9683e07734"  # Hyperliquid trader
COND_PM     = "0x95b6c59b628f15a94e42e5fdd08909cae5760a5093777eceab53e9e4900326cf"
VAULT_HL    = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
COIN_HL     = "BTC"

BASE = "https://graphadvocate.com"

# Real sample inputs, keyed by catalog path. The catalog's own `body` carries
# PLACEHOLDERS ('0x…40hex'), which 400 before payment and so register nothing —
# these are the values that make the underlying compute return sensible JSON.
# The endpoint LIST is not written here: it comes from `_PAID_CATALOG` below.
SAMPLE_BODIES = {
    "/route":                    {"question": "Top 20 USDC holders on Ethereum"},
    "/ask":                      {"question": "Top 10 recipient addresses by payment count in the last 30 days"},
    "/onchain-x402/address":     {"address": WALLET_HL},
    "/polymarket/pnl-quick":     {"wallet": WALLET_PM},
    "/polymarket/pnl":           {"wallet": WALLET_PM},
    "/polymarket/screen":        {"condition_id": COND_PM, "n": 3},
    "/polymarket/risk":          {"wallet": WALLET_PM},
    "/polymarket/leaders":       {"limit": 5},
    "/hyperliquid/score":        {"user": WALLET_HL},
    "/hyperliquid/pnl":          {"user": WALLET_HL},
    "/hyperliquid/screen":       {"coin": COIN_HL, "n": 5},
    "/hyperliquid/vault":        {"vault": VAULT_HL},
    "/hyperliquid/risk":         {"user": WALLET_HL},
    "/hyperliquid/fills":        {"user": WALLET_HL},
    "/kalshi/consensus-trend":   {"limit": 5},
    "/kalshi-polymarket/spread": {"limit": 5},
    "/kalshi/sports-live-edge":  {"limit": 5},
    "/narrative/divergence":     {"limit": 5},
    "/predmarket/spread":        {"limit": 5},
    "/uniswap/pretrade":         {"token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "chain": "base"},
    "/uniswap/basis":            {"coin": COIN_HL, "chain": "ethereum"},
    "/uniswap/traders":          {"token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "chain": "base"},
    "/agent/score":              {"wallet": WALLET_HL, "days": 30},
    # /tip takes any amount and registering it buys nothing a priced endpoint
    # does not already buy. Deliberately excluded; see SKIP below.
}
SKIP = {"/tip"}


def _load_targets():
    """Build the target list from `_PAID_CATALOG`, the single source of truth.

    This list used to be typed by hand. It was written 2026-05-10 with the 10
    endpoints that existed then and never grew, while the catalogue reached 24 —
    so a "refresh every paid endpoint" run silently covered 10 of them, and the
    14 it skipped stayed invisible to CDP Bazaar. That is the same drift the
    2026-08-12 audit fixed for llms.txt, the README and the docs; this script was
    missed because nothing reads it but a human.

    Bazaar listing is settlement-triggered — this file's own docstring says it:
    an endpoint nobody has paid for is never indexed, so it is never discovered,
    so nobody pays for it. Coverage here is worth real money.

    Unknown paths raise rather than skip: a new priced endpoint must either get a
    sample body or be named in SKIP, so it can never fall out of a refresh run
    unnoticed the way these 14 did.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from a2a_server import _PAID_CATALOG

    targets, missing = [], []
    for entry in _PAID_CATALOG.values():
        path, price = entry.get("path"), entry.get("price")
        if not path or path in SKIP:
            continue
        if not price:  # /route bills the flat query price; catalogued blank
            price = "$0.01"
        body = SAMPLE_BODIES.get(path)
        if body is None:
            missing.append(path)
            continue
        targets.append(("POST", path, body, price.lstrip("$"),
                        f"register {path}"))
    if missing:
        raise SystemExit(
            "No sample body for priced endpoint(s): " + ", ".join(sorted(missing))
            + "\nAdd one to SAMPLE_BODIES (or to SKIP) — a refresh run must not "
              "silently omit a paid endpoint."
        )
    return sorted(targets, key=lambda t: t[1])


TARGETS = _load_targets()


def _bazaar_listed_paths():
    """Paths CDP Bazaar already indexes for graphadvocate.com.

    Paginated deliberately: the list is ~15k resources and a single default page
    is 100, so a naive fetch reports GA as absent entirely.
    """
    import urllib.request
    listed, off = set(), 0
    while True:
        url = ("https://api.cdp.coinbase.com/platform/v2/x402/discovery/"
               f"resources?limit=100&offset={off}")
        req = urllib.request.Request(url, headers={"User-Agent": "graph-advocate"})
        page = json.load(urllib.request.urlopen(req, timeout=40))
        items = page.get("items") or page.get("data") or []
        if not items:
            break
        for i in items:
            res = i.get("resource") or i.get("url") or ""
            if "graphadvocate.com" in res:
                listed.add(res.replace(BASE, "").rstrip("/"))
        off += len(items)
        if len(items) < 100:
            break
    return listed


async def main():
    only_missing = "--only-missing" in sys.argv
    dry_run = "--dry-run" in sys.argv

    targets = TARGETS
    if only_missing:
        listed = _bazaar_listed_paths()
        targets = [t for t in TARGETS if t[1] not in listed]
        print(f"# bazaar already lists {len(listed)} GA paths; "
              f"{len(targets)} of {len(TARGETS)} need registering")
        for t in targets:
            print(f"#   missing: {t[1]}")
        print()
        if not targets:
            print("nothing to do — every priced endpoint is already indexed")
            return

    if dry_run:
        total = sum(float(t[3]) for t in targets)
        print(f"# DRY RUN — would pay {len(targets)} endpoint(s), ${total:.2f} USDC total")
        for m, path, body, price, _ in targets:
            print(f"  {m} {path:<28} ${price}  {json.dumps(body)}")
        return

    pk = os.environ.get("GA_BASE_WALLET_PK", "").strip()
    if not pk:
        print(json.dumps({"ok": False, "error": "GA_BASE_WALLET_PK not set"}))
        sys.exit(1)
    if not pk.startswith("0x"):
        pk = "0x" + pk

    from eth_account import Account
    from x402 import x402Client, prefer_network
    from x402.mechanisms.evm.signers import EthAccountSigner
    from x402.mechanisms.evm.exact import ExactEvmScheme
    from x402.http.clients.httpx import wrapHttpxWithPayment

    account = Account.from_key(pk)
    signer = EthAccountSigner(account)
    client = x402Client()
    client.register("eip155:8453", ExactEvmScheme(signer=signer))
    client.register_policy(prefer_network("eip155:8453"))
    http = wrapHttpxWithPayment(client, timeout=120.0)

    print(f"# payer: {account.address}")
    expected_total = sum(float(t[3]) for t in targets)
    print(f"# total expected spend: ${expected_total:.2f}")
    print()

    summary = []
    for method, path, body, price, purpose in targets:
        url = f"{BASE}{path}"
        print(f"=== {method} {path}  (${price})  — {purpose} ===")
        t0 = time.time()
        try:
            resp = await http.request(method, url, json=body)
            settled = bool(resp.headers.get("x-payment-response"))
            try:
                snippet = json.dumps(resp.json())[:200]
            except Exception:
                snippet = resp.text[:200]
            elapsed = time.time() - t0
            print(f"  HTTP {resp.status_code}  settled={settled}  latency={elapsed:.2f}s")
            print(f"  body: {snippet}")
            summary.append({
                "path": path, "status": resp.status_code, "settled": settled,
                "price_usd": price, "ok": resp.status_code == 200 and settled,
            })
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {str(e)[:200]}")
            summary.append({"path": path, "ok": False, "error": str(e)[:200]})
        print()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    ok = sum(1 for s in summary if s.get("ok"))
    print(f"  {ok}/{len(summary)} succeeded with settlement")
    actual_spent = sum(float(s["price_usd"]) for s in summary if s.get("ok") and "price_usd" in s)
    print(f"  total spent on settled calls: ${actual_spent:.2f}")
    print()
    print(f"  failures:")
    for s in summary:
        if not s.get("ok"):
            err = s.get("error")
            if not err:
                status = s.get("status")
                settled = s.get("settled")
                err = f"status={status} settled={settled}"
            print(f"    - {s['path']}: {err}")


if __name__ == "__main__":
    asyncio.run(main())
