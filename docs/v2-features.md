# HerdFlow v2 Feature Roadmap

**Compiled from**: session memories, engram patterns/decisions, e2e testing insights (2026-03-16)

---

## Tier 1 — Critical (fix what's broken or limited)

### 1.1 Wire real TrackingHistory to tools
**Problem**: All 4 ADK tools return hardcoded mock data. `storage/history.py` has a complete SQLite implementation (`TrackingHistory`) that's never instantiated.
**Fix**: Instantiate `TrackingHistory` in `setup()`, pass to tool functions via closure. Perception loop calls `record_behavior()` and `record_zone_visit()` each frame so history accumulates.
**Impact**: Tools answer from real data instead of "COW-003 lying for 72 hours" every time.

### 1.2 Session resumption
**Problem**: WebSocket to Gemini drops after ~5 min (keepalive timeout) or on network blip. `audio_output_bridge` dies, agent goes silent.
**Fix**: Implement `SessionResumptionConfig` — store resumption handle from `session_resumption_update` events, reconnect with handle on disconnect. Google docs show the pattern.
**Impact**: Unlimited session length, graceful recovery from network issues.

### 1.3 Graceful session recovery
**Problem**: When ADK session dies (1006/1008/1011), `audio_output_bridge` task crashes but other tasks keep running. Agent is half-alive (perception works, voice dead).
**Fix**: Catch session errors in `audio_output_bridge`, trigger full ADK session restart (new `run_live()` call with resumption handle). Notify farmer: "Sorry, had a brief connection issue. I'm back."
**Impact**: No more silent agent after network hiccup.

### 1.4 CUDA / GPU inference
**Problem**: `uv` can't resolve CUDA PyTorch wheels on Windows. RF-DETR runs on CPU at ~2.4 FPS.
**Fix**: Pin `torch` CUDA wheel URL in pyproject.toml extras, or use Docker with nvidia runtime.
**Impact**: RF-DETR at 15-30 FPS on GPU, enabling real-time detection.

---

## Tier 2 — High Value (make it production-worthy)

### 2.1 Livestock re-identification (ReID)
**Problem**: ByteTrack assigns new IDs when spatial continuity breaks (video loop, camera switch, occlusion). COW-001 becomes COW-042.
**Approach** (ranked):
1. Gemini multimodal embeddings — crop bbox → embedding → vector DB → nearest-neighbor match
2. Color histogram pre-filter — HSV histogram matching, zero API cost
3. Lightweight ReID model (OSNet) — local GPU, ~5ms per crop
4. Ear tag detection — Gemini vision OCR on crop
5. Gait signature — temporal movement patterns (research-grade)
**Implementation**: Start with (2) as fast filter, add (1) for confirmed new tracks. Store in `animal_embeddings` SQLite table.

### 2.2 Multi-agent architecture
**Problem**: Single agent handles voice + tools + visual awareness. As scope grows (lab reports, treatments, compliance), one agent's prompt becomes unwieldy.
**Design** (already scaffolded in `adk_agents.py`):
- **Voice Agent**: audio only, <1s latency, low trust (can hallucinate)
- **Analyst Agent** (Gemini 3 Pro): multi-step temporal analysis, 5-15s OK, medium trust
- **Records Agent** (Gemini 3 Flash): validated writes (lab results, treatments, vaccinations), high trust, strict validation
- **Embedding Pipeline**: NOT an LLM — Gemini multimodal embeddings → vector DB
**Split criterion**: trust level + latency, not domain.

### 2.3 System of records
**Problem**: No write operations. Can't register animals, record lab results, log treatments, track vaccinations.
**Features**:
- `register_animal(ear_tag, breed, dob, owner)` — new animal in registry
- `record_lab_result(track_id, test_type, results, date)` — blood panel, fecal, mastitis
- `log_treatment(track_id, medication, dosage, vet_name)` — with withdrawal period calculation
- `update_vaccination(track_id, vaccine, date, next_due)` — compliance tracking
**Owned by**: Records Agent with strict validation (drug interactions, withdrawal periods).

### 2.4 Agent memory across sessions
**Problem**: Agent forgets everything between sessions. "COW-003 was limping yesterday" is lost.
**Design**:
- `record_note(track_id, note)` tool — voice agent records observations
- `recall_notes(track_id)` tool — retrieves all past observations
- Per-animal notes table in SQLite, timestamped
- Per-farmer preferences store (Engram-style key-value)
**Levels**: Session (ADK state, exists), Animal (notes table, v2), Farmer (preferences, v2).

### 2.5 Live camera feed (replace FileVideoSource)
**Problem**: Demo uses pre-recorded mp4. Production needs RTSP/WebRTC camera input.
**Options**:
- RTSP → OpenCV → numpy frames (same interface as FileVideoSource)
- WebRTC camera from farmer's phone/tablet → LiveKit → agent subscribes to video track
- USB camera → V4L2/DirectShow → numpy frames
**Interface**: `VideoSource` protocol with `frames()` generator — FileVideoSource and RTSPVideoSource both implement it.

### 2.6 Frontend UI polish (shadcn)
**Problem**: Current React UI is functional but basic Tailwind. No polished components.
**Plan**: Install shadcn/ui, swap Card/Badge/Alert/Dialog components. Keep existing data flow (hooks, data channels).
**Scope**: Cosmetic, 1-2 hours.

---

## Tier 3 — Nice to Have (differentiate for production)

### 3.1 Proactive alerts via voice
**Problem**: `proactivity=True` in RunConfig was stripped during debugging. Agent can't initiate speech unprompted.
**Fix**: Re-enable `ProactivityConfig(proactive_audio=True)`. Test if model supports it (was causing 1007 before, may work with `latest` model).
**Use case**: Agent says "Hey, COW-003 has been lying for 4 hours, might want to check on her" without farmer asking.

### 3.2 Affective dialog
**Problem**: `enable_affective_dialog=True` was stripped. Agent speaks in flat tone.
**Fix**: Re-enable and test. Adds emotional tone to responses (concern for sick animal, reassurance when herd is calm).

### 3.3 Dynamic zone detection improvements
**Current**: Vision analyst detects zones once from first frame via Gemini Flash.
**Improvements**:
- Re-detect zones periodically (every 5 min) as lighting changes
- Track zone occupancy over time (which zones are crowded, which empty)
- Alert when an animal enters an unusual zone (cow in gate area = possible escape)

### 3.4 Multi-camera support
**Problem**: Single camera feed. Real farms have 2-8 cameras.
**Design**: Multiple `perception_loop` instances, each with own detector + tracker. Shared `SceneGraph` merges entities across cameras. ReID (2.1) critical for cross-camera identity.

### 3.5 Historical trend analysis
**Problem**: Tools only query current session data. Can't answer "how has COW-003's behavior changed this week?"
**Requires**: TrackingHistory wired (1.1) + data spanning days + Analyst Agent (2.2).
**Use case**: Farmer asks "Is cow three getting better since treatment?" → Analyst queries week of behavior records + lab results + body condition scores.

### 3.6 VisionFlow platform abstraction
**Problem**: HerdFlow is hardcoded for livestock. The three-tier architecture (perception → reasoning → communication) is domain-agnostic.
**Vision**: VisionFlow platform where domain-specific code lives in config:
- `detector_class_filter` — which COCO classes to track
- `behavior_heuristics` — how to classify behaviors from bbox data
- `alert_rules` — domain-specific thresholds
- `prompt_persona` — voice agent personality
**Instances**: ShopFlow (retail), WildFlow (wildlife), YardFlow (construction).

### 3.7 Token endpoint for production
**Problem**: Manually generating LiveKit tokens via `generate_token.py`. Frontend has hardcoded token.
**Fix**: FastAPI endpoint `/api/token` that generates a fresh token with unique room name. Frontend fetches on connect.

### 3.8 Docker deployment
**Problem**: Dockerfile exists but untested. Needs CUDA support for GPU inference.
**Plan**: Multi-stage build — Python base with CUDA → install deps → copy agent code. Docker Compose with LiveKit server + agent + frontend.

### 3.9 Farmer mobile app
**Problem**: Browser-only access. Farmers are in the field.
**Options**: React Native wrapper, PWA, or native iOS/Android with LiveKit mobile SDK.

### 3.10 Body condition scoring
**Problem**: Agent can describe what it sees but can't quantify animal health.
**Approach**: Gemini vision + structured output to score body condition (1-5 scale) from video frames. Store scores over time in TrackingHistory. Alert on declining scores.

---

## Known Technical Debt

| Item | Location | Impact |
|------|----------|--------|
| All tools return mock data | `agent/adk_agents.py` | Agent lies about real data |
| `herdflow_agent.py` is dead code | `agent/herdflow_agent.py` | Confusing, should delete |
| `reasoning/tools.py` MockTrackingHistory unused | `agent/reasoning/tools.py` | Dead code |
| E402 ruff violations in main.py | `.env` loading before imports | Cosmetic, add noqa |
| `_analyzing` flag not atomic | `video_analyst.py` | Race condition under concurrent calls |
| No test for `analyze_frame` with real API | Tests | On-demand Gemini Pro path untested |
| Video FPS tied to `FileVideoSource` | `video_source.py` | Production needs RTSP/WebRTC |
| `frames()` return type is `__builtins__` | `video_source.py` | Should be `Iterator[np.ndarray]` |
