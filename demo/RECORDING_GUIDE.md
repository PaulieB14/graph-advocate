# Recording the demo with AI voiceover

## Tool: Tella.tv (recommended)

Free tier, no install, runs in browser. Built specifically for product demos.

### Setup (5 minutes)

1. Go to https://tella.tv → "Sign in with Google"
2. Create new video → "Screen recording with voiceover"
3. **Skip live narration** — choose "I'll add voiceover after"
4. Tella records your screen at high quality, auto-zooms when you click

### During recording (~3 minutes)

1. Open three tabs / panes in this order:
   - **Pane A (left):** Terminal in `~/graph-advocate/demo/`, ready to run `bash demo.sh`
   - **Pane B (middle):** https://graphadvocate.com/dashboard
   - **Pane C (right):** Empty browser tab (you'll paste Basescan URL into this)
2. Hit Tella's record button
3. In your terminal: `export X402_TIP_PK=<your test wallet PK> && bash demo.sh`
4. The script pauses between segments — use those pauses to switch tabs / let the action complete
5. When the hook tx settles, paste the Basescan URL (the script prints it) into Pane C and zoom

### Adding AI voiceover

1. After recording, in Tella's editor: click "Add Voiceover" → "AI Voiceover"
2. Paste the contents of `SCRIPT.md` (strip the markdown headers, just paste the spoken lines)
3. Pick a voice — **Adam** or **Brian** for confident-tech vibe; **Charlotte** for warmer
4. Tella generates the audio and time-aligns it to your video
5. Drag breakpoints if any segment runs long — Tella stretches the matching video clip

### Export

- 1080p MP4 → "Download" → drop into your hackathon submission

---

## Alternative: Descript (more control)

Better if you want to:
- Edit by transcript like a Google doc
- Use Overdub (clones your voice from 30s of audio)
- Auto-remove "ums" and silence

Workflow:
1. Record screen with QuickTime (no audio)
2. Drop video into Descript
3. Paste SCRIPT.md → "Generate AI voice over" → pick voice
4. Descript syncs voice to your video by length; trim as needed

Free tier: 1hr/month — covers a hackathon demo easily.

---

## Alternative: ElevenLabs + iMovie (most control, more steps)

1. **Voice (ElevenLabs):**
   - https://elevenlabs.io → free tier 10k chars/month
   - Pick voice (Adam/Brian recommended for this script)
   - Paste script → generate → download MP3
2. **Screen (QuickTime):**
   - File → New Screen Recording → record
3. **Combine (iMovie):**
   - Drop video → drop MP3 below → align → trim → export
4. Best total quality but takes 30-45 min vs Tella's 15

---

## Pre-flight checklist before recording

- [ ] `~/graph-advocate/demo/demo.sh` runs cleanly end-to-end (test once silent)
- [ ] `X402_TIP_PK` is set in your shell (test wallet, not graphadvocate.eth — using your own wallet for the hook is more authentic)
- [ ] Wallet has at least $0.10 USDC on Base + a few cents of ETH for gas
- [ ] Dashboard at `/dashboard` is loaded and showing recent activity
- [ ] Terminal font is large (cmd+ a few times) so judges can read it
- [ ] Browser zoom is 110%+ on the dashboard
- [ ] Mac screen recording set to 1920×1080 (avoid Retina-scaled blur)
- [ ] Wifi solid; one practice run end-to-end before recording

---

## Time budget breakdown

If you find yourself running long, here's what to cut first:
- IDENTITY section (1:50–2:30): -40 sec, lowest signal-to-cost
- One of the 4 demo queries: -12 sec each
- Production receipts onchain transfer list: -10 sec

If you have extra time:
- Show the live `settle-check ✓` log appearing in Railway logs after a tip
- Open https://8004scan.io directly in browser instead of API call
