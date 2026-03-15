# HerdFlow

## Project Overview
Real-time AI veterinary co-pilot for livestock monitoring. Uses RF-DETR for animal detection/tracking, Gemini Live API for voice interaction, and LiveKit for WebRTC transport. Targets the Gemini Live Agent Challenge "Live Agents" category.

## Tech Stack
- **Backend**: Python 3.12+ — LiveKit Agents, RF-DETR, Gemini 2.5 Flash Live API
- **Frontend**: React + TypeScript — Vite, Tailwind CSS 3.x, @livekit/components-react
- **Package Manager**: `uv` (backend), `npm` (frontend)
- **Database**: SQLite (tracking history via `storage/history.py`)
- **Deployment**: Docker → Google Cloud Run (GPU) + GCE (LiveKit server)
- **Build (backend)**: `uv sync`
- **Build (frontend)**: `cd frontend && npm run build`
- **Test (backend)**: `uv run pytest`
- **Test (frontend)**: `cd frontend && npx vitest run`
- **Lint (backend)**: `uv run ruff check .`
- **Lint (frontend)**: `cd frontend && npx eslint .`
- **Format (backend)**: `uv run ruff format --check .`
- **Format (frontend)**: `cd frontend && npx prettier --check .`
- **Typecheck (backend)**: `uv run pyright`
- **Typecheck (frontend)**: `cd frontend && npx tsc --noEmit`

## Repository Structure
```
herdflow/
├── agent/
│   ├── main.py                 # LiveKit Agent entrypoint
│   ├── herdflow_agent.py       # Agent class with persona
│   ├── perception/
│   │   ├── detector.py         # RF-DETR wrapper
│   │   ├── tracker.py          # ByteTrack via supervision
│   │   └── scene_graph.py      # Scene graph builder
│   ├── reasoning/
│   │   ├── sampler.py          # AdaptiveFrameSampler
│   │   ├── tools.py            # Gemini tool definitions
│   │   └── prompts.py          # System prompt templates
│   ├── alerts/
│   │   ├── rules.py            # Alert rule engine
│   │   └── models.py           # Alert data models
│   └── storage/
│       ├── history.py          # SQLite tracking history
│       └── models.py           # DB schema models
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── VideoPanel.tsx   # Annotated video display
│   │   │   ├── VoicePanel.tsx   # Voice UI + transcript
│   │   │   ├── AlertPanel.tsx   # Alert cards
│   │   │   └── Dashboard.tsx    # Herd summary metrics
│   │   └── hooks/
│   │       ├── useSceneGraph.ts # Scene graph subscription
│   │       └── useAlerts.ts     # Alert subscription
│   └── package.json
├── tests/                       # Backend pytest tests
├── Dockerfile
├── docker-compose.yml
├── cloudbuild.yaml
├── pyproject.toml
└── .env.example
```

## Three-Tier Architecture
1. **Tier 1 — Spatial Perception**: RF-DETR detection → ByteTrack → Scene Graph Builder (60 FPS)
2. **Tier 2 — Multimodal Reasoning**: Adaptive frame sampling → Gemini Live API (voice + video)
3. **Tier 3 — Communication**: LiveKit WebRTC rooms (video/audio/data channels) → React frontend

## Key Conventions
- Type hints on all public functions (Python + TypeScript)
- Async/await throughout (asyncio for Python, React hooks for frontend)
- Pydantic models or dataclasses for all data schemas
- `ruff` for Python linting/formatting, `eslint`+`prettier` for TypeScript
- Environment config via `.env` files (never commit secrets)
- Conventional commits

## Common Tasks
- **Build all**: `uv sync && cd frontend && npm install && npm run build`
- **Test all**: `uv run pytest && cd frontend && npx vitest run`
- **Test single (Python)**: `uv run pytest tests/test_file.py -k test_name`
- **Test single (TS)**: `cd frontend && npx vitest run src/path/to/test`
- **Lint all**: `uv run ruff check . && cd frontend && npx eslint .`
- **Pre-PR check**: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest && cd frontend && npx prettier --check . && npx eslint . && npx tsc --noEmit && npx vitest run`

## Swarm Development
This project supports multi-agent development via Claude Code TeammateTool.
- `/check` — full quality gate
- `/spawn-swarm <task>` — launch parallel agents
- `/review-pr` — code review checklist
- `/add-feature <name>` — scaffold a new feature

### Plan Execution
Use `.claude/skills/swarm-execution/SKILL.md` to execute implementation plans.
It combines superpowers review discipline (sequential tasks) with psmux swarm
parallelism (at PARALLEL SWARM markers in the plan). See the skill for details.

## Swarm Backend
**psmux/tmux: ACTIVE** — agents appear as visible panes next to you.

Current session detected. Agents will spawn into tmux panes via TeammateTool.
No additional setup needed.

To start a fresh swarm session:
```bash
psmux new-session -s herdflow
claude
```
