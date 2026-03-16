# Async Video Analyst Design

**Date**: 2026-03-16
**Status**: Approved
**Author**: Aravind + Claude

## Problem

Sending video JPEG frames directly to the Gemini Live session via `live_queue.send_realtime()` causes a 1007 "invalid argument" crash. The voice agent is currently blind — it answers only from hardcoded mock tool data, never from what's actually in the video.

## Solution

Replace real-time video-to-Gemini-Live with an async video analyst that:
1. Runs background summaries every 30s via Gemini 3 Flash (cheap, fast)
2. Provides on-demand deep analysis via Gemini 3 Pro (when farmer asks)
3. Exposes both capabilities as tools the voice agent can call

## Architecture

```
Camera → FileVideoSource → RF-DETR → SceneGraph → data channels (frontend)
                                          ↓
                    ┌─────────────────────────────────┐
                    │     VideoAnalyst (async)         │
                    │                                  │
                    │  Background (every 30s):         │
                    │    Latest frame + SceneGraph     │
                    │    → Gemini 3 Flash              │
                    │    → 2-3 sentence summary        │
                    │    → stored in shared state      │
                    │                                  │
                    │  On-demand (tool call):          │
                    │    Latest frame + SceneGraph     │
                    │    + farmer's question           │
                    │    → Gemini 3 Pro                │
                    │    → detailed visual analysis    │
                    │    → returned to voice agent     │
                    └─────────────────────────────────┘
                                    ↓
Voice Agent tools:
  get_scene_summary()      → latest background summary (instant)
  analyze_frame(question)  → on-demand Gemini 3 Pro (3-10s)
```

## Components

### 1. VideoAnalyst class

**File**: `agent/reasoning/video_analyst.py` (new)

```python
class VideoAnalyst:
    """Async video analysis — background summaries + on-demand deep analysis."""

    def __init__(
        self,
        background_model: str = "gemini-3-flash-preview",
        on_demand_model: str = "gemini-3-pro-preview",
        summary_interval_s: float = 30.0,
    ):
        ...
```

**State**:
- `latest_frame: np.ndarray | None` — updated by perception_loop every 2s
- `latest_scene_graph: SceneGraph | None` — updated alongside frame
- `latest_summary: str` — background summary, updated every 30s
- `_summary_lock: asyncio.Lock` — prevents concurrent summary writes

**Methods**:
- `update(frame, scene_graph)` — called by perception_loop, synchronous attribute assignment (no await between frame and SG — safe in single-threaded asyncio without locks)
- `run_background_loop()` — async task, every 30s:
  1. If `latest_frame` is None: set summary to text-only from scene graph, or "No video feed available" if both None. Skip API call.
  2. Encode frame as JPEG (640x360, quality 40)
  3. Call Gemini 3 Flash with prompt: "Describe what you see in this livestock camera frame. Focus on animal posture, behavior, and anything unusual. Be concise (2-3 sentences)." + scene graph JSON for context
  4. Store result in `latest_summary`
  5. On API failure: format scene graph as plain text fallback
- `get_summary() -> str` — returns latest_summary (instant, no API call)
- `analyze(question: str) -> str` — on-demand:
  1. If `latest_frame` is None: return "No video feed available — here's the scene data: {scene graph text}"
  2. If `_analyzing` flag is True (call already in flight): return previous result with note "Analysis in progress, showing last result"
  3. Set `_analyzing = True`
  4. Encode frame as JPEG (640x360, quality 80 — high quality for deep analysis)
  5. Call Gemini 3 Pro with: farmer's question + JPEG + scene graph JSON
  6. Set `_analyzing = False`, return the analysis text

**API usage**: Direct `google.genai.Client().models.generate_content()` — NOT the Live API. Standard request-response, no WebSocket.

### 2. Tool functions

**File**: `agent/adk_agents.py` (add to existing)

```python
# Module-level reference, set by entrypoint
_video_analyst: VideoAnalyst | None = None

def set_video_analyst(analyst: VideoAnalyst) -> None:
    global _video_analyst
    _video_analyst = analyst

async def get_scene_summary() -> dict:
    """Get the latest visual summary of the camera feed.
    Returns a 2-3 sentence description of what the camera currently shows."""
    if _video_analyst is None:
        logger.warning("get_scene_summary called but video analyst not initialized")
        return {"summary": "Video analyst not available."}
    return {"summary": _video_analyst.get_summary()}

async def analyze_frame(question: str) -> dict:
    """Analyze the current camera frame to answer a specific visual question.
    Use for detailed questions like 'what is cow three doing' or 'describe the herd'."""
    if _video_analyst is None:
        logger.warning("analyze_frame called but video analyst not initialized")
        return {"analysis": "Video analyst not available."}
    result = await _video_analyst.analyze(question)
    return {"analysis": result}
```

**Note on ADK tool execution**: ADK runs tool calls asynchronously — the audio stream continues while a tool awaits its response. The `analyze_frame` call (3-10s) does NOT block the voice session. The voice agent can say "Let me take a look..." while waiting.

### 3. Changes to perception_loop

- Remove all `live_queue.send_realtime(Blob(mime_type="image/jpeg"...))` code
- Remove `live_queue` parameter entirely
- Add `video_analyst: VideoAnalyst | None = None` parameter
- Each iteration: call `video_analyst.update(frame, sg)` to share latest frame/SG

### 4. Changes to entrypoint

- Create `VideoAnalyst()` instance
- Call `set_video_analyst(analyst)` to wire tools
- Start `asyncio.create_task(analyst.run_background_loop())`
- Pass `video_analyst` to `perception_loop` instead of `live_queue`
- Add `get_scene_summary` and `analyze_frame` to `herd_tools` list
- Remove `live_queue` from perception_loop call

### 5. Prompt changes

Add to voice agent prompt:
```
VISUAL AWARENESS:
You have access to a camera feed watching the herd. Use your tools:
- get_scene_summary: Quick overview of what the camera currently shows (instant).
- analyze_frame: Ask a specific visual question about the current frame (takes a few seconds).
When the farmer asks "what do you see?" or about a specific animal's appearance,
use these tools. Say "Let me take a look..." while waiting for the analysis.
```

## Models

| Purpose | Model | Frequency | Latency | Cost |
|---------|-------|-----------|---------|------|
| Background summary | gemini-3-flash-preview | Every 30s | 1-2s | ~$0.01-0.05/hr |
| On-demand analysis | gemini-3-pro-preview | On farmer request | 3-10s | ~$0.05-0.15/call |
| Voice agent | gemini-2.5-flash-native-audio | Continuous | Real-time | Existing |

## What this fixes

- **1007 error eliminated** — no video frames in the Gemini Live session
- **Voice agent gains visual awareness** — can describe the scene via tools
- **Session stability** — Live session handles audio only, much more stable
- **Hackathon demo** — farmer asks "what do you see?" and gets a real description

## What stays the same

- Audio bridge (bidirectional, working)
- Perception pipeline + data channels to frontend (working)
- Existing 4 mock tools (unchanged for now)
- Frontend React app (unchanged)
- AlertRuleEngine (deterministic Python, unchanged)

## Testing

- Unit test: `VideoAnalyst.get_summary()` returns formatted scene graph when no LLM available
- Unit test: `analyze_frame()` tool returns dict with "analysis" key
- Integration: start agent, ask "what do you see?" — verify tool call fires and agent speaks description
- Background loop: verify summary updates every ~30s in logs

## Config

Add to `agent/config.py`:
```python
# Video Analyst
video_analyst_background_model: str = "gemini-3-flash-preview"
video_analyst_on_demand_model: str = "gemini-3-pro-preview"
video_analyst_summary_interval_s: float = 30.0
```

## File changes summary

| File | Change |
|------|--------|
| `agent/reasoning/video_analyst.py` | NEW — VideoAnalyst class |
| `agent/adk_agents.py` | ADD get_scene_summary, analyze_frame tools + set_video_analyst |
| `agent/main.py` | MODIFY entrypoint + perception_loop |
| `agent/reasoning/prompts.py` | UPDATE persona (remove "live camera" claim), ADD VISUAL AWARENESS section |
| `agent/config.py` | ADD 3 video analyst config fields |
| `agent/main.py` | REMOVE scene_queue + sampler (dead code with video disabled) |
