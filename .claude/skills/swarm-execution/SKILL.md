---
name: swarm-execution
description: >
  Execute implementation plans using hybrid sequential+parallel strategy. Combines
  superpowers review discipline (implementer, spec-review, quality-review per task)
  with psmux/tmux swarm parallelism (TeammateTool, git worktrees, Pi agents) at
  plan-marked PARALLEL SWARM boundaries. Use when executing plans that have both
  sequential and parallel task groups.
---

# Swarm-Aware Plan Execution

Hybrid execution engine: superpowers review discipline for sequential tasks,
psmux swarm parallelism for independent tasks, automatic mode switching at
plan-marked boundaries.

## When to Use

- You have an implementation plan with `PARALLEL SWARM` markers
- The project has `.claude/skills/swarm-orchestrator/` and `.claude/skills/pi-dispatch/`
- You're running inside a psmux/tmux session (check: `echo $TMUX`)
- The plan has a "Swarm Agent Assignment" table

If no `PARALLEL SWARM` markers exist, fall back to standard
`superpowers:subagent-driven-development` (sequential with review).

## Execution Modes

### Mode 1: Sequential (superpowers-style)

For tasks that depend on each other or share state.

**Per task:**
1. Dispatch **implementer subagent** (fresh context, full task text from plan)
2. Handle status: DONE → review, NEEDS_CONTEXT → provide and re-dispatch, BLOCKED → escalate
3. Dispatch **spec compliance reviewer** (verify code matches requirements)
4. If issues → implementer fixes → re-review until approved
5. Dispatch **code quality reviewer** (verify clean, tested, maintainable)
6. If issues → implementer fixes → re-review until approved
7. Mark task complete, move to next

### Mode 2: Parallel Swarm

For task groups marked `PARALLEL SWARM` in the plan's dependency graph.

**Setup:**
```bash
# 1. Create worktrees per task (from plan's Swarm Agent Assignment table)
git worktree add .worktrees/<task-name> -b agent/<task-name>

# 2. Create team
# TeamCreate({ team_name: "<project-slug>" })

# 3. Create tasks with dependencies
# TaskCreate({ subject: "...", description: "..." })
# TaskUpdate({ taskId: "N", addBlockedBy: ["dep1", "dep2"] })
```

**Dispatch agents based on assignment table:**

| Assignment | How to Dispatch |
|-----------|----------------|
| Claude Code in worktree | `Agent({ prompt: "...", isolation: "worktree", mode: "auto" })` |
| Pi via pi-bridge.ps1 | `Bash({ command: "pwsh .claude/skills/pi-dispatch/scripts/pi-bridge.ps1 -TeamName '<slug>' -AgentName 'pi-<name>' -Prompt '<task text>' -WorkDir '.worktrees/<name>' -TaskId '<id>'" })` |
| Claude Code (main) | `Agent({ prompt: "...", mode: "auto" })` |

**Agent prompt template for swarm workers:**
```
You are a builder agent for [PROJECT]. Working in: [worktree path]

## Task
[FULL TEXT of task from plan — paste it, don't reference files]

## Rules
1. Only modify files in your assigned worktree
2. Follow TDD: write failing test → implement → verify pass
3. Run quality checks before reporting done:
   [project-specific check command]
4. Report back with:
   - Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
   - What you implemented
   - Test results
   - Files changed
   - Any concerns

## Context
[Scene-setting: where this fits, what other parallel agents are doing,
 what contracts/interfaces to respect]
```

**Pi agent prompt additions:**
```
You are a focused single-file implementer. Work fast, stay narrow.
Only touch the files listed in the task.
Do NOT refactor surrounding code.
Do NOT add features beyond what's specified.
```

**Monitor progress:**
- Check `TaskList()` for status updates
- Check TeammateTool inbox for Pi agent completions
- Don't poll — you'll be notified on completion

**After all parallel tasks complete:**
```bash
# Merge in dependency order (from plan)
git merge agent/<task-1>
git merge agent/<task-2>
# ... etc

# Run full quality check
[project-specific full check command]

# Cleanup
git worktree remove .worktrees/<task-1>
git worktree remove .worktrees/<task-2>
```

**Post-merge reviewer checkpoint:**

Dispatch a reviewer agent after every swarm merge. Use the reviewer persona
from `.claude/agents/reviewer.md`:

```
Agent({
  subagent_type: "general-purpose",
  prompt: "You are a code reviewer. Review the merged work from swarm tasks
           [list task names]. Use the checklist from .claude/agents/reviewer.md.
           Check for: cross-task interface consistency, no merge conflicts in
           logic, contracts still satisfied, tests still passing.
           Read the actual code — do not trust task reports.
           Report: APPROVED | CHANGES REQUESTED with specific issues."
})
```

If CHANGES REQUESTED → dispatch fix agent → re-review → repeat until APPROVED.

### Mode 3: Explorer Pre-Scan

Before entering a parallel swarm, optionally dispatch an explorer agent
(fast, read-only, Haiku model) to verify contract alignment:

```
Agent({
  subagent_type: "Explore",
  model: "haiku",
  prompt: "Scan [files] and verify [contracts]. Report mismatches with file:line."
})
```

## Mode Switching Protocol

Read the plan's dependency graph. Execute as follows:

```
For each chunk in plan:
  If chunk has no PARALLEL SWARM marker:
    → Mode 1 (Sequential): execute tasks one-by-one with review discipline

  If chunk has PARALLEL SWARM marker:
    → Mode 3 (Explorer): optional pre-scan for contract alignment
    → Mode 2 (Parallel Swarm): dispatch all independent tasks simultaneously
    → Wait for all tasks to complete
    → Merge in dependency order
    → Run full quality check
    → Dispatch reviewer checkpoint
    → If reviewer approves: continue to next chunk
    → If reviewer requests changes: dispatch fix agent, re-review

  If chunk has tasks that depend on parallel tasks completing:
    → Wait for swarm + review to finish
    → Switch back to Mode 1 for dependent tasks
```

## Model Selection for Agents

| Agent Role | Model | Why |
|-----------|-------|-----|
| Implementer (1-2 files, clear spec) | sonnet or haiku | Fast, cheap, mechanical |
| Implementer (multi-file, integration) | sonnet | Needs more context |
| Implementer (architecture, judgment) | opus | Design decisions |
| Pi agent (single file) | Pi default | Cheapest option |
| Spec compliance reviewer | sonnet | Reading + comparing |
| Code quality reviewer | superpowers:code-reviewer | Uses dedicated agent type |
| Post-merge reviewer | sonnet | Cross-file review |
| Explorer pre-scan | haiku | Read-only, speed matters |

## Concrete Example: HerdFlow Plan

```
Chunk 1-3 (Tasks 1-12): MODE 1 SEQUENTIAL
  → Each task: implementer → spec-review → quality-review → commit
  → Sequential because each builds on the last

PARALLEL SWARM 1 (Tasks 13, 15, 16):
  → Explorer pre-scan: verify models.py contracts
  → Create worktrees: detector, alerts, sampler
  → Dispatch:
    - Task 13 (detector): Claude Code in .worktrees/detector
    - Task 15 (alerts): Pi via pi-bridge.ps1 in .worktrees/alerts
    - Task 16 (sampler): Pi via pi-bridge.ps1 in .worktrees/sampler
  → Wait for all 3
  → Merge: detector, alerts, sampler
  → Run: uv run pytest tests/ -v

Task 14 (depends on 13+15): MODE 1 SEQUENTIAL
  → implementer → spec-review → quality-review → commit
  → Merge task-14 branch

REVIEWER CHECKPOINT R1:
  → Dispatch reviewer: check merged perception + alerts code
  → Must APPROVE before continuing

Task 17, 17b: MODE 1 SEQUENTIAL
  → Wire pipeline, SQLite history

PARALLEL SWARM 2 (Tasks 18, 19, 21):
  → Create worktrees: frontend-polish, deploy
  → Dispatch:
    - Task 18 (frontend): Claude Code in .worktrees/frontend-polish
    - Task 19 (deploy): Claude Code in .worktrees/deploy
    - Task 21 (README): Pi via pi-bridge.ps1 on main
  → Wait, merge, quality check

REVIEWER CHECKPOINT R2:
  → Dispatch reviewer
  → Must APPROVE before demo

Task 20 (demo): HUMAN
```

## Red Flags

**Never:**
- Dispatch parallel agents to the SAME worktree
- Skip the post-merge reviewer checkpoint
- Let Pi agents touch files outside their assignment
- Start a swarm without creating worktrees first
- Merge without running the full quality check
- Skip spec compliance review — even for Pi agent output
- Modify the plan's dependency order without human approval

**If a swarm agent fails:**
1. Check if it's a context problem → re-dispatch with more context
2. Check if it's too complex for Pi → re-dispatch as Claude Code
3. Check if it conflicts with another agent's work → serialize instead
4. If truly blocked → escalate to human

## Integration with Superpowers

This skill **composes with**, not replaces, superpowers skills:

| Superpowers Skill | How This Skill Uses It |
|-------------------|----------------------|
| `subagent-driven-development` | Mode 1 follows its exact protocol for sequential tasks |
| `dispatching-parallel-agents` | Mode 2 extends it with worktrees + Pi + TeammateTool |
| `test-driven-development` | All agents (sequential and parallel) follow TDD |
| `verification-before-completion` | Post-merge quality check before claiming done |
| `using-git-worktrees` | Worktree creation/cleanup for parallel agents |
| `requesting-code-review` | Reviewer checkpoint template |
| `finishing-a-development-branch` | After all tasks complete |

Superpowers prompt templates are referenced directly:
- Implementer: `superpowers/.../implementer-prompt.md` pattern
- Spec reviewer: `superpowers/.../spec-reviewer-prompt.md` pattern
- Code quality: `superpowers/.../code-quality-reviewer-prompt.md` pattern

These are **patterns**, not file reads — the controller constructs prompts
following these templates, filling in task-specific context.
