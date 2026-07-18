#!/usr/bin/env python3
"""Quick connectivity test for Pinax Streams (ws.dev.pinax.network).

The dev WS server requires auth — an unauthenticated connect returns HTTP 401.
This tries the Pinax JWT two ways (Bearer header, then ?token= query param)
and prints the first few streamed messages.

Run:
  TOKEN_API_JWT=<jwt> ./venv/bin/python demo/test_pinax_ws.py
  # or:  railway run --service graph-advocate -- ./venv/bin/python demo/test_pinax_ws.py
"""
import asyncio, json, os, sys, time
import websockets

JWT = os.environ.get("TOKEN_API_JWT") or os.environ.get("TOKEN_API_ACCESS_TOKEN")
STREAM = "base@erc20_transfers"   # one of the 3 live streams on the dev server
HOST = "ws.dev.pinax.network"


async def attempt(url, headers, label):
    print(f"\n=== {label} ===\n  {url}")
    try:
        async with websockets.connect(url, additional_headers=headers,
                                      open_timeout=12) as ws:
            print("  connected OK")
            n, t0 = 0, time.time()
            while n < 3 and time.time() - t0 < 20:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=20)
                except asyncio.TimeoutError:
                    print("  (no message within 20s)")
                    break
                n += 1
                s = msg if isinstance(msg, str) else msg.decode("utf-8", "ignore")
                print(f"  msg {n}: {s[:300]}")
            print(f"  -> {n} message(s) received")
            return n > 0
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {str(e)[:160]}")
        return False


async def main():
    if not JWT:
        print("ERROR: set TOKEN_API_JWT (or TOKEN_API_ACCESS_TOKEN) in the environment.")
        sys.exit(1)
    # 1) Bearer header on the raw /ws form
    ok = await attempt(f"wss://{HOST}/ws/{STREAM}",
                       {"Authorization": f"Bearer {JWT}"},
                       "Bearer header + /ws")
    # 2) token query param on the raw /ws form
    if not ok:
        ok = await attempt(f"wss://{HOST}/ws/{STREAM}?token={JWT}",
                           {}, "?token= query param + /ws")
    print("\nRESULT:", "STREAM WORKS" if ok else "could not stream — check auth method")


if __name__ == "__main__":
    asyncio.run(main())
