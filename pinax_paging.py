"""Plan-safe limits and paging for Pinax Token API list endpoints.

The free/plan JWT caps `limit` at 10 rows per request; anything larger returns
HTTP 403 "Parameter 'limit' exceeds maximum of 10 items." — which is how
"top 20 holders" requests failed outright. Every caller that passes a limit
goes through here: a request for N <= 10 is one call; N > 10 pages with
`page=1,2,…` (limit=10 each, 1-indexed, empty `data` = end) and merges rows
in order, up to TOTAL_CAP. An endpoint that ignores `page` (page 2 repeats
page 1) stops at the first page with a note. A 403 limit error is retried at
the cap instead of failing.
"""
from __future__ import annotations

import math
import os
from typing import Any, Awaitable, Callable

PAGE_MAX = int(os.getenv("PINAX_PAGE_MAX", "10"))
TOTAL_CAP = int(os.getenv("PINAX_TOTAL_CAP", "100"))

# fetch(params) -> (status_code, parsed_json_or_None, text)
Fetch = Callable[[dict], tuple[int, Any, str]]
AFetch = Callable[[dict], Awaitable[tuple[int, Any, str]]]


def requested_limit(params: dict) -> int | None:
    try:
        n = int(params.get("limit"))
    except (TypeError, ValueError):
        return None
    return max(1, n)


def is_limit_error(status: int, text: str) -> bool:
    return status == 403 and "limit" in (text or "").lower()


def _rows(body: Any) -> list | None:
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        return body["data"]
    return None


class _Pager:
    """Shared state machine for sync and async drivers."""

    def __init__(self, params: dict):
        self.params = dict(params)
        n = requested_limit(self.params)
        self.n = n
        self.target = min(n, TOTAL_CAP) if n else None
        self.notes: list[str] = []
        if n and n > TOTAL_CAP:
            self.notes.append(f"requested {n}; capped at {TOTAL_CAP} rows")
        self.paged = bool(self.target and self.target > PAGE_MAX and "page" not in self.params)

    def first_params(self) -> dict:
        p = dict(self.params)
        if self.target:
            p["limit"] = min(self.target, PAGE_MAX)
        if self.paged:
            p["page"] = 1
        return p

    def page_params(self, page: int) -> dict:
        p = dict(self.params)
        p["limit"] = PAGE_MAX
        p["page"] = page
        return p

    def pages_needed(self) -> int:
        return math.ceil(self.target / PAGE_MAX) if self.paged else 1

    def finish(self, body: Any, rows: list | None, pages: int) -> Any:
        if not isinstance(body, dict):
            return body
        out = dict(body)
        if rows is not None:
            out["data"] = rows[: self.target] if self.target else rows
        if self.target and self.n:
            got = len(out.get("data") or [])
            if pages > 1 and got < self.target:
                self.notes.append(f"source returned {got} of {self.target} requested")
        if self.notes or self.paged:
            out["_paging"] = {"requested": self.n, "returned": len(out.get("data") or []),
                              "pages": pages, "page_size": PAGE_MAX, "notes": self.notes}
        return out


def _cap_note(pg: _Pager):
    pg.notes.append(f"results capped at {PAGE_MAX} per request; this endpoint did not page")


def fetch_sync(fetch: Fetch, params: dict) -> tuple[int, Any, str]:
    pg = _Pager(params)
    p = pg.first_params()
    status, body, text = fetch(p)
    if is_limit_error(status, text) and p.get("limit", 0) != PAGE_MAX:
        p["limit"] = PAGE_MAX
        status, body, text = fetch(p)
    if is_limit_error(status, text):
        # Plan cap is lower than expected: retry at 10 is already done, so be explicit.
        return status, body, text
    rows = _rows(body)
    if status >= 400 or rows is None or not pg.paged:
        return status, pg.finish(body, rows, 1), text
    merged, pages = list(rows), 1
    for page in range(2, pg.pages_needed() + 1):
        if len(rows) < PAGE_MAX:
            break
        s2, b2, t2 = fetch(pg.page_params(page))
        r2 = _rows(b2)
        if s2 >= 400 or r2 is None:
            pg.notes.append(f"page {page} failed ({s2}); returning {len(merged)} rows")
            break
        if not r2:
            break
        if r2 == rows:
            _cap_note(pg)
            break
        merged.extend(r2)
        rows, pages = r2, page
    return status, pg.finish(body, merged, pages), text


async def fetch_async(fetch: AFetch, params: dict) -> tuple[int, Any, str]:
    pg = _Pager(params)
    p = pg.first_params()
    status, body, text = await fetch(p)
    if is_limit_error(status, text) and p.get("limit", 0) != PAGE_MAX:
        p["limit"] = PAGE_MAX
        status, body, text = await fetch(p)
    if is_limit_error(status, text):
        return status, body, text
    rows = _rows(body)
    if status >= 400 or rows is None or not pg.paged:
        return status, pg.finish(body, rows, 1), text
    merged, pages = list(rows), 1
    for page in range(2, pg.pages_needed() + 1):
        if len(rows) < PAGE_MAX:
            break
        s2, b2, t2 = await fetch(pg.page_params(page))
        r2 = _rows(b2)
        if s2 >= 400 or r2 is None:
            pg.notes.append(f"page {page} failed ({s2}); returning {len(merged)} rows")
            break
        if not r2:
            break
        if r2 == rows:
            _cap_note(pg)
            break
        merged.extend(r2)
        rows, pages = r2, page
    return status, pg.finish(body, merged, pages), text
