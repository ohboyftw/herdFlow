---
description: Scaffold a new feature following project patterns
allowed-tools: Bash, Read, Write, Edit
---

Scaffold a new feature: $ARGUMENTS

1. Analyze existing code patterns in the project
2. Create the necessary files following the three-tier architecture:
   - **Perception** (agent/perception/): detection/tracking modules
   - **Reasoning** (agent/reasoning/): Gemini integration, sampling, tools
   - **Alerts** (agent/alerts/): rule definitions, alert models
   - **Storage** (agent/storage/): database models, history queries
   - **Frontend** (frontend/src/components/): React components with LiveKit hooks
3. Add corresponding tests:
   - Python: `tests/test_<module>.py` using pytest
   - TypeScript: co-located `*.test.tsx` using vitest
4. Run `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest && cd frontend && npx prettier --check . && npx eslint . && npx tsc --noEmit && npx vitest run`
5. Show a summary of files created
