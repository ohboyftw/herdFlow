# HerdFlow — Google Cloud API Usage Proof

> **Gemini Live Agent Challenge — "Live Agents" Category**
> This document serves as proof of Google Cloud deployment and API usage.

## Summary

HerdFlow uses **6 Google Cloud services** across its two-pipe architecture (voice process + video process). All services are accessed via `GOOGLE_API_KEY` configured in `.env`.

---

## Google Cloud Services Used

### 1. Gemini 2.5 Flash Native Audio (Live API)

| | |
|---|---|
| **Service** | Gemini 2.5 Flash Native Audio — real-time bidirectional voice |
| **Model ID** | `gemini-2.5-flash-native-audio-preview-12-2025` |
| **File** | `agent/voice_agent.py` (line 191) |
| **SDK** | `google.adk.agents.Agent` — Google ADK |
| **Purpose** | Root voice agent: receives farmer speech as PCM audio, performs tool calling, responds with synthesized speech |

```python
# agent/voice_agent.py:189-199
adk_agent = Agent(
    name="herdflow",
    model="gemini-2.5-flash-native-audio-preview-12-2025",
    static_instruction=base_prompt + "\n\n" + tool_instruction,
    tools=herd_tools,
    sub_agents=sub_agents,
    before_model_callback=_inject_thinking_config,
    generate_content_config=genai_types.GenerateContentConfig(
        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
    ),
)
```

**Audio pipeline**: Farmer mic → LiveKit → PCM 16kHz → ADK `LiveRequestQueue` → Gemini Live API → PCM 24kHz → LiveKit → farmer speaker (`agent/voice_agent.py` lines 272-391).

---

### 2. Gemini 3 Flash (Vision — Background Summaries)

| | |
|---|---|
| **Service** | Gemini 3 Flash — multimodal vision model |
| **Model ID** | `gemini-3-flash-preview` |
| **File** | `agent/reasoning/video_analyst.py` (lines 79, 155, 298-310) |
| **SDK** | `google.genai.Client` — Google GenAI SDK |
| **Purpose** | Background scene analysis every 30s — sends JPEG frame + scene graph, receives 2-3 sentence summary |

```python
# agent/reasoning/video_analyst.py:298-310
response = await self._get_client().aio.models.generate_content(
    model=self.background_model,  # "gemini-3-flash-preview"
    contents=[
        types.Content(
            parts=[
                types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                types.Part.from_text(text=prompt),
            ]
        )
    ],
)
```

Also used for:
- **Zone detection** (`video_analyst.py` line 155) — identifies feed areas, water troughs, resting zones from first frame
- **Entity annotation** (`video_analyst.py` lines 224-236) — rich per-animal visual descriptions (color, posture, health)
- **Analyst sub-agent** (`voice_agent.py` line 164) — optional deep analysis agent

---

### 3. Gemini 3 Pro (Vision — On-Demand Deep Analysis)

| | |
|---|---|
| **Service** | Gemini 3 Pro — multimodal vision model (higher capability) |
| **Model ID** | `gemini-3-pro-preview` |
| **File** | `agent/reasoning/video_analyst.py` (lines 81, 355) |
| **SDK** | `google.genai.Client` — Google GenAI SDK |
| **Purpose** | On-demand deep visual analysis when farmer asks visual questions |

```python
# agent/reasoning/video_analyst.py:355-365
response = await self._get_client().aio.models.generate_content(
    model=self.on_demand_model,  # "gemini-3-pro-preview"
    contents=[
        types.Content(
            parts=[
                types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                types.Part.from_text(text=prompt),
            ]
        )
    ],
)
```

---

### 4. Google ADK (Agent Development Kit)

| | |
|---|---|
| **Service** | Google ADK — agent lifecycle management |
| **Packages** | `google.adk.agents`, `google.adk.runners`, `google.adk.sessions` |
| **File** | `agent/voice_agent.py` (lines 62-65) |
| **Purpose** | Full agent lifecycle: `Agent` definition, `Runner` execution, `LiveRequestQueue` for real-time audio, `InMemorySessionService` for session management |

```python
# agent/voice_agent.py:62-65
from google.adk.agents import Agent, LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
```

**Session rotation**: HerdFlow proactively rotates ADK sessions every 8 minutes to avoid Gemini Live's 10-minute hard deadline (`voice_agent.py` lines 107, 468-488).

---

### 5. Google GenAI SDK

| | |
|---|---|
| **Service** | Google GenAI Python SDK — unified API access |
| **Packages** | `google.genai`, `google.genai.types` |
| **Files** | `agent/voice_agent.py` (line 66), `agent/reasoning/video_analyst.py` (lines 101-103, 150, 207, 293, 353), `agent/adk_agents.py` (tool definitions) |
| **Purpose** | Content types (`Content`, `Part`, `Blob`), configuration (`GenerateContentConfig`, `ThinkingConfig`, `SpeechConfig`, `VoiceConfig`), and direct model API calls |

---

### 6. Google Cloud STT (Speech-to-Text)

| | |
|---|---|
| **Service** | Google Cloud Speech-to-Text via LiveKit plugin |
| **Package** | `livekit.plugins.google.STT` |
| **File** | `agent/voice_agent.py` (line 69, 401) |
| **Purpose** | Async transcription of farmer's speech — feeds conversation memory and publishes transcripts to frontend |

```python
# agent/voice_agent.py:69
from livekit.plugins.google import STT as GoogleSTT

# agent/voice_agent.py:401
stt = GoogleSTT(sample_rate=INPUT_SAMPLE_RATE)
```

---

### 7. Cloud Build (CI/CD)

| | |
|---|---|
| **Service** | Google Cloud Build |
| **File** | `cloudbuild.yaml` |
| **Purpose** | Docker image build and push to Google Container Registry |

```yaml
# cloudbuild.yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/herdflow-agent', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/herdflow-agent']
images:
  - 'gcr.io/$PROJECT_ID/herdflow-agent'
```

---

## Configuration

### API Key

All Google Cloud APIs authenticate via `GOOGLE_API_KEY` environment variable:

```bash
# .env.example
GOOGLE_API_KEY=
GOOGLE_CREDENTIALS_FILE=credentials.json
GEMINI_MODEL=gemini-3-flash-preview
```

Configuration is centralized in `agent/config.py` via Pydantic `BaseSettings`:

```python
# agent/config.py:15
google_api_key: str = ""

# agent/config.py:34-39
gemini_model: str = "gemini-3-flash-preview"
video_analyst_background_model: str = "gemini-3-flash-preview"
video_analyst_on_demand_model: str = "gemini-3-pro-preview"
```

### Deployment Target

- **Docker image**: `gcr.io/$PROJECT_ID/herdflow-agent` (multi-stage: Node 20 frontend + CUDA 12.4 backend)
- **Target**: Google Cloud Run (GPU) + GCE (LiveKit server)
- **Dockerfile**: Multi-stage build with `nvidia/cuda:12.4.1-runtime-ubuntu22.04` base

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Google Cloud Platform                         │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐  │
│  │ Cloud Build   │    │ Gemini API                           │  │
│  │ (CI/CD)      │    │                                      │  │
│  │              │    │  • 2.5 Flash Native Audio (Live API) │  │
│  └──────────────┘    │  • 3 Flash (vision summaries)        │  │
│                      │  • 3 Pro (deep visual analysis)      │  │
│                      │  • Cloud STT (transcription)         │  │
│                      └──────────────────────────────────────┘  │
│                              ▲                                  │
│                              │ GOOGLE_API_KEY                   │
│  ┌───────────────────────────┼──────────────────────────────┐  │
│  │ Cloud Run (GPU)           │                               │  │
│  │                           │                               │  │
│  │  ┌─────────────┐   ┌─────┴───────┐   ┌──────────────┐  │  │
│  │  │ Voice Agent  │   │ Video Agent  │   │ React        │  │  │
│  │  │ (ADK+Live)  │   │ (RF-DETR+   │   │ Frontend     │  │  │
│  │  │             │   │  Gemini 3)   │   │              │  │  │
│  │  └──────┬──────┘   └──────┬──────┘   └──────────────┘  │  │
│  │         │                 │                              │  │
│  │         └─────┬───────────┘                              │  │
│  │               │ LiveKit Data Channels                    │  │
│  │         ┌─────┴─────┐                                    │  │
│  │         │ LiveKit    │                                    │  │
│  │         │ Server     │                                    │  │
│  │         └────────────┘                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Evidence

See `docs/gcp_api_evidence.txt` for real log lines from live sessions showing:
- Gemini Live API connections (`google_genai._api_client` authentication)
- Gemini 3 Flash vision API calls (frame analysis with JPEG payloads)
- Google ADK tool calls routed through Gemini
- Google STT transcription events
- Entity annotation results from Gemini vision
