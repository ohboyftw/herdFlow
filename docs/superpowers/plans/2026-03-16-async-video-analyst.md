# Async Video Analyst Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace direct video-to-Gemini-Live (1007 crash) with an async video analyst that provides background summaries and on-demand visual analysis via tools.

**Architecture:** VideoAnalyst class runs as a background async task, receiving frames from perception_loop. It calls Gemini 3 Flash every 30s for summaries and Gemini 3 Pro on-demand when the farmer asks visual questions. Two new ADK tools expose this to the voice agent.

**Tech Stack:** google-genai (standard API, not Live), PIL for JPEG encoding, asyncio for background loop, existing ADK tool pattern.

**Spec:** `docs/superpowers/specs/2026-03-16-async-video-analyst-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `agent/reasoning/video_analyst.py` | CREATE | VideoAnalyst class — background summaries + on-demand analysis |
| `agent/adk_agents.py` | MODIFY | Add get_scene_summary, analyze_frame tools + set_video_analyst wiring |
| `agent/config.py` | MODIFY | Add 3 video analyst config fields |
| `agent/main.py` | MODIFY | Wire VideoAnalyst into entrypoint, update perception_loop |
| `agent/reasoning/prompts.py` | MODIFY | Update persona, add VISUAL AWARENESS section |
| `tests/test_video_analyst.py` | CREATE | Unit tests for VideoAnalyst |

---

## Chunk 1: VideoAnalyst Core + Tests

### Task 1: Config fields

**Files:**
- Modify: `agent/config.py` (Settings class)

- [ ] **Step 1: Add video analyst config fields**

```python
# Add to Settings class, after enable_analyst_subagent field:

    # Video Analyst
    video_analyst_background_model: str = "gemini-3-flash-preview"
    video_analyst_on_demand_model: str = "gemini-3-pro-preview"
    video_analyst_summary_interval_s: float = 30.0
```

- [ ] **Step 2: Verify import works**

Run: `uv run python -c "from agent.config import settings; print(settings.video_analyst_background_model)"`
Expected: `gemini-3-flash-preview`

- [ ] **Step 3: Commit**

```bash
git add agent/config.py
git commit -m "feat: add video analyst config fields"
```

### Task 2: VideoAnalyst class — write failing tests first

**Files:**
- Create: `tests/test_video_analyst.py`
- Create: `agent/reasoning/video_analyst.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for VideoAnalyst — async video analysis via Gemini API."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from agent.models import SceneGraph, HerdSummary
from agent.reasoning.video_analyst import VideoAnalyst


def _make_scene_graph(n_entities: int = 3) -> SceneGraph:
    """Create a minimal SceneGraph for testing."""
    return SceneGraph(
        frame_id=1,
        timestamp="2026-03-16T12:00:00Z",
        tracked_entities=[],
        active_alerts=[],
        herd_summary=HerdSummary(
            total_visible=n_entities,
            standing=n_entities,
            lying=0,
            walking=0,
            feeding=0,
            drinking=0,
        ),
        zones={},
    )


class TestVideoAnalystUpdate:
    def test_update_stores_frame_and_scene_graph(self) -> None:
        analyst = VideoAnalyst()
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        sg = _make_scene_graph(5)
        analyst.update(frame, sg)
        assert analyst.latest_frame is not None
        assert analyst.latest_scene_graph is not None
        assert analyst.latest_scene_graph.herd_summary.total_visible == 5

    def test_update_with_none_frame(self) -> None:
        analyst = VideoAnalyst()
        analyst.update(None, _make_scene_graph())
        assert analyst.latest_frame is None


class TestVideoAnalystSummary:
    def test_get_summary_before_any_update(self) -> None:
        analyst = VideoAnalyst()
        summary = analyst.get_summary()
        assert "No video feed" in summary or "not available" in summary.lower()

    def test_get_summary_before_background_loop_runs(self) -> None:
        """Before background loop runs, summary is the initial default."""
        analyst = VideoAnalyst()
        analyst.update(np.zeros((360, 640, 3), dtype=np.uint8), _make_scene_graph(4))
        summary = analyst.get_summary()
        assert "No video feed" in summary

    def test_format_scene_graph_fallback(self) -> None:
        analyst = VideoAnalyst()
        sg = _make_scene_graph(6)
        text = analyst._format_scene_graph(sg)
        assert "6" in text
        assert "standing" in text.lower()


class TestVideoAnalystAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_no_frame_returns_fallback(self) -> None:
        analyst = VideoAnalyst()
        analyst.update(None, _make_scene_graph(3))
        result = await analyst.analyze("What do you see?")
        assert "No video feed" in result or "scene data" in result.lower()

    @pytest.mark.asyncio
    async def test_analyze_sets_analyzing_flag(self) -> None:
        """Verify the _analyzing guard flag is managed."""
        analyst = VideoAnalyst()
        # Without a real API key, analyze will fail — that's fine for flag test
        analyst.update(np.zeros((360, 640, 3), dtype=np.uint8), _make_scene_graph())
        assert not analyst._analyzing


class TestVideoAnalystEncoding:
    def test_encode_frame_returns_bytes(self) -> None:
        analyst = VideoAnalyst()
        frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        jpeg = analyst._encode_frame(frame, quality=40)
        assert isinstance(jpeg, bytes)
        assert len(jpeg) > 0
        # JPEG magic bytes
        assert jpeg[:2] == b"\xff\xd8"

    def test_encode_frame_resizes(self) -> None:
        analyst = VideoAnalyst()
        frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        jpeg_low = analyst._encode_frame(frame, quality=40)
        jpeg_high = analyst._encode_frame(frame, quality=80)
        # Higher quality = larger file
        assert len(jpeg_high) > len(jpeg_low)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_video_analyst.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.reasoning.video_analyst'`

- [ ] **Step 3: Write VideoAnalyst class**

Create `agent/reasoning/video_analyst.py`:

```python
"""Async video analyst — background summaries + on-demand deep analysis.

Replaces direct video-to-Gemini-Live (which caused 1007 errors) with
standard Gemini API calls. Two modes:
- Background: Gemini 3 Flash every 30s for scene summaries
- On-demand: Gemini 3 Pro when farmer asks a visual question
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from agent.models import SceneGraph

logger = logging.getLogger("herdflow.video_analyst")

_BACKGROUND_PROMPT = (
    "You are a livestock camera analyst. Describe what you see in this frame. "
    "Focus on: number of animals, their posture (standing/lying/walking), "
    "any unusual behavior, and spatial distribution. Be concise (2-3 sentences).\n\n"
    "Scene tracking data:\n{scene_json}"
)

_ON_DEMAND_PROMPT = (
    "You are a veterinary visual analyst examining a livestock camera feed. "
    "A farmer is asking: {question}\n\n"
    "Analyze the image carefully. Reference specific animals by their track ID "
    "from the scene data when possible. Be detailed but concise.\n\n"
    "Scene tracking data:\n{scene_json}"
)


class VideoAnalyst:
    """Async video analysis — background summaries + on-demand deep analysis."""

    def __init__(
        self,
        background_model: str = "gemini-3-flash-preview",
        on_demand_model: str = "gemini-3-pro-preview",
        summary_interval_s: float = 30.0,
    ) -> None:
        self.background_model = background_model
        self.on_demand_model = on_demand_model
        self.summary_interval_s = summary_interval_s

        self.latest_frame: np.ndarray | None = None
        self.latest_scene_graph: SceneGraph | None = None
        self.latest_summary: str = "No video feed available yet."
        self._analyzing: bool = False
        self._last_analysis: str = ""
        self._client = None  # Lazy init

    def _get_client(self):
        """Lazy-init the genai client."""
        if self._client is None:
            from google import genai
            self._client = genai.Client()
        return self._client

    def update(self, frame: np.ndarray | None, scene_graph: SceneGraph) -> None:
        """Update latest frame and scene graph. Called by perception_loop."""
        self.latest_frame = frame
        self.latest_scene_graph = scene_graph

    def get_summary(self) -> str:
        """Return the latest summary (instant, no API call)."""
        return self.latest_summary

    def _format_scene_graph(self, sg: SceneGraph) -> str:
        """Format scene graph as human-readable text fallback."""
        hs = sg.herd_summary
        parts = [
            f"{hs.total_visible} animals visible:",
            f"{hs.standing} standing, {hs.lying} lying, {hs.walking} walking,",
            f"{hs.feeding} feeding, {hs.drinking} drinking.",
        ]
        if sg.active_alerts:
            alerts = [f"{a.type}:{a.entity_track_id}" for a in sg.active_alerts]
            parts.append(f"Active alerts: {', '.join(alerts)}.")
        entities = [
            f"{e.track_id}: {e.behavior} in {e.zone}"
            for e in sg.tracked_entities
        ]
        if entities:
            parts.append(f"Entities: {'; '.join(entities)}")
        return " ".join(parts)

    def _encode_frame(self, frame: np.ndarray, quality: int = 40) -> bytes:
        """Encode numpy frame as JPEG bytes, resized to 640x360."""
        img = Image.fromarray(frame).resize((640, 360), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    async def run_background_loop(self) -> None:
        """Background task: summarize the scene every N seconds."""
        logger.info(
            "[ANALYST] Background loop started (every %.0fs, model=%s)",
            self.summary_interval_s,
            self.background_model,
        )
        while True:
            await asyncio.sleep(self.summary_interval_s)
            try:
                if self.latest_frame is None:
                    if self.latest_scene_graph is not None:
                        self.latest_summary = self._format_scene_graph(
                            self.latest_scene_graph
                        )
                    else:
                        self.latest_summary = "No video feed available."
                    continue

                jpeg = self._encode_frame(self.latest_frame, quality=40)
                scene_json = (
                    self.latest_scene_graph.model_dump_json(indent=2)
                    if self.latest_scene_graph
                    else "{}"
                )
                prompt = _BACKGROUND_PROMPT.format(scene_json=scene_json)

                from google.genai import types

                response = await asyncio.to_thread(
                    self._get_client().models.generate_content,
                    model=self.background_model,
                    contents=[
                        types.Content(
                            parts=[
                                types.Part.from_image(
                                    image=types.Blob(
                                        data=jpeg, mime_type="image/jpeg"
                                    )
                                ),
                                types.Part.from_text(text=prompt),
                            ]
                        )
                    ],
                )
                self.latest_summary = response.text or self._format_scene_graph(
                    self.latest_scene_graph
                )
                logger.info("[ANALYST] Background summary: %s", self.latest_summary[:100])

            except Exception:
                logger.exception("[ANALYST] Background summary failed, using fallback")
                if self.latest_scene_graph is not None:
                    self.latest_summary = self._format_scene_graph(
                        self.latest_scene_graph
                    )

    async def analyze(self, question: str) -> str:
        """On-demand deep analysis of current frame via Gemini 3 Pro."""
        if self.latest_frame is None:
            fallback = ""
            if self.latest_scene_graph is not None:
                fallback = self._format_scene_graph(self.latest_scene_graph)
            return f"No video feed available. Scene data: {fallback}"

        if self._analyzing:
            return (
                f"Analysis already in progress. Last result: {self._last_analysis}"
                if self._last_analysis
                else "Analysis in progress, please wait."
            )

        self._analyzing = True
        try:
            jpeg = self._encode_frame(self.latest_frame, quality=80)
            scene_json = (
                self.latest_scene_graph.model_dump_json(indent=2)
                if self.latest_scene_graph
                else "{}"
            )
            prompt = _ON_DEMAND_PROMPT.format(
                question=question, scene_json=scene_json
            )

            from google.genai import types

            response = await asyncio.to_thread(
                self._get_client().models.generate_content,
                model=self.on_demand_model,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_image(
                                image=types.Blob(
                                    data=jpeg, mime_type="image/jpeg"
                                )
                            ),
                            types.Part.from_text(text=prompt),
                        ]
                    )
                ],
            )
            self._last_analysis = response.text or "Analysis returned empty."
            logger.info("[ANALYST] On-demand: %s", self._last_analysis[:150])
            return self._last_analysis

        except Exception:
            logger.exception("[ANALYST] On-demand analysis failed")
            if self.latest_scene_graph is not None:
                return (
                    f"Visual analysis failed. Scene data: "
                    f"{self._format_scene_graph(self.latest_scene_graph)}"
                )
            return "Visual analysis failed and no scene data available."
        finally:
            self._analyzing = False
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_video_analyst.py -v`
Expected: All tests PASS (tests only exercise non-API methods: update, get_summary, _encode_frame, _format_scene_graph, flag management)

- [ ] **Step 5: Commit**

```bash
git add agent/reasoning/video_analyst.py tests/test_video_analyst.py
git commit -m "feat: VideoAnalyst class — background summaries + on-demand analysis"
```

---

## Chunk 2: Tool Functions + Wiring

### Task 3: Add tool functions to adk_agents.py

**Files:**
- Modify: `agent/adk_agents.py`

- [ ] **Step 1: Add imports, module-level state, and tool functions**

At the top of `agent/adk_agents.py`, after existing imports (note: `from __future__ import annotations` is already present), add:

```python
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.reasoning.video_analyst import VideoAnalyst

logger = logging.getLogger("herdflow")

# Module-level video analyst reference, set by entrypoint
_video_analyst: VideoAnalyst | None = None


def set_video_analyst(analyst: VideoAnalyst) -> None:
    """Wire the video analyst instance for tool access."""
    global _video_analyst
    _video_analyst = analyst
```

Then after the existing `get_zone_history` function, before `herd_tools`, add:

```python
async def get_scene_summary() -> dict:
    """Get the latest visual summary of the camera feed.

    Returns a 2-3 sentence description of what the camera currently shows,
    including animal count, postures, and any notable observations.
    """
    if _video_analyst is None:
        logger.warning("get_scene_summary called but video analyst not initialized")
        return {"summary": "Video analyst not available."}
    return {"summary": _video_analyst.get_summary()}


async def analyze_frame(question: str) -> dict:
    """Analyze the current camera frame to answer a specific visual question.

    Use this for questions about what animals look like, their physical condition,
    or anything requiring visual inspection. Takes a few seconds to process.
    """
    if _video_analyst is None:
        logger.warning("analyze_frame called but video analyst not initialized")
        return {"analysis": "Video analyst not available."}
    result = await _video_analyst.analyze(question)
    return {"analysis": result}
```

Update `herd_tools` to include the new tools:

```python
herd_tools = [
    search_entity_history, get_herd_stats, find_by_description, get_zone_history,
    get_scene_summary, analyze_frame,
]
```

- [ ] **Step 2: Verify imports work**

Run: `uv run python -c "from agent.adk_agents import herd_tools; print(len(herd_tools), [t.__name__ for t in herd_tools])"`
Expected: `6 ['search_entity_history', 'get_herd_stats', 'find_by_description', 'get_zone_history', 'get_scene_summary', 'analyze_frame']`

- [ ] **Step 3: Commit**

```bash
git add agent/adk_agents.py
git commit -m "feat: add get_scene_summary and analyze_frame tools"
```

### Task 4: Wire VideoAnalyst into main.py

**Files:**
- Modify: `agent/main.py`

- [ ] **Step 1: Add import**

Add after the existing imports from `agent.adk_agents`:

```python
from agent.adk_agents import set_video_analyst
from agent.reasoning.video_analyst import VideoAnalyst
```

- [ ] **Step 2: Modify entrypoint — create analyst, wire it**

In the `entrypoint` function, after `scene_builder` and `sampler` setup (around line 120), add:

```python
    # Video analyst — async background + on-demand visual analysis
    video_analyst = VideoAnalyst(
        background_model=settings.video_analyst_background_model,
        on_demand_model=settings.video_analyst_on_demand_model,
        summary_interval_s=settings.video_analyst_summary_interval_s,
    )
    set_video_analyst(video_analyst)
```

- [ ] **Step 3: Modify perception_loop call — pass analyst instead of live_queue**

Replace the current perception_loop task creation:

```python
    # Old:
    # asyncio.create_task(perception_loop(ctx, scene_builder, scene_queue, video_source, live_queue))

    # New:
    asyncio.create_task(perception_loop(ctx, scene_builder, video_source, video_analyst=video_analyst))
    asyncio.create_task(video_analyst.run_background_loop())
```

- [ ] **Step 4: Modify perception_loop signature and body**

Change `perception_loop` signature (remove `scene_queue` and `live_queue`, add `video_analyst`):

```python
async def perception_loop(
    ctx: JobContext,
    builder: SceneGraphBuilder,
    video_source: FileVideoSource | None = None,
    video_analyst: VideoAnalyst | None = None,
) -> None:
```

Remove all `live_queue.send_realtime(Blob(...))` video-sending code from the loop body.

After `sg = await builder.process_frame(frame, frame_id)`, add:

```python
        # Update video analyst with latest frame + scene graph
        if video_analyst is not None:
            video_analyst.update(frame, sg)
```

- [ ] **Step 5: Remove dead code**

Remove from entrypoint:
- `scene_queue` creation (only used by sampler which is disabled)
- `sampler` creation
- `inject_context` function
- The commented-out `sampler.run` line

Remove from perception_loop:
- `scene_queue.put_nowait` at the end
- `scene_queue` parameter

- [ ] **Step 6: Verify agent starts**

Run: `uv run python -c "from agent.main import server; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add agent/main.py
git commit -m "feat: wire VideoAnalyst into entrypoint and perception_loop"
```

### Task 5: Update prompt

**Files:**
- Modify: `agent/reasoning/prompts.py`

- [ ] **Step 1: Update persona section**

Replace:
```
You can see the livestock through a live camera feed in real time. \
You observe posture, gait, movement patterns, and clustering behavior. \
```

With:
```
You have access to a livestock camera feed through your visual tools. \
```

- [ ] **Step 2: Add VISUAL AWARENESS section**

After the TOOL USAGE section, add:

```
VISUAL AWARENESS:
You have access to a camera watching the herd via your tools:
- get_scene_summary: Quick overview of what the camera shows (instant, no delay).
- analyze_frame: Deep visual analysis of the current frame (takes a few seconds).
When the farmer asks "what do you see?" or about an animal's appearance, \
use get_scene_summary first for a quick answer. If they want more detail, \
use analyze_frame with their specific question. \
Say "Let me take a closer look..." while waiting for analyze_frame results.
```

- [ ] **Step 3: Run existing tests to verify nothing broke**

Run: `uv run pytest tests/ -q`
Expected: 86+ tests pass

- [ ] **Step 4: Commit**

```bash
git add agent/reasoning/prompts.py
git commit -m "feat: update prompt — visual awareness via tools, not live camera"
```

---

## Chunk 3: Integration Test

### Task 6: Manual e2e verification

**Files:** None (manual test)

- [ ] **Step 1: Start the agent**

Run: `uv run python scripts/e2e.py`
Expected: Agent starts, logs show `[ANALYST] Background loop started`

- [ ] **Step 2: Wait 30s, verify background summary**

Watch logs for: `[ANALYST] Background summary: ...`
Expected: A 2-3 sentence description of the cattle scene

- [ ] **Step 3: Connect browser, ask "what do you see?"**

Open test.html, connect, say "What do you see right now?"
Expected:
- Log shows `[ADK] Tool call: get_scene_summary` or `analyze_frame`
- Agent speaks a description of the cattle scene
- No 1007 error

- [ ] **Step 4: Ask a specific visual question**

Say: "Is any cow lying down?"
Expected:
- Log shows `[ADK] Tool call: analyze_frame`
- Log shows `[ANALYST] On-demand: ...`
- Agent speaks the analysis result

- [ ] **Step 5: Verify session stability (2+ min)**

Keep session open 2+ minutes.
Expected: No crash, background summaries continue in logs every 30s

- [ ] **Step 6: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: async video analyst — background summaries + on-demand Gemini Pro analysis"
```
