# UAT Report — ADK+LiveKit E2E

**Date**: YYYY-MM-DD HH:MM IST
**Branch**: gemini3-stt-tts
**Commit**: (git rev)
**Tester**: Aravind

## Summary
- P0 (Golden Path): _/7 passed
- P1 (Edge Cases): _/5 passed
- P2 (UX Observation): _/1 reviewed

## Pre-flight
Run: `uv run python tests/uat/preflight.py`
Result: (paste output)

## P0 Results — Golden Path (all must pass)

| ID | Title | Status | Evidence |
|----|-------|--------|----------|
| UAT-001 | Agent process starts | | Log: `HerdFlow started` |
| UAT-002 | RF-DETR detector loads | | Log: `detector=RFDETRDetector` |
| UAT-003 | Agent registers with LiveKit | | Log: `worker registered` |
| UAT-004 | Participant joins | | Log: `Participant joined: farmer` |
| UAT-005 | Audio input bridge connects | | Log: `[BRIDGE] Subscribed` |
| UAT-006 | Agent greets farmer (AUDIO) | | Heard greeting? Y/N |
| UAT-013 | Session survives 2+ min | | Duration: ___s |

## P0 Tool Calls — Voice-triggered

| ID | Title | Spoken Prompt | Status | Evidence |
|----|-------|--------------|--------|----------|
| UAT-007 | search_entity_history | "How is cow three doing?" | | Log: `[ADK] Tool call: search_entity_history` |

## P1 Results — Edge Cases

| ID | Title | Status | Notes |
|----|-------|--------|-------|
| UAT-008 | get_herd_stats via voice | | "How many cows have fed today?" |
| UAT-009 | Video frames to Gemini | | Log: `[VIDEO] Sent frame` |
| UAT-010 | Agent describes scene | | "What do you see right now?" |
| UAT-011 | Data channel: scene_graph | | test.html data panel |
| UAT-012 | Data channel: overlay | | test.html data panel |

## P1 Context Compression

| ID | Title | Status | Notes |
|----|-------|--------|-------|
| UAT-014 | No context window crash | | Session alive after 2+ min |

## P2 — UX Observation

| ID | Title | Status | Notes |
|----|-------|--------|-------|
| UAT-015 | Proactive alert | | Agent spontaneously spoke? |

## Failure Analysis
(Fill in if any P0 fails)

**Failure ID**:
**Log excerpt**:
**Root cause hypothesis**:
**Fix attempted**:

## Audio Quality Notes
- Latency (farmer speaks → agent responds): ___s
- Audio clarity: (clear / garbled / silent)
- Voice naturalness: (natural / robotic / glitchy)

## Session Log
(Attach or paste relevant log lines)
