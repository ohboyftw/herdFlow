---
description: Launch a multi-agent swarm to work on a task in parallel
allowed-tools: Bash, Read, Write, Edit, Task, Teammate, TaskCreate, TaskUpdate, TaskList
---

Launch a multi-agent swarm: $ARGUMENTS

Load the swarm-orchestrator skill and follow its workflow:

1. Decompose into 2-5 independent subtasks
2. Create git worktrees per subtask
3. Create TeammateTool team and tasks with dependencies
4. Route agents (Claude Code for complex, Pi for focused)
5. Spawn agents, stagger to avoid rate limits
6. Monitor inbox and task status
7. Review and merge when complete
8. Run full CI: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest && cd frontend && npx prettier --check . && npx eslint . && npx tsc --noEmit && npx vitest run`
9. Create fix tasks for any failures
10. Cleanup: shutdown teammates, remove worktrees
