# HerdFlow MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use the `swarm-execution` skill (`.claude/skills/swarm-execution/SKILL.md`) to implement this plan. It combines superpowers review discipline (sequential tasks) with psmux swarm parallelism (at `PARALLEL SWARM` markers). Steps use checkbox (`- [ ]`) syntax for tracking. Falls back to `superpowers:subagent-driven-development` if no swarm backend is available.

**Goal:** Build and deploy a real-time AI veterinary co-pilot for the Gemini Live Agent Challenge by 2026-03-16 5:00 PM PDT.

**Architecture:** Three-tier vertical slice — mock scene graph → Gemini voice agent → React frontend, then thicken each tier with real implementations. Contract-first design with Pydantic as single source of truth. Event-driven async pipeline with GIL-safe GPU inference.

**Tech Stack:** Python 3.12 (uv), LiveKit Agents + google plugin, RF-DETR (rfdetr), ByteTrack (supervision), Gemini 2.5 Flash Live API, React 18 + TypeScript + Vite + Tailwind CSS, Docker, Google Cloud Run.

**Spec:** `docs/superpowers/specs/2026-03-15-herdflow-mvp-design.md` (v1.1)

**Existing tests:** `tests/conftest.py`, `tests/test_contracts.py`, `tests/test_handshakes.py`, `tests/test_golden_path.py` — 37 pre-written tests that will drive Phase 1.

---

## File Map

### Files to Create

| File | Responsibility |
|------|---------------|
| `agent/__init__.py` | Package init (exists) |
| `agent/models.py` | ALL Pydantic/dataclass contracts — single source of truth |
| `agent/config.py` | Pydantic Settings, loads `.env` |
| `agent/main.py` | LiveKit Agent entrypoint, perception_loop, data_channel_publisher |
| `agent/herdflow_agent.py` | HerdFlowAgent class (thin — persona + tools) |
| `agent/perception/__init__.py` | Package init |
| `agent/perception/detector.py` | RF-DETR wrapper + MockDetector |
| `agent/perception/tracker.py` | ByteTrack via supervision |
| `agent/perception/scene_graph.py` | SceneGraphBuilder (detect → track → classify → alert → graph) |
| `agent/reasoning/__init__.py` | Package init |
| `agent/reasoning/sampler.py` | AdaptiveFrameSampler (event-driven, queue-based) |
| `agent/reasoning/tools.py` | Gemini tool definitions (4 tools) + MockTrackingHistory |
| `agent/reasoning/prompts.py` | System prompt templates (static + dynamic + history) |
| `agent/alerts/__init__.py` | Package init |
| `agent/alerts/rules.py` | AlertRuleEngine + 4 rule classes |
| `agent/storage/__init__.py` | Package init |
| `agent/storage/history.py` | SQLite tracking history |
| `scripts/generate_types.py` | Pydantic → TypeScript auto-generation |
| `scripts/download_video.py` | Fetch demo cattle footage from Pexels |
| `frontend/package.json` | Frontend deps |
| `frontend/tsconfig.json` | TypeScript config |
| `frontend/vite.config.ts` | Vite config |
| `frontend/tailwind.config.ts` | Tailwind config |
| `frontend/index.html` | Entry HTML |
| `frontend/src/App.tsx` | Main app shell (70/30 layout) |
| `frontend/src/types/generated.ts` | Auto-generated TypeScript types |
| `frontend/src/components/VideoPanel.tsx` | Video + SVG overlay |
| `frontend/src/components/VoicePanel.tsx` | Voice UI + transcript |
| `frontend/src/components/AlertPanel.tsx` | Alert cards |
| `frontend/src/components/Dashboard.tsx` | Herd summary |
| `frontend/src/hooks/useSceneGraph.ts` | Scene graph data channel hook |
| `frontend/src/hooks/useAlerts.ts` | Alert data channel hook |
| `pyproject.toml` | Python project config |
| `.env.example` | Environment template |
| `Dockerfile` | Multi-stage build |
| `docker-compose.yml` | Dev stack (LiveKit + agent + frontend) |
| `cloudbuild.yaml` | GCP Cloud Build |

### Existing Files (tests — already created)

| File | Status |
|------|--------|
| `tests/__init__.py` | Exists |
| `tests/conftest.py` | Exists — 14 fixtures, 12 factory functions |
| `tests/test_contracts.py` | Exists — 18 contract tests |
| `tests/test_handshakes.py` | Exists — 16 handshake tests |
| `tests/test_golden_path.py` | Exists — 3 golden path tests |

---

## Chunk 1: Foundation (Phase 1)

### Task 1: Project Setup — pyproject.toml + .env.example

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "herdflow"
version = "0.1.0"
description = "Real-time AI veterinary co-pilot for livestock monitoring"
requires-python = ">=3.12"
dependencies = [
    "livekit-agents>=1.0",
    "livekit-plugins-google>=1.0",
    "livekit-plugins-silero>=1.0",
    "rfdetr>=1.0",
    "supervision>=0.25",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "numpy>=1.26",
    "aiosqlite>=0.20",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "anyio>=4.0",
    "hypothesis>=6.0",
    "hypothesis-jsonschema>=0.23",
    "ruff>=0.8",
    "pyright>=1.1",
    "pydantic2ts>=0.9",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "SIM"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "standard"
```

- [ ] **Step 2: Create .env.example**

```bash
# LiveKit
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# Google AI
GOOGLE_API_KEY=

# RF-DETR
RFDETR_MODEL=rf-detr-small
RFDETR_DETECTION_THRESHOLD=0.3
RFDETR_DISPLAY_THRESHOLD=0.5

# HerdFlow
MAX_FPS=2.0
MIN_INTERVAL_MS=200
ALERT_PROLONGED_LYING_S=3600
ALERT_ISOLATION_THRESHOLD=0.7
ALERT_MISSED_FEEDING_S=14400
ENTITY_ID_PREFIX=COW-
```

- [ ] **Step 3: Create .gitignore**

Standard Python + Node + env gitignore.

- [ ] **Step 4: Initialize git repo and install deps**

```bash
cd D:/Home/HerdFlow
git init
cp .env.example .env
uv sync
```

- [ ] **Step 5: Verify test runner works (tests will fail — no models yet)**

```bash
uv run pytest tests/ -v --co
```

Expected: collects 37 tests, import errors because `agent.models` doesn't exist yet.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example .gitignore
git commit -m "chore: project scaffold with dependencies"
```

---

### Task 2: Implement agent/models.py — Make All 37 Tests Pass

This is the core deliverable of Phase 1. Every contract defined in the design doc Section 4 goes here. The 37 pre-written tests drive the implementation.

**Files:**
- Create: `agent/models.py`
- Test: `tests/test_contracts.py`, `tests/test_handshakes.py`, `tests/test_golden_path.py`

- [ ] **Step 1: Create agent/models.py with all contracts**

Copy the full Python contract definitions from the design doc Section 4 into `agent/models.py`. This includes:

- `Detection` (dataclass)
- `TrackState` (enum)
- `TrackedEntity` (dataclass) — with `confidence`, `zone_dwell_s`, `bbox_aspect_ratio`
- `Severity` (enum)
- `Alert` (Pydantic) — with `key` property and `id` default factory
- `ZoneOccupancy`, `HerdSummary` (with `feeding`, `drinking`)
- `TrackedEntityModel` (Pydantic)
- `SceneGraph` (Pydantic)
- `ZoneCrossing`, `BehaviorChange`, `SceneDelta` (Pydantic)
- `SceneGraphSnapshot` (Pydantic — slim history)
- `GeminiContext` (Pydantic)
- `OverlayBox` (Pydantic — slim)
- `OverlayData` (Pydantic)
- `BehaviorRecord`, `EntityHistory`, `HerdStats`, `DescriptionMatch`, `DescriptionSearchResult`, `ZoneVisit`, `ZoneHistory` (Pydantic — tool responses)
- `FRONTEND_REQUIRED_FIELDS` (dict)

Reference: Design doc Section 4, lines 180-410.

- [ ] **Step 2: Run all 37 tests**

```bash
uv run pytest tests/ -v
```

Expected: ALL 37 PASS. If any fail, fix `models.py` to match the test expectations (tests are the contract — they don't change).

- [ ] **Step 3: Run ruff + pyright**

```bash
uv run ruff check agent/models.py
uv run ruff format --check agent/models.py
uv run pyright agent/models.py
```

Expected: clean on all three.

- [ ] **Step 4: Commit**

```bash
git add agent/models.py agent/__init__.py tests/
git commit -m "feat: implement all data contracts — 37 tests passing"
```

---

### Task 3: Config Module

**Files:**
- Create: `agent/config.py`

- [ ] **Step 1: Create agent/config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LiveKit
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    # Google AI
    google_api_key: str = ""

    # RF-DETR
    rfdetr_model: str = "rf-detr-small"
    rfdetr_detection_threshold: float = 0.3
    rfdetr_display_threshold: float = 0.5

    # HerdFlow
    max_fps: float = 2.0
    min_interval_ms: int = 200
    alert_prolonged_lying_s: float = 3600
    alert_isolation_threshold: float = 0.7
    alert_missed_feeding_s: float = 14400
    entity_id_prefix: str = "COW-"

    # Zone config (frame-relative percentages)
    zone_config: dict = {
        "feed_area": {"x1": 0.0, "y1": 0.0, "x2": 0.3, "y2": 0.5},
        "water_trough": {"x1": 0.7, "y1": 0.0, "x2": 1.0, "y2": 0.3},
        "rest_area": {"x1": 0.3, "y1": 0.5, "x2": 1.0, "y2": 1.0},
    }

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 2: Verify it loads**

```bash
uv run python -c "from agent.config import settings; print(settings.rfdetr_model)"
```

Expected: `rf-detr-small`

- [ ] **Step 3: Commit**

```bash
git add agent/config.py
git commit -m "feat: add pydantic settings config module"
```

---

### Task 4: TypeScript Type Generation Script

**Files:**
- Create: `scripts/generate_types.py`

- [ ] **Step 1: Create the generation script**

```python
"""Generate TypeScript types from agent/models.py Pydantic models.

Usage: uv run python scripts/generate_types.py
Output: frontend/src/types/generated.ts
"""
import json
import sys
from pathlib import Path

from agent.models import (
    Alert,
    HerdSummary,
    OverlayBox,
    OverlayData,
    SceneGraph,
    TrackedEntityModel,
    ZoneOccupancy,
)

HEADER = "// AUTO-GENERATED from agent/models.py — do not edit manually\n\n"

MODELS = [
    HerdSummary,
    ZoneOccupancy,
    TrackedEntityModel,
    Alert,
    SceneGraph,
    OverlayBox,
    OverlayData,
]


def pydantic_to_ts_type(python_type: str) -> str:
    """Map Python/Pydantic types to TypeScript types."""
    mapping = {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "null": "null",
    }
    return mapping.get(python_type, "any")


def schema_to_interface(name: str, schema: dict, defs: dict) -> str:
    """Convert a JSON Schema to a TypeScript interface."""
    lines = [f"export interface {name} {{"]
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    for field_name, field_schema in props.items():
        ts_type = resolve_type(field_schema, defs)
        optional = "" if field_name in required else "?"
        lines.append(f"  {field_name}{optional}: {ts_type};")

    lines.append("}")
    return "\n".join(lines)


def resolve_type(field_schema: dict, defs: dict) -> str:
    """Resolve a JSON Schema field to a TypeScript type."""
    if "$ref" in field_schema:
        ref_name = field_schema["$ref"].split("/")[-1]
        return ref_name

    if "anyOf" in field_schema:
        types = [resolve_type(t, defs) for t in field_schema["anyOf"]]
        return " | ".join(types)

    if "enum" in field_schema:
        return " | ".join(f"'{v}'" for v in field_schema["enum"])

    json_type = field_schema.get("type", "any")

    if json_type == "array":
        items = field_schema.get("items", {})
        item_type = resolve_type(items, defs)
        return f"{item_type}[]"

    if json_type == "object":
        addl = field_schema.get("additionalProperties", {})
        if addl:
            val_type = resolve_type(addl, defs)
            return f"Record<string, {val_type}>"
        return "Record<string, unknown>"

    return pydantic_to_ts_type(json_type)


def generate() -> str:
    """Generate all TypeScript interfaces."""
    output = [HEADER]

    # Collect all schemas
    for model in MODELS:
        schema = model.model_json_schema()
        defs = schema.get("$defs", {})
        name = model.__name__

        # Rename TrackedEntityModel → TrackedEntity for TS
        ts_name = "TrackedEntity" if name == "TrackedEntityModel" else name

        output.append(schema_to_interface(ts_name, schema, defs))
        output.append("")

    # Add Severity type alias
    output.append("export type Severity = 'info' | 'warning' | 'alert' | 'critical';")
    output.append("")

    return "\n".join(output)


def main():
    out_path = Path("frontend/src/types/generated.ts")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = generate()
    out_path.write_text(content, encoding="utf-8")
    print(f"Generated {out_path} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

```bash
uv run python scripts/generate_types.py
```

Expected: creates `frontend/src/types/generated.ts`.

- [ ] **Step 3: Commit**

```bash
git add scripts/generate_types.py frontend/src/types/generated.ts
git commit -m "feat: add TypeScript type generation from Pydantic models"
```

---

### Task 5: Package Init Files

**Files:**
- Create: `agent/perception/__init__.py`
- Create: `agent/reasoning/__init__.py`
- Create: `agent/alerts/__init__.py`
- Create: `agent/storage/__init__.py`

- [ ] **Step 1: Create all __init__.py files**

Empty files for all subpackages.

- [ ] **Step 2: Commit**

```bash
git add agent/perception/ agent/reasoning/ agent/alerts/ agent/storage/
git commit -m "chore: add subpackage init files"
```

---

## Chunk 2: Voice Agent Vertical Slice (Phase 2)

**Goal:** Get Gemini talking about a fake herd via LiveKit. Demoable milestone.

### Task 6: System Prompt

**Files:**
- Create: `agent/reasoning/prompts.py`

- [ ] **Step 1: Create the system prompt module**

```python
"""System prompt templates for HerdFlow agent.

Three layers:
- STATIC_PROMPT: persona, baselines, escalation rules (set once)
- Dynamic: {scene_graph_json} replaced per adaptive sample
- History: recent alerts + snapshots via GeminiContext
"""

STATIC_PROMPT = """
You are HerdFlow, an AI veterinary co-pilot for livestock monitoring.
You watch a herd through a camera and have access to a continuously
updated scene graph with tracked animals, their behaviors, zone
occupancy, and health alerts.

PERSONA:
- Speak like an experienced, caring farm veterinarian.
- Be concise and actionable. Farmers are busy.
- Reference animals by track ID (e.g., "cow number three").
- When proactively alerting, state the concern, the evidence,
  and a recommended action.

BEHAVIOR BASELINES:
- Cattle lie down 10-14 hours/day. >4 hours continuous = check.
- Healthy cattle visit feed area every 4-6 hours.
- Isolation from herd can indicate illness or calving.
- Sudden velocity changes may indicate distress or aggression.

ALERT ESCALATION:
- INFO: Mention casually if farmer asks.
- WARNING: Proactively mention at next natural pause.
- ALERT: Interrupt immediately with urgent tone.
- CRITICAL: Interrupt immediately with emphasis.

CURRENT SCENE GRAPH:
{scene_graph_json}
"""


def build_system_prompt(scene_graph_json: str = "{}") -> str:
    """Build the full system prompt with current scene graph injected."""
    return STATIC_PROMPT.format(scene_graph_json=scene_graph_json)
```

- [ ] **Step 2: Commit**

```bash
git add agent/reasoning/prompts.py
git commit -m "feat: add system prompt templates with persona and baselines"
```

---

### Task 7: Mock Tracking History (Gemini Tool Backend)

**Files:**
- Create: `agent/reasoning/tools.py`
- Create: `tests/test_tools.py`

- [ ] **Step 1: Write failing test for mock tools**

```python
# tests/test_tools.py
import pytest
from agent.reasoning.tools import MockTrackingHistory


@pytest.mark.asyncio
async def test_mock_search_entity_history():
    history = MockTrackingHistory()
    result = await history.search_entity_history("COW-003", 60)
    assert result.track_id == "COW-003"
    assert result.current_behavior == "lying"
    assert len(result.records) > 0


@pytest.mark.asyncio
async def test_mock_get_herd_stats():
    history = MockTrackingHistory()
    result = await history.get_herd_stats(60)
    assert result.total_animals == 8
    assert "COW-003" in result.not_fed


@pytest.mark.asyncio
async def test_mock_find_by_description():
    history = MockTrackingHistory()
    result = await history.find_by_description("the brown cow near the fence")
    assert len(result.matches) > 0


@pytest.mark.asyncio
async def test_mock_get_zone_history():
    history = MockTrackingHistory()
    result = await history.get_zone_history("water_trough", 120)
    assert result.zone == "water_trough"
    assert len(result.visits) > 0
    assert "COW-003" in result.animals_not_visited
```

- [ ] **Step 2: Run test — should fail**

```bash
uv run pytest tests/test_tools.py -v
```

- [ ] **Step 3: Implement MockTrackingHistory and herd_tools in agent/reasoning/tools.py**

Implement `MockTrackingHistory` with the mock responses from design doc Section 6. Also define and export `herd_tools` — a list of tool function definitions that wrap `MockTrackingHistory` methods for registration with Gemini:

```python
# At module level, export this for HerdFlowAgent
mock_history = MockTrackingHistory()

async def search_entity_history(track_id: str, minutes: int = 60):
    """Query behavior history for a specific animal."""
    return (await mock_history.search_entity_history(track_id, minutes)).model_dump()

async def get_herd_stats(minutes: int = 60):
    """Get aggregate herd statistics over a time window."""
    return (await mock_history.get_herd_stats(minutes)).model_dump()

async def find_by_description(description: str):
    """Find animals matching a natural language description."""
    return (await mock_history.find_by_description(description)).model_dump()

async def get_zone_history(zone: str, minutes: int = 120):
    """Get zone occupancy history."""
    return (await mock_history.get_zone_history(zone, minutes)).model_dump()

herd_tools = [search_entity_history, get_herd_stats, find_by_description, get_zone_history]
```

Reference: Design doc Section 6, mock response JSON blocks.

- [ ] **Step 4: Run test — should pass**

```bash
uv run pytest tests/test_tools.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agent/reasoning/tools.py tests/test_tools.py
git commit -m "feat: add mock tracking history with demo scenario data"
```

---

### Task 8: HerdFlowAgent Class

**Files:**
- Create: `agent/herdflow_agent.py`

- [ ] **Step 1: Create the agent class**

```python
"""HerdFlow agent — thin wrapper providing persona and tools to LiveKit AgentSession."""

from livekit.agents import Agent

from agent.reasoning.prompts import STATIC_PROMPT
from agent.reasoning.tools import herd_tools


class HerdFlowAgent(Agent):
    """LiveKit Agent with HerdFlow veterinary persona and scene-query tools."""

    def __init__(self):
        super().__init__(
            instructions=STATIC_PROMPT,
            tools=herd_tools,
        )
```

- [ ] **Step 2: Verify import works**

```bash
uv run python -c "from agent.herdflow_agent import HerdFlowAgent; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add agent/herdflow_agent.py
git commit -m "feat: add HerdFlowAgent class with persona and tools"
```

---

### Task 9: LiveKit Agent Entrypoint (Mock Mode)

**Files:**
- Create: `agent/main.py`

- [ ] **Step 1: Create the entrypoint with mock perception**

Implement `agent/main.py` with:
- `AgentServer` setup
- `on_process_started`: no model loading in mock mode
- `entrypoint`: creates `AgentSession` with Gemini RealtimeModel, starts with `HerdFlowAgent`
- Mock scene graph injected as static context (no perception loop yet)
- No adaptive sampling yet — just static context injection

Reference: Design doc Section 8 (Communication Layer), simplified for mock mode.

```python
"""LiveKit Agent entrypoint for HerdFlow.

Phase 2 (mock mode): Static scene graph, no perception pipeline.
Phases 4+: Real detection, tracking, adaptive sampling.
"""
import asyncio
import logging

from livekit.agents import AgentServer, AgentSession
from livekit.plugins import google, silero

from agent.config import settings
from agent.herdflow_agent import HerdFlowAgent
from agent.models import SceneGraph
from agent.reasoning.prompts import build_system_prompt

# Build a mock scene graph for Phase 2
from tests.conftest import make_scene_graph

logger = logging.getLogger("herdflow")

server = AgentServer()


@server.on_process_started
async def on_process_started(proc):
    """Pre-load VAD model."""
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("HerdFlow agent process started (mock mode)")


@server.rtc_session()
async def entrypoint(ctx):
    vad = ctx.proc.userdata["vad"]

    # Mock scene graph for Phase 2
    mock_sg = make_scene_graph(entities=8, alerts=1)
    prompt = build_system_prompt(mock_sg.model_dump_json(indent=2))

    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-preview",
            proactivity=True,
            enable_affective_dialog=True,
            thinking_config={"thinking_budget": 1024},
        ),
        vad=vad,
    )

    agent = HerdFlowAgent()
    agent._instructions = prompt  # inject mock scene graph

    await session.start(
        room=ctx.room,
        agent=agent,
    )

    # Greet the farmer
    await session.generate_reply()
    logger.info("HerdFlow agent session started")
```

- [ ] **Step 2: Install and start local LiveKit dev server**

```bash
# Download LiveKit server binary (or use Docker)
docker run --rm -p 7880:7880 -p 7881:7881 livekit/livekit-server --dev
```

- [ ] **Step 3: Test the agent connects**

```bash
uv run python -m agent.main
```

Expected: agent starts, connects to LiveKit, waits for a room participant.

- [ ] **Step 4: Test voice interaction**

Open LiveKit's meet app at `http://localhost:7880` (or use LiveKit CLI to join a room). Speak to the agent. It should respond as a veterinary co-pilot with awareness of the mock herd.

- [ ] **Step 5: Commit**

```bash
git add agent/main.py
git commit -m "feat: LiveKit agent entrypoint with mock scene graph (Phase 2 milestone)"
```

---

## Chunk 3: Frontend (Phase 3)

**Goal:** React frontend with video, voice transcript, alerts, and dashboard. Demoable milestone.

### Task 10: Frontend Scaffold

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/tailwind.config.ts`, `frontend/index.html`, `frontend/src/main.tsx`

- [ ] **Step 1: Scaffold with Vite**

```bash
cd D:/Home/HerdFlow
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install @livekit/components-react @livekit/components-styles livekit-client
npm install -D tailwindcss @tailwindcss/vite
```

- [ ] **Step 2: Configure Tailwind in vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

- [ ] **Step 3: Add Tailwind import to src/index.css**

```css
@import "tailwindcss";
```

- [ ] **Step 4: Verify it runs**

```bash
cd frontend && npm run dev
```

Expected: Vite dev server at http://localhost:5173.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: frontend scaffold with React, Vite, Tailwind, LiveKit SDK"
```

---

### Task 11: LiveKit Data Channel Hooks

**Files:**
- Create: `frontend/src/hooks/useSceneGraph.ts`
- Create: `frontend/src/hooks/useAlerts.ts`

- [ ] **Step 1: Create useSceneGraph hook**

```typescript
import { useEffect, useState } from 'react';
import { Room, RoomEvent, DataPacket_Kind } from 'livekit-client';
import type { SceneGraph } from '../types/generated';

export function useSceneGraph(room: Room | undefined): SceneGraph | null {
  const [sceneGraph, setSceneGraph] = useState<SceneGraph | null>(null);

  useEffect(() => {
    if (!room) return;

    const handler = (payload: Uint8Array, participant: any, kind: any, topic: string | undefined) => {
      if (topic === 'scene_graph') {
        try {
          const data = JSON.parse(new TextDecoder().decode(payload)) as SceneGraph;
          setSceneGraph(data);
        } catch (e) {
          console.error('Failed to parse scene_graph:', e);
        }
      }
    };

    room.on(RoomEvent.DataReceived, handler);
    return () => { room.off(RoomEvent.DataReceived, handler); };
  }, [room]);

  return sceneGraph;
}
```

- [ ] **Step 2: Create useAlerts hook**

```typescript
import { useEffect, useState } from 'react';
import { Room, RoomEvent } from 'livekit-client';
import type { Alert } from '../types/generated';

export function useAlerts(room: Room | undefined): Alert[] {
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    if (!room) return;

    const handler = (payload: Uint8Array, participant: any, kind: any, topic: string | undefined) => {
      if (topic === 'alerts') {
        try {
          const alert = JSON.parse(new TextDecoder().decode(payload)) as Alert;
          setAlerts(prev => {
            // Dedup by id, keep last 20
            const filtered = prev.filter(a => a.id !== alert.id);
            return [...filtered, alert].slice(-20);
          });
        } catch (e) {
          console.error('Failed to parse alert:', e);
        }
      }
    };

    room.on(RoomEvent.DataReceived, handler);
    return () => { room.off(RoomEvent.DataReceived, handler); };
  }, [room]);

  return alerts;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat: add useSceneGraph and useAlerts data channel hooks"
```

---

### Task 12: Frontend Components

**Files:**
- Create: `frontend/src/components/VideoPanel.tsx`
- Create: `frontend/src/components/VoicePanel.tsx`
- Create: `frontend/src/components/AlertPanel.tsx`
- Create: `frontend/src/components/Dashboard.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create VideoPanel**

LiveKit `VideoRenderer` + SVG overlay. Receives `OverlayData` from data channel. Renders bounding boxes colored by behavior, track IDs above boxes, zone boundaries as dashed rectangles. Reference: Design doc Section 8 (SVG Overlay Rendering).

- [ ] **Step 2: Create VoicePanel**

Transcript display + microphone toggle. Uses LiveKit's `useParticipantTracks` for audio. Shows scrolling transcript with speaker labels.

- [ ] **Step 3: Create AlertPanel**

Alert cards with severity color coding (Tailwind classes from design doc). Click to expand. Auto-dismiss resolved alerts.

- [ ] **Step 4: Create Dashboard**

Herd summary metrics from SceneGraph: total count, behavior breakdown, active alert count. Simple card layout.

- [ ] **Step 5: Wire up App.tsx with 70/30 split layout**

```typescript
// 70/30 split: video left, panels right
<div className="flex h-screen bg-slate-900 text-white">
  <div className="w-[70%] relative">
    <VideoPanel room={room} />
  </div>
  <div className="w-[30%] flex flex-col border-l border-slate-700">
    <VoicePanel room={room} />
    <AlertPanel alerts={alerts} />
    <Dashboard sceneGraph={sceneGraph} />
  </div>
</div>
```

- [ ] **Step 6: Test end-to-end**

Start LiveKit dev server + agent + frontend. Join room, verify video + voice + data channels work.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat: frontend components — VideoPanel, VoicePanel, AlertPanel, Dashboard (Phase 3 milestone)"
```

---

## Chunk 4: Real Perception (Phases 4-5)

**Goal:** Replace mock detections with real RF-DETR + ByteTrack pipeline.

**Swarm parallelism:** Tasks 13-14 (perception) can run in parallel with Task 15 (alert rules) after Phase 3 is complete.

### Task 13: RF-DETR Detector

**Files:**
- Create: `agent/perception/detector.py`
- Create: `tests/test_detector.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_detector.py
import numpy as np
import pytest
from agent.perception.detector import RFDETRDetector, MockDetector
from agent.models import Detection


def test_mock_detector_returns_detections():
    detector = MockDetector()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detections = detector.detect_sync(frame)
    assert isinstance(detections, list)
    assert all(isinstance(d, Detection) for d in detections)
    assert len(detections) > 0


def test_mock_detector_confidence_above_threshold():
    detector = MockDetector()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detections = detector.detect_sync(frame)
    assert all(d.confidence >= 0.3 for d in detections)


def test_mock_detector_bbox_format():
    detector = MockDetector()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detections = detector.detect_sync(frame)
    for d in detections:
        x1, y1, x2, y2 = d.bbox
        assert x2 > x1 and y2 > y1
```

- [ ] **Step 2: Run test — should fail**

```bash
uv run pytest tests/test_detector.py -v
```

- [ ] **Step 3: Implement detector.py**

Implement `RFDETRDetector` (wraps `rfdetr` package, uses `ThreadPoolExecutor`) and `MockDetector` (returns moving hardcoded detections). Reference: Design doc Section 5.

- [ ] **Step 4: Run test — should pass**

```bash
uv run pytest tests/test_detector.py -v
```

- [ ] **Step 5: Test real RF-DETR on local GPU (manual)**

```bash
uv run python -c "
from agent.perception.detector import RFDETRDetector
import numpy as np
d = RFDETRDetector()
frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
import asyncio
result = asyncio.run(d.detect(frame))
print(f'Found {len(result)} detections')
"
```

- [ ] **Step 6: Commit**

```bash
git add agent/perception/detector.py tests/test_detector.py
git commit -m "feat: RF-DETR detector with ThreadPoolExecutor for GIL safety"
```

---

### Task 14: ByteTrack Tracker + SceneGraphBuilder

**Files:**
- Create: `agent/perception/tracker.py`
- Create: `agent/perception/scene_graph.py`
- Create: `tests/test_tracker.py`
- Create: `tests/test_scene_graph.py`

- [ ] **Step 1: Write failing tests for tracker**

```python
# tests/test_tracker.py
import pytest
from agent.perception.tracker import Tracker
from agent.models import TrackedEntity, TrackState
from tests.conftest import make_detection


def test_tracker_assigns_persistent_ids():
    tracker = Tracker()
    dets = [make_detection(bbox=(100, 200, 300, 400))]
    tracked = tracker.update(dets, frame_id=1)
    assert len(tracked) == 1
    assert tracked[0].track_id.startswith("COW-")

    # Same position next frame should keep same ID
    tracked2 = tracker.update(dets, frame_id=2)
    assert tracked2[0].track_id == tracked[0].track_id


def test_tracker_new_detection_gets_new_id():
    tracker = Tracker()
    dets1 = [make_detection(bbox=(100, 200, 300, 400))]
    tracked1 = tracker.update(dets1, frame_id=1)

    dets2 = [
        make_detection(bbox=(100, 200, 300, 400)),
        make_detection(bbox=(500, 200, 700, 400)),
    ]
    tracked2 = tracker.update(dets2, frame_id=2)
    assert len(tracked2) == 2
    ids = {t.track_id for t in tracked2}
    assert len(ids) == 2  # two unique IDs
```

- [ ] **Step 2: Write failing tests for scene graph builder**

```python
# tests/test_scene_graph.py
import pytest
from agent.perception.scene_graph import SceneGraphBuilder
from agent.perception.detector import MockDetector
from agent.perception.tracker import Tracker
from agent.config import settings
from agent.models import SceneGraph, SceneDelta, Alert
from tests.conftest import sample_frame


class NullAlertEngine:
    """Stub alert engine for testing SGB without depending on alerts/rules.py."""
    def evaluate(self, entities):
        return []


@pytest.mark.asyncio
async def test_scene_graph_builder_produces_valid_graph():
    builder = SceneGraphBuilder(
        detector=MockDetector(),
        tracker=Tracker(),
        zone_config=settings.zone_config,
        alert_engine=NullAlertEngine(),
    )
    frame = sample_frame()
    sg = await builder.process_frame(frame, frame_id=1)
    assert isinstance(sg, SceneGraph)
    assert sg.frame_id == 1
    assert sg.herd_summary.total_visible == len(sg.tracked_entities)


@pytest.mark.asyncio
async def test_scene_graph_delta_first_frame_significant():
    builder = SceneGraphBuilder(
        detector=MockDetector(),
        tracker=Tracker(),
        zone_config=settings.zone_config,
        alert_engine=NullAlertEngine(),
    )
    frame = sample_frame()
    sg = await builder.process_frame(frame, frame_id=1)
    delta = builder.get_delta(None, sg)
    assert isinstance(delta, SceneDelta)
    assert delta.is_significant
```

> **Note:** `NullAlertEngine` is used instead of the real `AlertRuleEngine` so that Task 14 does not depend on Task 15. The real alert engine is integrated in Task 17 (wire pipeline).

- [ ] **Step 3: Run tests — should fail**

```bash
uv run pytest tests/test_tracker.py tests/test_scene_graph.py -v
```

- [ ] **Step 4: Implement tracker.py**

ByteTrack via `supervision`. Converts `list[Detection]` to `sv.Detections`, runs `ByteTrack.update_with_detections()`, converts back to `list[TrackedEntity]` with persistent IDs using entity_id_prefix from config.

Reference: Design doc Section 5 (Tracker).

- [ ] **Step 5: Implement scene_graph.py**

SceneGraphBuilder orchestrating detector → tracker → behavior classification → alert evaluation → SceneGraph construction. Includes behavior priority chain and zone dwell-time gating.

Reference: Design doc Section 5 (SceneGraphBuilder), behavior classification priority chain.

- [ ] **Step 6: Run tests — should pass**

```bash
uv run pytest tests/test_tracker.py tests/test_scene_graph.py -v
```

- [ ] **Step 7: Run ALL tests to verify no regressions**

```bash
uv run pytest tests/ -v
```

- [ ] **Step 8: Commit**

```bash
git add agent/perception/ tests/test_tracker.py tests/test_scene_graph.py
git commit -m "feat: ByteTrack tracker + SceneGraphBuilder with behavior classification (Phase 5 milestone)"
```

---

## Chunk 5: Alert Engine + Adaptive Sampling (Phase 6)

### Task 15: Alert Rule Engine

**Files:**
- Create: `agent/alerts/rules.py`
- Create: `tests/test_alerts.py`

**Can run in parallel with Tasks 13-14 (different files, no dependencies).**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_alerts.py
import pytest
from agent.alerts.rules import (
    AlertRuleEngine,
    ProlongedLyingRule,
    IsolationRule,
    MissedFeedingRule,
)
from agent.config import settings
from agent.models import Alert, Severity
from tests.conftest import make_tracked_entity


def test_prolonged_lying_fires_above_threshold():
    rule = ProlongedLyingRule(threshold_s=3600)
    entity = make_tracked_entity(behavior="lying", behavior_duration_s=4320)
    alert = rule.check(entity)
    assert alert is not None
    assert alert.type == "prolonged_lying"
    assert alert.severity == Severity.WARNING


def test_prolonged_lying_does_not_fire_below_threshold():
    rule = ProlongedLyingRule(threshold_s=3600)
    entity = make_tracked_entity(behavior="lying", behavior_duration_s=1800)
    assert rule.check(entity) is None


def test_prolonged_lying_does_not_fire_for_standing():
    rule = ProlongedLyingRule(threshold_s=3600)
    entity = make_tracked_entity(behavior="standing", behavior_duration_s=5000)
    assert rule.check(entity) is None


def test_isolation_fires_above_threshold():
    rule = IsolationRule(threshold=0.7)
    entity = make_tracked_entity(isolation_score=0.82)
    alert = rule.check(entity)
    assert alert is not None
    assert alert.type == "isolation"


def test_isolation_does_not_fire_below_threshold():
    rule = IsolationRule(threshold=0.7)
    entity = make_tracked_entity(isolation_score=0.3)
    assert rule.check(entity) is None


def test_missed_feeding_fires_above_threshold():
    rule = MissedFeedingRule(threshold_s=14400)
    entity = make_tracked_entity(last_feed_visit_s=18000)
    alert = rule.check(entity)
    assert alert is not None
    assert alert.type == "missed_feeding"
    assert alert.severity == Severity.ALERT


def test_engine_dedup_same_alert():
    engine = AlertRuleEngine(settings)
    entity = make_tracked_entity(
        behavior="lying", behavior_duration_s=4320,
        isolation_score=0.82, last_feed_visit_s=18000,
    )
    alerts1 = engine.evaluate([entity])
    alerts2 = engine.evaluate([entity])  # same entity, same state
    # Second call should be suppressed by cooldown
    assert len(alerts2) == 0


def test_engine_auto_resolves_cleared_condition():
    engine = AlertRuleEngine(settings)
    # Fire alert
    entity_lying = make_tracked_entity(behavior="lying", behavior_duration_s=4320)
    engine.evaluate([entity_lying])
    assert len(engine._active) > 0

    # Condition clears — cow stands up
    entity_standing = make_tracked_entity(
        behavior="standing", behavior_duration_s=0,
        isolation_score=0.2, last_feed_visit_s=100,
    )
    engine.evaluate([entity_standing])
    # Active alerts for this entity should be resolved
```

- [ ] **Step 2: Run tests — should fail**

```bash
uv run pytest tests/test_alerts.py -v
```

- [ ] **Step 3: Implement rules.py**

`AlertRuleEngine` with `ProlongedLyingRule`, `IsolationRule`, `MissedFeedingRule`, `VelocityAnomalyRule`. Each implements `check(entity) -> Optional[Alert]`. Engine handles dedup via cooldowns and auto-resolution.

Reference: Design doc Section 7.

- [ ] **Step 4: Run tests — should pass**

```bash
uv run pytest tests/test_alerts.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agent/alerts/rules.py tests/test_alerts.py
git commit -m "feat: alert rule engine with 4 rules, dedup, auto-resolution"
```

---

### Task 16: Adaptive Frame Sampler

**Files:**
- Create: `agent/reasoning/sampler.py`
- Create: `tests/test_sampler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sampler.py
import asyncio
import pytest
from agent.reasoning.sampler import AdaptiveFrameSampler
from agent.models import SceneDelta
from tests.conftest import make_scene_graph, make_scene_delta


def test_sampler_rate_limit():
    sampler = AdaptiveFrameSampler(max_fps=2.0, min_interval_ms=200)
    sg = make_scene_graph()
    delta_sig = make_scene_delta(new_entities=["COW-009"])

    # First call should always send
    assert sampler.should_send(delta_sig, user_speaking=False, elapsed_ms=1000)

    # Within rate limit should not send
    assert not sampler.should_send(delta_sig, user_speaking=False, elapsed_ms=100)


def test_sampler_user_speaking_overrides_rate_limit():
    sampler = AdaptiveFrameSampler(max_fps=2.0, min_interval_ms=200)
    delta_sig = make_scene_delta(new_entities=["COW-009"])
    # User speaking overrides rate limit (but still needs delta or user query)
    # Per spec: "user_is_speaking" always sends regardless of rate limit or delta
    assert sampler.should_send(delta_sig, user_speaking=True, elapsed_ms=50)
    # Even with no delta, user speaking always triggers (need latest context)
    delta_quiet = make_scene_delta()
    assert sampler.should_send(delta_quiet, user_speaking=True, elapsed_ms=50)


def test_sampler_quiet_scene_no_send():
    sampler = AdaptiveFrameSampler(max_fps=2.0, min_interval_ms=200)
    delta_quiet = make_scene_delta()
    # No significant delta, not speaking — should not send
    assert not sampler.should_send(delta_quiet, user_speaking=False, elapsed_ms=5000)
```

- [ ] **Step 2: Run tests — should fail**

```bash
uv run pytest tests/test_sampler.py -v
```

- [ ] **Step 3: Implement sampler.py**

Event-driven `AdaptiveFrameSampler` with `should_send()` method and `run()` coroutine consuming from `asyncio.Queue`.

Reference: Design doc Section 6 (AdaptiveFrameSampler).

- [ ] **Step 4: Run tests — should pass**

```bash
uv run pytest tests/test_sampler.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agent/reasoning/sampler.py tests/test_sampler.py
git commit -m "feat: adaptive frame sampler with rate limiting and event-driven queue"
```

---

### Task 17: Wire Real Pipeline into Agent Entrypoint

**Files:**
- Modify: `agent/main.py`

- [ ] **Step 1: Update main.py to use real perception pipeline**

Replace mock scene graph with real pipeline:
- `perception_loop` consuming video frames from LiveKit
- `AdaptiveFrameSampler` consuming from `asyncio.Queue`
- `data_channel_publisher` sending overlays
- `SceneGraphBuilder` with real detector + tracker + alert engine

Reference: Design doc Section 8 (`perception_loop`, `data_channel_publisher`).

- [ ] **Step 2: Test with pre-recorded video**

Download cattle footage from Pexels, configure as LiveKit video source, verify detection + tracking + voice agent all work together.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add agent/main.py
git commit -m "feat: wire real perception pipeline into agent entrypoint (Phase 6 milestone)"
```

---

### Task 17b: SQLite Tracking History (Replace Mock)

**Files:**
- Create: `agent/storage/history.py`
- Create: `tests/test_history.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_history.py
import pytest
from agent.storage.history import TrackingHistory
from agent.models import EntityHistory, HerdStats, ZoneHistory


@pytest.mark.asyncio
async def test_record_and_query_entity_history():
    history = TrackingHistory(":memory:")
    await history.initialize()
    await history.record_behavior("COW-003", "lying", "rest_area", 4320.0)
    result = await history.search_entity_history("COW-003", minutes=60)
    assert isinstance(result, EntityHistory)
    assert result.track_id == "COW-003"
    assert len(result.records) >= 1


@pytest.mark.asyncio
async def test_herd_stats():
    history = TrackingHistory(":memory:")
    await history.initialize()
    await history.record_behavior("COW-001", "feeding", "feed_area", 600.0)
    await history.record_behavior("COW-002", "standing", "rest_area", 300.0)
    result = await history.get_herd_stats(minutes=60)
    assert isinstance(result, HerdStats)
    assert result.total_animals >= 2


@pytest.mark.asyncio
async def test_zone_history():
    history = TrackingHistory(":memory:")
    await history.initialize()
    await history.record_zone_visit("COW-001", "water_trough", 120.0)
    result = await history.get_zone_history("water_trough", minutes=60)
    assert isinstance(result, ZoneHistory)
    assert result.zone == "water_trough"
    assert len(result.visits) >= 1
```

- [ ] **Step 2: Run tests — should fail**

```bash
uv run pytest tests/test_history.py -v
```

- [ ] **Step 3: Implement TrackingHistory with aiosqlite**

```python
# agent/storage/history.py
"""SQLite-backed tracking history for Gemini tool queries.

Same interface as MockTrackingHistory — drop-in replacement.
Uses aiosqlite for async SQLite access.
"""
import aiosqlite
from agent.models import EntityHistory, HerdStats, ZoneHistory, DescriptionSearchResult
```

Implement `TrackingHistory` class with:
- `initialize()`: create tables (behaviors, zone_visits)
- `record_behavior()`: insert behavior record
- `record_zone_visit()`: insert zone visit
- `search_entity_history()`, `get_herd_stats()`, `get_zone_history()`, `find_by_description()`: query methods matching MockTrackingHistory interface

- [ ] **Step 4: Run tests — should pass**

```bash
uv run pytest tests/test_history.py -v
```

- [ ] **Step 5: Wire into agent/reasoning/tools.py**

Update `tools.py` to accept either `MockTrackingHistory` or `TrackingHistory` (same interface). Update `agent/main.py` to use real history when not in mock mode.

- [ ] **Step 6: Commit**

```bash
git add agent/storage/history.py tests/test_history.py agent/reasoning/tools.py
git commit -m "feat: SQLite tracking history replacing mock backend"
```

---

## Chunk 6: Polish + Deploy (Phases 7-9)

### Task 18: Frontend Polish

**Files:**
- Modify: `frontend/src/components/VideoPanel.tsx`
- Modify: `frontend/src/components/AlertPanel.tsx`
- Modify: `frontend/src/components/Dashboard.tsx`
- Modify: `frontend/src/App.tsx`

**Can run in parallel with Task 19 (deployment).**

- [ ] **Step 1: Add SVG bounding box overlay to VideoPanel**

Render bounding boxes from overlay data channel:
- `stroke-emerald-400` for active animals
- `stroke-blue-400` for resting
- `stroke-amber-400` for animals with alert flags
- Track ID labels above boxes
- Zone boundaries as dashed rectangles
- Pulsing red circle on animals with active alerts

- [ ] **Step 2: Style AlertPanel with severity colors**

- INFO: `bg-slate-100`
- WARNING: `bg-amber-50 border-amber-400`
- ALERT: `bg-red-50 border-red-500`
- CRITICAL: `bg-red-100 border-red-700 animate-pulse`

- [ ] **Step 3: Add behavior breakdown chart to Dashboard**

Simple bar chart or stat cards showing standing/lying/walking/feeding/drinking counts.

- [ ] **Step 4: Add animated waveform to VoicePanel**

Show agent speech activity indicator.

- [ ] **Step 5: Verify everything looks good**

Full end-to-end test with pre-recorded video.

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: frontend polish — SVG overlays, severity colors, dashboard (Phase 7 milestone)"
```

---

### Task 19: Docker + Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `cloudbuild.yaml`

- [ ] **Step 1: Create Dockerfile (multi-stage)**

Reference: Design doc Section 9 (Dockerfile).

```dockerfile
# Stage 1: Frontend
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python agent
FROM nvidia/cuda:12.4-runtime-ubuntu22.04
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY agent/ agent/
COPY --from=frontend /app/frontend/dist /app/frontend/dist
CMD ["uv", "run", "python", "-m", "agent.main"]
```

- [ ] **Step 2: Create docker-compose.yml for local dev**

Reference: Design doc Section 9 (Local Development Stack).

- [ ] **Step 3: Generate uv.lock**

```bash
uv lock
```

- [ ] **Step 4: Test Docker build locally**

```bash
docker compose build
docker compose up
```

- [ ] **Step 5: Sign up for LiveKit Cloud (free tier)**

Get `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`. Update `.env`.

- [ ] **Step 6: Create GCP project and deploy**

```bash
gcloud projects create herdflow-demo
gcloud config set project herdflow-demo
gcloud builds submit --tag gcr.io/herdflow-demo/herdflow-agent
gcloud run deploy herdflow-agent \
    --image gcr.io/herdflow-demo/herdflow-agent \
    --platform managed --region us-central1 \
    --allow-unauthenticated \
    --gpu 1 --gpu-type nvidia-l4 \
    --memory 16Gi --cpu 4
```

- [ ] **Step 7: Verify deployed agent works**

Test voice interaction with deployed agent via LiveKit Cloud room.

- [ ] **Step 8: Commit**

```bash
git add Dockerfile docker-compose.yml cloudbuild.yaml uv.lock
git commit -m "feat: Docker + GCP Cloud Run deployment (Phase 8 milestone)"
```

---

### Task 20: Demo Video

**Files:** None (recording only)

- [ ] **Step 1: Prepare demo script**

Follow the demo plan from Design doc Section 9 (Demo Video Plan). 4 minutes max.

- [ ] **Step 2: Source cattle footage**

Download 2-3 clean clips from Pexels (search "cattle farm", "cows grazing").

- [ ] **Step 3: Record demo**

Screen record the full pipeline: agent startup, voice conversation, anomaly detection, proactive alert, temporal query, architecture diagram, GCP proof.

- [ ] **Step 4: Upload and submit**

Upload demo video to YouTube/Google Drive. Submit via competition portal.

---

### Task 21: README + Video Download Script

**Files:**
- Create: `README.md`
- Create: `scripts/download_video.py`

**Can run in Swarm 2, parallel with Tasks 18-19. Assign to Pi agent.**

- [ ] **Step 1: Create README.md**

Hackathon submission README with:
- Project description (HerdFlow = AI veterinary co-pilot)
- Architecture diagram (text-based, 3-tier)
- Quick start instructions (`docker compose up`)
- Environment setup (.env.example reference)
- Demo video link (placeholder)
- Tech stack list
- VisionFlow platform vision

- [ ] **Step 2: Create scripts/download_video.py**

```python
"""Download demo cattle footage from Pexels free stock video."""
import subprocess
import sys
from pathlib import Path

VIDEOS = [
    # Pexels free stock video URLs — search "cattle farm"
    # Replace with actual URLs after browsing Pexels
]

OUTPUT_DIR = Path("demo_videos")


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    for url in VIDEOS:
        filename = OUTPUT_DIR / url.split("/")[-1]
        if filename.exists():
            print(f"Skipping {filename} (exists)")
            continue
        print(f"Downloading {url}...")
        subprocess.run(["curl", "-L", "-o", str(filename), url], check=True)
    print(f"Downloaded {len(VIDEOS)} videos to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add README.md scripts/download_video.py
git commit -m "docs: add README and video download script"
```

---

## Task Dependency Graph

```
Task 1 (scaffold) ──→ Task 2 (models) ──→ Task 3 (config)
                                      ├──→ Task 4 (type gen)
                                      ├──→ Task 5 (init files)
                                      └──→ Task 6 (prompts) ──→ Task 7 (mock tools)
                                                              ──→ Task 8 (agent class)
                                                              ──→ Task 9 (entrypoint) ──┐
                                                                                         │
                                          Task 10 (frontend scaffold) ──→ Task 11 (hooks)│
                                                                       ──→ Task 12 (components)
                                                                                         │
              ┌──────────────── PARALLEL SWARM 1 (after Phase 3) ──────────────┐         │
              │                          │                          │           │         │
       Task 13 (detector)       Task 15 (alerts)           Task 16 (sampler)   │         │
              │                          │                          │           │         │
              └──── Task 14 (tracker + SGB) ←── depends on 13+15 ──┘           │         │
                              │                                                │         │
                     Task R1: REVIEWER CHECKPOINT (swarm 1 merge review)       │         │
                              │                                                │         │
                     Task 17 (wire pipeline) ──→ Task 17b (SQLite history)     │         │
                              │                                                │         │
              ┌──────────── PARALLEL SWARM 2 ──────────────┐                   │         │
              │                    │                        │                   │         │
       Task 18 (frontend)   Task 19 (deploy)   Task 21 (README + video dl)    │         │
              │                    │                        │                   │         │
              └──── Task R2: REVIEWER CHECKPOINT (swarm 2 merge review) ───────┘         │
                              │                                                          │
                     Task 20 (demo video) ───────────────────────────────────────────────┘
```

### Corrected Dependencies
- Task 14 (tracker + SGB) depends on **both** Task 13 (detector) and Task 15 (alerts) — its tests import MockDetector and AlertRuleEngine
- Tasks 13, 15, 16 are truly independent and can run in PARALLEL SWARM 1
- Task 14 runs after 13+15 complete, then merges
- Reviewer checkpoints (R1, R2) validate merged work before proceeding

## Swarm Orchestration Guide

### Swarm 1: Perception + Alert Engine (after Phase 3)

**Setup commands:**
```bash
# Create worktrees
git worktree add .worktrees/detector -b agent/detector
git worktree add .worktrees/alerts -b agent/alerts
git worktree add .worktrees/sampler -b agent/sampler

# Create team
# TeamCreate({ team_name: "herdflow" })

# Create tasks with dependencies
# TaskCreate({ subject: "RF-DETR detector", description: "Task 13..." })      → ID 1
# TaskCreate({ subject: "Alert rule engine", description: "Task 15..." })     → ID 2
# TaskCreate({ subject: "Adaptive sampler", description: "Task 16..." })      → ID 3
# TaskCreate({ subject: "Tracker + SGB", description: "Task 14..." })         → ID 4
# TaskUpdate({ taskId: "4", addBlockedBy: ["1", "2"] })
# TaskCreate({ subject: "Review swarm 1 merge", description: "R1..." })       → ID 5
# TaskUpdate({ taskId: "5", addBlockedBy: ["1", "2", "3", "4"] })
```

**Agent dispatch:**
```bash
# Claude Code agents in worktrees (Tasks 13, 14)
# Agent({ prompt: "...", isolation: "worktree" })

# Pi agents for focused single-file tasks (Tasks 15, 16)
pwsh .claude/skills/pi-dispatch/scripts/pi-bridge.ps1 \
  -TeamName "herdflow" \
  -AgentName "pi-alerts" \
  -Prompt "Implement agent/alerts/rules.py following Task 15 in the plan..." \
  -WorkDir ".worktrees/alerts" \
  -TaskId "2"

pwsh .claude/skills/pi-dispatch/scripts/pi-bridge.ps1 \
  -TeamName "herdflow" \
  -AgentName "pi-sampler" \
  -Prompt "Implement agent/reasoning/sampler.py following Task 16 in the plan..." \
  -WorkDir ".worktrees/sampler" \
  -TaskId "3"
```

**Merge sequence (after all 3 complete):**
```bash
git merge agent/detector     # Task 13
git merge agent/alerts        # Task 15
git merge agent/sampler       # Task 16
# Now Task 14 can start (depends on 13+15)
# After Task 14 completes:
git merge agent/tracker-sgb   # Task 14
uv run pytest tests/ -v       # Full regression check
git worktree remove .worktrees/detector
git worktree remove .worktrees/alerts
git worktree remove .worktrees/sampler
```

**Reviewer checkpoint R1:**
```bash
# Dispatch reviewer agent (read-only)
# Agent({ subagent_type: "general-purpose",
#         prompt: "Review the merged perception + alerts code against the spec.
#                  Use the reviewer checklist from .claude/agents/reviewer.md.
#                  Check: type hints, no bare except, async properly awaited,
#                  Pydantic models for data schemas, scene graph changes backward-compatible." })
```

### Swarm 2: Polish + Deploy (after Phase 6)

**Setup commands:**
```bash
git worktree add .worktrees/frontend-polish -b agent/frontend-polish
git worktree add .worktrees/deploy -b agent/deploy
```

**Agent dispatch:**
- Task 18 (frontend polish): Claude Code in worktree
- Task 19 (deploy): Claude Code in worktree
- Task 21 (README + video download): Pi agent

**Merge + Review R2 follows same pattern as Swarm 1.**

### Explorer Agent Usage

Before Swarm 1 starts, dispatch an explorer agent to verify contract alignment:
```bash
# Agent({ subagent_type: "Explore", model: "haiku",
#         prompt: "Scan agent/models.py and tests/conftest.py.
#                  Verify all model fields match between TrackedEntity and TrackedEntityModel.
#                  Check that FRONTEND_REQUIRED_FIELDS matches the actual model fields.
#                  Report any mismatches with file:line references." })
```

## Swarm Agent Assignment

| Task | Agent Type | Worktree | Why |
|------|-----------|----------|-----|
| Tasks 1-5 (foundation) | Single Claude Code | main | Sequential, fast |
| Tasks 6-9 (voice agent) | Single Claude Code | main | Needs Gemini API testing |
| Tasks 10-12 (frontend) | Claude Code | main | React + LiveKit SDK |
| **Swarm 1 (parallel):** | | | |
| Task 13 (detector) | Claude Code | `.worktrees/detector` | GPU-specific, multi-file |
| Task 15 (alerts) | Pi via pi-bridge.ps1 | `.worktrees/alerts` | Single file, pattern-based |
| Task 16 (sampler) | Pi via pi-bridge.ps1 | `.worktrees/sampler` | Single file, focused |
| Task 14 (tracker + SGB) | Claude Code | `.worktrees/tracker-sgb` | Depends on 13+15, multi-file |
| Task R1 (review) | Claude Code (reviewer persona) | main | Read-only review after merge |
| Task 17 (wire pipeline) | Claude Code | main | Integration, needs full context |
| Task 17b (SQLite history) | Claude Code | main | Replaces mock with real DB |
| **Swarm 2 (parallel):** | | | |
| Task 18 (frontend polish) | Claude Code | `.worktrees/frontend-polish` | CSS/SVG, independent |
| Task 19 (deploy) | Claude Code | `.worktrees/deploy` | Docker + GCP |
| Task 21 (README + video dl) | Pi via pi-bridge.ps1 | main | Single files, mechanical |
| Task R2 (review) | Claude Code (reviewer persona) | main | Read-only review after merge |
| Task 20 (demo) | Human | — | Recording |
