# HerdFlow — Task Completion Checklist

When finishing a task, run these checks before committing:

1. **Format**: `uv run ruff format --check .`
2. **Lint**: `uv run ruff check .`
3. **Type check**: `uv run pyright` (for modified files at minimum)
4. **Tests**: `uv run pytest tests/ -v`
5. **If frontend changed**:
   - `cd frontend && npx prettier --check .`
   - `cd frontend && npx eslint .`
   - `cd frontend && npx tsc --noEmit`
   - `cd frontend && npx vitest run`
6. **If models.py changed**: Re-run `uv run python -m scripts.generate_types`
7. **Commit** with conventional commit message
