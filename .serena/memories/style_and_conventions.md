# HerdFlow — Code Style & Conventions

## Python
- **Python 3.12+** with `from __future__ import annotations`
- **Type hints** on ALL public functions
- **Pydantic v2** for serialization models, `dataclass` for in-process-only types
- **ruff** for linting and formatting (line-length=100, target py312)
- **ruff lint rules**: E, F, I, N, UP, B, A, SIM
- Use `datetime.UTC` (not `timezone.utc`) per UP017 rule
- Use `X | None` (not `Optional[X]`) per UP045 rule
- **async/await** throughout — asyncio for backend
- **Functional patterns** preferred over heavy OOP; composition over inheritance
- **Files under 400 lines**
- **Explicit error handling** — no bare try/except
- **No secrets in code** — use `.env` files

## TypeScript/React
- **React 18** with functional components and hooks
- **TypeScript strict mode**
- **Tailwind CSS 3.x** for styling
- **eslint + prettier** for linting/formatting
- Types auto-generated from Python models — don't edit `generated.ts` manually

## Testing
- **pytest** with `asyncio_mode = "auto"`
- Contract-first: tests define the interface, implementation matches
- TDD for new features: failing test → implement → pass
- Test files alongside source for unit tests, `tests/` dir for integration

## Commits
- Conventional commits: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`
