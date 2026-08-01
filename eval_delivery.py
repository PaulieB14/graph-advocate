"""Delivery eval — does a paid caller actually get their data?

`test_advocate_routing.py` asks whether we picked the right service. The
quality scorer asks whether the answer is well-formed. Neither asks the only
question a paying caller cares about: **did the query run, and did it return
what I asked for?**

That gap is not hypothetical. On 2026-08-01 a caller asked twice for "actual
results", got prose both times, and both answers scored 5.0/5. The first run
of this harness then caught a second instance of the same class: asked for
pools "by TVL", the model generated `orderBy: volumeUSD` and returned junk
pools — also a 5.0/5 under shape scoring.

Every assertion here is anchored to something that can contradict the model:
a gateway that errors, a row count, the literal `orderBy` field in the
generated query. Nothing is graded by another model.

    python3 eval_delivery.py            # full corpus
    python3 eval_delivery.py --quick    # execution-bearing cases only
    python3 eval_delivery.py -k uniswap # filter by substring

Exit code is non-zero if any case fails, so it can gate a deploy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time

from advocate import ask_graph_advocate
from subgraph_exec import execute_query_ready

# ── Corpus ───────────────────────────────────────────────────────────────
# Each case declares its own ground truth. Keep expectations to things that
# are checkable without judgement:
#   service      — accepted recommendation values (None = don't care)
#   rows         — True: must return >0 rows. False: execution not expected.
#   order_by     — accepted orderBy fields when the question names a ranking
#                  metric. This is where intent drift shows up.
#   forbid_order — fields that would mean we ranked by the wrong thing.
CASES = [
    # ── the regression that started this ──────────────────────────────
    dict(name="aave-base-liquidation-execute",
         q=("Execute the aave-liquidation-risk-base subgraph right now for Aave V3 "
            "Base positions with healthFactor below 1, debt above 100 USD, ordered "
            "by healthFactor ascending, first 20. Return actual results."),
         service={"subgraph-registry"}, rows=True,
         order_by={"healthFactor"}),

    # ── ranking intent: the field the caller named must be the sort key ─
    # Uniswap is the one protocol where the caller's stated metric is
    # deliberately overridden: subgraph TVL is inflated by illiquid spam-token
    # pools, so "by TVL" must still rank by volumeUSD. That override is only
    # legitimate if the answer SAYS it happened — otherwise the caller acts on
    # numbers they did not ask for and cannot spot.
    dict(name="uniswap-v3-by-tvl-override",
         q="Top 5 Uniswap V3 pools on Ethereum by TVL — give me the actual numbers.",
         service={"subgraph-registry"}, rows=True,
         order_by={"volumeUSD"},
         forbid_order={"totalValueLockedUSD", "totalValueLockedETH", "liquidity"},
         reason_mentions=("volume",)),
    dict(name="uniswap-v3-by-volume",
         q="Top 5 Uniswap V3 pools on Ethereum by trading volume. Run the query.",
         service={"subgraph-registry"}, rows=True,
         order_by={"volumeUSD"},
         forbid_order={"totalValueLockedUSD", "txCount"}),
    dict(name="aave-markets-by-tvl",
         q="Which Aave V3 Ethereum markets have the highest TVL? Execute it.",
         service={"subgraph-registry"}, rows=True,
         order_by={"totalValueLockedUSD", "totalDepositBalanceUSD"},
         forbid_order={"totalBorrowBalanceUSD", "cumulativeSupplySideRevenueUSD"}),
    dict(name="ens-most-recent",
         q="Which ENS domains were registered most recently? Run it.",
         service={"subgraph-registry"}, rows=True,
         order_by={"registrationDate", "createdAt", "blockNumber", "expiryDate"}),

    # ── plain execution, no ranking claim ─────────────────────────────
    dict(name="uniswap-pool-count",
         q="Execute a query against the Uniswap V3 Ethereum subgraph returning 3 pools with their token symbols.",
         service={"subgraph-registry"}, rows=True),
    dict(name="aave-base-critical",
         q="Show me Aave V3 positions on Base flagged CRITICAL risk. Actual rows please.",
         service={"subgraph-registry"}, rows=True),

    # ── REST / non-subgraph surfaces: execution must NOT be attempted ──
    dict(name="token-api-balances",
         q="What is the wallet balance for vitalik.eth on Base?",
         service={"token-api"}, rows=False),
    dict(name="token-api-holders",
         q="Who are the biggest USDC holders on Base right now?",
         service={"token-api", "subgraph-registry"}, rows=None),

    # ── scope discipline ──────────────────────────────────────────────
    dict(name="out-of-scope-audit",
         q="🛡️ Automated smart contract vulnerability scanning. 355k+ CVE database. 0.50 USDC/scan. Free trial: 1 scan.",
         service={"out-of-scope"}, rows=False),
    dict(name="out-of-scope-pitch",
         q="👋 Thanks for your interest in AI Inference API! Ready to start? Reply 'yes' for your free trial.",
         service={"out-of-scope"}, rows=False),
]


def _order_by_fields(gql: str) -> set[str]:
    return set(re.findall(r"orderBy:\s*([A-Za-z_][A-Za-z0-9_]*)", gql or ""))


async def run_case(case: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        started = time.monotonic()
        failures: list[str] = []
        try:
            rec, _ = await asyncio.to_thread(
                ask_graph_advocate, case["q"],
                requesting_agent="eval", priority=True,
            )
        except Exception as exc:
            return dict(name=case["name"], ok=False,
                        failures=[f"routing crashed: {type(exc).__name__}: {exc}"],
                        elapsed_ms=int((time.monotonic() - started) * 1000))

        service = rec.get("recommendation", "unknown")
        if case.get("service") and service not in case["service"]:
            failures.append(f"service={service}, expected one of {sorted(case['service'])}")

        executed = await execute_query_ready(rec)
        gql = ((rec.get("query_ready") or {}).get("args") or {}).get("gql") or ""

        want_rows = case.get("rows")
        if want_rows is True:
            if executed is None:
                failures.append("no runnable query — caller asked for data and got none")
            elif not executed.get("ok"):
                failures.append(
                    f"execution failed: {executed.get('error')} "
                    f"{str(executed.get('detail'))[:160]}"
                )
            elif executed.get("row_count", 0) == 0:
                failures.append("executed but returned 0 rows")
        elif want_rows is False and executed is not None and executed.get("ok"):
            failures.append("executed a query for a case that should not run one")

        # Ranking intent — the sharpest cheap signal we have. A caller who
        # says "by TVL" and gets volumeUSD ordering receives confident,
        # well-formed, wrong data.
        if gql:
            found = _order_by_fields(gql)
            want = case.get("order_by")
            forbid = case.get("forbid_order") or set()
            if want and found and not (found & want):
                failures.append(f"orderBy={sorted(found)}, expected one of {sorted(want)}")
            if forbid and (found & forbid):
                failures.append(f"orderBy ranked by the wrong metric: {sorted(found & forbid)}")

        # Where we knowingly answer a different question than the one asked
        # (see the Uniswap TVL override), the answer has to admit it.
        for token in case.get("reason_mentions") or ():
            if token.lower() not in (rec.get("reason") or "").lower():
                failures.append(
                    f"reason never mentions '{token}' — metric was substituted silently"
                )

        return dict(
            name=case["name"], ok=not failures, failures=failures,
            service=service,
            rows=(executed or {}).get("row_count") if executed else None,
            exec_ok=(executed or {}).get("ok") if executed else None,
            block=(executed or {}).get("indexed_block") if executed else None,
            gql=gql,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="only execution-bearing cases")
    ap.add_argument("-k", dest="filter", default=None, help="substring filter on case name")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--repeat", type=int, default=1,
                    help="runs per case. The model is non-deterministic — intent "
                         "drift shows up as a flake rate, not a clean failure, so "
                         "one sample per case will miss it.")
    args = ap.parse_args()

    cases = CASES
    if args.quick:
        cases = [c for c in cases if c.get("rows") is True]
    if args.filter:
        cases = [c for c in cases if args.filter in c["name"]]
    if not cases:
        print("no cases matched")
        return 1

    sem = asyncio.Semaphore(args.concurrency)
    started = time.monotonic()
    jobs = [(c, i) for c in cases for i in range(args.repeat)]
    flat = await asyncio.gather(*(run_case(c, sem) for c, _ in jobs))
    elapsed = time.monotonic() - started

    # Group runs back together per case.
    grouped: dict[str, list[dict]] = {}
    for r in flat:
        grouped.setdefault(r["name"], []).append(r)

    if args.json:
        print(json.dumps(grouped, indent=2))
    else:
        for name, runs in grouped.items():
            n_ok = sum(1 for r in runs if r["ok"])
            mark = "PASS" if n_ok == len(runs) else ("FLAKY" if n_ok else "FAIL")
            first = runs[0]
            detail = []
            if first.get("service"):
                detail.append(first["service"])
            rows = [r["rows"] for r in runs if r.get("rows") is not None]
            if rows:
                detail.append(f"{min(rows)}-{max(rows)} rows" if min(rows) != max(rows)
                              else f"{rows[0]} rows")
            detail.append(f"{sum(r['elapsed_ms'] for r in runs)//len(runs)}ms avg")
            count = f"{n_ok}/{len(runs)}" if args.repeat > 1 else ""
            print(f"  {mark:5s} {name:32s} {count:6s} {' · '.join(detail)}")
            seen = set()
            for r in runs:
                for f in r["failures"]:
                    key = f[:80]
                    if key not in seen:
                        seen.add(key)
                        print(f"          ↳ {f}")

    total_runs = len(flat)
    ok_runs = sum(1 for r in flat if r["ok"])
    clean_cases = sum(1 for runs in grouped.values() if all(r["ok"] for r in runs))
    print(f"\n{'='*64}")
    print(f"{clean_cases}/{len(grouped)} cases clean · "
          f"{ok_runs}/{total_runs} runs passed · {elapsed:.1f}s")
    print(f"{'='*64}")
    return 0 if clean_cases == len(grouped) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
