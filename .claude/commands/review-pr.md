---
description: Review the current diff for code quality and correctness
---

Review the current staged or unstaged git diff. Check for:

### Python Backend
- [ ] Type hints on all public functions
- [ ] No bare `except:` — catch specific exceptions
- [ ] Proper logging (not print)
- [ ] Context managers for resources
- [ ] No mutable default arguments
- [ ] Async functions properly awaited
- [ ] Pydantic/dataclass models for data schemas
- [ ] Scene graph changes backward-compatible or all references updated

### TypeScript Frontend
- [ ] No `any` types
- [ ] Proper error boundaries in React components
- [ ] Null checks on optional values
- [ ] async/await error handling (no unhandled promises)
- [ ] Test coverage for new components
- [ ] No console.log in production code
- [ ] LiveKit hooks properly cleaned up (useEffect returns)

### Cross-Cutting
- [ ] No secrets committed (.env, API keys)
- [ ] Scene graph schema changes reflected in both backend and frontend
- [ ] Alert models consistent across Python and TypeScript types
- [ ] Docker build not broken by new dependencies

Provide feedback organized by severity:
- Red (must fix): blocking issues
- Yellow (should fix): important but not blocking
- Green (nice to have): style and improvement suggestions
