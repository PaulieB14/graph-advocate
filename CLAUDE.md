# Graph Advocate

## What this is

Claude-powered A2A routing agent for The Graph Protocol. Agents ask plain-English data questions, get back the right subgraph + a ready-to-run GraphQL query.

**Live:** `https://graphadvocate.com`
**Deploys:** Railway auto-deploys on push to `main`
**Stack:** Python, Starlette/uvicorn, SQLite, Anthropic API

## Key files



| File | Purpose |
|---|---|
| `advocate.py` | Core routing logic, system prompt, Claude calls, auto-search, SQLite logging |
| `a2a_server.py` | A2A HTTP server (JSON-RPC 2.0), x402 payments, dashboard, feedback, quality scoring |
| `subgraph_exec.py` | Runs a routing answer's `query_ready` against the gateway (paid `/route`) |
| `test_advocate_routing.py` | 100-case offline suite — run after any advocate.py change |
| `eval_delivery.py` | Live delivery eval — did the query actually run and return what was asked? |
| `erc8004-registration.json` | On-chain agent metadata (synced to IPFS + Arbitrum) |
| `.env.example` | All env vars documented |

## Run locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
ANTHROPIC_API_KEY=sk-ant-... python3 a2a_server.py
```

Test: `python3 test_advocate_routing.py` (100 tests must pass, offline, ~10s)

Delivery eval (live — makes real model + gateway calls):

```bash
python3 eval_delivery.py                    # full corpus, one run each
python3 eval_delivery.py --quick --repeat 5 # execution cases, 5x — catches flaky intent drift
```

Shape tests can't see whether a caller got their data. `eval_delivery.py` asserts against
things that can contradict the model: gateway errors, row counts, the literal `orderBy`
field. **Always use `--repeat`** on ranking cases — the model is non-deterministic, and the
Uniswap TVL contradiction showed up as 2/5, not as a clean failure.

## API endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | POST | A2A JSON-RPC 2.0 (main agent endpoint) |
| `/.well-known/agent-card.json` | GET | A2A agent card |
| `/chat` | GET/POST | Web chat UI |
| `/dashboard` | GET | Live monitoring dashboard |
| `/dashboard/data` | GET | Dashboard JSON API (15s poll) |
| `/feedback` | POST | Agent feedback (was_useful, tool_executed) |
| `/feedback/stats` | GET | Feedback summary |
| `/quality` | GET | Response quality metrics (auto-scored 0-5) |
| `/export/json` | GET | Full activity history |
| `/export/csv` | GET | Activity CSV export |
| `/export/stats` | GET | Summary stats for grant reporting |
| `/logs` | GET | Last 100 requests as JSON |
| `/agent/score` | POST | $0.02 — 0-100 reputation score (ERC-8004 + USDC settlements + feedback registry) |

## Routing services

| Service | Best for |
|---|---|
| **token-api** | Wallet balances, swaps, NFTs, holders (EVM/Solana/TON) |
| **subgraph-registry** | Find the right subgraph from 15,500+ indexed |
| **substreams** | Raw block data, traces, streaming |
| **graph-aave-mcp** | Aave V2/V3/V4 — 40 tools (incl. cross-chain liquidation risk) |
| **graph-polymarket-mcp** | Polymarket — 31 tools |
| **graph-lending-mcp** | Cross-protocol lending (Messari) |
| **graph-limitless-mcp** | Limitless prediction markets on Base |
| **predictfun-mcp** | Predict.fun on BNB Chain |
| **mcp8004** | ERC-8004 agent auth for MCP servers |
| **8004scan** | Agent discovery via ERC-8004 registry |

## Architecture

- **Layer 1:** `_auto_search` — keyword matching with word boundaries, runs live subgraph/substreams/token-api/8004scan searches
- **Layer 2:** Claude API call with system prompt + search context
- **Layer 3:** `_extract_json` → `_fallback_route` → `_inject_missing_fields` — robust response parsing
- **Caching:** Benchmark bot static responses (3 queries) + SQLite persistent cache (24h TTL) + in-memory cache
- **Scoring:** Every response auto-scored 0-5 (parse, query_ready, subgraph_id, curl, install)
- **x402:** 3 free queries/day per sender, then $0.01 USDC on Base

## Adding a new paid endpoint — the six places

Every documentation drift found in the 2026-08-08 audit came from missing one of these. The
generated surfaces were correct throughout; only the hand-maintained ones rotted. Work the list
in order and verify at the end — a missed step usually fails **silently**, not loudly.

| # | Place | File | Miss it and… |
|---|---|---|---|
| 1 | `RouteConfig` metadata dict | `a2a_server.py` (~450) | absent from `openapi.json` + `/.well-known/x402` |
| 2 | The handler | `a2a_server.py` (~8700) | nothing to call |
| 3 | ASGI **prefix allowlist** | `a2a_server.py` (~11270, `scope["path"].startswith(...)`) | **silent 404** |
| 4 | `PaymentMiddlewareASGI(routes={...})` | `a2a_server.py` (~10370) | **silent 404, identical to #3** |
| 5 | `AgentSkill` list (agent card) | `a2a_server.py` (~2245) | invisible to A2A callers |
| 6 | `llms.txt` price table | `a2a_server.py` (~3860) | invisible to LLM tooling |

Plus the README's paid-endpoint table, which humans read first and which omitted 7 live endpoints
before the audit.

**#3 and #4 are the trap.** They are ~900 lines apart, produce byte-identical 404s, and each one
alone is insufficient. If a new endpoint 404s in production, check both before checking anything
else.

**Generated, so leave alone:** `openapi.json`, `/.well-known/x402`. Both derive from #1. CDP Bazaar
and x402scan crawl `/.well-known/x402`, so they need no manual registration either.

**Not a paid-endpoint surface:** `agents/capabilities.json` lists *routed services*, not priced
paths — see below.

### Verifying it landed

```bash
# 402 = wired. 404 = missed #3 or #4. 500 locally is normal (no CDP keys) —
# compare against a known-good sibling rather than reading it as a defect.
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://graphadvocate.com/<path> \
  -H 'content-type: application/json' -d '{}'
```

`pkill -f a2a_server.py` does not reliably kill a local server. Confirm with `pgrep` — a stale
process serving old code produces phantom 404s that look exactly like a wiring bug.

## Adding a new routed service (capability)

Services are separate from priced endpoints and live in **`advocate.py`**, not `a2a_server.py`:

1. `_SERVICE_METADATA` — drives `build_capabilities()` → `/agents/capabilities.json`
2. `_SERVICE_CURL_EXAMPLES` — install / curl / get-started hints. Reads **only** those three keys;
   anything else added here is ignored silently
3. The routing prompt in `advocate.py` (~line 189) — what the model actually reads when choosing
4. README services line

The two dicts are ~200 lines apart and both contain a `"graph-limitless-mcp"` key, so an anchored
edit can land in the wrong one. Verify with `build_capabilities()` rather than by grepping.

**Declared ≠ reachable, and reachable ≠ declared.** `graph-uniswap-mcp` was published to npm and
named in the routing prompt for months while `capabilities.json` omitted it — an outside agent
(issue #5) found the inconsistency before we did.

## What NOT to break

- Word boundary matching in `_auto_search` — prevents "compound" matching "compounded"
- Thread-local SQLite with WAL mode in `advocate.py` — no per-request connections
- Benchmark bot static responses — saves ~120 Claude calls/day
- `cache_for_seconds` field in responses — agents use this to avoid re-querying

## Agent identity

- **ERC-8004:** Agent #734 on Arbitrum
- **ENS:** `graphadvocate.eth`
- **Wallet:** `0x575267eED09c338FAE5716A486A7B58A5749A292`
- **A2A Registry:** `afd9b3bb-413c-41cf-9874-6361ea309e32`
- **ClawHub:** `clawhub.ai/paulieb14/graph-advocate`
