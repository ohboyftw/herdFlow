# HerdFlow Codebase Deep Analysis

> Generated 2026-03-17 via Code Graph + RLM analysis. Branch: `gemini3-stt-tts` (v0.20, 86 commits).

## Architecture Summary

**3,447 Python lines** across 22 files + **1,014 TypeScript lines** across 13 files. Lean codebase.

## Two-Pipe Architecture (the core design)

```
main.py (107 lines) — thin launcher, spawns two processes:

┌─ VOICE PROCESS (voice_agent.py, 530 lines) ──────────┐
│  ADK AgentServer + Gemini Live (native audio)         │
│  LiveKit STT for transcription                        │
│  AnalystBridge → reads video pipe summaries            │
│  ConversationMemory → session rotation                 │
│  Tool calls: search_entity_history, get_herd_stats,   │
│              find_by_description, get_zone_history     │
└───────────────────────────────────────────────────────┘

┌─ VIDEO PROCESS (video_agent.py, 324 lines) ───────────┐
│  Raw rtc.Room (no ADK, direct LiveKit)                 │
│  RF-DETR detector → ByteTrack → SceneGraphBuilder      │
│  VideoAnalyst (Gemini Flash) → summaries every 30s     │
│  Publishes: scene_graph, overlay, alerts, zone_config, │
│             analyst_summary, analyst_annotations        │
└───────────────────────────────────────────────────────┘

Bridge: AnalystBridge (153 lines) — voice reads video's data channels
```

## Module Dependency Graph

```
models.py (325 lines, 24 Pydantic models)
    ↑ imported by everything

perception/
    detector.py  →  Detection model
    tracker.py   →  TrackedEntity, ByteTrack via supervision
    scene_graph.py → SceneGraph, HerdSummary, Alert
    video_source.py → FileVideoSource (av/PyAV)

reasoning/
    video_analyst.py (380 lines) → Gemini Flash, frame analysis
    analyst_bridge.py (153 lines) → cross-pipe data relay
    memory.py (77 lines) → conversation context stuffing
    prompts.py (117 lines) → 5KB veterinarian persona prompt
    tools.py (167 lines) → 4 tool definitions (MOCK data!)

alerts/
    rules.py → ProlongedLying, Isolation, MissedFeeding rules

storage/
    history.py → SQLite via aiosqlite (never wired to tools)
```

## File Size Distribution

| File | Lines | Role |
|------|-------|------|
| voice_agent.py | 530 | Voice process (ADK + Gemini Live) |
| reasoning/video_analyst.py | 380 | Gemini Flash frame analysis |
| models.py | 325 | 24 Pydantic data models |
| video_agent.py | 324 | Video process (RF-DETR + LiveKit) |
| adk_agents.py | 269 | ADK tool functions |
| storage/history.py | 235 | SQLite tracking history |
| perception/scene_graph.py | 214 | Scene graph builder |
| reasoning/tools.py | 167 | Tool definitions (mock data) |
| reasoning/analyst_bridge.py | 153 | Cross-pipe data relay |
| perception/detector.py | 145 | RF-DETR wrapper |

## Data Channel Protocol (11 topics)

| Topic | Publisher | Consumer | Format |
|-------|-----------|----------|--------|
| `scene_graph` | video_agent | Frontend hook | SceneGraph JSON |
| `overlay` | video_agent | VideoPanel | OverlayData JSON |
| `alerts` | video_agent | AlertPanel | Alert JSON |
| `zone_config` | video_agent | VideoPanel | DetectedZone[] JSON |
| `analyst_summary` | video_agent | AnalystBridge | `{summary: string}` |
| `analyst_annotations` | video_agent | AnalystBridge | `{annotations: ...}` |
| `analyst_request` | voice_agent | video_agent | Request JSON |
| `analyst_response` | video_agent | voice_agent | Response string |
| `transcript` | voice_agent | VoicePanel | UTF-8 string |

## Frontend (React + LiveKit)

Clean 50-line `App.tsx` — 70/30 split layout:
- **Left (70%)**: VideoPanel with overlay annotations
- **Right (30%)**: VoicePanel → AlertPanel → Dashboard
- **5 custom hooks**: useSceneGraph, useOverlay, useAlerts, useTranscript, useZones

### Frontend Components

| Component | Lines | Role |
|-----------|-------|------|
| VideoPanel.tsx | 225 | Annotated video display with overlay boxes |
| VoicePanel.tsx | 165 | Voice UI, speaking indicator, transcript |
| Dashboard.tsx | 134 | Herd summary metrics, behavior bars |
| AlertPanel.tsx | 130 | Alert cards with relative timestamps |

## Key Data Models (models.py)

### Core Pipeline Models
- **Detection** — raw detector output (bbox, confidence, class)
- **TrackedEntity** — ByteTrack-assigned identity with behavior, zone, velocity
- **SceneGraph** — full scene state: herd summary, tracked entities, zones, alerts
- **SceneDelta** — incremental changes: new/exited entities, zone crossings, behavior changes

### Communication Models
- **OverlayData** / **OverlayBox** — frontend bounding box annotations
- **GeminiContext** — scene graph + recent alerts + history snapshots for Gemini context

### Tool Response Models
- **EntityHistory** / **BehaviorRecord** — per-entity behavior timeline
- **HerdStats** — aggregate herd statistics
- **DescriptionSearchResult** / **DescriptionMatch** — natural language entity search
- **ZoneHistory** / **ZoneVisit** — zone occupancy history

## Key External Dependencies

| Package | Purpose |
|---------|---------|
| `livekit` | WebRTC rooms, agents framework |
| `google` (genai) | Gemini 2.5 Flash Live API |
| `pydantic` | Data models, validation |
| `supervision` | ByteTrack multi-object tracking |
| `numpy` | Array operations for detection |
| `PIL` | Image processing |
| `av` (PyAV) | Video file decoding |
| `aiosqlite` | Async SQLite for tracking history |

## Health Metrics

- **Total functions**: 124 (45 async = 36%)
- **TODO/FIXME**: 2
- **Mock/hardcoded references**: 21 — all 4 data tools return mock data
- **Dead code**: `herdflow_agent.py` (19 lines, unused)
- **Largest function**: `entrypoint()` in voice_agent.py (396 lines — refactor candidate)
- **Docker**: untested
- **Tests**: 106 passing (backend only)

## Architecture Diagram

Excalidraw: https://excalidraw.com/#json=4uaCEoguXMPVSZgc4y9hF,120vV1A5A6BBMlYEhpH78w
