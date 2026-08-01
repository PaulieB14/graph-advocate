"""Run a routing answer's `query_ready` against The Graph gateway.

Graph Advocate has always returned a *recommendation* plus a ready-to-run
query and stopped there. On 2026-08-01 a paying caller asked twice, 96
seconds apart, to "execute the aave-liquidation-risk-base subgraph right now
… return actual results" and got prose both times — including the claim "I am
a routing and query-building agent and cannot make live HTTP calls myself",
which was never true of the server. The auto-scorer graded both 5.0/5,
because it grades answer shape and not whether the caller got their data.

This module closes that gap. When a routing answer carries a runnable
subgraph query, we run it and attach the rows.

Two rules govern everything here:

1. **Never fabricate.** No API key, no runnable query, a gateway error, a
   timeout, GraphQL errors — each reports itself as exactly that. An empty
   result set is a real answer (`ok: True, row_count: 0`), not a failure.
2. **Never regress.** Execution is additive. Every failure path leaves the
   routing answer untouched, so the worst case is precisely today's
   behaviour plus one `executed.ok = False` field explaining why.

Every executed payload carries the indexed block height it was served at, so
the caller can tell fresh data from a stalled index without a second round
trip. That is the anchor: a number the answer cannot argue with.
"""

from __future__ import annotations

import os
import time
from typing import Any

GATEWAY_URL = "https://gateway.thegraph.com/api/subgraphs/id/{subgraph_id}"

# A paid request must not hang on a slow indexer. Eight seconds is well
# inside the caller's patience and comfortably above the ~1-2s a healthy
# gateway query takes.
DEFAULT_TIMEOUT_S = 8.0

# Cap the payload rather than streaming an unbounded result set back through
# an x402 response. Truncation is always reported, never silent.
DEFAULT_MAX_ROWS = 100

_META_PROBE = "{ _meta { block { number timestamp } deployment hasIndexingErrors } }"

# Phrases the model writes when it talks itself out of work it can do. Once a
# query has actually run, leaving these in the prose contradicts the rows
# sitting directly beneath them.
_FALSE_CAPABILITY_MARKERS = (
    "cannot make live",
    "can not make live",
    "cannot execute",
    "can not execute",
    "cannot run",
    "can not run",
    "unable to execute",
    "unable to run",
    "don't execute",
    "do not execute",
    "cannot query",
    "i cannot fetch",
    "cannot make http",
    "cannot make live http calls",
)


def strip_false_capability_claims(reason: str) -> str:
    """Drop sentences claiming we can't execute, once we have executed.

    Applied only on a successful run. Splitting on sentence boundaries is
    crude, but the alternative — shipping "I cannot make live HTTP calls
    myself" directly above a hundred live rows — is worse.
    """
    if not isinstance(reason, str) or not reason.strip():
        return reason
    kept = []
    for sentence in reason.replace("\n", " ").split(". "):
        lowered = sentence.lower()
        if any(marker in lowered for marker in _FALSE_CAPABILITY_MARKERS):
            continue
        kept.append(sentence.strip())
    cleaned = ". ".join(s for s in kept if s).strip()
    if cleaned and not cleaned.endswith((".", "!", "?")):
        cleaned += "."
    # Never hand back an empty reason just because the model wrote nothing else.
    return cleaned or reason


def _api_key() -> str | None:
    return os.environ.get("GRAPH_API_KEY") or os.environ.get("GATEWAY_API_KEY")


def extract_runnable(rec: dict) -> tuple[str, str] | None:
    """Pull (subgraph_id, gql) out of a routing answer, or None.

    Tolerates the shape drift already present in the codebase: the GraphQL
    document appears as `gql` in most templates and `query` in a few.
    """
    if not isinstance(rec, dict):
        return None
    qr = rec.get("query_ready")
    if not isinstance(qr, dict):
        return None
    if qr.get("tool") != "execute_query_by_subgraph_id":
        return None
    args = qr.get("args")
    if not isinstance(args, dict):
        return None
    subgraph_id = args.get("subgraph_id")
    gql = args.get("gql") or args.get("query")
    if not isinstance(subgraph_id, str) or not isinstance(gql, str):
        return None
    if not subgraph_id.strip() or not gql.strip():
        return None
    return subgraph_id.strip(), gql.strip()


def _truncate(data: dict, max_rows: int) -> tuple[dict, int, bool]:
    """Cap list-valued fields. Returns (data, total_rows, was_truncated)."""
    total = 0
    truncated = False
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, list):
            total += len(value)
            if len(value) > max_rows:
                out[key] = value[:max_rows]
                truncated = True
                continue
        out[key] = value
    return out, total, truncated


async def execute_query_ready(
    rec: dict,
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> dict | None:
    """Execute `rec["query_ready"]` and return an `executed` block.

    Returns None when the answer carries nothing runnable — the caller should
    then leave the routing answer exactly as it was. Any other outcome,
    including failure, returns a dict safe to attach under `executed`.
    """
    runnable = extract_runnable(rec)
    if runnable is None:
        return None
    subgraph_id, gql = runnable

    key = _api_key()
    if not key:
        return {
            "ok": False,
            "error": "no_api_key",
            "detail": "GRAPH_API_KEY is not set on the server; returning routing only.",
            "subgraph_id": subgraph_id,
        }

    import httpx

    url = GATEWAY_URL.format(subgraph_id=subgraph_id)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    started = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json={"query": gql})
            resp.raise_for_status()
            payload = resp.json()

            # The caller asked for data, not for a freshness audit — but an
            # answer they cannot date is an answer they cannot trust. If the
            # query didn't ask for _meta, fetch it separately so every
            # executed result carries the block it was served at.
            meta = None
            if "_meta" not in gql:
                try:
                    meta_resp = await client.post(
                        url, headers=headers, json={"query": _META_PROBE}
                    )
                    meta_resp.raise_for_status()
                    meta = (meta_resp.json().get("data") or {}).get("_meta")
                except Exception:
                    meta = None  # freshness is a bonus, never a failure cause
    except httpx.TimeoutException:
        return {
            "ok": False,
            "error": "timeout",
            "detail": f"Gateway did not respond within {timeout:.0f}s.",
            "subgraph_id": subgraph_id,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "error": "http_error",
            "status": exc.response.status_code,
            "detail": exc.response.text[:300],
            "subgraph_id": subgraph_id,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:  # network reset, bad JSON, DNS…
        return {
            "ok": False,
            "error": type(exc).__name__,
            "detail": str(exc)[:300],
            "subgraph_id": subgraph_id,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    elapsed_ms = int((time.monotonic() - started) * 1000)

    # GraphQL reports field/schema errors in a 200 body. A query that names a
    # field the subgraph doesn't have lands here — the single most likely way
    # a generated query fails, and the caller needs the real message to fix it.
    if payload.get("errors"):
        messages = [
            str(e.get("message", e))[:200]
            for e in payload["errors"][:3]
            if isinstance(e, (dict, str))
        ]
        return {
            "ok": False,
            "error": "graphql_errors",
            "detail": messages,
            "subgraph_id": subgraph_id,
            "elapsed_ms": elapsed_ms,
            "hint": (
                "The routing answer above is still valid — the generated query "
                "names a field this subgraph does not expose. Check the schema "
                "at the playground URL and adjust the selection set."
            ),
        }

    data = payload.get("data")
    if not isinstance(data, dict):
        return {
            "ok": False,
            "error": "empty_response",
            "detail": "Gateway returned no data block.",
            "subgraph_id": subgraph_id,
            "elapsed_ms": elapsed_ms,
        }

    data, row_count, truncated = _truncate(data, max_rows)
    if meta is None:
        meta = data.get("_meta")

    executed: dict[str, Any] = {
        "ok": True,
        "subgraph_id": subgraph_id,
        "gql": gql,
        "data": data,
        "row_count": row_count,
        "elapsed_ms": elapsed_ms,
        "source": f"The Graph gateway — subgraph {subgraph_id}",
    }
    if truncated:
        executed["truncated_to"] = max_rows
        executed["truncation_note"] = (
            f"Result capped at {max_rows} rows per field. Re-run the query "
            f"with a smaller `first:` or paginate with `skip:` for the rest."
        )
    if isinstance(meta, dict):
        block = meta.get("block") or {}
        executed["indexed_block"] = block.get("number")
        executed["indexed_timestamp"] = block.get("timestamp")
        if meta.get("hasIndexingErrors"):
            executed["indexing_errors"] = True
            executed["indexing_errors_note"] = (
                "This subgraph reports indexing errors; rows may be incomplete."
            )
    if row_count == 0:
        # Zero rows is a legitimate answer to a filtered query. Say so plainly
        # rather than letting it read as a failure.
        executed["empty_result_note"] = (
            "The query ran successfully and matched no entities. This is a real "
            "result, not an error — the filters excluded everything at this block."
        )
    return executed
