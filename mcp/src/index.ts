#!/usr/bin/env node
/**
 * graph-advocate-mcp — Graph Advocate as an installed dependency.
 *
 * GA has always been a URL: agents discovered it, called it once, and never
 * came back. 8,242 lifetime requests produced 20 paying customers, because
 * nothing about a URL compounds. An MCP server does: it is installed once and
 * then called every session, by a loop nobody has to re-acquire.
 *
 * **This package holds no private key, by design.** Free endpoints answer
 * directly. A paid endpoint returns its 402 challenge as structured data — the
 * price, the asset, the payTo address, and the exact body to send again — so
 * the *caller's* wallet settles it (Claude Code's x402 skill, an x402 SDK, or a
 * human). Shipping a signing key inside an npm package that thousands of people
 * `npx` is a liability that no amount of convenience pays for.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const BASE = (process.env.GRAPH_ADVOCATE_URL || "https://graphadvocate.com").replace(/\/+$/, "");
const SENDER = process.env.GRAPH_ADVOCATE_SENDER || "";
const TIMEOUT_MS = Number(process.env.GRAPH_ADVOCATE_TIMEOUT_MS || 60_000);

type PaymentRequired = {
  status: "payment_required";
  price_usdc: string;
  amount_base_units: string;
  asset: string;
  network: string;
  pay_to: string;
  endpoint: string;
  retry_body: unknown;
  how_to_pay: string;
};

/** Shape a 402 into something an agent can act on without reading the spec. */
function asPaymentRequired(endpoint: string, body: unknown, challenge: any): PaymentRequired {
  const accept = (challenge?.accepts || [])[0] || {};
  const amount = String(accept.amount ?? "");
  const price = amount ? `$${(Number(amount) / 1e6).toFixed(2)}` : "unknown";
  return {
    status: "payment_required",
    price_usdc: price,
    amount_base_units: amount,
    asset: String(accept.asset ?? ""),
    network: String(accept.network ?? ""),
    pay_to: String(accept.payTo ?? ""),
    endpoint: `${BASE}${endpoint}`,
    retry_body: body,
    how_to_pay:
      "POST retry_body to endpoint again with an x402 `X-PAYMENT` header. Any x402 SDK " +
      "signs and retries automatically. This server holds no key and will not pay for you.",
  };
}

async function call(endpoint: string, body?: unknown, method: "GET" | "POST" = "POST") {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${endpoint}`, {
      method,
      headers: method === "POST" ? { "content-type": "application/json" } : {},
      body: method === "POST" ? JSON.stringify(body ?? {}) : undefined,
      signal: controller.signal,
    });
    const text = await res.text();
    let parsed: any;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = { raw: text.slice(0, 2000) };
    }
    if (res.status === 402) return asPaymentRequired(endpoint, body ?? {}, parsed);
    if (!res.ok) {
      // A 4xx here means the request was wrong, and — since GA returns 4xx
      // rather than 200-with-error — that no payment was taken for it.
      return { status: "error", http_status: res.status, detail: parsed };
    }
    return parsed;
  } catch (err: any) {
    return {
      status: "error",
      detail: err?.name === "AbortError" ? `timed out after ${TIMEOUT_MS}ms` : String(err?.message || err),
    };
  } finally {
    clearTimeout(timer);
  }
}

const TOOLS = [
  {
    name: "route_data_request",
    description:
      "Ask any blockchain data question in plain English and get back the right service, a " +
      "ready-to-run query, and — when the answer carries a runnable subgraph query — the live " +
      "rows themselves. Covers 15,500+ subgraphs across 20+ chains, Token API (EVM/Solana/TON), " +
      "Aave, Uniswap, ENS, Polymarket, Hyperliquid and ERC-8004 agent discovery. Always costs " +
      "$0.01 USDC on Base over HTTP — the free daily tier applies to the A2A endpoint, not to " +
      "this one — and returns a payment_required object when unpaid.",
    inputSchema: {
      type: "object",
      properties: {
        request: {
          type: "string",
          description: "Plain-English question, e.g. 'top 20 USDC holders on Base'",
        },
      },
      required: ["request"],
    },
    run: (a: any) => call("/route", { request: a.request, ...(SENDER ? { sender: SENDER } : {}) }),
  },
  {
    name: "check_quota",
    description:
      "Free. How much free daily quota a wallet has left on the A2A endpoint. Note the quota " +
      "does NOT apply to route_data_request, which is charged every call — so a non-zero " +
      "remaining_today here does not make the next routing call free.",
    inputSchema: {
      type: "object",
      properties: {
        sender: { type: "string", description: "EVM wallet address (0x + 40 hex)" },
      },
      required: [],
    },
    run: (a: any) => {
      const who = a.sender || SENDER;
      if (!who) {
        return Promise.resolve({
          status: "error",
          detail:
            "No wallet given. Pass `sender`, or set GRAPH_ADVOCATE_SENDER. The free tier is " +
            "only granted to a well-formed EVM address; anonymous callers pay from call 1.",
        });
      }
      return call(`/quota?sender=${encodeURIComponent(who)}`, undefined, "GET");
    },
  },
  {
    name: "polymarket_trader_score",
    description:
      "Skill score and classification (sharp / retail / neutral) for a Polymarket wallet, " +
      "derived from its trading history. $0.01 USDC on Base.",
    inputSchema: {
      type: "object",
      properties: { wallet: { type: "string", description: "EVM wallet address" } },
      required: ["wallet"],
    },
    run: (a: any) => call("/polymarket/pnl-quick", { wallet: a.wallet }),
  },
  {
    name: "hyperliquid_trader_score",
    description:
      "Skill score for a Hyperliquid perps trader — win rate, sizing discipline, drawdown. " +
      "$0.02 USDC on Base.",
    inputSchema: {
      type: "object",
      properties: { wallet: { type: "string", description: "EVM wallet address" } },
      required: ["wallet"],
    },
    run: (a: any) => call("/hyperliquid/score", { wallet: a.wallet }),
  },
  {
    name: "preflight_price",
    description:
      "Free. Read any Graph Advocate endpoint's 402 challenge WITHOUT paying: exact price, " +
      "asset, network and payTo. Use to budget a run, or to drive a payment from your own " +
      "wallet. Never settles anything.",
    inputSchema: {
      type: "object",
      properties: {
        path: {
          type: "string",
          description: "Endpoint path, e.g. /polymarket/screen or /agent/score",
        },
      },
      required: ["path"],
    },
    run: async (a: any) => {
      const path = a.path.startsWith("/") ? a.path : `/${a.path}`;
      const out = await call(path, {});
      // A 402 is the success case here; anything else means the endpoint is
      // free, dead, or rejected the empty probe body.
      return out;
    },
  },
] as const;

const server = new Server(
  { name: "graph-advocate-mcp", version: "2.11.1" },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const tool = TOOLS.find((t) => t.name === req.params.name);
  if (!tool) {
    return {
      isError: true,
      content: [{ type: "text" as const, text: `unknown tool: ${req.params.name}` }],
    };
  }
  const result = await tool.run((req.params.arguments ?? {}) as any);
  return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
});

const transport = new StdioServerTransport();
await server.connect(transport);
