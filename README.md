# HerdFlow — AI Veterinary Co-Pilot

Real-time AI-powered livestock monitoring system that combines computer vision, voice interaction, and proactive health alerts.

**Gemini Live Agent Challenge** — Live Agents Category
**Team:** OhboyConsultancy FZ LLC

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    TIER 1: PERCEPTION                    │
│  Camera → RF-DETR Detection → ByteTrack → Scene Graph   │
│                    (60 FPS pipeline)                     │
├─────────────────────────────────────────────────────────┤
│                    TIER 2: REASONING                     │
│  Adaptive Sampler → Gemini 2.5 Flash Live API           │
│  (Event-driven context injection + voice interaction)   │
├─────────────────────────────────────────────────────────┤
│                  TIER 3: COMMUNICATION                   │
│  LiveKit WebRTC → React Dashboard (video/voice/data)    │
└─────────────────────────────────────────────────────────┘
```

## Key Features

- **Real-time animal detection & tracking** — RF-DETR + ByteTrack via supervision
- **Voice-first interaction** — Talk to your herd monitor like a colleague
- **Proactive health alerts** — Prolonged lying, isolation, missed feeding detection
- **Temporal reasoning** — "How long has cow #3 been lying?" with SQLite history
- **Adaptive context** — Only injects scene data into Gemini when something changes

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Detection | RF-DETR (rfdetr) |
| Tracking | ByteTrack (supervision) |
| Voice AI | Gemini 2.5 Flash Live API |
| Transport | LiveKit Agents + WebRTC |
| Backend | Python 3.12, asyncio |
| Frontend | React 18, TypeScript, Tailwind CSS |
| Database | SQLite (aiosqlite) |
| Deployment | Docker → Google Cloud Run (GPU) |

## Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd herdflow

# Option 1: Docker (recommended)
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY
docker compose up

# Option 2: Local development
uv sync --dev
cd frontend && npm install && cd ..
# Terminal 1: docker run --rm -p 7880:7880 -p 7881:7881 livekit/livekit-server --dev
# Terminal 2: uv run python -m agent.main
# Terminal 3: cd frontend && npm run dev
```

## Environment Variables

See `.env.example` for all configuration options.

Required:
- `GOOGLE_API_KEY` — Gemini API key
- `LIVEKIT_URL` — LiveKit server URL
- `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` — LiveKit credentials

## Demo Video

[Link to demo video — TODO]

## VisionFlow Platform Vision

HerdFlow is an instance of the **VisionFlow** pattern — a domain-agnostic architecture for real-time visual monitoring with AI reasoning. The same three-tier architecture (Perception → Reasoning → Communication) can be adapted to:
- Construction site safety monitoring
- Warehouse operations tracking
- Wildlife conservation surveillance
- Manufacturing quality inspection

Domain-specific code is isolated in configuration, prompts, and alert rules.

## License

MIT
