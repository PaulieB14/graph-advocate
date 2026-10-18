"""ERC-8004 feedback invite for PAID responses only.

After a settled x402 payment, Graph Advocate asks the caller (once, briefly)
to leave on-chain ERC-8004 reputation feedback. No incentive is offered and
nothing is rated on the caller's behalf.

Where it goes:
  * REST paid routes: only when the response is 2xx AND carries a successful
    PAYMENT-RESPONSE settlement header. JSON-object bodies get a `feedback`
    field; every eligible response also gets `Link` + `X-ERC8004-Feedback`
    headers. Caller-dictated ("reply with only JSON") requests and non-object
    bodies get headers only - the caller's JSON is never touched.
  * A2A paid path: message metadata always; the JSON body only when it is a
    plain object and the request was not caller-dictated JSON.
  * MCP (/mcp, /mcp/sse) is free today, so it never gets an invite.

Kill switch: GA_FEEDBACK_INVITE=0.

Contract addresses verified 2026-10-17: listed in the official
erc-8004/erc-8004-contracts README (same CREATE2 address on every mainnet),
and eth_call getIdentityRegistry() on Base and Arbitrum One returns the
IdentityRegistry 0x8004A169FB4a3325136EB29fA0ceB6D2e539a432 where agents
#41034 (Base) and #734 (Arbitrum) are registered.
"""
from __future__ import annotations

import base64
import json
import os
import re

SCAN_URL = "https://8004scan.io/agents/base/41034"
REPUTATION_REGISTRY = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
IDENTITY_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
HUMAN_LINE = f"Found this useful? Rate Graph Advocate on 8004scan: {SCAN_URL}"
GIVE_FEEDBACK_SIG = ("giveFeedback(uint256 agentId,int128 value,uint8 valueDecimals,"
                     "string tag1,string tag2,string endpoint,string feedbackURI,"
                     "bytes32 feedbackHash)")

FEEDBACK = {
    "message": HUMAN_LINE,
    "erc8004": {
        "scan_url": SCAN_URL,
        "registrations": [
            {"chain": "base", "chainId": 8453, "agentId": 41034,
             "identityRegistry": IDENTITY_REGISTRY,
             "reputationRegistry": REPUTATION_REGISTRY},
            {"chain": "arbitrum", "chainId": 42161, "agentId": 734,
             "identityRegistry": IDENTITY_REGISTRY,
             "reputationRegistry": REPUTATION_REGISTRY},
        ],
        "method": GIVE_FEEDBACK_SIG,
        "example": "giveFeedback(41034, 90, 0, \"\", \"\", \"\", \"\", 0x0) on Base; value is your score",
        "note": "Optional, honest feedback only; no reward is offered.",
    },
}

HEADER_LINK = f'<{SCAN_URL}>; rel="feedback"'
HEADER_ERC8004 = f"eip155:8453:{REPUTATION_REGISTRY}:41034"

_CALLER_JSON_RE = re.compile(
    r"\b(?:reply|respond|return|answer|output)\s+(?:with\s+)?only\s+(?:a\s+|one\s+|the\s+)?"
    r"(?:single\s+)?(?:valid\s+)?json",
    re.I,
)


def enabled() -> bool:
    return os.environ.get("GA_FEEDBACK_INVITE", "1").strip() != "0"


def is_caller_dictated(request_text: str | bytes | None) -> bool:
    if not request_text:
        return False
    if isinstance(request_text, bytes):
        request_text = request_text.decode("utf-8", "replace")
    return bool(_CALLER_JSON_RE.search(request_text))


def add_to_body(obj):
    """Return obj with a `feedback` field if obj is a dict without one; else obj."""
    if isinstance(obj, dict) and "feedback" not in obj:
        out = dict(obj)
        out["feedback"] = FEEDBACK
        return out
    return obj


def settlement_succeeded(headers) -> bool:
    """True when a PAYMENT-RESPONSE / X-PAYMENT-RESPONSE header reports success."""
    for k, v in headers:
        name = (k.decode() if isinstance(k, bytes) else k).lower()
        if name not in ("payment-response", "x-payment-response"):
            continue
        raw = v.decode() if isinstance(v, bytes) else v
        try:
            data = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)))
        except Exception:
            try:
                data = json.loads(raw)
            except Exception:
                continue
        if isinstance(data, dict) and data.get("success") is True:
            return True
    return False


class PaidFeedbackASGI:
    """Wraps the x402-protected app (outside PaymentMiddlewareASGI)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not enabled():
            await self.app(scope, receive, send)
            return

        req_buf = bytearray()

        async def _recv():
            msg = await receive()
            if msg.get("type") == "http.request" and len(req_buf) < 256_000:
                req_buf.extend(msg.get("body", b""))
            return msg

        state = {"start": None, "eligible": False, "buf": bytearray()}

        async def _send(msg):
            t = msg.get("type")
            if t == "http.response.start":
                status = msg.get("status", 0)
                hdrs = list(msg.get("headers") or [])
                if 200 <= status < 300 and settlement_succeeded(hdrs):
                    state["start"] = msg
                    state["eligible"] = True
                    return
                await send(msg)
                return
            if t == "http.response.body" and state["eligible"]:
                state["buf"].extend(msg.get("body", b""))
                if msg.get("more_body"):
                    return
                await _flush()
                return
            await send(msg)

        async def _flush():
            start = state["start"]
            body = bytes(state["buf"])
            hdrs = [(k, v) for k, v in (start.get("headers") or [])
                    if (k.decode() if isinstance(k, bytes) else k).lower() != "content-length"]
            ctype = ""
            for k, v in hdrs:
                if (k.decode() if isinstance(k, bytes) else k).lower() == "content-type":
                    ctype = v.decode() if isinstance(v, bytes) else v
            if "json" in ctype.lower() and not is_caller_dictated(bytes(req_buf)):
                try:
                    obj = json.loads(body)
                    if _looks_like_error(obj):
                        await send(start)
                        await send({"type": "http.response.body", "body": body, "more_body": False})
                        return
                    new = add_to_body(obj)
                    if new is not obj:
                        body = json.dumps(new).encode()
                except Exception:
                    pass
            hdrs.append((b"link", HEADER_LINK.encode()))
            hdrs.append((b"x-erc8004-feedback", HEADER_ERC8004.encode()))
            hdrs.append((b"content-length", str(len(body)).encode()))
            await send({**start, "headers": hdrs})
            await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, _recv, _send)


def _looks_like_error(obj) -> bool:
    return isinstance(obj, dict) and (
        "error" in obj
        or str(obj.get("recommendation", "")).lower() in ("error", "payment-failed", "payment-required")
        or str(obj.get("status", "")).lower() == "error")


def decorate_a2a_message(message, request_text: str | None):
    """Mutate an a2a Message for a paid reply: metadata always (unless the
    reply is an error); a `feedback` JSON field when the text part is a plain
    JSON object and the request wasn't caller-dictated JSON. Never raises."""
    if not enabled():
        return message
    try:
        target, obj = None, None
        for part in getattr(message, "parts", None) or []:
            root = getattr(part, "root", part)
            text = getattr(root, "text", None)
            if isinstance(text, str):
                target = root
                try:
                    obj = json.loads(text)
                except Exception:
                    obj = None
                break
        if _looks_like_error(obj):
            return message
        meta = dict(getattr(message, "metadata", None) or {})
        meta["feedback"] = FEEDBACK
        message.metadata = meta
        if target is not None and not is_caller_dictated(request_text):
            new = add_to_body(obj)
            if new is not obj:
                target.text = json.dumps(new)
    except Exception:
        pass
    return message


class PaidEventQueue:
    """Proxy around an a2a EventQueue that decorates outgoing Messages."""

    def __init__(self, inner, request_text: str | None):
        self._inner = inner
        self._req = request_text

    async def enqueue_event(self, event):
        if hasattr(event, "parts") and hasattr(event, "role"):
            decorate_a2a_message(event, self._req)
        return await self._inner.enqueue_event(event)

    def __getattr__(self, name):
        return getattr(self._inner, name)
