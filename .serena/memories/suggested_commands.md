# HerdFlow — Development Commands

System: Windows 11, Git Bash available. Use `uv` for Python, `npm` for frontend.

## Backend (Python)
- **Install deps**: `uv sync --dev`
- **Run tests**: `uv run pytest tests/ -v`
- **Run single test**: `uv run pytest tests/test_file.py -k test_name`
- **Lint**: `uv run ruff check .`
- **Lint fix**: `uv run ruff check . --fix`
- **Format**: `uv run ruff format .`
- **Format check**: `uv run ruff format --check .`
- **Type check**: `uv run pyright`
- **Run agent**: `uv run python -m agent.main`
- **Generate TS types**: `uv run python -m scripts.generate_types`
- **Verify config**: `uv run python -c "from agent.config import settings; print(settings.rfdetr_model)"`

## Frontend (TypeScript/React)
- **Install**: `cd frontend && npm install`
- **Dev server**: `cd frontend && npm run dev`
- **Build**: `cd frontend && npm run build`
- **Test**: `cd frontend && npx vitest run`
- **Lint**: `cd frontend && npx eslint .`
- **Format check**: `cd frontend && npx prettier --check .`
- **Type check**: `cd frontend && npx tsc --noEmit`

## Full Quality Gate (Pre-PR)
```bash
uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest && cd frontend && npx prettier --check . && npx eslint . && npx tsc --noEmit && npx vitest run
```

## Git / System
- `git status`, `git log --oneline -10`, `git diff`
- Conventional commits: `feat:`, `fix:`, `chore:`, `refactor:`
