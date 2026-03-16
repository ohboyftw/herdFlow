# Two-Pipe Architecture Design

**Date**: 2026-03-16
**Status**: Approved
**Author**: Aravind + Claude
**Predecessor**: v0.10 (single-process, tagged)

## Problem

Single-process architecture causes GIL contention between audio and video:
- Audio bridges, video publish (5 FPS), RF-DETR inference, VideoAnalyst API calls, STT — all in one asyncio event loop
- Video's `frame.tobytes()` (2.7MB x 5/sec) and RF-DETR compete with audio frame processing
- Result: voice input sometimes dropped, ~8s response latency, agent goes quiet during analyst calls

## Solution

Split into two independent processes communicating via LiveKit data channels:
- **Voice process**: ADK Live session (audio only) + STT + tool dispatch
- **Video process**: Perception pipeline + video publishing + VideoAnalyst (NO ADK)

## Architecture

```
┌─────────────────────────────────┐    ┌─────────────────────────────────┐
│  Process 1: voice-agent         │    │  Process 2: video-agent         │
│  LiveKit participant            │    │  LiveKit participant            │
│                                 │    │                                 │
│  ADK Runner.run_live()          │    │  NO ADK                        │
│  ├── Audio in (farmer mic)      │    │                                 │
│  ├── Audio out (agent speech)   │    │  FileVideoSource (5 FPS)       │
│  ├── Tool dispatch:             │    │  ├── Publish video track        │
│  │   ├── search_entity_history  │    │  └── Feed to RF-DETR            │
│  │   ├── get_herd_stats         │    │                                 │
│  │   ├── find_by_description    │    │  RF-DETR → ByteTrack            │
│  │   ├── get_zone_history       │    │  └── SceneGraphBuilder          │
│  │   ├── get_scene_summary *    │    │      └── Publish data channels: │
│  │   └── analyze_frame *        │    │          scene_graph, overlay,   │
│  └── LiveKit STT (async)        │    │          alerts                 │
│                                 │    │                                 │
│  AnalystBridge                  │    │  VideoAnalyst                   │
│  ├── Subscribes to analyst      │    │  ├── Background (30s): summary  │
│  │   data channels from video   │    │  │   → publish: analyst_summary │
│  ├── Caches latest summary +    │    │  ├── Annotations (30s): per-cow │
│  │   annotations                │    │  │   → publish: analyst_annotations│
│  └── Request/response for       │    │  ├── On-demand analysis          │
│      on-demand analyze_frame    │    │  │   ← subscribe: analyst_request│
│                                 │    │  │   → publish: analyst_response │
│  * reads from AnalystBridge     │    │  └── Zone detection (once)      │
│                                 │    │      → publish: zone_config     │
└─────────────────────────────────┘    └─────────────────────────────────┘
         │                                        │
         └────────── LiveKit Room ────────────────┘
                         │
              ┌──────────┴──────────┐
              │   React Frontend    │
              │  Subscribes to ALL  │
              │  data channels      │
              └─────────────────────┘
```

## Data Channel Protocol

### Video → Frontend + Voice

| Channel | Payload | Frequency |
|---------|---------|-----------|
| `scene_graph` | SceneGraph JSON | Every 2s |
| `overlay` | OverlayData JSON (with Gemini labels) | Every 2s |
| `alerts` | Alert JSON | On alert fire |
| `zone_config` | DetectedZone[] JSON | Once (first frame) |
| `analyst_summary` | `{"summary": "3 cows standing..."}` | Every 30s |
| `analyst_annotations` | `{"annotations": {"COW-001": {...}, ...}}` | Every 30s |

### Voice → Frontend

| Channel | Payload | Frequency |
|---------|---------|-----------|
| `transcript` | `{"speaker": "farmer", "text": "...", "final": true}` | On final STT |

### Voice ↔ Video (request/response for on-demand analysis)

| Channel | Direction | Payload |
|---------|-----------|---------|
| `analyst_request` | voice → video | `{"question": "describe cow 3", "request_id": "abc123"}` |
| `analyst_response` | video → voice | `{"answer": "brown cow lying...", "request_id": "abc123"}` |

`request_id` correlates request with response. Voice process awaits with 30s timeout.

**Note**: `analyst_*` channels are inter-process only — the frontend does not subscribe to them.

## Dispatch Strategy (H1 fix)

LiveKit dispatches ONE agent per room event. Two `AgentServer` instances can't both auto-dispatch to the same room without server-side explicit dispatch config.

**Solution**: Voice process uses `AgentServer` (gets dispatched normally by LiveKit). Video process uses raw `rtc.Room()` + `room.connect(url, token)` as a plain participant — no `AgentServer`, no dispatch needed. The `e2e.py` script generates a separate token for the video participant.

## Token Generation (H2 fix)

`scripts/e2e.py` generates three tokens:
- `farmer` — for the browser (test.html / React app)
- `herdflow-voice` — used internally by `AgentServer` (generated from LIVEKIT_API_KEY/SECRET, not manual)
- `herdflow-video` — for the video process's raw `Room.connect()` call

The voice process (`AgentServer`) generates its own token internally. Only the video process and farmer need explicit tokens from `e2e.py`.

## Request/Response Concurrency (H3 fix)

`AnalystBridge.request_analysis()` maintains a `dict[str, asyncio.Future]` keyed by `request_id`. On data channel receive, matches `request_id` and resolves the corresponding future. On timeout, returns fallback: `"Visual analysis timed out — video feed may be unavailable."`.

## Crash Degradation (M1 fix)

`AnalystBridge` tracks `_last_update_time`. If no `analyst_summary` received in 60s (2x the 30s interval), marks video as unavailable:
- `get_summary()` returns `"Video feed unavailable — no recent data."`
- `request_analysis()` returns immediately with fallback instead of waiting 30s

## Startup Ordering (M3 fix)

Startup order does not matter. `AnalystBridge` caches the latest value, which arrives every 30s from the video process. The first 30s may have stale default data ("No video feed available yet."), which is acceptable. No explicit synchronization needed.

## Logging (L2 fix)

Each process writes to its own log file:
- Voice: `logs/herdflow-voice.log`
- Video: `logs/herdflow-video.log`

Prevents interleaved writes from two processes.

## Signal Handling (L4 fix)

`main.py` launcher registers `atexit` + `SIGINT`/`SIGTERM` handlers to terminate both child processes on Ctrl+C.

## Components

### 1. voice_agent.py (new)

Voice process entrypoint. Extracted from current `main.py`:
- LiveKit `AgentServer` + `@server.rtc_session()` entrypoint
- `setup()` — loads Silero VAD only (no RF-DETR, no video source)
- ADK Agent + Runner + `run_live()` with audio-only RunConfig
- `audio_input_bridge()` — farmer mic → ADK LiveRequestQueue
- `audio_output_bridge()` — ADK events → LiveKit AudioSource (with interruption handling)
- `transcription_loop()` — LiveKit Google STT → transcript data channel
- AnalystBridge instance — subscribes to video process data channels

Tools read from AnalystBridge:
- `get_scene_summary()` → `bridge.get_summary()` (instant, cached)
- `analyze_frame(question)` → `bridge.request_analysis(question)` (async, 30s timeout)
- Other 4 tools unchanged (mock data, same as before)

### 2. video_agent.py (new)

Video process entrypoint. Extracted from current `main.py`:
- Raw `rtc.Room()` + `room.connect(url, token)` — plain LiveKit participant, NO AgentServer
- Loads RF-DETR detector + FileVideoSource on startup
- `video_publish_loop()` — reads frames at 5 FPS, publishes video track, shares via `shared_frame`
- `perception_loop()` — reads `shared_frame`, runs RF-DETR → ByteTrack → SceneGraphBuilder, publishes scene_graph/overlay/alerts data channels, merges Gemini annotations onto overlay
- `VideoAnalyst` instance — background summary + annotations every 30s, publishes analyst_summary/analyst_annotations data channels
- Zone detection on first frame → publishes zone_config
- Subscribes to `analyst_request` → runs on-demand Gemini Pro → publishes `analyst_response`

### 3. analyst_bridge.py (new)

Voice-side bridge to video process's analyst:

```python
class AnalystBridge:
    """Cache + request/response bridge for analyst data from video process."""

    latest_summary: str = "No video feed available yet."
    latest_annotations: dict[str, dict] = {}
    _last_update_time: float = 0.0  # monotonic clock
    _pending_requests: dict[str, asyncio.Future] = {}  # request_id → Future
    _stale_threshold_s: float = 60.0  # 2x the 30s interval

    async def start(self, room: Room) -> None:
        """Subscribe to analyst_summary, analyst_annotations, analyst_response channels."""

    def _is_stale(self) -> bool:
        """True if no update received in 60s — video process likely down."""

    def get_summary(self) -> str:
        """Return cached summary. Returns fallback if stale."""

    def get_annotation(self, track_id: str) -> dict | None:
        """Return cached annotation for a track_id (instant)."""

    async def request_analysis(self, question: str) -> str:
        """Publish request to analyst_request channel, await response via Future.
        Returns fallback on timeout or if video is stale."""
```

### 4. main.py (modified)

Thin launcher that spawns both processes:

```python
# Option A: subprocess
subprocess.Popen([sys.executable, "-m", "agent.voice_agent", "dev"])
subprocess.Popen([sys.executable, "-m", "agent.video_agent", "dev"])

# Option B: multiprocessing
Process(target=run_voice).start()
Process(target=run_video).start()
```

Prefer Option A (subprocess) — fully independent, separate stdout, can restart individually.

### 5. scripts/e2e.py (modified)

Generates token, patches test.html + frontend/.env, launches both processes.

### 6. adk_agents.py (modified)

Tools read from AnalystBridge instead of VideoAnalyst:
- `set_analyst_bridge(bridge)` replaces `set_video_analyst(analyst)`
- `get_scene_summary()` → `bridge.get_summary()`
- `analyze_frame(question)` → `bridge.request_analysis(question)`

## File Changes Summary

| File | Action |
|------|--------|
| `agent/voice_agent.py` | CREATE — voice process entrypoint |
| `agent/video_agent.py` | CREATE — video process entrypoint |
| `agent/reasoning/analyst_bridge.py` | CREATE — voice-side data channel bridge |
| `agent/main.py` | MODIFY — thin launcher for both processes |
| `agent/adk_agents.py` | MODIFY — tools use AnalystBridge |
| `scripts/e2e.py` | MODIFY — launch both processes |
| `agent/reasoning/video_analyst.py` | UNCHANGED — used by video process |
| `agent/perception/*` | UNCHANGED — used by video process |
| `agent/reasoning/prompts.py` | UNCHANGED — used by voice process |
| `agent/models.py` | UNCHANGED — shared |
| `agent/config.py` | UNCHANGED — shared |
| `frontend/*` | UNCHANGED — subscribes to same data channels |

## What This Fixes

- **GIL contention eliminated** — RF-DETR, frame encoding, VideoAnalyst API calls in separate process
- **Voice latency reduced** — voice process only handles audio + ADK + STT
- **Independent lifecycle** — can restart voice without losing video, and vice versa
- **Same frontend** — no frontend changes needed, same data channels

## What Stays the Same

- All data types (models.py)
- All perception code (detector, tracker, scene_graph)
- VideoAnalyst class (runs in video process unchanged)
- Frontend (subscribes to same channels)
- Prompt (used by voice process)
- 6 ADK tools (interface unchanged, backend switches to AnalystBridge)

## Testing

- Unit: AnalystBridge cache + request/response logic (mock data channels)
- Integration: both processes start, voice tools return analyst data
- E2E: farmer asks "what do you see?", voice process gets answer from video process via data channel
- Regression: 92 existing tests still pass (models, contracts, etc.)

## Config

Add to `agent/config.py`:
```python
# Voice agent LiveKit identity
voice_agent_identity: str = "herdflow-voice"
# Video agent LiveKit identity
video_agent_identity: str = "herdflow-video"
```
