# HerdFlow — Project Overview

Real-time AI veterinary co-pilot for livestock monitoring. Targets the Gemini Live Agent Challenge "Live Agents" category (OhboyConsultancy FZ LLC).

## Three-Tier Architecture
1. **Tier 1 — Spatial Perception**: RF-DETR detection → ByteTrack (via supervision) → Scene Graph Builder (60 FPS)
2. **Tier 2 — Multimodal Reasoning**: Adaptive frame sampling → Gemini 2.5 Flash Live API (voice + video)
3. **Tier 3 — Communication**: LiveKit WebRTC rooms (video/audio/data channels) → React frontend

## Tech Stack
- **Backend**: Python 3.12+ — LiveKit Agents, RF-DETR (rfdetr), ByteTrack (supervision), Gemini Live API, Pydantic 2, aiosqlite
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + @livekit/components-react
- **Package Manager**: `uv` (backend), `npm` (frontend)
- **Database**: SQLite via aiosqlite (tracking history)
- **Deployment**: Docker → Google Cloud Run (GPU) + GCE (LiveKit server)

## Key Design Decisions
- **Pydantic single source of truth**: `agent/models.py` defines ALL contracts; TypeScript auto-generated
- **Two entity representations**: `TrackedEntity` (dataclass, in-process) + `TrackedEntityModel` (Pydantic, serialization)
- **GIL safety**: RF-DETR inference in ThreadPoolExecutor
- **Event-driven sampler**: asyncio.Queue, not polling
- **Dual threshold**: Detection 0.3 (ByteTrack), display 0.5

## Codebase Structure
```
agent/           — Backend Python package
  models.py      — ALL Pydantic/dataclass contracts (single source of truth)
  config.py      — Pydantic Settings from .env
  main.py        — LiveKit Agent entrypoint (to be created)
  herdflow_agent.py — Agent class with persona (to be created)
  perception/    — RF-DETR detector, ByteTrack tracker, scene graph builder
  reasoning/     — Adaptive sampler, Gemini tools, system prompts
  alerts/        — Alert rule engine
  storage/       — SQLite tracking history
frontend/        — React + TypeScript + Vite + Tailwind
  src/types/generated.ts — Auto-generated from models.py
scripts/         — generate_types.py, download_video.py
tests/           — pytest: contract, handshake, golden path tests
docs/superpowers/ — Design spec + implementation plan
```
