# HerdFlow — Gemini 3 STT/TTS Branch Design

**Branch**: `gemini3-stt-tts`
**Goal**: Replace Gemini 2.5 Flash Native Audio (20s latency) with Gemini 3 Flash LLM + Google Cloud STT + Google Cloud TTS (~1-1.5s latency). Satisfy competition requirements: Gemini 3 model + Gen AI SDK + Google Cloud services.

---

## 1. Voice Pipeline Architecture

### Current (master)
```
Mic → LiveKit → Gemini 2.5 Flash Native Audio (bidi WebSocket) → audio back
                [single model: STT + reasoning + TTS in one]
                [~20s latency, no Gemini 3]
```

### New (this branch)
```
Mic → Silero VAD (local) → Google Cloud STT (streaming) → text
                                                            ↓
                                                Gemini 3 Flash (generateContent)
                                                + scene context + herd_tools
                                                            ↓
                                                response text → Google Cloud TTS → audio → LiveKit → speaker
```

### Expected Latency
| Component | Latency |
|-----------|---------|
| Silero VAD | ~10ms (local) |
| Google STT (streaming) | ~200ms |
| Gemini 3 Flash | ~500-1000ms |
| Google TTS (streaming) | ~300ms |
| **Total** | **~1-1.5s** |

### Code Changes

**`agent/main.py`** — Replace RealtimeModel with three components:
```python
session = AgentSession(
    stt=google.STT(
        languages="en-US",
        model="latest_long",
        credentials_file="credentials.json",
    ),
    llm=google.LLM(
        model="gemini-3-flash-preview",
        temperature=0.7,
        thinking_config={"thinking_budget": 256},
    ),
    tts=google.TTS(
        voice_name="en-US-Neural2-D",  # male, warm tone
        speaking_rate=1.1,
        credentials_file="credentials.json",
    ),
    vad=vad,
)
```

**`agent/herdflow_agent.py`** — No change needed. Agent keeps `instructions` and `tools`.

### Authentication
- **Gemini 3 Flash (LLM)**: Uses `GOOGLE_API_KEY` env var (existing)
- **Cloud STT / Cloud TTS**: Uses GCP service account via `credentials.json` (gitignored)
- **Project**: `herdflow-demo` (`id-herdflow-agent@herdflow-demo.iam.gserviceaccount.com`)

### GCP APIs Required
- Cloud Speech-to-Text API
- Cloud Text-to-Speech API
- Cloud Firestore API (future)

---

## 2. Real RF-DETR Pipeline

### Current
`MockDetector` returns 8 fake bounding boxes with jitter.

### Change
Use `RFDETRDetector` on real cattle video via `FileVideoSource`. The detector exists in `agent/perception/detector.py` with ThreadPoolExecutor for GIL safety.

### Config
```env
USE_REAL_DETECTOR=1
DEMO_VIDEO_PATH=demo_videos/cattle_pen_720p.mp4
```

### Risk
RF-DETR is trained on COCO (class 20 = cow). Should detect cattle out of the box, but confidence may vary. Test with both demo videos before committing.

### Fallback
If RF-DETR produces poor results on cattle video, stay with MockDetector for the demo and show RF-DETR separately.

### Demo Videos Available
| File | Source | Duration | Size |
|------|--------|----------|------|
| `cattle_pen_720p.mp4` | Pexels (close-up pen) | 11.4s | 8.5 MB |
| `yt_cattle_farm_720p.mp4` | YouTube (farm overview) | 120s | 16 MB |

---

## 3. Testing Strategy

Layer-by-layer validation. Each layer must pass before proceeding to the next.

### Layer 1: GCP Credentials
**What**: Verify service account can authenticate to Cloud Speech-to-Text.
**How**:
```python
from google.cloud import speech_v2
client = speech_v2.SpeechAsyncClient.from_service_account_json("credentials.json")
```
**Pass criteria**: No authentication error.

### Layer 2: Google Cloud STT
**What**: Transcribe a short audio clip using Cloud Speech-to-Text.
**How**: Record a 5-second WAV, send to STT API, verify transcription.
**Pass criteria**: Returns recognizable English text from spoken input.

### Layer 3: Gemini 3 Flash LLM
**What**: Send a text prompt to Gemini 3 Flash via `google.LLM`.
**How**:
```python
from livekit.plugins import google
llm = google.LLM(model="gemini-3-flash-preview")
# Send: "You are a vet. There are 8 cows. 3 are lying down. Any concerns?"
```
**Pass criteria**: Returns a coherent veterinary response. Latency < 2s.

### Layer 4: Google Cloud TTS
**What**: Synthesize a sentence to audio using Cloud Text-to-Speech.
**How**:
```python
from livekit.plugins import google
tts = google.TTS(voice_name="en-US-Neural2-D", credentials_file="credentials.json")
# Synthesize: "Good morning, farmer. Your herd looks healthy today."
```
**Pass criteria**: Returns playable audio bytes. Latency < 500ms.

### Layer 5: STT → LLM → TTS Pipeline (no LiveKit)
**What**: Wire all three components locally, verify text round-trip.
**How**: Create a test script that:
1. Reads a WAV file → STT → text
2. Sends text + scene context → Gemini 3 Flash → response text
3. Sends response text → TTS → audio file
**Pass criteria**: End-to-end produces audible veterinary response. Total latency < 3s.

### Layer 6: RF-DETR on Cattle Video
**What**: Run real detector on demo video frames.
**How**:
```bash
USE_REAL_DETECTOR=1 uv run python -m scripts.trace_pipeline
```
**Pass criteria**:
- Detects at least 1 cow per frame with confidence > 0.3
- Bounding boxes are reasonable (not full-frame, not tiny)
- Processing at > 5 FPS on RTX 4060

### Layer 7: Full LiveKit Session
**What**: Agent + STT + LLM + TTS + perception via LiveKit Cloud.
**How**:
1. Start agent: `uv run python -m agent.main dev`
2. Connect via test page: `http://localhost:5175/test.html`
3. Speak to agent, verify voice response
**Pass criteria**:
- Agent joins room within 5s
- Voice response latency < 3s
- Scene context reflected in responses ("I see 8 cows...")
- Data channels (scene_graph, overlay, alerts) flowing

### Layer 8: Tool Calls
**What**: Verify Gemini 3 Flash calls the herd_tools functions.
**How**: Ask specific questions during Layer 7 session:
- "How long has cow number 3 been lying down?" → should call `search_entity_history`
- "How many cows have fed in the last hour?" → should call `get_herd_stats`
- "Which cow is near the fence?" → should call `find_by_description`
- "Has anyone visited the water trough?" → should call `get_zone_history`
**Pass criteria**: Agent responds with data from mock tool responses (COW-003 lying 4320s, 6 of 8 fed, COW-005 near fence, etc.)

### Layer 9: Frontend React App
**What**: Full React app (not just test.html) connected to LiveKit with live data.
**How**:
1. Update `frontend/.env` with LiveKit Cloud credentials
2. Start frontend: `cd frontend && npm run dev`
3. Open in browser, verify all panels
**Pass criteria**:
- VideoPanel shows "LIVE" status badge
- Dashboard shows herd summary (entity count, behavior breakdown)
- AlertPanel shows severity-colored alert cards
- VoicePanel shows agent speaking indicator
- SVG overlay renders bounding boxes (if RF-DETR active)

### Layer 10: Demo Recording
**What**: Screen record the full demo for submission.
**How**: Use OBS or similar to record:
1. Agent startup + connection (5s)
2. Greeting + first voice exchange (15s)
3. Proactive alert notification (15s)
4. Farmer asks temporal question, tool call responds (20s)
5. Show dashboard + data flowing (10s)
6. Architecture diagram overlay (10s)
**Pass criteria**: Smooth 4-minute video showing all capabilities.

---

## 4. Implementation Order

| Step | Task | Depends On | Estimated Time |
|------|------|------------|----------------|
| 1 | Create `scripts/test_layers.py` (layers 1-5) | credentials.json | 15 min |
| 2 | Run layer tests, fix issues | Step 1 | 15 min |
| 3 | Update `agent/main.py` for STT+LLM+TTS | Step 2 passes | 10 min |
| 4 | Test RF-DETR on cattle video (layer 6) | GPU available | 10 min |
| 5 | Full LiveKit session test (layer 7) | Steps 3+4 | 15 min |
| 6 | Tool call testing (layer 8) | Step 5 | 10 min |
| 7 | Frontend wiring (layer 9) | Step 5 | 15 min |
| 8 | Demo recording (layer 10) | All above | 20 min |

**Total estimated: ~2 hours**

---

## 5. Competition Compliance Checklist

| Requirement | How We Satisfy | Status |
|-------------|---------------|--------|
| Gemini model | Gemini 3 Flash Preview (LLM) | This branch |
| Gen AI SDK | `google-genai` via `livekit-plugins-google` LLM class | This branch |
| Google Cloud service #1 | Cloud Speech-to-Text (STT) | This branch |
| Google Cloud service #2 | Cloud Text-to-Speech (TTS) | This branch |
| Google Cloud service #3 | Cloud Run (deployment) | Dockerfile ready |
| Live Agents category | Real-time voice + video via LiveKit | Working |

---

## 6. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Cloud STT auth fails | Test in Layer 1 before touching agent code |
| Gemini 3 Flash doesn't support tools well | Fall back to gemini-2.5-flash (non-audio) which has proven tool support |
| RF-DETR poor on cattle video | Fall back to MockDetector, show RF-DETR separately |
| Voice latency still > 3s | Reduce thinking_budget to 0, use shorter system prompt |
| LiveKit Cloud rate limits | Free tier supports 100 participants/month, plenty for demo |
