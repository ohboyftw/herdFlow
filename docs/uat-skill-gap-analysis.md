# UAT Skill Gap Analysis: Web App Testing vs. Real-Time Voice/Video Pipeline

**Date**: 2026-03-16
**Context**: Applied UAT skill to HerdFlow (LiveKit + Google ADK + Gemini Live voice/video pipeline)

## 1. What Worked from the Current Skill

- **Priority tiering (P0/P1/P2)** mapped cleanly. P0 for "does the pipeline start and connect," P1 for secondary features, P2 for subjective quality.
- **Pre-flight phase concept** was the most valuable part. Validating prerequisites before running anything saved significant debugging time.
- **Evidence collection pattern** carried over, though medium changed from screenshots to log pattern matches.
- **Structured test case JSON and report format** directly reusable.
- **Phased workflow** (discovery, generation, execution, reporting) provided useful mental model.

## 2. What Was Missing or Didn't Apply

- **Playwright is irrelevant** for voice/video/WebRTC. No pages, no DOM, no forms.
- **No "log-check" test type.** Verification is "does this regex appear in stdout within N seconds."
- **No sequential dependency chains.** Tests have strict ordering (agent registers → participant joins → audio bridge → greeting). No `depends_on` field.
- **No token/credential lifecycle management.** Need JWT expiry validation, service account checks, API key presence.
- **No "human-triggered, machine-verified" hybrid.** Human speaks, log pattern verifies tool call fired.
- **No process lifecycle management.** Skill assumes app is already running at a URL.
- **No media quality assessment.** Audio clarity, latency, naturalness have no Playwright equivalent.
- **No timeout/timing semantics.** Voice interactions have 5-15s latency. No `wait_for` pattern.

## 3. Specific Proposed Changes

### 3a. Skill Description

**Current:**
```
Generate and execute user acceptance tests from PRD acceptance criteria or
by crawling the application. Hybrid execution: golden-path scenarios run
fully automated via Playwright, edge cases flag manual checkpoints, UX
checks produce screenshot checklists for human review.
```

**Proposed:**
```
Generate and execute user acceptance tests from PRD acceptance criteria or
by analyzing the application. Hybrid execution: golden-path scenarios run
fully automated (via Playwright for web apps, or via log/process verification
for backend/real-time pipelines), edge cases flag manual checkpoints, UX/quality
checks produce human review checklists. Supports web apps, voice/video pipelines,
WebRTC systems, and headless services.
```

### 3b. Prerequisites

**Current:** Only checks Playwright installation.

**Proposed:** Determine application type and check appropriate toolchain:
- **Web app:** Playwright check (existing)
- **Pipeline/service:** Process management, credential validation, dependency imports, asset existence

### 3c. Phase 0 Pre-flight

**Current:** Playwright available → resolve URL → reachability check.

**Proposed:** Add pipeline path:
- Validate environment (.env exists, required vars non-empty)
- Validate credentials (service accounts, JWT expiry, API keys)
- Validate dependencies (Python packages importable, models available)
- Validate assets (data files exist, non-zero size)
- Validate import chain (main entrypoint imports without error)
- Generate standalone `preflight.py` with pass/fail per check
- Classify failures as CRITICAL (blocks testing) vs WARNING (proceed with caution)

### 3d. Phase 2 Generation

**Current:** Generate Playwright scripts only.

**Proposed:** Add pipeline mode:
- Test cases specify `type`: "automated", "manual", or "log-check"
- `log_pattern` (regex) for machine-verifiable assertions
- `verification` (human-readable pass description)
- Tests ordered by `depends_on` for startup cascades
- Evidence captured as log excerpts, not screenshots

### 3e. Phase 3 Execution

**Current:** Run P0 → P1 → P2 with Playwright.

**Proposed pipeline execution:**
- Start application process, capture stdout/stderr to log file
- "automated"/"log-check" tests: tail log, match regex within timeout
- "manual" tests: print instructions, wait for human action, verify via log pattern
- Respect `depends_on` ordering — skip downstream if upstream failed
- Session tests: prompt human to keep active, set timer, check for crash indicators

## 4. New Sections to Add

### 4a. Application Type Detection

| Signal | Type | Execution Engine |
|--------|------|-----------------|
| User provides a URL | Web App | Playwright browser automation |
| User provides startup command, no web UI | Pipeline/Service | Process management + log verification |
| App uses WebRTC/LiveKit/voice/video | Real-Time Pipeline | Process + manual interaction + log verification |

### 4b. Manual Interaction Protocol

For tests requiring human interaction (voice input, physical actions):
1. Print clear instructions: what to do, what to say, what to observe
2. Wait for human confirmation: `[Press Enter when done, or 's' to skip]`
3. After human acts, run automated verification (log pattern match) if available
4. If no automated verification, ask: `Did you observe [expected behavior]? (y/n)`
5. Record human's answer as evidence alongside log excerpts

### 4c. Credential & Token Lifecycle

- Pre-flight validates token existence, format, and expiry
- JWT tokens: decode payload, check `exp` claim. If expired, block with regen instructions
- API keys: validate non-empty and correct length/prefix
- Service account files: validate JSON structure, required fields
- Expiry warnings: <1 hour = warn, expired = block

### 4d. Process Lifecycle Management

1. **Start**: launch process, redirect stdout+stderr to `tests/uat/evidence/session.log`
2. **Readiness**: wait for readiness log pattern with timeout. If not seen, fail pre-flight
3. **During tests**: continuously capture logs, demarcate each test's log window by timestamp
4. **Teardown**: send SIGTERM, wait for graceful shutdown, capture final log lines

### 4e. Quality Assessment Rubric (P2)

| Dimension | 1 (Fail) | 3 (Acceptable) | 5 (Excellent) |
|-----------|----------|-----------------|---------------|
| Audio clarity | Unintelligible | Understandable with effort | Natural, clear |
| Response latency | >15s or no response | 5-15s | <5s |
| Conversation coherence | Off-topic or confused | Relevant but generic | Contextually aware |
| Video awareness | Ignores video entirely | Acknowledges but vague | Describes specific details |
| Session stability | Crashes within 1 min | Occasional glitches | Smooth for 5+ min |

Human reviewer assigns scores. Average >= 3 per dimension = pass.

## 5. Schema Extensions

### New fields for test case schema

```json
{
  "type": "automated | manual | log-check",
  "log_pattern": "regex or null",
  "depends_on": ["UAT-003", "UAT-004"],
  "timeout_seconds": 30,
  "verification": "Human-readable pass description",
  "checkpoint": "none | screenshot | observe | listen | log-excerpt"
}
```

### Top-level metadata extension

```json
{
  "app_type": "pipeline",
  "startup_command": "uv run python -m agent.main dev",
  "readiness_pattern": "worker registered",
  "log_file": "tests/uat/evidence/session.log",
  "token_sources": [
    {"name": "LiveKit JWT", "location": "frontend/public/test.html", "pattern": "const TOKEN = '([^']+)'"}
  ]
}
```

## Summary

The current UAT skill is solid for Playwright-driven web app testing. ~40% of concepts transferred directly. The remaining 60% needs adaptation for the "application is a process, not a page" paradigm. The three biggest gaps are: (1) no log-based verification engine, (2) no dependency/ordering between test cases, (3) no credential lifecycle management. The proposed changes make the skill polymorphic across web apps and real-time pipelines without breaking the existing web app path.
