"""Pinax Streams firehose consumer for Graph Advocate.

A background asyncio task holds one live WebSocket to ws.pinax.network
(JWT from TOKEN_API_JWT) and processes the multi-chain swap + ERC-20
transfer stream, maintaining bounded in-memory state for GET /firehose/data:

  - whales:   USDC transfers >= $100k, live, across 8 EVM chains
  - feed:     recent DEX swaps (one row per block)
  - trending: rolling 60-second protocol + chain leaderboards

The task is fully isolated: if Pinax or the JWT is unavailable it retries
with backoff and /firehose/data just serves stale/empty — GA is never
affected. All buffers are bounded deques.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import Counter, deque

log = logging.getLogger("firehose")

WS_URL = "wss://ws.pinax.network/ws/*@swaps/*@erc20_transfers"
WHALE_USD = 100_000          # USDC-transfer threshold for the whale feed
TREND_WINDOW = 60            # seconds for the rolling trending leaderboards

# USDC per Pinax network identifier -> (contract address lowercased, decimals)
USDC = {
    "mainnet":      ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    "base":         ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
    "arbitrum-one": ("0xaf88d065e77c8cc2239327c5edb3a432268e5831", 6),
    "polygon":      ("0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", 6),
    "optimism":     ("0x0b2c639c533813f4aa9d7837caf62653d097ff85", 6),
    "avalanche":    ("0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e", 6),
    "bsc":          ("0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", 18),
    "unichain":     ("0x078d782b760474a361dda0af3839290b0ef57ad6", 6),
}


class _State:
    def __init__(self) -> None:
        self.whales: deque = deque(maxlen=30)
        self.feed: deque = deque(maxlen=40)
        self.window: deque = deque(maxlen=8000)   # (ts, network, protocol)
        self.total_swaps = 0
        self.total_whale_usd = 0.0
        self.whale_count = 0
        self.blocks = 0
        self.connected = False
        self.started = time.time()


_S = _State()


def _jwt() -> str | None:
    return os.environ.get("TOKEN_API_JWT") or os.environ.get("TOKEN_API_ACCESS_TOKEN")


def _handle(payload: dict) -> None:
    table = payload.get("table")
    net = payload.get("network", "?")
    events = payload.get("events") or []
    if not events:
        return

    if table == "swaps":
        _S.blocks += 1
        now = time.time()
        protos = Counter()
        for ev in events:
            proto = ev.get("protocol") or ev.get("amm") or "unknown"
            protos[proto] += 1
            _S.total_swaps += 1
            _S.window.append((now, net, proto))
        top = protos.most_common(1)[0][0]
        _S.feed.appendleft({
            "ts": time.strftime("%H:%M:%S"),
            "network": net,
            "protocol": top,
            "count": len(events),
        })

    elif table == "erc20_transfers":
        usdc = USDC.get(net)
        if not usdc:
            return
        addr, dec = usdc
        scale = 10 ** dec
        for ev in events:
            if (ev.get("log_address") or "").lower() != addr:
                continue
            try:
                usd = int(ev.get("amount") or 0) / scale
            except (TypeError, ValueError):
                continue
            if usd < WHALE_USD:
                continue
            _S.total_whale_usd += usd
            _S.whale_count += 1
            _S.whales.appendleft({
                "ts": time.strftime("%H:%M:%S"),
                "network": net,
                "usd": round(usd, 2),
                "from": ev.get("from", ""),
                "to": ev.get("to", ""),
                "tx": ev.get("tx_hash", ""),
            })


async def run() -> None:
    """Background task — connect, consume, reconnect forever. Never raises."""
    jwt = _jwt()
    if not jwt:
        log.warning("firehose: no TOKEN_API_JWT — consumer not started")
        return
    try:
        import websockets
    except ImportError:
        log.warning("firehose: websockets not installed — consumer not started")
        return

    hdr = {"Authorization": f"Bearer {jwt}"}
    backoff = 2
    while True:
        try:
            # websockets >=14 uses additional_headers; older uses extra_headers
            try:
                conn = websockets.connect(
                    WS_URL, additional_headers=hdr,
                    open_timeout=20, ping_interval=30, max_queue=2048,
                )
            except TypeError:
                conn = websockets.connect(
                    WS_URL, extra_headers=hdr,
                    open_timeout=20, ping_interval=30, max_queue=2048,
                )
            async with conn as ws:
                _S.connected = True
                backoff = 2
                log.info("firehose: connected to Pinax Streams")
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        _handle(msg.get("data", msg))
                    except Exception:
                        continue
        except Exception as e:
            _S.connected = False
            log.warning(f"firehose: disconnected ({type(e).__name__}) — retry in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


def snapshot() -> dict:
    """JSON-serialisable view for GET /firehose/data."""
    now = time.time()
    recent = [(n, p) for (ts, n, p) in _S.window if now - ts <= TREND_WINDOW]
    proto = Counter(p for (_n, p) in recent)
    chain = Counter(n for (n, _p) in recent)
    swaps_per_sec = round(len(recent) / TREND_WINDOW, 1)
    return {
        "connected": _S.connected,
        "uptime_seconds": int(now - _S.started),
        "totals": {
            "swaps": _S.total_swaps,
            "blocks": _S.blocks,
            "whale_count": _S.whale_count,
            "whale_usd": round(_S.total_whale_usd, 2),
            "swaps_per_sec": swaps_per_sec,
        },
        "whales": list(_S.whales),
        "feed": list(_S.feed),
        "trending_protocols": [
            {"name": p, "swaps": c} for p, c in proto.most_common(8)
        ],
        "trending_chains": [
            {"name": n, "swaps": c} for n, c in chain.most_common(9)
        ],
        "window_seconds": TREND_WINDOW,
    }
