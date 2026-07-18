# Graph Advocate — Hackathon Demo Script

**Length:** ~80 seconds (faster, more focused)
**Style:** Confident tech narrator, direct, not corporate
**Approach:** Single dashboard tab, voiceover does all the work

---

## The full script (paste this into Tella's AI Voiceover)

```
The Graph is the data layer for blockchains. It has three main services: Subgraphs for indexed protocol history, Token API for live wallet balances and transfers, and Substreams for raw real-time streaming.

AI agents need this data — but figuring out which service to use, and how to query it, is hard. Wrong service, wrong query, no data.

That's where Graph Advocate comes in. It's an autonomous AI agent that routes any data question to the right Graph service. Ask it about Uniswap pools, it picks the right subgraph. Ask about wallet balances, it routes to Token API. Ask about live trades, it points you at Substreams.

Other agents pay one cent in USDC on Base for each query. No API keys. No humans in the loop. Real onchain settlement.

Four thousand requests served. Real money earned. Registered as ERC-8004 number seven thirty four, with ENS graphadvocate dot eth.

Watch — that's a live paid query landing right now.
```

**Word count:** 142 words → ~70 seconds at AI voice cadence (140 wpm)

---

## What's on screen during recording

**Just one tab:** `https://graphadvocate.com/dashboard`

That's it. No tab switching. No terminal in frame. The dashboard already shows:
- Total request count
- Wallet balance
- Live activity feed (where the paid query will appear)
- Quality scores
- Service breakdown

You record the dashboard, the voiceover does all the explaining.

---

## Recording flow (60-90 seconds)

**Before pressing record:**
1. Open dashboard in browser, full-screen
2. In a separate terminal (NOT in frame): be ready to run `python3 ~/graph-advocate/demo/send_paid_query.py`

**Record:**
1. Hit record in Tella, only capturing the browser tab
2. Wait 10 seconds with dashboard visible (the dashboard auto-refreshes every 15s)
3. In your off-screen terminal: trigger the paid query
4. Wait ~15 seconds — the new payment shows up in the activity feed and the wallet balance ticks up
5. Stop recording

**Add voiceover:**
1. In Tella editor: "Add Voiceover" → "AI Voiceover"
2. Paste the script above
3. Pick voice: **Adam** or **Brian** (confident-tech vibe)
4. Tella aligns audio to video — drag if a section is slow

**Export:**
- 1080p MP4 → submit

---

## Total time: 10–15 minutes

That's it. One tab, one voiceover, one paid query landing live.
