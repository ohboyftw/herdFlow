# Two-Pipe Architecture Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split HerdFlow into two independent processes — voice (ADK + audio) and video (perception + analyst) — communicating via LiveKit data channels, eliminating GIL contention that causes voice input drops.

**Architecture:** Voice process uses LiveKit AgentServer + ADK run_live() for audio only. Video process uses raw rtc.Room.connect() for perception pipeline + video publishing + VideoAnalyst. Inter-process communication via LiveKit data channels. AnalystBridge in voice process caches video analyst data and handles request/response for on-demand analysis.

**Tech Stack:** Python 3.12+, LiveKit agents SDK, Google ADK, google-genai, livekit-plugins-google (STT), asyncio

**Spec:** `docs/superpowers/specs/2026-03-16-two-pipe-architecture-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `agent/reasoning/analyst_bridge.py` | CREATE | Voice-side cache + request/response bridge for analyst data channels |
| `agent/voice_agent.py` | CREATE | Voice process entrypoint — ADK session, audio bridges, STT, tools |
| `agent/video_agent.py` | CREATE | Video process entrypoint — perception, video publish, VideoAnalyst |
| `agent/adk_agents.py` | MODIFY | Tools use AnalystBridge instead of VideoAnalyst |
| `agent/config.py` | MODIFY | Add voice/video agent identity config |
| `agent/main.py` | MODIFY | Thin launcher spawning both processes |
| `scripts/e2e.py` | MODIFY | Generate video token, launch both processes |
| `tests/test_analyst_bridge.py` | CREATE | Unit tests for AnalystBridge |

---

## Chunk 1: AnalystBridge + Tests

### Task 1: Config fields

**Files:**
- Modify: `agent/config.py`

- [ ] **Step 1: Add identity config fields**

```python
    # Two-pipe architecture
    voice_agent_identity: str = "herdflow-voice"
    video_agent_identity: str = "herdflow-video"
```

- [ ] **Step 2: Verify**

Run: `uv run python -c "from agent.config import settings; print(settings.voice_agent_identity)"`
Expected: `herdflow-voice`

- [ ] **Step 3: Commit**

```bash
git add agent/config.py
git commit -m "feat: add voice/video agent identity config"
```

### Task 2: AnalystBridge — write failing tests first

**Files:**
- Create: `tests/test_analyst_bridge.py`
- Create: `agent/reasoning/analyst_bridge.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for AnalystBridge — voice-side cache for video analyst data."""

from __future__ import annotations

import asyncio
import time

import pytest

from agent.reasoning.analyst_bridge import AnalystBridge


class TestAnalystBridgeCache:
    def test_initial_summary_is_fallback(self) -> None:
        bridge = AnalystBridge()
        assert "No video feed" in bridge.get_summary()

    def test_update_summary(self) -> None:
        bridge = AnalystBridge()
        bridge._on_summary_received('{"summary": "3 cows standing"}')
        assert "3 cows standing" in bridge.get_summary()

    def test_update_annotations(self) -> None:
        bridge = AnalystBridge()
        bridge._on_annotations_received(
            '{"annotations": {"COW-001": {"label": "brown cow"}}}'
        )
        ann = bridge.get_annotation("COW-001")
        assert ann is not None
        assert ann["label"] == "brown cow"

    def test_get_annotation_missing(self) -> None:
        bridge = AnalystBridge()
        assert bridge.get_annotation("COW-999") is None

    def test_data_received_dispatches_by_topic(self) -> None:
        bridge = AnalystBridge()
        bridge._on_data_received(
            b'{"summary": "dispatched test"}', topic="analyst_summary"
        )
        assert "dispatched test" in bridge.get_summary()

    def test_staleness_detection(self) -> None:
        bridge = AnalystBridge(stale_threshold_s=0.1)
        bridge._on_summary_received('{"summary": "fresh data"}')
        assert not bridge.is_stale()
        # Simulate time passing
        bridge._last_update_time = time.monotonic() - 1.0
        assert bridge.is_stale()

    def test_stale_summary_returns_fallback(self) -> None:
        bridge = AnalystBridge(stale_threshold_s=0.1)
        bridge._on_summary_received('{"summary": "old data"}')
        bridge._last_update_time = time.monotonic() - 1.0
        summary = bridge.get_summary()
        assert "unavailable" in summary.lower()


class TestAnalystBridgeRequestResponse:
    @pytest.mark.asyncio
    async def test_request_analysis_timeout_returns_fallback(self) -> None:
        bridge = AnalystBridge()
        # No video process to respond — should timeout
        result = await bridge.request_analysis("what do you see?", timeout_s=0.1)
        assert "timed out" in result.lower() or "unavailable" in result.lower()

    @pytest.mark.asyncio
    async def test_request_response_matching(self) -> None:
        bridge = AnalystBridge()

        # Simulate response arriving after request
        async def _send_response() -> None:
            await asyncio.sleep(0.05)
            # Find the pending request_id
            for req_id in bridge._pending_requests:
                bridge._on_response_received(
                    f'{{"answer": "brown cow lying", "request_id": "{req_id}"}}'
                )
                break

        asyncio.create_task(_send_response())
        result = await bridge.request_analysis("describe cow 3", timeout_s=1.0)
        assert "brown cow" in result

    @pytest.mark.asyncio
    async def test_stale_bridge_returns_immediate_fallback(self) -> None:
        bridge = AnalystBridge(stale_threshold_s=0.1)
        bridge._last_update_time = time.monotonic() - 1.0
        # Should return immediately, not wait 30s
        result = await bridge.request_analysis("what?", timeout_s=5.0)
        assert "unavailable" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_analyst_bridge.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement AnalystBridge**

Create `agent/reasoning/analyst_bridge.py`:

```python
"""Voice-side bridge to video process's analyst via LiveKit data channels.

Caches latest summary and annotations from the video process.
Handles request/response for on-demand analyze_frame calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

logger = logging.getLogger("herdflow.analyst_bridge")


class AnalystBridge:
    """Cache + request/response bridge for analyst data from video process."""

    def __init__(self, stale_threshold_s: float = 60.0) -> None:
        self.latest_summary: str = "No video feed available yet."
        self.latest_annotations: dict[str, dict] = {}
        self._last_update_time: float = 0.0
        self._stale_threshold_s = stale_threshold_s
        self._pending_requests: dict[str, asyncio.Future[str]] = {}
        self._room = None

    async def start(self, room) -> None:
        """Subscribe to analyst data channels from video process."""
        self._room = room
        room.on("data_received", self._on_data_received)
        logger.info("[BRIDGE] AnalystBridge started, listening for analyst channels")

    def _on_data_received(
        self, payload: bytes, participant=None, kind=None, topic: str | None = None
    ) -> None:
        if topic == "analyst_summary":
            self._on_summary_received(payload.decode("utf-8"))
        elif topic == "analyst_annotations":
            self._on_annotations_received(payload.decode("utf-8"))
        elif topic == "analyst_response":
            self._on_response_received(payload.decode("utf-8"))

    def _on_summary_received(self, data: str) -> None:
        try:
            parsed = json.loads(data)
            self.latest_summary = parsed.get("summary", self.latest_summary)
            self._last_update_time = time.monotonic()
            logger.debug("[BRIDGE] Summary updated: %s", self.latest_summary[:80])
        except (json.JSONDecodeError, KeyError):
            logger.warning("[BRIDGE] Failed to parse analyst_summary")

    def _on_annotations_received(self, data: str) -> None:
        try:
            parsed = json.loads(data)
            self.latest_annotations = parsed.get("annotations", {})
            self._last_update_time = time.monotonic()
            logger.debug("[BRIDGE] Annotations updated: %d entities", len(self.latest_annotations))
        except (json.JSONDecodeError, KeyError):
            logger.warning("[BRIDGE] Failed to parse analyst_annotations")

    def _on_response_received(self, data: str) -> None:
        try:
            parsed = json.loads(data)
            request_id = parsed.get("request_id", "")
            answer = parsed.get("answer", "")
            if request_id in self._pending_requests:
                self._pending_requests[request_id].set_result(answer)
                logger.info("[BRIDGE] Response received for %s", request_id)
        except (json.JSONDecodeError, KeyError):
            logger.warning("[BRIDGE] Failed to parse analyst_response")

    def is_stale(self) -> bool:
        if self._last_update_time == 0.0:
            return True
        return (time.monotonic() - self._last_update_time) > self._stale_threshold_s

    def get_summary(self) -> str:
        if self.is_stale() and self._last_update_time > 0:
            return "Video feed unavailable — no recent data."
        return self.latest_summary

    def get_annotation(self, track_id: str) -> dict | None:
        return self.latest_annotations.get(track_id)

    async def request_analysis(self, question: str, timeout_s: float = 30.0) -> str:
        if self.is_stale():
            return "Video feed unavailable — cannot analyze frame."

        if self._room is None:
            return "Not connected to LiveKit room."

        request_id = uuid.uuid4().hex[:8]
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            payload = json.dumps({"question": question, "request_id": request_id})
            await self._room.local_participant.publish_data(
                payload.encode(), topic="analyst_request"
            )
            logger.info("[BRIDGE] Sent analyst_request %s: %s", request_id, question[:50])

            result = await asyncio.wait_for(future, timeout=timeout_s)
            return result
        except TimeoutError:
            logger.warning("[BRIDGE] analyst_request %s timed out", request_id)
            return "Visual analysis timed out — video feed may be unavailable."
        finally:
            self._pending_requests.pop(request_id, None)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_analyst_bridge.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run all tests**

Run: `uv run pytest tests/ -q`
Expected: 92+ tests pass

- [ ] **Step 6: Commit**

```bash
git add agent/reasoning/analyst_bridge.py tests/test_analyst_bridge.py
git commit -m "feat: AnalystBridge — voice-side cache + request/response for analyst data"
```

---

## Chunk 2: Voice Agent Process

### Task 3: Create voice_agent.py

**Files:**
- Create: `agent/voice_agent.py`

- [ ] **Step 1: Create voice_agent.py**

Extract from `agent/main.py` — voice-specific code only. This file contains:
- `.env` loading
- Logging setup (to `logs/herdflow-voice.log`)
- `AgentServer` with `initialize_process_timeout=60.0`
- `setup()` — loads Silero VAD only (NO RF-DETR, NO FileVideoSource)
- `entrypoint()` — ADK agent creation, audio bridges, STT, AnalystBridge
- Audio constants (INPUT_SAMPLE_RATE, OUTPUT_SAMPLE_RATE, NUM_CHANNELS)

Key differences from current `main.py`:
- No `perception_loop`, no `video_publish_loop`
- No RF-DETR, no SceneGraphBuilder, no FileVideoSource imports
- No VideoAnalyst — uses AnalystBridge instead
- `setup()` only loads `silero.VAD`
- Log file: `logs/herdflow-voice.log`
- `entrypoint()` creates AnalystBridge, calls `bridge.start(room)` after connecting

The `entrypoint()` starts these tasks:
1. `audio_input_bridge()` — farmer mic → ADK
2. `audio_output_bridge()` — ADK → LiveKit (with interruption handling)
3. `transcription_loop()` — LiveKit STT → transcript data channel
4. (NO perception_loop, NO video_publish_loop)

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from agent.voice_agent import server; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent/voice_agent.py
git commit -m "feat: voice_agent.py — voice process entrypoint (ADK + audio only)"
```

### Task 4: Update adk_agents.py tools to use AnalystBridge

**Files:**
- Modify: `agent/adk_agents.py`

- [ ] **Step 1: Replace VideoAnalyst references with AnalystBridge**

Change:
- `from agent.reasoning.video_analyst import VideoAnalyst` → `from agent.reasoning.analyst_bridge import AnalystBridge`
- `_video_analyst: VideoAnalyst | None` → `_analyst_bridge: AnalystBridge | None`
- `set_video_analyst(analyst)` → `set_analyst_bridge(bridge)`
- `get_scene_summary()` → calls `_analyst_bridge.get_summary()`
- `analyze_frame(question)` → calls `_analyst_bridge.request_analysis(question)`

Keep backward compatibility with fallback chain:

```python
_analyst_bridge: AnalystBridge | None = None
_video_analyst: VideoAnalyst | None = None

def set_analyst_bridge(bridge: AnalystBridge) -> None:
    global _analyst_bridge
    _analyst_bridge = bridge

async def get_scene_summary() -> dict:
    if _analyst_bridge is not None:
        return {"summary": _analyst_bridge.get_summary()}
    if _video_analyst is not None:
        return {"summary": _video_analyst.get_summary()}
    return {"summary": "Video analyst not available."}

async def analyze_frame(question: str) -> dict:
    if _analyst_bridge is not None:
        result = await _analyst_bridge.request_analysis(question)
        return {"analysis": result}
    if _video_analyst is not None:
        result = await _video_analyst.analyze(question)
        return {"analysis": result}
    return {"analysis": "Video analyst not available."}
```

- [ ] **Step 2: Verify**

Run: `uv run python -c "from agent.adk_agents import herd_tools; print(len(herd_tools))"`
Expected: `6`

- [ ] **Step 3: Commit**

```bash
git add agent/adk_agents.py
git commit -m "feat: tools use AnalystBridge (with VideoAnalyst fallback)"
```

---

## Chunk 3: Video Agent Process

### Task 5a: Create video_agent.py skeleton

**Files:**
- Create: `agent/video_agent.py`

- [ ] **Step 1: Create skeleton with room connection + logging**

```python
"""HerdFlow video agent — perception pipeline + visual analyst.

Runs as independent process, connects to LiveKit as plain participant.
Publishes: video track, scene_graph, overlay, alerts, analyst_summary,
analyst_annotations, zone_config data channels.
"""

from __future__ import annotations

import asyncio
import os
import logging
from pathlib import Path

# Load .env
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# Log to separate file
_log_dir = Path(__file__).resolve().parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_fh = logging.FileHandler(_log_dir / "herdflow-video.log", mode="a", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(name)s  %(message)s"))
_fh.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_fh)
logging.getLogger().setLevel(logging.DEBUG)
for _h in logging.getLogger().handlers:
    if isinstance(_h, logging.StreamHandler) and _h is not _fh:
        _h.setLevel(logging.INFO)

import livekit.rtc as rtc

logger = logging.getLogger("herdflow.video")


async def main() -> None:
    token = os.environ.get("VIDEO_AGENT_TOKEN", "")
    url = os.environ.get("LIVEKIT_URL", "")
    if not token or not url:
        logger.error("VIDEO_AGENT_TOKEN and LIVEKIT_URL must be set")
        return

    room = rtc.Room()
    await room.connect(url, token)
    logger.info("Video agent connected to room: %s", room.name)

    # TODO: start perception + video + analyst loops

    try:
        while True:
            await asyncio.sleep(1)
    finally:
        await room.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from agent.video_agent import main; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent/video_agent.py
git commit -m "feat: video_agent.py skeleton — room connection + logging"
```

### Task 5b: Move video_publish_loop to video_agent

- [ ] **Step 1: Extract video_publish_loop from main.py, adapt for raw Room**

Replace `ctx.room.local_participant` with `room.local_participant`. Add video track creation + `video_publish_loop()` to `main()` in video_agent.py.

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: video_agent — video_publish_loop (5 FPS, shared_frame)"
```

### Task 5c: Move perception_loop to video_agent

- [ ] **Step 1: Extract perception_loop, adapt for raw Room**

Move RF-DETR loading, SceneGraphBuilder, perception_loop. Replace `ctx.room` with `room`. Keep data channel publishing (scene_graph, overlay, alerts).

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: video_agent — perception_loop (RF-DETR + data channels)"
```

### Task 5d: Wire VideoAnalyst + analyst request/response

- [ ] **Step 1: Add VideoAnalyst, background loop, analyst data channel publishing**

Wire `VideoAnalyst` instance, start background loop, publish `analyst_summary` and `analyst_annotations` data channels. Subscribe to `analyst_request`, run on-demand Gemini Pro, publish `analyst_response`.

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: video_agent — VideoAnalyst + analyst request/response channels"
```

### Task 5e: Import tests for both agents

- [ ] **Step 1: Verify both modules import**

```python
# tests/test_two_pipe.py
def test_voice_agent_imports() -> None:
    from agent.voice_agent import server
    assert server is not None

def test_video_agent_imports() -> None:
    from agent.video_agent import main
    assert callable(main)

def test_analyst_bridge_wiring() -> None:
    from agent.adk_agents import set_analyst_bridge, herd_tools
    assert callable(set_analyst_bridge)
    assert len(herd_tools) == 6
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -q`
Expected: 92+ existing + new tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_two_pipe.py
git commit -m "test: import tests for voice_agent, video_agent, analyst_bridge wiring"
```

---

## Chunk 4: Launcher + E2E Script

### Task 6: Update main.py as thin launcher

**Files:**
- Modify: `agent/main.py`

- [ ] **Step 1: Replace main.py with launcher**

`main.py` becomes a thin launcher that:
1. Loads `.env`
2. Generates video agent token
3. Spawns voice process: `subprocess.Popen([sys.executable, "-m", "agent.voice_agent", "dev"])`
4. Spawns video process: `subprocess.Popen([sys.executable, "-m", "agent.video_agent"], env={...VIDEO_AGENT_TOKEN...})`
5. Registers `atexit` + signal handlers to kill both on Ctrl+C
6. Waits for both processes

- [ ] **Step 2: Verify**

Run: `uv run python -c "from agent.main import main; print('OK')"`
Expected: `OK` (doesn't launch, just imports)

- [ ] **Step 3: Commit**

```bash
git add agent/main.py
git commit -m "refactor: main.py → thin launcher for voice + video processes"
```

### Task 7: Update scripts/e2e.py

**Files:**
- Modify: `scripts/e2e.py`

- [ ] **Step 1: Generate video token + launch both**

Update `e2e.py` to:
1. Generate farmer token (for browser, existing)
2. Generate video agent token (for video process, new)
3. Patch test.html + frontend/.env (existing)
4. Set `VIDEO_AGENT_TOKEN` env var
5. Launch `agent.main` (which spawns both processes)

- [ ] **Step 2: Commit**

```bash
git add scripts/e2e.py
git commit -m "feat: e2e.py generates video token, launches two-pipe architecture"
```

---

## Chunk 5: Integration Test

### Task 8: Manual e2e verification

- [ ] **Step 1: Start both processes**

Run: `uv run python scripts/e2e.py`
Expected:
- Voice process: `registered worker`, `Published audio track`
- Video process: `Video agent connected to room`, `[VIDEO] Publishing at ~5 FPS`

- [ ] **Step 2: Connect browser, verify voice**

Open test.html, say "What do you see?"
Expected: Agent responds using `get_scene_summary` tool (data from video process)

- [ ] **Step 3: Verify video + data channels**

Check test.html data panel for scene_graph, overlay updates
Expected: Scene data flowing from video process

- [ ] **Step 4: Verify on-demand analysis**

Say "Describe the color of the cows"
Expected:
- Voice logs: `[BRIDGE] Sent analyst_request`
- Video logs: `[ANALYST] On-demand:`
- Voice logs: `[BRIDGE] Response received`
- Agent speaks the visual description

- [ ] **Step 5: Verify independence**

Kill video process (Ctrl+C in its terminal).
Expected: Voice agent continues working, says "Video feed unavailable" for visual questions.

- [ ] **Step 6: Commit + tag**

```bash
git add agent/voice_agent.py agent/video_agent.py agent/reasoning/analyst_bridge.py agent/main.py agent/adk_agents.py agent/config.py scripts/e2e.py tests/
git commit -m "feat: two-pipe architecture — voice + video as independent processes"
git tag -a v0.20 -m "v0.20 — two-pipe architecture: voice + video processes"
```
