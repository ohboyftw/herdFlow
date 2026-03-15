---
name: swarm-orchestrator
description: >
  Multi-agent swarm orchestration for HerdFlow using TeammateTool and
  git worktrees. Use when the user wants parallel agents, says "spawn swarm",
  "multi-agent", "parallel work", or any request to split work across agents.
---

# Swarm Orchestration for HerdFlow

## Leader Workflow

### 1. Decompose
Break task into independent subtasks scoped to specific files/modules.
HerdFlow natural boundaries: perception/, reasoning/, alerts/, storage/, frontend/components/, frontend/hooks/.

### 2. Create Worktrees
```bash
git worktree add .worktrees/task-1 -b agent/task-1
git worktree add .worktrees/task-2 -b agent/task-2
```

### 3. Create Team and Tasks
```
Teammate({ operation: "spawnTeam", team_name: "herdflow" })
TaskCreate({ subject: "...", description: "...", activeForm: "..." })
# Set dependencies for review task
TaskUpdate({ taskId: "N", addBlockedBy: ["1", "2"] })
```

### 4. Spawn Agents
- Complex multi-file work → Claude Code `general-purpose`
- Focused single-file work → Pi agent via Bash subagent
- Codebase scanning → Claude Code `Explore` (Haiku)

### 5. Merge and Verify
```bash
git merge agent/task-1
git merge agent/task-2
uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest && cd frontend && npx prettier --check . && npx eslint . && npx tsc --noEmit && npx vitest run
git worktree remove .worktrees/task-1
git worktree remove .worktrees/task-2
```

### 6. Handle Failures
If tests fail: identify which task broke it, create fix task, spawn new agent.

## Agent Routing for HerdFlow

| Task | Agent | Why |
|------|-------|-----|
| New perception module | Claude Code | Multi-file, needs architecture context |
| Frontend component | Claude Code | React + LiveKit integration |
| Alert rule addition | Pi | Single file, pattern-based |
| Test writing (unit) | Pi | Focused, single test file |
| Test writing (integration) | Claude Code | Needs perception pipeline context |
| Scene graph schema change | Claude Code | Cascading changes across tiers |
| Code review | Claude Code | Judgment-heavy |
| Prompt engineering | Pi | Single file (prompts.py) |
| Docker/deployment | Pi | Mechanical config |
