---
name: project-dev
description: >
  Core development knowledge for HerdFlow. Covers build system, testing,
  coding patterns, and feature workflow for Python/LiveKit + React/TypeScript.
  Use when writing code, adding features, fixing bugs, running tests, or
  discussing project internals.
---

# HerdFlow Development Guide

## Build and Test

```bash
# Backend
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright

# Frontend
cd frontend && npm install
npx vitest run
npx eslint .
npx prettier --check .
npx tsc --noEmit

# Full quality gate
uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest && cd frontend && npx prettier --check . && npx eslint . && npx tsc --noEmit && npx vitest run
```

## Adding a New Feature

1. Create branch: `git checkout -b feature/<name>`
2. **Backend**: Add module in `agent/` following the three-tier pattern (perception → reasoning → communication)
3. **Frontend**: Add component in `frontend/src/components/`, hook in `frontend/src/hooks/`
4. Write tests:
   - Python: `tests/test_<module>.py` using pytest + anyio for async
   - TypeScript: co-located `*.test.tsx` or in `__tests__/`
5. Run full quality gate
6. Commit with conventional commit message

## Testing

### Backend (Python)
- Location: `tests/`
- Framework: pytest with anyio for async tests
- Single test: `uv run pytest tests/test_file.py -k test_name`
- Pattern: Given/When/Then with descriptive test names
- Mock external APIs (Gemini, LiveKit) but test perception pipeline with real numpy arrays

### Frontend (TypeScript)
- Location: co-located `*.test.tsx` files
- Framework: vitest + @testing-library/react
- Single test: `cd frontend && npx vitest run src/path/to/test`
- Pattern: Render → interact → assert on DOM

## Code Review Criteria

### Python Backend
- [ ] Type hints on all public functions
- [ ] No bare `except:` — catch specific exceptions
- [ ] Proper logging (not print)
- [ ] Context managers for resources (DB connections, file handles)
- [ ] No mutable default arguments
- [ ] f-strings over .format()
- [ ] Async functions properly awaited
- [ ] Pydantic/dataclass models for data schemas

### TypeScript Frontend
- [ ] No `any` types
- [ ] Proper error boundaries in React components
- [ ] Null checks on optional values
- [ ] async/await error handling (no unhandled promises)
- [ ] Test coverage for new components
- [ ] No console.log in production code
- [ ] LiveKit hooks properly cleaned up (useEffect returns)
