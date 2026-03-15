# Gemini 3 STT/TTS Iteration Plan

**Branch**: `gemini3-stt-tts`
**Spec**: `docs/superpowers/specs/2026-03-16-gemini3-stt-tts-design.md`
**Approach**: Log first, look later. Each step validates one layer, commits, moves on.

---

## Step 1: Validate GCP credentials + STT + TTS + Gemini 3 (offline)

**Files**: Create `scripts/test_layers.py`

- [ ] Test Cloud STT auth with `credentials.json`
- [ ] Test Gemini 3 Flash text completion via `google.LLM`
- [ ] Test Cloud TTS synthesis via `google.TTS`
- [ ] Print pass/fail for each, log errors

```bash
GOOGLE_APPLICATION_CREDENTIALS=credentials.json uv run python -m scripts.test_layers
```

**Commit**: `test: layer validation script for GCP credentials + STT + LLM + TTS`

---

## Step 2: Update agent/main.py for STT + LLM + TTS pipeline

**Files**: Modify `agent/main.py`

- [ ] Replace `google.beta.realtime.RealtimeModel` with `google.STT()` + `google.LLM(model="gemini-3-flash-preview")` + `google.TTS()`
- [ ] Pass `credentials_file` to STT and TTS
- [ ] Keep Silero VAD
- [ ] Keep perception loop + data channels unchanged

**Commit**: `feat: switch to Gemini 3 Flash + Cloud STT/TTS pipeline`

---

## Step 3: Test RF-DETR on cattle video

**Files**: None (config change only)

- [ ] Set `USE_REAL_DETECTOR=1` in `.env`
- [ ] Run `scripts/trace_pipeline.py` with `cattle_pen_720p.mp4`
- [ ] Run with `yt_cattle_farm_720p.mp4`
- [ ] Evaluate: does it detect cows? What confidence? How many FPS?
- [ ] Decision: use real detector or stay with mock for demo

**Commit**: `test: RF-DETR evaluation on cattle demo videos`

---

## Step 4: End-to-end LiveKit test

**Files**: Update `frontend/public/test.html` token

- [ ] Start agent: `uv run python -m agent.main dev`
- [ ] Connect via test page
- [ ] Verify: voice response < 3s
- [ ] Verify: scene data flowing
- [ ] Verify: ask "how are the cows?" — agent uses scene context
- [ ] Log review: check all [B1]-[B8] boundaries firing

**Commit**: `fix: any issues found during e2e test`

---

## Step 5: Tool call test

- [ ] Ask: "How long has cow 3 been lying?"
- [ ] Ask: "How many cows fed in the last hour?"
- [ ] Verify tool functions are called (check agent logs)
- [ ] Fix any tool registration issues

**Commit**: `fix: tool call issues (if any)`

---

## Step 6: Frontend React app

**Files**: Update `frontend/.env`, verify `frontend/src/App.tsx`

- [ ] Set `VITE_LIVEKIT_URL` and `VITE_LIVEKIT_TOKEN` in `frontend/.env`
- [ ] Start frontend: `cd frontend && npm run dev`
- [ ] Verify Dashboard, AlertPanel, VoicePanel render with live data
- [ ] Screenshot for submission

**Commit**: `feat: frontend wired to LiveKit Cloud`

---

## Step 7: Final commit + save state

- [ ] Run full test suite: `uv run pytest tests/ -v`
- [ ] Commit all changes
- [ ] Update memory with final state
- [ ] Merge to master if everything works
