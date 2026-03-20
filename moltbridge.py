"""
MoltBridge Ed25519 authentication and discovery client.
Allows Graph Advocate to register, discover agents by capability,
and broker introductions via the MoltBridge trust network.
"""

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path

import httpx
from nacl.signing import SigningKey
from nacl.encoding import RawEncoder

MOLTBRIDGE_URL = os.getenv("MOLTBRIDGE_URL", "https://api.moltbridge.ai")
AGENT_ID = os.getenv("MOLTBRIDGE_AGENT_ID", "graph-advocate")
KEY_PATH = Path(os.getenv("MOLTBRIDGE_KEY_PATH", ".moltbridge_key"))

CAPABILITIES = [
    "onchain-data-routing",
    "token-api",
    "subgraph-query",
    "defi-data",
    "evm-data",
    "solana-data",
]


def _load_or_create_key() -> SigningKey:
    """Load Ed25519 signing key from file, or generate and save a new one."""
    if KEY_PATH.exists():
        raw = KEY_PATH.read_bytes()
        return SigningKey(raw)
    key = SigningKey.generate()
    KEY_PATH.write_bytes(bytes(key))
    KEY_PATH.chmod(0o600)
    print(f"Generated new Ed25519 key at {KEY_PATH}")
    return key


_signing_key = _load_or_create_key()


def get_public_key_b64url() -> str:
    """Return the public key as base64url-encoded string."""
    raw = _signing_key.verify_key.encode(encoder=RawEncoder)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class _JSCompatEncoder(json.JSONEncoder):
    """Match JavaScript's JSON serialization for signature compatibility."""

    def encode(self, o: object) -> str:
        return self._normalize(o)

    def _normalize(self, o: object) -> str:
        if isinstance(o, bool):
            return "true" if o else "false"
        if isinstance(o, float):
            if o == int(o) and not (o != o):
                return str(int(o))
            return repr(o)
        if isinstance(o, int):
            return str(o)
        if isinstance(o, str):
            return json.dumps(o)
        if o is None:
            return "null"
        if isinstance(o, list):
            return "[" + ",".join(self._normalize(item) for item in o) + "]"
        if isinstance(o, dict):
            items = sorted(o.items())
            return "{" + ",".join(
                json.dumps(k) + ":" + self._normalize(v) for k, v in items
            ) + "}"
        return json.dumps(o)


def _canon_json(payload: dict | None) -> str:
    """Canonical JSON matching JS serialization: compact, sorted, JS-compatible numbers."""
    if not payload:
        return ""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, cls=_JSCompatEncoder)


def _sign_auth_header(method: str, path: str, payload: dict = None) -> str:
    """
    Create MoltBridge auth header.
    Signature covers: ${method}:${path_no_query}:${timestamp}:${sha256(body)}
    Format: MoltBridge-Ed25519 <agent_id>:<timestamp>:<signature>
    """
    timestamp = str(int(time.time()))
    body_str = _canon_json(payload)
    body_hash = hashlib.sha256(body_str.encode()).hexdigest()
    sign_path = path.split("?")[0]
    message = f"{method}:{sign_path}:{timestamp}:{body_hash}".encode()
    signed = _signing_key.sign(message)
    signature = base64.urlsafe_b64encode(signed.signature).rstrip(b"=").decode()
    return f"MoltBridge-Ed25519 {AGENT_ID}:{timestamp}:{signature}"


def _request(method: str, path: str, payload: dict = None) -> dict:
    """Make an authenticated request to MoltBridge."""
    body = _canon_json(payload)
    headers = {
        "Authorization": _sign_auth_header(method.upper(), path, payload),
        "Content-Type": "application/json",
    }
    if method.upper() == "POST":
        r = httpx.post(f"{MOLTBRIDGE_URL}{path}", headers=headers, content=body, timeout=30)
    elif method.upper() == "GET":
        r = httpx.get(f"{MOLTBRIDGE_URL}{path}", headers=headers, timeout=30)
    else:
        r = httpx.put(f"{MOLTBRIDGE_URL}{path}", headers=headers, content=body, timeout=30)
    return r.json()


# --- Verification (proof-of-work challenge) ---

def get_challenge() -> dict:
    """Request a proof-of-work challenge from /verify."""
    r = httpx.post(f"{MOLTBRIDGE_URL}/verify", json={}, timeout=30)
    return r.json()


def solve_challenge(nonce: str, difficulty: int) -> str:
    """Find X such that SHA256(nonce + X) has `difficulty` leading zero hex chars."""
    target = "0" * difficulty
    attempt = 0
    while True:
        candidate = str(attempt)
        h = hashlib.sha256((nonce + candidate).encode()).hexdigest()
        if h[:difficulty] == target:
            return candidate
        attempt += 1


def _fuzzy_match(token: str, candidates: dict, threshold: int = 2) -> str | None:
    """Find the best matching candidate within edit distance threshold."""
    best, best_dist = None, threshold + 1
    for word in candidates:
        if abs(len(token) - len(word)) > threshold:
            continue
        # Levenshtein via dynamic programming
        m, n = len(token), len(word)
        dp = list(range(n + 1))
        for i in range(1, m + 1):
            prev, dp[0] = dp[0], i
            for j in range(1, n + 1):
                temp = dp[j]
                dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (0 if token[i - 1] == word[j - 1] else 1))
                prev = temp
        if dp[n] < best_dist:
            best, best_dist = word, dp[n]
    return best


def solve_cognitive(text: str) -> str:
    """
    Decode obfuscated cognitive challenge text and solve the math.
    Example: "sOlVe: NIIn/eet~e-EENN PLLU^s^ TTWWennttyy" → "39.00"
    Strategy: strip non-alpha, collapse repeated chars, fuzzy-match number words.
    """
    cleaned = re.sub(r'(?i)s\s*o\s*l\s*v\s*e\s*:', '', text).strip()
    alpha_only = re.sub(r'[^a-zA-Z\s]', '', cleaned).strip()
    collapsed = re.sub(r'(.)\1+', r'\1', alpha_only, flags=re.IGNORECASE)
    collapsed = collapsed.lower().strip()
    tokens = collapsed.split()

    WORDS = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
        "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
        "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
        "hundred": 100, "thousand": 1000,
    }
    OPS = {"plus": "+", "minus": "-", "times": "*", "multiplied": "*",
           "divided": "/", "over": "/"}
    ALL_WORDS = {**WORDS, **OPS, "by": None}

    numbers = []
    ops = []
    current = 0
    for t in tokens:
        # Exact match first, then fuzzy
        matched = t if t in ALL_WORDS else _fuzzy_match(t, ALL_WORDS)
        if matched is None:
            continue
        if matched in WORDS:
            val = WORDS[matched]
            if val == 100:
                current *= 100
            elif val == 1000:
                current *= 1000
            elif val >= 20 and current == 0:
                current = val
            elif val < 10 and current >= 20:
                current += val
            else:
                current += val
        elif matched in OPS:
            numbers.append(current)
            current = 0
            ops.append(OPS[matched])
        # "by" → skip

    numbers.append(current)

    result = float(numbers[0])
    for i, op in enumerate(ops):
        n = float(numbers[i + 1])
        if op == "+":
            result += n
        elif op == "-":
            result -= n
        elif op == "*":
            result *= n
        elif op == "/":
            result = result / n if n != 0 else 0.0

    return f"{result:.2f}"


def submit_solution(challenge_id: str, proof_of_work: str, cognitive_answer: str) -> dict:
    """Submit proof-of-work + cognitive answer to get verification token."""
    r = httpx.post(
        f"{MOLTBRIDGE_URL}/verify",
        json={
            "challenge_id": challenge_id,
            "proof_of_work": proof_of_work,
            "cognitive_answer": cognitive_answer,
        },
        timeout=30,
    )
    return r.json()


def verify() -> str:
    """Complete the full verification flow. Returns the verification token."""
    print("Requesting challenge...")
    challenge = get_challenge()
    print(f"  Challenge ID: {challenge.get('challenge_id')}")
    print(f"  Difficulty: {challenge.get('difficulty')}")

    cog = challenge.get("cognitive_challenge", {})
    cog_text = cog.get("text", "")
    print(f"  Cognitive challenge: {cog_text}")

    print("Solving proof-of-work...")
    solution = solve_challenge(challenge["nonce"], challenge["difficulty"])
    print(f"  PoW solution: {solution}")

    cog_answer = solve_cognitive(cog_text)
    print(f"  Cognitive answer: {cog_answer}")

    print("Submitting solution...")
    result = submit_solution(challenge["challenge_id"], solution, cog_answer)
    if result.get("verified"):
        print("  Verified!")
        return result["token"]
    else:
        raise RuntimeError(f"Verification failed: {result}")


# --- Registration ---

def register(verification_token: str) -> dict:
    """Register the Graph Advocate agent with MoltBridge."""
    payload = {
        "agent_id": AGENT_ID,
        "name": "Graph Advocate",
        "platform": "moltbridge",
        "pubkey": get_public_key_b64url(),
        "capabilities": CAPABILITIES,
        "clusters": ["blockchain", "defi", "web3-data"],
        "a2a_endpoint": os.getenv(
            "ADVOCATE_PUBLIC_URL",
            "https://graph-advocate-production.up.railway.app",
        ),
        "verification_token": verification_token,
        "omniscience_acknowledged": True,
        "article22_consent": True,
    }
    r = httpx.post(f"{MOLTBRIDGE_URL}/register", json=payload, timeout=30)
    return r.json()


# --- Discovery (authenticated) ---

def discover_by_capability(capability: str, max_results: int = 10) -> dict:
    """Find agents matching a capability tag."""
    return _request("POST", "/discover-capability", {
        "capabilities": [capability],
        "max_results": max_results,
    })


def discover_broker(target_agent_id: str, max_hops: int = 4) -> dict:
    """Find the best broker path to reach a target agent."""
    return _request("POST", "/discover-broker", {
        "target_identifier": target_agent_id,
        "max_hops": max_hops,
    })


def get_credibility(target_agent_id: str) -> dict:
    """Get credibility packet for a target agent."""
    return _request("GET", f"/credibility-packet?target={target_agent_id}")


def attest(target_agent_id: str, capability: str, rating: int, comment: str = "") -> dict:
    """Submit an attestation about another agent's capabilities."""
    return _request("POST", "/attest", {
        "targetAgentId": target_agent_id,
        "capability": capability,
        "rating": rating,
        "comment": comment,
    })


def update_profile(capabilities: list = None, clusters: list = None) -> dict:
    """Update agent profile on MoltBridge."""
    payload = {}
    if capabilities:
        payload["capabilities"] = capabilities
    if clusters:
        payload["clusters"] = clusters
    return _request("PUT", "/profile", payload)


# --- CLI ---

if __name__ == "__main__":
    print(f"Agent ID: {AGENT_ID}")
    print(f"Public key (b64url): {get_public_key_b64url()}")
    print(f"Capabilities: {CAPABILITIES}")
    print()

    # Step 1: Verify
    token = verify()
    print()

    # Step 2: Register
    print("Registering with MoltBridge...")
    result = register(token)
    print(json.dumps(result, indent=2))
    print()

    # Step 3: Discover
    for cap in ["blockchain-data", "defi", "analytics", "crypto"]:
        print(f"Discovering agents with '{cap}' capability...")
        result = discover_by_capability(cap)
        print(json.dumps(result, indent=2))
        print()
