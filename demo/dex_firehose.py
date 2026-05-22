#!/usr/bin/env python3
"""
DEX FIREHOSE — a live, multi-chain DEX-swap monitor for your terminal.

Streams every decoded DEX swap across 9 chains (Solana + 8 EVM) in real time
from Pinax Streams (ws.pinax.network), and renders a live ANSI dashboard:
chain activity leaderboard, hottest protocols, and a rolling swap feed.

No proxy, no deps beyond `websockets`. Auth uses the Token API JWT already
saved in the local token-api MCP config — it is never printed.

Run:
  ~/graph-advocate/venv/bin/python ~/graph-advocate/demo/dex_firehose.py
Quit: Ctrl-C
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
from collections import Counter, deque

try:
    import websockets
except ImportError:
    sys.exit("pip install websockets  (or run with graph-advocate/venv python)")

WS_URL = "wss://ws.pinax.network/ws/*@swaps"

# ── ANSI ──────────────────────────────────────────────────────────────────
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
CLEAR, HOME, HIDE, SHOW = "\033[2J", "\033[H", "\033[?25l", "\033[?25h"

def c(code: str) -> str:
    return f"\033[{code}m"

# per-chain accent colors
CHAIN_COLOR = {
    "solana": c("38;5;141"),       # purple
    "mainnet": c("38;5;111"),      # ethereum blue
    "base": c("38;5;39"),          # base blue
    "bsc": c("38;5;220"),          # binance gold
    "polygon": c("38;5;135"),      # polygon violet
    "optimism": c("38;5;203"),     # optimism red
    "arbitrum-one": c("38;5;45"),  # arbitrum cyan
    "avalanche": c("38;5;167"),    # avax red
    "unichain": c("38;5;205"),     # uniswap pink
}
CHAIN_LABEL = {
    "solana": "SOLANA", "mainnet": "ETHEREUM", "base": "BASE", "bsc": "BSC",
    "polygon": "POLYGON", "optimism": "OPTIMISM", "arbitrum-one": "ARBITRUM",
    "avalanche": "AVALANCHE", "unichain": "UNICHAIN",
}
ACCENT = c("38;5;48")   # firehose green
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def load_jwt() -> str:
    path = os.path.expanduser("~/.claude.json")
    found = []

    def walk(o):
        if isinstance(o, dict):
            srv = o.get("mcpServers")
            if srv and "token-api" in srv:
                a = srv["token-api"].get("args", [])
                for i, x in enumerate(a):
                    if x == "--access-token" and i + 1 < len(a):
                        found.append(a[i + 1])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.load(open(path)))
    if not found:
        sys.exit("No Token API JWT found in the token-api MCP config.")
    return found[0]


class State:
    def __init__(self) -> None:
        self.chains: Counter = Counter()
        self.protocols: Counter = Counter()
        self.total = 0
        self.blocks = 0
        self.biggest_block = 0
        self.feed: deque = deque(maxlen=14)
        self.rate_window: deque = deque(maxlen=400)  # timestamps for swaps/sec
        self.start = time.time()
        self.connected = False

    def swaps_per_sec(self) -> float:
        now = time.time()
        recent = [t for t in self.rate_window if now - t < 10]
        return len(recent) / 10.0


def bar(value: int, peak: int, width: int) -> str:
    if peak <= 0:
        return " " * width
    filled = round(width * value / peak)
    return "█" * filled + "·" * (width - filled)


def render(st: State, frame: int) -> str:
    W = 76
    out = [HOME]
    spin = SPIN[frame % len(SPIN)]
    up = int(time.time() - st.start)
    dot = f"{ACCENT}●{RESET}" if st.connected else f"{c('38;5;203')}○{RESET}"

    out.append(f"{BOLD}{ACCENT}  ╔{'═' * W}╗{RESET}")
    title = f"{spin}  D E X   F I R E H O S E  —  live multi-chain swap stream"
    out.append(f"{BOLD}{ACCENT}  ║{RESET} {BOLD}{title}{RESET}"
               + " " * (W - len(title) - 1) + f"{BOLD}{ACCENT}║{RESET}")
    stat = (f"{dot} ws.pinax.network   swaps {BOLD}{st.total:,}{RESET}   "
            f"{ACCENT}{st.swaps_per_sec():.1f}/s{RESET}   blocks {st.blocks:,}   "
            f"up {up // 60}m{up % 60:02d}s")
    out.append(f"  {c('38;5;240')}╠{'═' * W}╣{RESET}")
    out.append(f"  {DIM}│{RESET} {stat}")
    out.append(f"  {c('38;5;240')}╚{'═' * W}╝{RESET}")
    out.append("")

    # Chains leaderboard
    out.append(f"  {BOLD}CHAINS{RESET}   {DIM}swaps by network (last reset){RESET}")
    peak = max(st.chains.values()) if st.chains else 1
    for net, n in st.chains.most_common(9):
        col = CHAIN_COLOR.get(net, "")
        label = CHAIN_LABEL.get(net, net.upper())
        out.append(f"   {col}{label:<10}{RESET} {col}{bar(n, peak, 34)}{RESET} "
                   f"{BOLD}{n:>7,}{RESET}")
    for _ in range(9 - len(st.chains)):
        out.append("")
    out.append("")

    # Protocols
    out.append(f"  {BOLD}HOT PROTOCOLS{RESET}   {DIM}most-used DEX protocols{RESET}")
    ppeak = max(st.protocols.values()) if st.protocols else 1
    for proto, n in st.protocols.most_common(5):
        out.append(f"   {c('38;5;180')}{proto[:20]:<20}{RESET} "
                   f"{c('38;5;180')}{bar(n, ppeak, 24)}{RESET} {BOLD}{n:>7,}{RESET}")
    for _ in range(5 - len(st.protocols.most_common(5))):
        out.append("")
    out.append("")

    # Live feed
    out.append(f"  {BOLD}LIVE FEED{RESET}   {DIM}newest swaps{RESET}")
    for i, (ts, net, proto, blk) in enumerate(reversed(st.feed)):
        col = CHAIN_COLOR.get(net, "")
        label = CHAIN_LABEL.get(net, net.upper())
        glow = BOLD if i == 0 else DIM if i > 8 else ""
        out.append(f"   {DIM}{ts}{RESET} {col}◆{RESET} {glow}{col}{label:<9}{RESET}"
                   f"{glow}{proto[:22]:<23}{RESET}{DIM}blk {blk}{RESET}")
    for _ in range(14 - len(st.feed)):
        out.append("")
    out.append(f"  {DIM}biggest block: {st.biggest_block} swaps   ·   Ctrl-C to quit{RESET}")
    return "\n".join(out)


async def consume(st: State, jwt: str) -> None:
    while True:
        try:
            async with websockets.connect(
                WS_URL,
                additional_headers={"Authorization": f"Bearer {jwt}"},
                open_timeout=15,
                ping_interval=30,
            ) as ws:
                st.connected = True
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    payload = msg.get("data", msg)
                    if payload.get("table") != "swaps":
                        continue
                    events = payload.get("events") or []
                    net = payload.get("network", "?")
                    blk = payload.get("block_num", 0)
                    if not events:
                        continue
                    st.blocks += 1
                    st.biggest_block = max(st.biggest_block, len(events))
                    now = time.time()
                    ts = time.strftime("%H:%M:%S")
                    for ev in events:
                        proto = ev.get("protocol") or ev.get("amm") or "unknown"
                        st.total += 1
                        st.chains[net] += 1
                        st.protocols[proto] += 1
                        st.rate_window.append(now)
                    # one feed line per block (its dominant protocol)
                    top_proto = Counter(
                        (e.get("protocol") or "unknown") for e in events
                    ).most_common(1)[0][0]
                    st.feed.append((ts, net, f"{top_proto} ×{len(events)}", blk))
        except Exception:
            st.connected = False
            await asyncio.sleep(2)


async def main() -> None:
    jwt = load_jwt()
    st = State()
    sys.stdout.write(CLEAR + HIDE)
    task = asyncio.create_task(consume(st, jwt))
    frame = 0
    try:
        while True:
            sys.stdout.write(render(st, frame))
            sys.stdout.flush()
            frame += 1
            await asyncio.sleep(0.25)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        task.cancel()
        sys.stdout.write(SHOW + RESET + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.stdout.write(SHOW + RESET + "\n")
