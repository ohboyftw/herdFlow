---
description: Run the full pre-PR quality gate
---

Run the complete quality check for this project:

1. **Python format**: `uv run ruff format --check .`
2. **Python lint**: `uv run ruff check .`
3. **Python typecheck**: `uv run pyright`
4. **Python tests**: `uv run pytest`
5. **Frontend format**: `cd frontend && npx prettier --check .`
6. **Frontend lint**: `cd frontend && npx eslint .`
7. **Frontend typecheck**: `cd frontend && npx tsc --noEmit`
8. **Frontend tests**: `cd frontend && npx vitest run`

Format the output as a checklist with pass/fail status for each step.
If any step fails, explain the issue and suggest a fix.
If all pass, confirm the code is ready for PR.
