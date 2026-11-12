"""Copy-paste payment help attached to every 402 (JSON field `how_to_pay`) and rendered as a
small HTML page for browsers that GET a paid endpoint.

x402 is "HTTP 402 + sign a USDC authorization + retry". An x402 client does all three, so the
whole job for a buyer is: give a client a funded Base wallet key and call the URL. Snippets use
the current v2 packages (@x402/fetch + @x402/evm; python `x402`).
"""
from __future__ import annotations

import html
import json
from typing import Any

FREE_RULE = (
    "Free: every unpaid request gets the live top-3 rows in `free_preview.live_preview` (no signup). "
    "POST / (A2A) with metadata.sender = your 0x wallet also gets 3 full answers/day. "
    "POST /route and the other paid endpoints cost the listed price per call, from the first call."
)


def how_to_pay(url: str, body: dict | None, price: str, method: str = "POST") -> dict:
    body_json = json.dumps(body or {"request": "top Uniswap V3 pools on Ethereum by volume"})
    js = (
        'import { wrapFetchWithPaymentFromConfig } from "@x402/fetch";\n'
        'import { ExactEvmScheme } from "@x402/evm";\n'
        'import { privateKeyToAccount } from "viem/accounts";\n'
        "\n"
        "// A Base wallet holding a little USDC (and no ETH needed: payment is a signed authorization).\n"
        'const account = privateKeyToAccount(process.env.EVM_PRIVATE_KEY);\n'
        "const pay = wrapFetchWithPaymentFromConfig(fetch, {\n"
        '  schemes: [{ network: "eip155:8453", client: new ExactEvmScheme(account) }],\n'
        "});\n"
        f'const res = await pay("{url}", {{\n'
        f'  method: "{method}", headers: {{ "content-type": "application/json" }},\n'
        f"  body: JSON.stringify({body_json}),\n"
        "});\n"
        "console.log(await res.json());   // 402 -> signs -> retries -> rows\n"
    )
    py = (
        "# pip install 'x402[evm,httpx]' eth-account\n"
        "import asyncio, os\n"
        "from eth_account import Account\n"
        "from x402 import x402Client\n"
        "from x402.http.clients import x402HttpxClient\n"
        "from x402.mechanisms.evm import EthAccountSigner\n"
        "from x402.mechanisms.evm.exact import ExactEvmScheme\n"
        "\n"
        "async def main():\n"
        '    signer = EthAccountSigner(Account.from_key(os.environ["EVM_PRIVATE_KEY"]))\n'
        "    client = x402Client()\n"
        '    client.register("eip155:8453", ExactEvmScheme(signer))\n'
        "    async with x402HttpxClient(client) as http:\n"
        f'        r = await http.post("{url}", json={body_json})\n'
        "        await r.aread(); print(r.json())\n"
        "asyncio.run(main())\n"
    )
    curl = (
        f"# 1) see the price and exact challenge (free):\n"
        f"curl -i -X {method} {url} -H 'content-type: application/json' -d '{body_json}'\n"
        "#    -> HTTP 402, `payment-required` header (base64 JSON), `free_preview.live_preview`\n"
        "# 2) sign that challenge with any x402 client (above) and re-send with the header it produces:\n"
        f"curl -X {method} {url} -H 'content-type: application/json' -H \"PAYMENT-SIGNATURE: $SIGNED\" -d '{body_json}'"
    )
    mcp = (
        'npx -y graph-advocate-mcp   # tools: route_data_request ($0.01), preflight_price (free), check_quota (free)\n'
        "# The MCP holds no key: it returns the 402 challenge as data; your wallet/x402 skill settles it."
    )
    return {
        "one_step": (f"Give any x402 client a Base wallet with >= {price} USDC and call this URL: it reads the 402, "
                     "signs a gas-free USDC authorization, retries, and returns the paid result. "
                     "No account, no API key."),
        "price": price,
        "network": "Base mainnet (eip155:8453), asset USDC 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "free": FREE_RULE,
        "javascript_x402_fetch": js,
        "python_x402_httpx": py,
        "curl": curl,
        "mcp": mcp,
        "docs": "https://graphadvocate.com/llms.txt",
    }


def render_html(payload: dict[str, Any]) -> str:
    """Human view of a 402 for browsers. `payload` is the same dict served as JSON."""
    e = html.escape
    fp = payload.get("free_preview") or {}
    lv = fp.get("live_preview") or {}
    h2p = payload.get("how_to_pay") or {}
    resource = (payload.get("resource") or {}).get("url", "")
    rows_html = ""
    if lv.get("rows"):
        cols = [c for c in lv["rows"][0].keys() if c not in ("raw",)]
        rows_html = ("<h2>Free live rows</h2><p>" + e(str(lv.get("scope", ""))) + " &mdash; fetched " + e(str(lv.get("fetched_at", "")))
                     + "</p><table><tr>" + "".join(f"<th>{e(c)}</th>" for c in cols) + "</tr>"
                     + "".join("<tr>" + "".join(f"<td>{e(str(r.get(c, '')))}</td>" for c in cols) + "</tr>" for r in lv["rows"])
                     + "</table><p class=n>" + e(str(lv.get("note", ""))) + "</p>")
    snippets = "".join(
        f"<h3>{e(t)}</h3><pre>{e(h2p.get(k, ''))}</pre>"
        for t, k in (("JavaScript (x402-fetch)", "javascript_x402_fetch"), ("Python (x402 + httpx)", "python_x402_httpx"),
                     ("curl", "curl"), ("MCP", "mcp")) if h2p.get(k))
    return (
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Graph Advocate &mdash; payment required</title><style>"
        "body{font:15px/1.5 system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#111}"
        "pre{background:#0b1020;color:#d6e2ff;padding:12px;border-radius:8px;overflow:auto;font-size:12.5px}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;font-size:13px}"
        "th{background:#f4f4f8}.n{color:#555;font-size:13px}code{background:#eef;padding:1px 4px;border-radius:4px}"
        "</style></head><body>"
        f"<h1>402 &mdash; this endpoint is paid ({e(str(h2p.get('price', '')))} USDC on Base)</h1>"
        f"<p><code>{e(resource)}</code></p>"
        f"<p><b>Pay in one step:</b> {e(str(h2p.get('one_step', '')))}</p>"
        f"<p>{e(str(h2p.get('free', FREE_RULE)))}</p>"
        + rows_html + "<h2>Copy-paste</h2>" + snippets +
        "<p class=n>Machine-readable challenge: the <code>payment-required</code> response header (base64 JSON) or request with "
        "<code>Accept: application/json</code>. Docs: <a href='/llms.txt'>llms.txt</a> &middot; <a href='/openapi.json'>openapi.json</a> "
        "&middot; <a href='/.well-known/x402'>/.well-known/x402</a></p></body></html>"
    )
