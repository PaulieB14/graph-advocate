"""Agent reputation scoring — derive a 0-100 score from on-chain + off-chain signals.

Purpose: when one agent is considering integrating with / paying / following
another agent, surface a single number + signal breakdown so the decision is
data-driven. The "x402 reputation oracle" idea — composite of four ground-truth
signals that resist gaming by listing operators:

  1. ERC-8004 registration (Base) — verifiable on-chain identity + age
  2. IPFS metadata health — declared services, x402 support flag
  3. USDC settlement velocity (Base, last 30d) — real buyer activity
  4. Recency — when was the last paid call

CDP Bazaar's `l30DaysTotalCalls` field can be operator-faked. These four signals
are derived from chain state + IPFS content-hash + immutable settlement events,
so they're harder to spoof.

Composite score: 0-100, tiered into 5 buckets. See `_tier_for` for thresholds.

Usage (CLI):
    python3 -c "import asyncio, agent_score; \
        print(asyncio.run(agent_score.score_agent('0x9dba414637c611a16bea6f0796bfcbcbdc410df8')))"

Or from scripts/score_agent.py for batch scoring with pretty output.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Optional

import httpx

log = logging.getLogger("agent-score")

# ---- canonical chain config -----------------------------------------------

_BASE_RPC = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")
_BASE_USDC = "0x833589fCD6EDb6E08f4c7C32D4f71b54bdA02913"
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Agent0 ERC-8004 Base mainnet subgraph (verified id from wf wtas1wfx6)
_AGENT0_SUBGRAPH_ID = "43s9hQRurMGjuYnC1r2ZwS6xSQktbFyXMPMqGKUFJojb"
_GRAPH_API_KEY = os.environ.get("GRAPH_API_KEY", "")

_HTTP_HEADERS = {"User-Agent": "graph-advocate-score/1.0"}

# ---- score weight table — sum to 100 ---------------------------------------
# Pinned here so the rubric is auditable from the dashboard. Adjust weights only
# after running calibrate_against_known_set() and checking the distribution.
#
# Three axes:
#   identity (8004 + IPFS)        : 30 pts
#   activity (USDC settlements)    : 40 pts
#   reputation (8004 feedback/val) : 30 pts
# Hard gate: without 8004 registration, score = 0 regardless of activity/rep.
_WEIGHTS = {
    # identity
    "erc8004_registered":      15,
    "erc8004_age_gt_7d":        5,
    "ipfs_metadata_valid":      5,
    "ipfs_declares_x402":       5,
    # activity
    "received_any_30d":        10,
    "distinct_senders_3_plus": 10,
    "distinct_senders_10_plus": 5,
    "active_last_7d":          10,
    "active_last_24h":          5,
    # reputation (on-chain feedback + validation registry)
    "any_feedback":            10,
    "distinct_feedback_clients_3_plus": 10,
    "positive_avg_feedback":    5,
    "any_validation":           5,
}
_MAX_SCORE = sum(_WEIGHTS.values())  # 100 by construction

# Scoring tiers — keep boundaries round-numbered so reviewers can sanity check
_TIERS = [
    (80, "active_verified"),
    (60, "active"),
    (40, "registered_or_settling"),
    (20, "dormant_low_signal"),
    (0,  "no_evidence"),
]


@dataclass
class ScoreSignals:
    # identity
    erc8004_registered: bool = False
    erc8004_agent_id: Optional[str] = None
    erc8004_agent_count_for_owner: int = 0  # owners often run multiple agents
    erc8004_age_days: Optional[float] = None
    erc8004_token_uri: Optional[str] = None
    ipfs_metadata_valid: bool = False
    ipfs_declares_x402: bool = False
    declared_skills: list[str] = field(default_factory=list)
    declared_services: list[dict] = field(default_factory=list)
    # activity
    usdc_received_30d_usdc: float = 0.0
    distinct_senders_30d: int = 0
    tx_count_30d: int = 0
    last_received_age_sec: Optional[int] = None
    sample_recent_payers: list[str] = field(default_factory=list)
    # reputation (on-chain feedback + validation registries, aggregated across
    # ALL agents owned by this wallet — one operator often runs many agents
    # but only some accrue feedback)
    feedback_count: int = 0
    distinct_feedback_clients: int = 0
    avg_feedback_value: Optional[float] = None
    validation_count: int = 0
    validation_approved_count: int = 0


def _tier_for(score: int) -> str:
    for threshold, tier in _TIERS:
        if score >= threshold:
            return tier
    return "no_evidence"


# ============================================================================
# Signal 1: ERC-8004 registration via Agent0 Base subgraph
# ============================================================================

async def _query_8004_for_owner(client: httpx.AsyncClient, owner: str) -> Optional[dict]:
    """Fetch ALL ERC-8004 agents owned by `owner` on Base, plus their feedback
    + validation events, in one round trip.

    Returns a dict with:
      primary: the agent record (highest agentId — usually the most recent
        production deployment)
      all_agents: list of all agent records owned by this wallet
      feedback: aggregated non-revoked feedback events across all agents
      validations: aggregated validation events across all agents

    Aggregating is critical because operators frequently run multiple agents
    (test/staging/prod). Wallet-behavior-score has 12 registered agents but
    feedback only on agent #51123 — picking the latest (#55656) misses the
    reputation signal entirely.

    Returns None if the owner has no ERC-8004 registration on Base.
    """
    if not _GRAPH_API_KEY:
        log.warning("GRAPH_API_KEY missing — skipping 8004 lookup")
        return None
    url = f"https://gateway.thegraph.com/api/{_GRAPH_API_KEY}/subgraphs/id/{_AGENT0_SUBGRAPH_ID}"
    # Schema (verified by introspection on 43s9hQR…ojb):
    #   Agent { agentId, agentURI, owner:Bytes, agentWallet:Bytes, createdAt,
    #           lastActivity, totalFeedback, feedback[Feedback], validations[Validation] }
    #   Feedback { clientAddress, value:BigDecimal, isRevoked, createdAt, tag1, tag2 }
    #   Validation { validatorAddress, response:Int, status:ValidationStatus, createdAt }
    #
    # Match on owner OR agentWallet — same wallet often appears as both, but
    # some agents use hot-wallet separation and only match one.
    q = """
    query($wallet: Bytes!) {
      byOwner: agents(where: {owner: $wallet}, orderBy: agentId, orderDirection: desc, first: 50) {
        id chainId agentId agentURI owner agentWallet createdAt lastActivity totalFeedback
        feedback(first: 100, where: {isRevoked: false}, orderBy: createdAt, orderDirection: desc) {
          clientAddress value createdAt tag1
        }
        validations(first: 50, orderBy: createdAt, orderDirection: desc) {
          validatorAddress response status createdAt
        }
      }
      byWallet: agents(where: {agentWallet: $wallet}, orderBy: agentId, orderDirection: desc, first: 50) {
        id chainId agentId agentURI owner agentWallet createdAt lastActivity totalFeedback
        feedback(first: 100, where: {isRevoked: false}, orderBy: createdAt, orderDirection: desc) {
          clientAddress value createdAt tag1
        }
        validations(first: 50, orderBy: createdAt, orderDirection: desc) {
          validatorAddress response status createdAt
        }
      }
    }
    """
    try:
        r = await client.post(url, json={"query": q, "variables": {"wallet": owner.lower()}})
        body = r.json()
        if body.get("errors"):
            log.warning(f"8004 query returned errors for {owner}: {body['errors']}")
            return None
        data = body.get("data") or {}
        # Dedup union of byOwner + byWallet by agent id
        seen, all_agents = set(), []
        for source in (data.get("byOwner") or [], data.get("byWallet") or []):
            for a in source:
                if a["id"] in seen:
                    continue
                seen.add(a["id"])
                all_agents.append(a)
        if not all_agents:
            return None
        # Primary = most-recent createdAt (production deployment most likely)
        primary = max(all_agents, key=lambda a: int(a.get("createdAt") or 0))
        # Aggregate feedback + validations across the owner's agent set
        all_feedback = [f for a in all_agents for f in (a.get("feedback") or [])]
        all_validations = [v for a in all_agents for v in (a.get("validations") or [])]
        return {
            "primary": primary,
            "all_agents": all_agents,
            "feedback": all_feedback,
            "validations": all_validations,
        }
    except Exception as exc:
        log.warning(f"8004 query failed for {owner}: {exc}")
        return None


# ============================================================================
# Signal 2: IPFS metadata fetch
# ============================================================================

async def _fetch_ipfs_metadata(client: httpx.AsyncClient, agent_uri: str) -> Optional[dict]:
    """Fetch ERC-8004 registration metadata from IPFS. Returns parsed JSON or None.

    Accepts `ipfs://<cid>` or `https://...` URIs. Uses ipfs.io gateway as primary.
    """
    if not agent_uri:
        return None
    if agent_uri.startswith("ipfs://"):
        cid = agent_uri.removeprefix("ipfs://").split("/")[0]
        url = f"https://ipfs.io/ipfs/{cid}"
    elif agent_uri.startswith("http"):
        url = agent_uri
    else:
        return None
    try:
        r = await client.get(url, timeout=15.0)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as exc:
        log.debug(f"IPFS fetch failed for {agent_uri}: {exc}")
        return None


# ============================================================================
# Signal 3: USDC settlement activity via chunked Base RPC eth_getLogs
# ============================================================================

# Base block time is ~2s; 30 days ≈ 1,296,000 blocks. Public RPC limits
# eth_getLogs to 10k blocks per call → 130 chunks. ~1-2s per chunk = 2-4 min
# total. Cache hot for 6h so repeat lookups against the same address are free.
_BLOCKS_PER_DAY = 43200
_CHUNK = 9999


async def _scan_usdc_inflows(
    client: httpx.AsyncClient, receiver: str, days: int = 30
) -> dict:
    """Scan USDC Transfer events to a receiver over `days` days on Base.

    Returns a dict with:
      tx_count, distinct_senders, total_received_usdc,
      last_received_block, last_received_ts, sample_senders[]

    All counts derived from immutable Transfer events — no operator can fake.
    """
    # Get current block height
    head_resp = await client.post(_BASE_RPC, json={
        "jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1
    })
    head = int(head_resp.json()["result"], 16)
    total_blocks = days * _BLOCKS_PER_DAY
    chunks_needed = max(1, total_blocks // _CHUNK)

    topic_to = "0x000000000000000000000000" + receiver.lower()[2:]
    distinct_senders: dict[str, int] = {}
    tx_count = 0
    total_atomic = 0
    last_block = 0
    for i in range(chunks_needed):
        to_b = head - i * _CHUNK
        fr_b = max(0, to_b - _CHUNK + 1)
        try:
            r = await client.post(_BASE_RPC, json={
                "jsonrpc": "2.0", "method": "eth_getLogs",
                "params": [{
                    "address": _BASE_USDC,
                    "topics": [_TRANSFER_TOPIC, None, topic_to],
                    "fromBlock": hex(fr_b), "toBlock": hex(to_b),
                }], "id": 1,
            })
            logs = (r.json().get("result") or [])
        except Exception:
            continue
        for lg in logs:
            sender = "0x" + lg["topics"][1][-40:]
            amount_atomic = int(lg["data"], 16)
            distinct_senders[sender] = distinct_senders.get(sender, 0) + 1
            tx_count += 1
            total_atomic += amount_atomic
            block_n = int(lg["blockNumber"], 16)
            if block_n > last_block:
                last_block = block_n
        if fr_b == 0:
            break

    # Resolve timestamp for last block (if any)
    last_ts = None
    last_age_sec = None
    if last_block > 0:
        try:
            r = await client.post(_BASE_RPC, json={
                "jsonrpc": "2.0", "method": "eth_getBlockByNumber",
                "params": [hex(last_block), False], "id": 1,
            })
            last_ts = int(r.json()["result"]["timestamp"], 16)
            last_age_sec = int(time.time()) - last_ts
        except Exception:
            pass

    # Sample 5 most-active senders
    sample = sorted(distinct_senders.items(), key=lambda x: -x[1])[:5]
    return {
        "tx_count": tx_count,
        "distinct_senders": len(distinct_senders),
        "total_received_usdc": round(total_atomic / 1e6, 6),
        "last_received_block": last_block or None,
        "last_received_ts": last_ts,
        "last_received_age_sec": last_age_sec,
        "sample_senders": [s[0] for s in sample],
    }


# ============================================================================
# Compose the score
# ============================================================================

def _compute_score(signals: ScoreSignals) -> tuple[int, dict[str, int]]:
    """Sum the weighted signals. Returns (total, per-signal-points-awarded).

    Hard gate: without an ERC-8004 registration on Base, score is 0 regardless
    of settlement activity. Reason: settlement signals alone can't distinguish
    a real agent from a burn address, USDC contract, or CEX hot wallet — the
    0x000…000 control received $494M USDC from 14k tx in our calibration but
    is obviously not an agent. ERC-8004 registration is the only ground-truth
    proof that this wallet self-identifies as an addressable agent.
    """
    if not signals.erc8004_registered:
        return 0, {}
    awarded = {}
    if signals.erc8004_registered:
        awarded["erc8004_registered"] = _WEIGHTS["erc8004_registered"]
    if signals.erc8004_age_days is not None and signals.erc8004_age_days > 7:
        awarded["erc8004_age_gt_7d"] = _WEIGHTS["erc8004_age_gt_7d"]
    if signals.ipfs_metadata_valid:
        awarded["ipfs_metadata_valid"] = _WEIGHTS["ipfs_metadata_valid"]
    if signals.ipfs_declares_x402:
        awarded["ipfs_declares_x402"] = _WEIGHTS["ipfs_declares_x402"]
    if signals.usdc_received_30d_usdc > 0:
        awarded["received_any_30d"] = _WEIGHTS["received_any_30d"]
    if signals.distinct_senders_30d >= 3:
        awarded["distinct_senders_3_plus"] = _WEIGHTS["distinct_senders_3_plus"]
    if signals.distinct_senders_30d >= 10:
        awarded["distinct_senders_10_plus"] = _WEIGHTS["distinct_senders_10_plus"]
    if signals.last_received_age_sec is not None and signals.last_received_age_sec <= 7 * 86400:
        awarded["active_last_7d"] = _WEIGHTS["active_last_7d"]
    if signals.last_received_age_sec is not None and signals.last_received_age_sec <= 86400:
        awarded["active_last_24h"] = _WEIGHTS["active_last_24h"]
    # Reputation: ERC-8004 feedback + validation registry signals, aggregated
    # across all of the owner's agents (one operator, many registered agents).
    if signals.feedback_count >= 1:
        awarded["any_feedback"] = _WEIGHTS["any_feedback"]
    if signals.distinct_feedback_clients >= 3:
        awarded["distinct_feedback_clients_3_plus"] = _WEIGHTS["distinct_feedback_clients_3_plus"]
    if signals.avg_feedback_value is not None and signals.avg_feedback_value > 0:
        awarded["positive_avg_feedback"] = _WEIGHTS["positive_avg_feedback"]
    if signals.validation_count >= 1:
        awarded["any_validation"] = _WEIGHTS["any_validation"]
    return sum(awarded.values()), awarded


def _verdict_text(score: int, signals: ScoreSignals) -> str:
    tier = _tier_for(score)
    bits = []
    if signals.erc8004_registered:
        if signals.erc8004_age_days is not None:
            bits.append(f"ERC-8004 registered ({signals.erc8004_age_days:.0f}d old, agent #{signals.erc8004_agent_id})")
        else:
            bits.append(f"ERC-8004 registered (agent #{signals.erc8004_agent_id})")
    else:
        bits.append("no ERC-8004 registration on Base")
    if signals.ipfs_metadata_valid:
        skills = ", ".join(signals.declared_skills[:3]) if signals.declared_skills else "no skills declared"
        bits.append(f"metadata valid (skills: {skills})")
    if signals.usdc_received_30d_usdc > 0:
        bits.append(
            f"received ${signals.usdc_received_30d_usdc:.4f} USDC from "
            f"{signals.distinct_senders_30d} distinct sender(s) in 30d "
            f"({signals.tx_count_30d} tx)"
        )
        if signals.last_received_age_sec is not None:
            hrs = signals.last_received_age_sec / 3600
            if hrs < 24:
                bits.append(f"last paid call {hrs:.1f}h ago")
            else:
                bits.append(f"last paid call {hrs/24:.1f}d ago")
    else:
        bits.append("no USDC inflow in 30d")
    # Reputation tail — only show if signals exist (avoid noise for unrated agents)
    if signals.feedback_count > 0:
        rep = f"{signals.feedback_count} feedback event(s) from {signals.distinct_feedback_clients} distinct client(s)"
        if signals.avg_feedback_value is not None:
            rep += f", avg value {signals.avg_feedback_value}"
        bits.append(rep)
    if signals.validation_count > 0:
        bits.append(f"{signals.validation_count} validation(s) ({signals.validation_approved_count} approved)")
    if signals.erc8004_agent_count_for_owner > 1:
        bits.append(f"owner runs {signals.erc8004_agent_count_for_owner} registered agents")
    return f"[{tier}] " + " — ".join(bits) + "."


# ============================================================================
# Public API
# ============================================================================

async def score_agent(wallet: str, *, days: int = 30) -> dict:
    """Score an agent by its owner/operator wallet address.

    Combines ERC-8004 registration, IPFS metadata, and USDC settlement
    activity into a 0-100 composite score with full signal breakdown.

    Returns:
        {
          'wallet': '0x...',
          'score': int 0-100,
          'tier': 'active_verified' | 'active' | ...,
          'signals': {...},
          'awarded_points': {signal_name: points, ...},
          'verdict': human-readable summary string,
          'computed_at_ts': unix timestamp,
        }
    """
    if not (isinstance(wallet, str) and wallet.startswith("0x") and len(wallet) == 42):
        raise ValueError(f"invalid wallet address: {wallet!r}")
    addr = wallet.lower()
    sig = ScoreSignals()

    async with httpx.AsyncClient(headers=_HTTP_HEADERS, timeout=20.0) as client:
        # Signal 1 — 8004 registration (returns primary + all_agents + feedback + validations)
        bundle = await _query_8004_for_owner(client, addr)
        if bundle:
            primary = bundle["primary"]
            sig.erc8004_registered = True
            sig.erc8004_agent_id = primary.get("agentId")
            sig.erc8004_agent_count_for_owner = len(bundle.get("all_agents") or [])
            sig.erc8004_token_uri = primary.get("agentURI")
            ts = primary.get("createdAt")
            if ts:
                try:
                    sig.erc8004_age_days = (time.time() - int(ts)) / 86400
                except Exception:
                    pass

            # Reputation signals — aggregated across all of owner's agents.
            # Why aggregate: an operator may run a test + a staging + a prod
            # agent; reputation accrues on whichever one users hit. Owner-level
            # aggregation captures the operator's track record holistically.
            feedback = bundle.get("feedback") or []
            sig.feedback_count = len(feedback)
            distinct_clients = {f.get("clientAddress", "").lower() for f in feedback}
            distinct_clients.discard("")
            sig.distinct_feedback_clients = len(distinct_clients)
            values = []
            for f in feedback:
                try:
                    values.append(float(f.get("value")))
                except (TypeError, ValueError):
                    continue
            if values:
                sig.avg_feedback_value = round(sum(values) / len(values), 4)

            validations = bundle.get("validations") or []
            sig.validation_count = len(validations)
            sig.validation_approved_count = sum(
                1 for v in validations if (v.get("status") or "").upper() in ("APPROVED", "ACCEPTED", "VALID")
            )

            # Signal 2 — IPFS metadata
            if sig.erc8004_token_uri:
                meta = await _fetch_ipfs_metadata(client, sig.erc8004_token_uri)
                if meta:
                    sig.ipfs_metadata_valid = True
                    sig.ipfs_declares_x402 = bool(meta.get("x402Support") or meta.get("x402_support"))
                    sig.declared_skills = list(meta.get("skills") or meta.get("capabilities") or [])
                    sig.declared_services = list(meta.get("services") or [])

        # Signal 3 — USDC settlement activity (chunked RPC scan)
        settle = await _scan_usdc_inflows(client, addr, days=days)
        sig.usdc_received_30d_usdc = settle["total_received_usdc"]
        sig.distinct_senders_30d = settle["distinct_senders"]
        sig.tx_count_30d = settle["tx_count"]
        sig.last_received_age_sec = settle.get("last_received_age_sec")
        sig.sample_recent_payers = settle.get("sample_senders") or []

    score, awarded = _compute_score(sig)
    return {
        "wallet": wallet,
        "score": score,
        "max_score": _MAX_SCORE,
        "tier": _tier_for(score),
        "signals": asdict(sig),
        "awarded_points": awarded,
        "verdict": _verdict_text(score, sig),
        "computed_at_ts": int(time.time()),
    }
