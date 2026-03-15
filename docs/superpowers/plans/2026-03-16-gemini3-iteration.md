# Gemini 3 STT/TTS Iteration Plan (v2 — post-review)

**Branch**: `gemini3-stt-tts`
**Spec**: `docs/superpowers/specs/2026-03-16-gemini3-stt-tts-design.md`
**Approach**: Log first, look later. Each step validates one layer, commits, moves on.
**Realistic estimate**: ~3 hours

---

## Step 1: Config + Credential Setup

**Files**: `agent/config.py`, `.env`, `.env.example`

- [ ] Add `google_credentials_file: str = "credentials.json"` to `Settings`
- [ ] Add `GOOGLE_CREDENTIALS_FILE=credentials.json` to `.env.example`
- [ ] Verify `.env` is in `.gitignore` (contains live secrets)
- [ ] Verify `credentials.json` is in `.gitignore`

**Commit**: `chore: add GCP credentials config`

---

## Step 2: Layer Validation Script (offline, no LiveKit)

**Files**: Create `scripts/test_layers.py`

Tests each component in isolation, then wired together:

- [ ] **Layer 1 — GCP Auth**: Instantiate `google.STT(credentials_file=...)`, verify no auth error
- [ ] **Layer 2 — Cloud STT**: Transcribe a short WAV file, print result
- [ ] **Layer 3 — Gemini 3 Flash**: `google.LLM(model="gemini-3-flash-preview")` answer a vet question
- [ ] **Layer 4 — Cloud TTS**: Synthesize a sentence, save to WAV
- [ ] **Layer 5 — Round-trip**: STT text → Gemini 3 + scene context → TTS audio (total < 3s)
- [ ] **Layer 5b — Tool smoke test**: Verify `google.LLM` can call a `@function_tool` function

```bash
GOOGLE_APPLICATION_CREDENTIALS=credentials.json uv run python -m scripts.test_layers
```

**Commit**: `test: offline layer validation — STT + LLM + TTS + tool calls`

---

## Step 3: Update agent/main.py for STT + LLM + TTS

**Files**: `agent/main.py`

- [ ] Replace `google.beta.realtime.RealtimeModel(...)` with three components:
  ```python
  stt=google.STT(credentials_file=settings.google_credentials_file)
  llm=google.LLM(model="gemini-3-flash-preview", thinking_config={"thinking_budget": 256})
  tts=google.TTS(credentials_file=settings.google_credentials_file)
  ```
- [ ] Remove `proactivity=True` and `enable_affective_dialog=True` (RealtimeModel-only features)
- [ ] **Proactive alerts replacement**: Add alert-triggered `session.say()` in perception loop when critical alerts fire (replaces model-driven proactivity)
- [ ] Keep Silero VAD, perception loop, data channels unchanged

**Commit**: `feat: switch to Gemini 3 Flash + Cloud STT/TTS pipeline`

---

## Step 4: RF-DETR on Cattle Video (PARALLEL with Step 5)

**Files**: None (config + test only)

- [ ] Run `scripts/trace_pipeline.py` with `DEMO_VIDEO_PATH=demo_videos/cattle_pen_720p.mp4` and `USE_REAL_DETECTOR=1`
- [ ] Run with `yt_cattle_farm_720p.mp4`
- [ ] Log: detection count, confidence range, FPS
- [ ] **Decision gate**: Use real detector or stay with mock for demo

**Commit**: `test: RF-DETR evaluation on cattle demo videos`

---

## Step 5: End-to-End LiveKit Test (PARALLEL with Step 4)

**Files**: `frontend/public/test.html`

- [ ] Generate fresh LiveKit token (previous ones expired)
- [ ] Update test.html with new token + LiveKit Cloud URL
- [ ] Start agent: `GOOGLE_APPLICATION_CREDENTIALS=credentials.json uv run python -m agent.main dev`
- [ ] Connect via test page
- [ ] Verify: voice response latency (target < 3s)
- [ ] Verify: scene data flowing in data channels
- [ ] Verify: agent references scene context in responses
- [ ] Log review: check [B1]-[B8] + STT/LLM/TTS trace

**Commit**: `fix: e2e issues found during LiveKit test`

---

## Step 6: Tool Call Test

- [ ] During live session, ask: "How long has cow 3 been lying?"
- [ ] Ask: "How many cows fed in the last hour?"
- [ ] Ask: "Which cow is near the fence?"
- [ ] Verify tool functions called (check agent logs for `search_entity_history`, `get_herd_stats`, etc.)
- [ ] Verify responses contain mock data (COW-003 lying 4320s, 6/8 fed, COW-005 near fence)

**Commit**: `fix: tool call issues (if any)`

---

## Step 7: Frontend React App

**Files**: `frontend/.env`

- [ ] Set `VITE_LIVEKIT_URL=wss://herdflow-wfjy59n7.livekit.cloud`
- [ ] Generate fresh token, set `VITE_LIVEKIT_TOKEN=...`
- [ ] Start: `cd frontend && npm run dev`
- [ ] Verify: Dashboard shows herd summary
- [ ] Verify: AlertPanel shows severity-colored cards
- [ ] Verify: VoicePanel shows speaking indicator
- [ ] Verify: SVG overlays render (if RF-DETR active)

**Commit**: `feat: frontend wired to LiveKit Cloud`

---

## Step 8: Final Validation + Demo Prep

- [ ] Run full test suite: `.venv/Scripts/python -m pytest tests/ -v` (86+ tests pass)
- [ ] Run `scripts/trace_pipeline.py` clean
- [ ] Commit all changes
- [ ] Update memory with final state
- [ ] Merge to master if stable
- [ ] Demo recording (separate task — OBS screen capture, 4 min)

**Commit**: `chore: final validation before merge`

---

## Review Issues Addressed

| Review Issue | Resolution |
|---|---|
| I1 (crit) credentials config missing | Step 1 adds to Settings + .env.example |
| I2 (crit) offline pipeline test skipped | Step 2 includes Layer 5 round-trip + tool smoke test |
| I3 (crit) demo recording omitted | Step 8 includes demo prep |
| I4 (mod) proactivity loss | Step 3 adds alert-triggered session.say() |
| I5 (mod) steps 3+4 serial | Steps 4+5 marked PARALLEL |
| I6 (mod) expired frontend token | Steps 5+7 generate fresh tokens |
| I7 (mod) secrets in .env | Step 1 verifies .gitignore |
| I8 (minor) time optimistic | Updated to ~3 hours |
| I9 (minor) test criteria unspecified | Step 2 lists all 5 layers + tool smoke |
| I10 (minor) Cloud Run not deployed | Step 8 notes demo recording; deployment deferred |
