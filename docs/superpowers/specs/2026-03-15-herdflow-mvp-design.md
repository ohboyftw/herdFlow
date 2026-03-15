# HerdFlow MVP Design Specification

**Version:** 1.1 (post-review)
**Date:** 2026-03-15
**Target:** Gemini Live Agent Challenge — "Live Agents" category
**Deadline:** 2026-03-16, 5:00 PM PDT

## 1. Overview

HerdFlow is a real-time AI veterinary co-pilot that monitors livestock through camera feeds, detects anomalies, tracks individual animals, and communicates findings through natural voice conversation. It fuses RF-DETR (object detection), Gemini Live API (voice reasoning), and LiveKit (WebRTC transport).

HerdFlow is an instance of the **VisionFlow** pattern — a domain-agnostic three-tier architecture (Spatial Perception → Multimodal Reasoning → Voice Communication) that can be reconfigured for any real-time visual monitoring domain.

## 2. Build Strategy

**Approach: Vertical Slice First**

Build a thin end-to-end path (mock scene graph → Gemini voice → basic React UI), then thicken each layer with real implementations. Demoable at every stage.

### Build Phases

| Phase | What | Demoable After? |
|-------|------|-----------------|
| 1 | Project scaffold + shared contracts + smoke tests | No (infra) |
| 2 | Mock scene graph + LiveKit dev server + Gemini Live voice agent | **Yes** — voice agent talks about fake herd |
| 3 | Basic React frontend (video + voice + alerts) | **Yes** — full UI with mock data |
| 4 | RF-DETR detection pipeline (local 4060) | **Yes** — real detections visible |
| 5 | ByteTrack integration + real scene graph builder | **Yes** — persistent animal IDs |
| 6 | Adaptive sampling + alert rule engine | **Yes** — proactive voice alerts |
| 7 | Frontend polish (overlays, dashboard, Tailwind) | **Yes** — demo-ready UI |
| 8 | Docker + LiveKit Cloud + GCP deployment | **Yes** — deployed |
| 9 | Demo video recording | **Submission** |

### Swarm Parallelism Opportunities

- After Phase 3: RF-DETR (agent 1) + frontend polish (agent 2) + alert rules (agent 3)
- After Phase 6: deployment (agent 1) + frontend polish (agent 2)

### Infrastructure Progression

1. **Development:** Local LiveKit dev server (`livekit-server --dev`)
2. **Staging:** LiveKit Cloud (free tier)
3. **Production:** Self-hosted LiveKit on GCE (if time permits)

### Hardware Available

- Local NVIDIA GeForce 4060 (development + testing)
- Google Colab GPU access (backup)
- Google Cloud account (needs project provisioning)
- Gemini API key available as PowerShell env var

## 3. Project Structure

```
herdflow/
├── agent/
│   ├── __init__.py
│   ├── main.py                 # LiveKit Agent entrypoint
│   ├── config.py               # Pydantic Settings from .env
│   ├── models.py               # ALL shared Pydantic contracts (single source of truth)
│   ├── herdflow_agent.py       # Agent class with persona
│   ├── perception/
│   │   ├── __init__.py
│   │   ├── detector.py         # RF-DETR wrapper
│   │   ├── tracker.py          # ByteTrack via supervision
│   │   └── scene_graph.py      # Scene graph builder
│   ├── reasoning/
│   │   ├── __init__.py
│   │   ├── sampler.py          # AdaptiveFrameSampler
│   │   ├── tools.py            # Gemini tool definitions
│   │   └── prompts.py          # System prompt templates
│   ├── alerts/
│   │   ├── __init__.py
│   │   └── rules.py            # Alert rule engine
│   └── storage/
│       ├── __init__.py
│       └── history.py          # SQLite tracking history
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── types/
│   │   │   └── generated.ts    # Auto-generated from Python models
│   │   ├── components/
│   │   │   ├── VideoPanel.tsx   # Annotated video with SVG overlay
│   │   │   ├── VoicePanel.tsx   # Voice UI + transcript
│   │   │   ├── AlertPanel.tsx   # Alert cards with severity
│   │   │   └── Dashboard.tsx    # Herd summary metrics
│   │   └── hooks/
│   │       ├── useSceneGraph.ts # Scene graph data channel subscription
│   │       └── useAlerts.ts     # Alert data channel subscription
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tailwind.config.ts
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── test_contracts.py       # Round-trip + boundary edge cases + property-based
│   ├── test_handshakes.py      # Module pair handshakes (9 boundaries)
│   ├── test_golden_path.py     # End-to-end traces
│   ├── test_detector.py
│   ├── test_tracker.py
│   ├── test_scene_graph.py
│   ├── test_sampler.py
│   └── test_alerts.py
├── scripts/
│   ├── generate_types.py       # Pydantic → TypeScript
│   └── download_video.py       # Fetch demo cattle footage
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── cloudbuild.yaml
├── .env.example
└── README.md
```

## 4. Data Contracts

All contracts live in `agent/models.py` — the single source of truth. TypeScript types are auto-generated from it via `scripts/generate_types.py`.

### Contract Hierarchy

```
models.py
├── Detection              # Detector output (in-process, uses numpy)
├── TrackState (enum)       # ACTIVE | TENTATIVE | DELETED
├── TrackedEntity           # Tracker output (in-process, has numpy fields)
├── Severity (enum)         # INFO | WARNING | ALERT | CRITICAL
├── Alert                   # Pydantic — crosses serialization boundary
├── ZoneOccupancy           # Pydantic
├── HerdSummary             # Pydantic
├── TrackedEntityModel      # Pydantic — serializable version of TrackedEntity
├── ZoneCrossing            # Pydantic
├── BehaviorChange          # Pydantic
├── SceneDelta              # Pydantic — drives adaptive sampling
├── SceneGraph              # Pydantic — THE central contract
├── SceneGraphSnapshot      # Pydantic — slim history snapshot for GeminiContext
├── OverlayBox              # Pydantic — slim bbox for 30 FPS overlay channel
├── OverlayData             # Pydantic — sent to frontend for SVG rendering
├── GeminiContext           # Pydantic — what gets injected into Gemini session
├── BehaviorRecord          # Pydantic — Gemini tool response
├── EntityHistory           # Pydantic — Gemini tool response
├── HerdStats               # Pydantic — Gemini tool response
├── DescriptionMatch        # Pydantic — Gemini tool response
├── DescriptionSearchResult # Pydantic — Gemini tool response
├── ZoneVisit               # Pydantic — Gemini tool response
└── ZoneHistory             # Pydantic — Gemini tool response
```

### Design Decisions

1. **Two entity representations:** `TrackedEntity` (dataclass with numpy arrays for mask/embedding) for in-process perception. `TrackedEntityModel` (Pydantic) for serialization across boundaries 7-9. SceneGraphBuilder converts between them.

2. **Datetime handling:** All `datetime` fields use UTC with timezone info enforced via Pydantic validator. Serialized as ISO 8601 strings. TypeScript receives strings, parses with `new Date()`.

3. **bbox format:** `list[int]` not `tuple` in Pydantic models — tuples serialize to JSON arrays but Pydantic's JSON schema marks them as fixed-length arrays which some validators reject. Semantically `[x1, y1, x2, y2]`.

4. **GeminiContext:** Wraps what gets injected into Gemini's running context on each adaptive sample — `scene_graph` (current), `recent_alerts` (last 5), `history_snapshots` (last 10).

5. **Frontend consumer contract:** Explicitly declared `FRONTEND_REQUIRED_FIELDS` dict specifying which fields the frontend actually reads. Consumer-driven contract testing validates the backend never drops these.

6. **Type generation pipeline:** `scripts/generate_types.py` reads `agent/models.py` → writes `frontend/src/types/generated.ts`. CI fails if generated types are out of date.

### Module Boundary Map (9 Edges)

| # | Producer → Consumer | Data Contract | Serialization |
|---|---------------------|---------------|---------------|
| 1 | VideoFrame → Detector | `np.ndarray` (H,W,3 uint8) | In-process |
| 2 | Detector → Tracker | `list[Detection]` | In-process |
| 3 | Tracker → SceneGraphBuilder | `list[TrackedEntity]` | In-process |
| 4 | SceneGraphBuilder → AlertRuleEngine | `SceneGraph` | In-process |
| 5 | AlertRuleEngine → SceneGraphBuilder | `list[Alert]` | In-process |
| 6 | SceneGraphBuilder → AdaptiveFrameSampler | `SceneGraph + SceneDelta` | In-process |
| 7 | AdaptiveFrameSampler → Gemini Live API | `JSON string + video frame` | JSON over WebSocket |
| 8 | Agent → LiveKit Data Channels | `SceneGraph / Alert / Overlay JSON` | JSON over WebRTC |
| 9 | LiveKit Data Channels → React Components | `SceneGraph / Alert / Overlay` | JSON → TypeScript types |

Boundaries 7, 8, 9 are critical serialization boundaries where contract drift occurs.

### Python Contract Definitions

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, field_validator


# ── Boundary 2: Detector → Tracker ──

@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    mask: Optional[np.ndarray] = None
    embedding: Optional[np.ndarray] = None


# ── Boundary 3: Tracker → SceneGraphBuilder ──

class TrackState(str, Enum):
    ACTIVE = "active"
    TENTATIVE = "tentative"
    DELETED = "deleted"

@dataclass
class TrackedEntity:
    track_id: str
    class_name: str
    confidence: float              # propagated from Detection
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float]
    velocity: tuple[float, float]  # pixels/second (normalized to 1280x720)
    behavior: str
    behavior_duration_s: float
    zone: str
    zone_dwell_s: float            # seconds in current zone (for dwell-time gating)
    last_feed_visit_s: float
    isolation_score: float
    bbox_aspect_ratio: float       # width/height — lying cows typically > 1.5
    flags: list[str]
    first_seen: datetime
    last_seen: datetime
    age_frames: int
    state: TrackState


# ── Boundary 5: Alert output ──

class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"

class Alert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    severity: Severity
    entity_track_id: str
    description: str
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None

    @property
    def key(self) -> str:
        """Dedup key: same alert type + same entity = same alert."""
        return f"{self.type}:{self.entity_track_id}"

    @field_validator("timestamp", "resolved_at", mode="before")
    @classmethod
    def ensure_utc(cls, v):
        if v is not None and isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


# ── Boundary 4+6: SceneGraph ──

class ZoneOccupancy(BaseModel):
    occupancy: int

class HerdSummary(BaseModel):
    total_visible: int
    standing: int
    lying: int
    walking: int
    feeding: int
    drinking: int

class TrackedEntityModel(BaseModel):
    track_id: str
    class_name: str
    confidence: float
    bbox: list[int]
    centroid: list[float]
    velocity: list[float]
    behavior: str
    behavior_duration_s: float
    zone: str
    last_feed_visit_s: float
    isolation_score: float
    flags: list[str]

class SceneGraph(BaseModel):
    timestamp: datetime
    frame_id: int
    herd_summary: HerdSummary
    tracked_entities: list[TrackedEntityModel]
    zones: dict[str, ZoneOccupancy]
    active_alerts: list[Alert]

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


# ── Boundary 6: SceneDelta ──

class ZoneCrossing(BaseModel):
    track_id: str
    from_zone: str
    to_zone: str

class BehaviorChange(BaseModel):
    track_id: str
    from_behavior: str
    to_behavior: str

class SceneDelta(BaseModel):
    new_entities: list[str]
    exited_entities: list[str]
    zone_crossings: list[ZoneCrossing]
    new_alerts: list[Alert]
    velocity_spikes: list[str]
    behavior_changes: list[BehaviorChange]

    @property
    def is_significant(self) -> bool:
        return bool(
            self.new_entities or self.exited_entities
            or self.zone_crossings or self.new_alerts
            or self.velocity_spikes or self.behavior_changes
        )


# ── Boundary 7: Gemini context injection ──

class SceneGraphSnapshot(BaseModel):
    """Slim version of SceneGraph for history context. Keeps size manageable."""
    timestamp: datetime
    frame_id: int
    herd_summary: HerdSummary
    entity_count: int
    alert_types: list[str]  # just the type strings, not full Alert objects

class GeminiContext(BaseModel):
    scene_graph: SceneGraph
    recent_alerts: list[Alert]              # last 5
    history_snapshots: list[SceneGraphSnapshot]  # last 10, slim

    def to_prompt_injection(self) -> str:
        return self.model_dump_json(indent=2)


# ── Boundary 8-9: LiveKit data channels ──
# No wrapper type. Publish typed payloads directly to named channels:
#   "scene_graph" channel → SceneGraph
#   "alerts" channel → Alert
#   "overlay" channel → OverlayData

class OverlayBox(BaseModel):
    """Slim model for 30 FPS overlay rendering. Only fields needed for SVG."""
    track_id: str
    bbox: list[int]
    behavior: str
    flags: list[str]

class OverlayData(BaseModel):
    frame_id: int
    boxes: list[OverlayBox]


# ── Gemini tool response models ──

class BehaviorRecord(BaseModel):
    behavior: str
    zone: str
    duration_s: float
    started_at: datetime

class EntityHistory(BaseModel):
    track_id: str
    records: list[BehaviorRecord]
    current_behavior: str
    current_duration_s: float

class HerdStats(BaseModel):
    period_minutes: int
    total_animals: int
    fed_in_period: int
    not_fed: list[str]
    avg_lying_duration_s: float
    alerts_fired: int
    behavior_breakdown: dict[str, int]

class DescriptionMatch(BaseModel):
    track_id: str
    confidence: float
    reason: str
    current_behavior: str
    zone: str
    centroid: list[float]

class DescriptionSearchResult(BaseModel):
    matches: list[DescriptionMatch]

class ZoneVisit(BaseModel):
    track_id: str
    entered_at: datetime
    duration_s: float

class ZoneHistory(BaseModel):
    zone: str
    period_minutes: int
    visits: list[ZoneVisit]
    current_occupancy: int
    peak_occupancy: int
    animals_not_visited: list[str]


# ── Frontend consumer contract ──

FRONTEND_REQUIRED_FIELDS = {
    "tracked_entities": [
        "track_id", "bbox", "centroid", "behavior",
        "behavior_duration_s", "flags", "confidence", "zone",
    ],
    "active_alerts": [
        "id", "type", "severity", "entity_track_id", "description",
    ],
    "herd_summary": [
        "total_visible", "standing", "lying", "walking", "feeding", "drinking",
    ],
    "zones": None,  # full dict required
}
```

### TypeScript Mirror Types (Auto-Generated)

```typescript
// frontend/src/types/generated.ts
// AUTO-GENERATED from agent/models.py — do not edit manually

export interface SceneGraph {
  timestamp: string;
  frame_id: number;
  herd_summary: HerdSummary;
  tracked_entities: TrackedEntity[];
  zones: Record<string, ZoneOccupancy>;
  active_alerts: Alert[];
}

export interface HerdSummary {
  total_visible: number;
  standing: number;
  lying: number;
  walking: number;
  feeding: number;
  drinking: number;
}

export interface TrackedEntity {
  track_id: string;
  class_name: string;
  confidence: number;
  bbox: number[];
  centroid: number[];
  velocity: number[];
  behavior: string;
  behavior_duration_s: number;
  zone: string;
  last_feed_visit_s: number;
  isolation_score: number;
  flags: string[];
}

export interface ZoneOccupancy {
  occupancy: number;
}

export type Severity = 'info' | 'warning' | 'alert' | 'critical';

export interface Alert {
  id: string;
  type: string;
  severity: Severity;
  entity_track_id: string;
  description: string;
  timestamp: string;
  resolved: boolean;
  resolved_at: string | null;
}

export interface OverlayBox {
  track_id: string;
  bbox: number[];
  behavior: string;
  flags: string[];
}

export interface OverlayData {
  frame_id: number;
  boxes: OverlayBox[];
}
```

## 5. Perception Pipeline (Tier 1)

### Detector (`agent/perception/detector.py`)

- Wraps RF-DETR via the `rfdetr` Python package (Roboflow, pip-installable)
- Loads model once at process start
- Model: RF-DETR Small (17.3M params, 54.2 mAP, ~4ms on RTX 4060)
- Filters by class (cow/cattle) only — passes all confidence levels to tracker
- Display threshold (0.5) applied separately in overlay rendering
- Detection threshold (0.3) matches ByteTrack's `track_activation_threshold` so cascaded association works correctly
- **GIL safety:** Inference runs in `ThreadPoolExecutor` via `asyncio.run_in_executor()` to avoid blocking the event loop
- Mock phase: `MockDetector` returns hardcoded detections that move over time

```python
class RFDETRDetector:
    def __init__(self, model: str = "rf-detr-small",
                 detection_threshold: float = 0.3,  # matches ByteTrack
                 display_threshold: float = 0.5,    # for overlay only
                 device: str = "cuda"):
        self._executor = ThreadPoolExecutor(max_workers=1)
        ...

    async def detect(self, frame: np.ndarray) -> list[Detection]:
        """Run inference in executor to avoid blocking asyncio event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._detect_sync, frame)

    def _detect_sync(self, frame: np.ndarray) -> list[Detection]:
        """Synchronous inference — runs in thread pool."""
        ...
```

### Tracker (`agent/perception/tracker.py`)

**ByteTrack via `supervision`** — not KV-Tracker.

> **Correction from original spec:** The original specification referenced "KV-Tracker" as the multi-object tracking component. Investigation revealed that KV-Tracker (CVPR 2026, arXiv:2512.22581) is a 6-DoF camera pose estimation system for 3D reconstruction — it does not perform multi-object tracking, data association, or identity assignment across frames. The reference was a hallucination in the original spec documents.

ByteTrack (ECCV 2022) is the correct tool for this use case:
- 80.3 MOTA on MOT17, 30 FPS
- Two-stage cascaded association recovers occluded objects via low-confidence detections
- Proven on cattle tracking in published livestock CV research
- pip-installable via `supervision` with direct RF-DETR integration

```python
import supervision as sv

class Tracker:
    def __init__(self, max_age: int = 300):
        self._tracker = sv.ByteTrack(
            track_activation_threshold=0.3,
            lost_track_buffer=max_age,
        )

    def update(self, detections: list[Detection],
               frame_id: int) -> list[TrackedEntity]:
        sv_detections = self._to_sv_detections(detections)
        tracked = self._tracker.update_with_detections(sv_detections)
        return self._to_tracked_entities(tracked, frame_id)
```

### SceneGraphBuilder (`agent/perception/scene_graph.py`)

Orchestrates detector + tracker + alert engine per frame:
- Maintains zone config (rectangular regions as frame-relative percentages)
- Classifies behavior via explicit priority chain (evaluated top-to-bottom, first match wins):
  1. `velocity > 0.1 px/s` → **"walking"** (motion overrides everything)
  2. `zone == "feed_area" AND zone_dwell_s >= 10` → **"feeding"** (dwell-time gated)
  3. `zone == "water_trough" AND zone_dwell_s >= 10` → **"drinking"** (dwell-time gated)
  4. `velocity < 0.1 AND bbox_aspect_ratio > 1.5` → **"lying"** (wide bbox = recumbent)
  5. `velocity < 0.1` → **"standing"** (default stationary)
- Velocity units: pixels/second normalized to 1280x720 reference frame
- Zone dwell-time gating (10s min) prevents false feeding/drinking from walk-throughs
- Bbox aspect ratio (width/height > 1.5) distinguishes lying from standing without pose estimation
- Computes SceneDelta by diffing current vs previous SceneGraph
- Converts `TrackedEntity` (dataclass) → `TrackedEntityModel` (Pydantic) at serialization boundary

```python
class SceneGraphBuilder:
    def __init__(self, detector, tracker, zone_config, alert_engine):
        ...
    async def process_frame(self, frame: np.ndarray,
                            frame_id: int) -> SceneGraph:
        detections = await self.detector.detect(frame)
        tracked = self.tracker.update(detections, frame_id)
        behaviors = self._classify_behaviors(tracked)
        alerts = self.alert_engine.evaluate(tracked)
        return self._build_graph(tracked, behaviors, alerts, frame_id)

    def get_delta(self, prev: SceneGraph, curr: SceneGraph) -> SceneDelta:
        ...
```

### Zone Configuration

```python
ZONE_CONFIG = {
    "feed_area":     {"x1": 0.0, "y1": 0.0, "x2": 0.3, "y2": 0.5},
    "water_trough":  {"x1": 0.7, "y1": 0.0, "x2": 1.0, "y2": 0.3},
    "rest_area":     {"x1": 0.3, "y1": 0.5, "x2": 1.0, "y2": 1.0},
}
```

## 6. Reasoning Engine (Tier 2)

### Gemini Live API Integration

Uses LiveKit Agents `google` plugin — not raw Gemini SDK:

```python
from livekit.plugins import google

llm = google.beta.realtime.RealtimeModel(
    model="gemini-2.5-flash-native-audio-preview",
    proactivity=True,
    enable_affective_dialog=True,
    thinking_config={"thinking_budget": 1024},
)
```

**Context injection pattern:**
1. SceneGraphBuilder produces SceneGraph every frame (60 FPS)
2. AdaptiveFrameSampler decides when to forward frame + context to Gemini (~0-2 FPS)
3. On trigger: `session.update_context(scene_graph=sg.model_dump_json())`

**Fallback:** If `proactivity=True` doesn't work as documented (preview API), poll alerts on a timer and use `session.generate_reply()` to trigger speech manually on critical alerts.

### System Prompt (`agent/reasoning/prompts.py`)

Three layers:
- **Static (once):** Agent persona, cattle behavior baselines, alert escalation rules
- **Dynamic (event-driven):** `{scene_graph_json}` replaced on each adaptive sample
- **History (rolling):** Last 5 alerts + last 10 scene graphs via GeminiContext

### Gemini Tool Definitions (`agent/reasoning/tools.py`)

| Tool | Input | Output | Example Query |
|------|-------|--------|---------------|
| `search_entity_history` | `track_id, minutes` | `EntityHistory` | "How long has COW-003 been lying?" |
| `get_herd_stats` | `minutes` | `HerdStats` | "How many cows fed in the last hour?" |
| `find_by_description` | `description` | `DescriptionSearchResult` | "The brown cow near the fence" |
| `get_zone_history` | `zone, minutes` | `ZoneHistory` | "Was the water trough busy this morning?" |

### Mock Tool Responses (Phase 2)

Pre-built scenario data designed to be veterinarily plausible and set up demo conversations. COW-003 is the "problem cow" (prolonged lying + missed feeding + high isolation). COW-007 also hasn't fed.

```python
class MockTrackingHistory:
    """Phase 2 stand-in. Same interface as real SQLite history."""

    async def search_entity_history(self, track_id: str, minutes: int) -> EntityHistory:
        return self._scenarios.get(track_id, self._default_history)

    async def get_herd_stats(self, minutes: int) -> HerdStats:
        return self._herd_stats

    async def find_by_description(self, description: str) -> DescriptionSearchResult:
        return self._description_results

    async def get_zone_history(self, zone: str, minutes: int) -> ZoneHistory:
        return self._zone_histories.get(zone, self._default_zone)
```

#### Mock Response: `search_entity_history("COW-003", 60)`

```json
{
    "track_id": "COW-003",
    "records": [
        {"behavior": "walking", "zone": "feed_area", "duration_s": 600,
         "started_at": "2026-03-15T08:00:00Z"},
        {"behavior": "feeding", "zone": "feed_area", "duration_s": 1200,
         "started_at": "2026-03-15T08:10:00Z"},
        {"behavior": "walking", "zone": "rest_area", "duration_s": 300,
         "started_at": "2026-03-15T08:30:00Z"},
        {"behavior": "lying", "zone": "rest_area", "duration_s": 4320,
         "started_at": "2026-03-15T08:35:00Z"}
    ],
    "current_behavior": "lying",
    "current_duration_s": 4320
}
```

#### Mock Response: `get_herd_stats(60)`

```json
{
    "period_minutes": 60,
    "total_animals": 8,
    "fed_in_period": 6,
    "not_fed": ["COW-003", "COW-007"],
    "avg_lying_duration_s": 1800,
    "alerts_fired": 2,
    "behavior_breakdown": {
        "standing": 3, "lying": 2, "walking": 1, "feeding": 1, "drinking": 1
    }
}
```

#### Mock Response: `find_by_description("the brown cow near the fence")`

```json
{
    "matches": [
        {
            "track_id": "COW-005",
            "confidence": 0.72,
            "reason": "Located near zone boundary (rest_area edge), closest to fence region",
            "current_behavior": "standing",
            "zone": "rest_area",
            "centroid": [0.85, 0.45]
        }
    ]
}
```

#### Mock Response: `get_zone_history("water_trough", 120)`

```json
{
    "zone": "water_trough",
    "period_minutes": 120,
    "visits": [
        {"track_id": "COW-001", "entered_at": "2026-03-15T07:15:00Z", "duration_s": 120},
        {"track_id": "COW-004", "entered_at": "2026-03-15T07:30:00Z", "duration_s": 90},
        {"track_id": "COW-002", "entered_at": "2026-03-15T08:00:00Z", "duration_s": 150},
        {"track_id": "COW-006", "entered_at": "2026-03-15T08:45:00Z", "duration_s": 60}
    ],
    "current_occupancy": 1,
    "peak_occupancy": 2,
    "animals_not_visited": ["COW-003", "COW-007", "COW-008"]
}
```

### AdaptiveFrameSampler (`agent/reasoning/sampler.py`)

**Event-driven** — consumes from `asyncio.Queue` fed by the perception loop (no polling):

```python
class AdaptiveFrameSampler:
    def __init__(self, max_fps: float = 2.0, min_interval_ms: int = 200):
        self.max_fps = max_fps
        self.min_interval_ms = min_interval_ms

    async def run(self, session: AgentSession, scene_queue: asyncio.Queue):
        """Consume scene graphs from queue, inject context when significant."""
        last_send_time = 0

        while True:
            sg, delta = await scene_queue.get()  # blocks until new data
            now = time.monotonic()
            elapsed_ms = (now - last_send_time) * 1000
            user_speaking = session.vad.is_speaking

            should_send = (
                user_speaking                         # ALWAYS on farmer query
                or (
                    delta.is_significant              # meaningful change
                    and elapsed_ms >= self.min_interval_ms
                    and elapsed_ms >= 1000 / self.max_fps
                )
            )

            if should_send:
                ctx = GeminiContext(
                    scene_graph=sg,
                    recent_alerts=sg.active_alerts[:5],
                    history_snapshots=[],  # populated by history manager
                )
                await session.update_context(
                    scene_graph=ctx.to_prompt_injection()
                )
                last_send_time = now
```

Note: The sampler controls **text context injection** only. Gemini receives the continuous video track via LiveKit's native multimodal session.

Trigger priority:
1. **CRITICAL:** `user_query`, `alert_fired` — override rate limits
2. **HIGH:** `new_entity`, `zone_crossing`
3. **MEDIUM:** `velocity_spike`, `behavior_change`, `entity_exit`

Quiet suppression: no significant deltas → queue stays empty → zero context injections → zero token cost.

## 7. Alert Rule Engine

### Rule Definitions

| Rule | Condition | Severity | Default Threshold | Demo Trigger |
|------|-----------|----------|-------------------|--------------|
| `prolonged_lying` | behavior="lying" AND duration > threshold | WARNING | 3600s (1hr) | COW-003 at 4320s |
| `isolation` | isolation_score > threshold | WARNING | 0.7 | COW-003 at 0.82 |
| `missed_feeding` | last_feed_visit > threshold | ALERT | 14400s (4hr) | COW-003 at 18000s |
| `velocity_anomaly` | velocity > 2x rolling 5-min avg | INFO | 2.0x | Random spike |
| `herd_dispersal` | std_dev of centroids > threshold | INFO | Configurable | Not in demo |
| `limping_suspect` | gait_asymmetry > threshold | WARNING | 0.6 | Not in demo |

### Engine Design

```python
class AlertRuleEngine:
    def __init__(self, config: Settings):
        self._rules: list[AlertRule] = [
            ProlongedLyingRule(threshold_s=config.ALERT_PROLONGED_LYING_S),
            IsolationRule(threshold=config.ALERT_ISOLATION_THRESHOLD),
            MissedFeedingRule(threshold_s=config.ALERT_MISSED_FEEDING_S),
            VelocityAnomalyRule(multiplier=2.0),
        ]
        self._active: dict[str, Alert] = {}
        self._cooldowns: dict[str, float] = {}

    def evaluate(self, entities: list[TrackedEntity]) -> list[Alert]:
        new_alerts = []
        for rule in self._rules:
            for entity in entities:
                fired = rule.check(entity)
                if fired and not self._in_cooldown(fired):
                    new_alerts.append(fired)
                    self._active[fired.key] = fired
                    self._cooldowns[fired.key] = time.monotonic()
        self._resolve_cleared(entities)
        return new_alerts
```

Each rule implements the `AlertRule` protocol:

```python
class AlertRule(Protocol):
    def check(self, entity: TrackedEntity) -> Optional[Alert]: ...
```

### Alert Lifecycle

1. **Fire:** `rule.check()` returns Alert → added to `_active` + `_cooldowns`
2. **Dedup:** Same type+entity suppressed for 5 minutes via cooldown
3. **Inject:** Alert appears in `SceneGraph.active_alerts` → Gemini sees it
4. **Proactive speech:** Gemini reads alert, initiates voice notification per escalation rules
5. **Resolve:** Condition clears → `resolved=True`, removed from active list

Rules are pure functions of current entity state. No database queries. Temporal state (behavior_duration_s, last_feed_visit_s) is carried on TrackedEntity.

## 8. Communication Layer (Tier 3)

### LiveKit Agent Entrypoint (`agent/main.py`)

```python
@server.on_process_started
async def on_process_started(proc):
    proc.userdata["detector"] = RFDETRDetector(...)
    proc.userdata["tracker"] = Tracker(...)
    proc.userdata["alert_engine"] = AlertRuleEngine(settings)

@server.rtc_session()
async def entrypoint(ctx):
    scene_builder = SceneGraphBuilder(detector, tracker, zone_config, alert_engine)
    sampler = AdaptiveFrameSampler(max_fps=2.0, min_interval_ms=200)
    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(...),
        vad=silero.VAD.load(),
    )
    await session.start(room=ctx.room, agent=HerdFlowAgent())

    # Inter-task communication via asyncio queues
    scene_queue = asyncio.Queue(maxsize=1)  # latest-value-wins for sampler
    overlay_queue = asyncio.Queue(maxsize=1) # latest-value-wins for publisher

    asyncio.create_task(perception_loop(ctx.room, scene_builder, scene_queue, overlay_queue))
    asyncio.create_task(sampler.run(session, scene_queue))
    asyncio.create_task(data_channel_publisher(ctx.room, overlay_queue))
```

### HerdFlowAgent Class (`agent/herdflow_agent.py`)

```python
class HerdFlowAgent(Agent):
    """LiveKit Agent with HerdFlow persona and Gemini tools."""

    def __init__(self):
        super().__init__(
            instructions=SYSTEM_PROMPT,
            tools=herd_tools,  # search_entity_history, get_herd_stats, etc.
        )
```

The agent class is thin — persona and behavior are defined by the system prompt (Section 6). Tools are defined in `reasoning/tools.py`. The `AgentSession` handles voice I/O, VAD, and Gemini communication.

### Perception Loop (`agent/main.py`)

```python
async def perception_loop(
    room: Room,
    scene_builder: SceneGraphBuilder,
    scene_queue: asyncio.Queue,
    overlay_queue: asyncio.Queue,
):
    """Process every video frame through RF-DETR + ByteTrack + SceneGraph.

    Reads frames from the LiveKit video track at camera FPS.
    Publishes SceneGraph to scene_queue (for sampler) and
    OverlayData to overlay_queue (for data channel publisher).
    Both queues are maxsize=1 (latest-value-wins).
    """
    video_stream = VideoStream(room=room, track=room.video_tracks[0])
    frame_id = 0
    prev_graph = None

    async for frame_event in video_stream:
        frame = frame_event.frame.to_ndarray(format="bgr24")
        frame_id += 1

        sg = await scene_builder.process_frame(frame, frame_id)
        delta = scene_builder.get_delta(prev_graph, sg)

        # Latest-value-wins: drain old value, put new one
        try:
            scene_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        await scene_queue.put((sg, delta))

        overlay = OverlayData(
            frame_id=frame_id,
            boxes=[OverlayBox(track_id=e.track_id, bbox=e.bbox,
                              behavior=e.behavior, flags=e.flags)
                   for e in sg.tracked_entities],
        )
        try:
            overlay_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        await overlay_queue.put(overlay)

        prev_graph = sg
```

### Data Channel Publisher (`agent/main.py`)

```python
async def data_channel_publisher(
    room: Room,
    overlay_queue: asyncio.Queue,
):
    """Publish overlay data to frontend via LiveKit data channel."""
    while True:
        overlay = await overlay_queue.get()
        await room.local_participant.publish_data(
            overlay.model_dump_json().encode(),
            topic="overlay",
        )
```

### Gemini Video Input Clarification

Gemini receives the **continuous video track** via the LiveKit Agents google plugin's native multimodal session — not manually pushed frames. The `AdaptiveFrameSampler` controls only **text context injection** frequency (scene graph JSON), not video frame delivery. Gemini handles its own internal frame sampling from the continuous video stream.

This means:
- Gemini always "sees" the video (plugin manages the stream)
- The sampler controls how often structured scene graph data is injected as text context
- Rate limiting applies to context injection only, keeping token costs manageable

### Data Channel Protocol

| Channel | Payload | Frequency | Consumer |
|---------|---------|-----------|----------|
| `scene_graph` | `SceneGraph` JSON | On delta events | `useSceneGraph` hook |
| `alerts` | `Alert` JSON | On new alert | `useAlerts` hook |
| `overlay` | `OverlayData` JSON | ~30 FPS | `VideoPanel` SVG layer |

`overlay` is separate from `scene_graph` because bounding boxes need detection-framerate updates (smooth), while full scene graphs update only on significant deltas.

### Frontend Architecture

React + Vite + Tailwind CSS. 70/30 split-panel layout:

```
┌─────────────────────────────────────┬──────────────────┐
│                                     │   VoicePanel     │
│          VideoPanel                 │   - Transcript   │
│   - LiveKit VideoRenderer           │   - Waveform     │
│   - SVG overlay (bboxes, IDs,       │   - Mic toggle   │
│     zone boundaries)                │                  │
│   - Alert pulse indicators          ├──────────────────┤
│                                     │   AlertPanel     │
│                                     │   - Severity     │
│                                     │   - Click to ask │
├─────────────────────────────────────┼──────────────────┤
│                                     │   Dashboard      │
│                                     │   - Herd count   │
│                                     │   - Behaviors    │
│                                     │   - Active alerts│
└─────────────────────────────────────┴──────────────────┘
```

### SVG Overlay Rendering

- Bounding boxes colored by behavior: `stroke-emerald-400` (active), `stroke-blue-400` (resting), `stroke-amber-400` (alert flag)
- Track ID labels above each box
- Zone boundaries as dashed rectangles
- Pulsing red circle on animals with active alerts

### Frontend Hooks

```typescript
function useSceneGraph(room: Room): SceneGraph | null
// Subscribes to "scene_graph" data channel, validates against generated types

function useAlerts(room: Room): Alert[]
// Subscribes to "alerts" data channel, maintains rolling list, auto-dismisses resolved
```

## 9. Deployment & Demo

### Local Development Stack

```yaml
# docker-compose.yml (dev)
services:
  livekit-server:
    image: livekit/livekit-server
    command: --dev
    ports: ["7880:7880"]

  herdflow-agent:
    build: .
    environment:
      - LIVEKIT_URL=ws://livekit-server:7880
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
```

### Production Deployment (GCP)

| Component | Service | Config |
|-----------|---------|--------|
| Agent + RF-DETR | Cloud Run (GPU) or GCE n1-standard-4 + L4 | 16GB RAM, 4 vCPU, 1x NVIDIA L4 |
| LiveKit Server | LiveKit Cloud (free tier) | Auto-managed |
| Frontend | Cloud Storage + Cloud CDN | Static build, HTTPS |
| Demo videos | Cloud Storage | Pre-recorded cattle footage |

### Dockerfile (Multi-Stage)

```dockerfile
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/ .
RUN npm ci && npm run build

FROM nvidia/cuda:12.4-runtime-ubuntu22.04
# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
# Generate lockfile if missing: uv lock (run locally before build)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY agent/ agent/
COPY --from=frontend /app/frontend/dist /app/frontend/dist
CMD ["uv", "run", "python", "-m", "agent.main"]
```

### Environment Variables

```bash
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
GOOGLE_API_KEY=
RFDETR_MODEL=rf-detr-small
RFDETR_THRESHOLD=0.5
MAX_FPS=2.0
MIN_INTERVAL_MS=200
ALERT_PROLONGED_LYING_S=3600
ALERT_ISOLATION_THRESHOLD=0.7
ALERT_MISSED_FEEDING_S=14400
```

### Demo Video Plan (< 4 Minutes)

| Time | Segment | Content | Tech Shown |
|------|---------|---------|------------|
| 0:00–0:15 | Hook | Cattle + HerdFlow voice greeting | Gemini Live |
| 0:15–0:45 | Problem | Existing CV = dashboards, no voice | Slides |
| 0:45–1:30 | Core Demo | RF-DETR bboxes, farmer asks "How's the herd?" | Detection + tracking + voice |
| 1:30–2:15 | Anomaly | COW-003 isolating, agent proactively alerts | Proactive alerts + adaptive sampling |
| 2:15–2:45 | Query | "Which cows haven't fed?" → agent answers | Tool use + temporal reasoning |
| 2:45–3:15 | Architecture | Diagram: RF-DETR → Scene Graph → Gemini → LiveKit | Architecture |
| 3:15–3:45 | GCP Proof | Cloud Run dashboard | Deployment proof |
| 3:45–4:00 | Close | VisionFlow platform vision | Impact statement |

### Demo Video Footage

Source: Pexels stock video (free, no attribution required) for clean demo footage. Optionally CattleEyeView dataset (CC BY-SA 4.0) for annotated frames to validate detection accuracy.

## 10. Testing Strategy

### Test Pyramid

```
         ┌─────────────┐
         │  Golden Path │  2-3 end-to-end traces
         │  (E2E)       │
        ┌┴─────────────┴┐
        │  Handshake     │  9 boundary tests
        │  Tests         │
       ┌┴───────────────┴┐
       │  Contract Tests  │  Round-trip, edge cases, property-based
       │                  │
      ┌┴─────────────────┴┐
      │  Unit Tests        │  Per-module logic
      └────────────────────┘
```

### Unit Tests

| Module | Test File | Key Assertions |
|--------|-----------|----------------|
| Detector | `test_detector.py` | Output is `list[Detection]`, confidence filtering, class mapping |
| Tracker | `test_tracker.py` | ID persistence, occlusion recovery, track termination |
| SceneGraphBuilder | `test_scene_graph.py` | Zone assignment, behavior classification, delta computation |
| AlertRuleEngine | `test_alerts.py` | Rules fire at threshold, dedup/cooldown, auto-resolution |
| AdaptiveFrameSampler | `test_sampler.py` | Rate limiting, trigger priority, quiet suppression, user override |

### Contract Tests (`test_contracts.py`)

- **Round-trip serialization** for every Pydantic model crossing a serialization boundary
- **Boundary edge cases**: empty entity list, zero alerts, null zones, single critical alert
- **Property-based (Hypothesis)**: random valid payloads generated from JSON schema survive serialization
- **Consumer-driven**: verify backend never drops fields in `FRONTEND_REQUIRED_FIELDS`

### Handshake Tests (`test_handshakes.py`)

One test per boundary edge:
1. Detector → Tracker: mock detections produce valid TrackedEntity list
2. Tracker → SceneGraphBuilder: tracked entities produce valid SceneGraph
3. SceneGraphBuilder → AlertRuleEngine: scene graph evaluates without error
4. AlertRuleEngine → SceneGraphBuilder: alerts conform to Alert model
5. SceneGraphBuilder → AdaptiveFrameSampler: delta.is_significant triggers correctly
6. SceneGraphBuilder delta: empty→populated scene produces significant delta
7. AdaptiveFrameSampler → Gemini: JSON context string is valid and under token limits
8. Agent → LiveKit data channels: SceneGraph JSON parses correctly
9. LiveKit → React: Python JSON output matches TypeScript required fields

### Golden Path Tests (`test_golden_path.py`)

```
mock frame → Detection → TrackedEntity → SceneGraph → SceneDelta → JSON → TypeScript parse
```

Verify data integrity and trace_id preservation across all 3 tiers.

### Contract Validation Techniques

1. **Auto-generated TypeScript from Pydantic**: `scripts/generate_types.py` — CI fails if out of date
2. **Property-based testing with Hypothesis**: random valid payloads via `hypothesis-jsonschema`
3. **Consumer-driven contract verification**: `FRONTEND_REQUIRED_FIELDS` validated on every backend change

### CI Gate

```bash
uv run ruff format --check . \
  && uv run ruff check . \
  && uv run pyright \
  && uv run python scripts/generate_types.py \
  && git diff --exit-code frontend/src/types/generated.ts \
  && uv run pytest \
  && cd frontend && npx prettier --check . \
  && npx eslint . \
  && npx tsc --noEmit \
  && npx vitest run
```

### Test Fixtures (`tests/conftest.py`)

```python
def sample_frame(width=1280, height=720) -> np.ndarray
def mock_detection(class_name="cow", confidence=0.94) -> Detection
def mock_tracked_entity(track_id="COW-003", behavior="lying") -> TrackedEntity
def build_scene_graph(entities=8, alerts=0) -> SceneGraph
def minimal_entity() -> TrackedEntityModel
```

## 11. VisionFlow Generalization

HerdFlow is a specific instance of a general VisionFlow pattern. The three-tier architecture is domain-agnostic.

### Abstraction Points

| Point | File | HerdFlow Value | Swappable For |
|-------|------|----------------|---------------|
| Detector class filter | `config.py` | `["cow", "cattle"]` | `["person"]`, `["elephant"]` |
| Entity ID prefix | `config.py` | `"COW-"` | `"CUST-"`, `"ELE-"` |
| Behavior classifier | `scene_graph.py` | velocity + zone heuristics | pose-based, migration patterns |
| Zone definitions | `config.py` | feed, water, rest | entrance, checkout, waterhole |
| Alert rules | `rules.py` | lying, isolation, feeding | queue, restricted zone, fence |
| System prompt | `prompts.py` | Veterinary co-pilot | Store manager, ranger |
| Behavior baselines | `prompts.py` | Cattle norms | Human norms, elephant patterns |

### What Stays the Same Across All VisionFlow Instances

- RF-DETR detection pipeline
- ByteTrack tracking + persistent IDs
- SceneGraph schema and SceneDelta computation
- AdaptiveFrameSampler logic
- Gemini Live API integration + tool interface
- LiveKit WebRTC transport + data channels
- React frontend structure
- Alert engine architecture
- Contract testing framework

### Hackathon Approach

We don't build the abstraction layer. Domain-specific knowledge is isolated in config + prompts + rules, not hardcoded in pipeline code. Swap domain = swap config, not rewrite pipeline.

### Competition Closing (Demo 3:45-4:00)

> "HerdFlow is built on VisionFlow — a general-purpose real-time vision agent platform. The same architecture powers livestock monitoring today, and can be reconfigured for retail analytics, wildlife conservation, or workplace safety tomorrow. Change the prompt, change the rules, change the world you're watching."

## 12. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Gemini Live API preview instability | Core feature broken | Fallback: poll alerts + manual `generate_reply()` |
| RF-DETR poor performance on cattle footage | Bad demo visuals | COCO pre-trained includes cow class; test early with real footage |
| LiveKit Cloud free tier limits | Can't demo | Local dev server as backup; self-hosted GCE |
| GCP provisioning delays | Can't deploy | Demo locally; screen record Cloud Run separately |
| Token cost from high frame rate | API bill | Adaptive sampling caps at 2 FPS; zero during quiet |
| Time pressure (24 hours) | Incomplete MVP | Vertical slice ensures demoable at every phase |
| GIL blocking from RF-DETR inference | Event loop starvation | ThreadPoolExecutor for all GPU inference |
| ByteTrack ID swaps on re-entry | Wrong animal identity | Acceptable for demo; BoT-SORT upgrade path for production |
| Behavior misclassification (lying vs standing) | False prolonged_lying alerts | bbox aspect ratio heuristic + dwell-time gating |

## Appendix A: Review Findings (v1.0 → v1.1)

The following issues were found by spec review and expert panel review, and have been addressed in v1.1:

### Critical (Fixed)
- **C1:** `TrackedEntity` dataclass missing `confidence` field → added
- **C2:** Field mismatches between `TrackedEntity` ↔ `TrackedEntityModel` → aligned; added `zone_dwell_s`, `bbox_aspect_ratio`
- **C3:** `Alert.key` property referenced but never defined → added `@property` returning `f"{self.type}:{self.entity_track_id}"`
- **P0 (Expert):** GIL blocking — RF-DETR inference blocks asyncio event loop → wrapped in `ThreadPoolExecutor` via `run_in_executor()`

### Important (Fixed)
- **P1:** Detector threshold 0.5 defeats ByteTrack cascaded association at 0.3 → split into `detection_threshold=0.3` and `display_threshold=0.5`
- **P1:** Behavior classification ambiguous precedence → explicit priority chain with dwell-time gating and bbox aspect ratio
- **P1:** Gemini video input unclear (continuous vs pushed frames) → clarified: continuous track via plugin, sampler controls text context only
- **I1:** `DataChannelMessage` wrapper loses type safety → dropped; publish typed payloads directly to named channels
- **I3:** `HerdFlowAgent` class never defined → added interface spec
- **I5:** 10 historical SceneGraphs produce large context → slim `SceneGraphSnapshot` model
- **I6:** `perception_loop` function never defined → added full implementation spec
- **P2:** Sampler polling at 60Hz unnecessarily → event-driven via `asyncio.Queue`
- **P2:** Overlay payload too large at 30 FPS → slim `OverlayBox` model

### Minor (Fixed)
- **M1:** `HerdSummary` missing `feeding`/`drinking` counts → added
- **M2:** `Alert.id` no default factory → added `Field(default_factory=...)`
- **M6:** GPU inconsistency T4 vs L4 → standardized to L4
- **I7:** Dockerfile references `uv.lock` without generation step → added note
- **M7:** Video frame delivery mechanism to Gemini → covered by P1 clarification
