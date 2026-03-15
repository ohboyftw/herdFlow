---
name: pi-dispatch
description: >
  Bridge Pi coding agents into Claude Code TeammateTool inboxes. Use when
  spawning Pi agents as part of a swarm, routing simple tasks to Pi, or
  discussing multi-model agent orchestration.
---

# Pi Agent Dispatch Bridge

Pi agents do not know about TeammateTool inboxes. This skill bridges them.

## Usage

Wrap Pi invocations with the bridge script:

```bash
pwsh .claude/skills/pi-dispatch/scripts/pi-bridge.ps1 \
  -TeamName "herdflow" \
  -AgentName "pi-worker-1" \
  -Prompt "Your task description" \
  -WorkDir ".worktrees/task-name" \
  -TaskId "3"
```

The bridge runs Pi, captures output, and writes completion to the leader inbox.

## When to Use Pi vs Claude Code

Pi is better when: task is 1-3 files, straightforward implementation, you want
speed, or you are hitting Claude API rate limits.

Claude Code is better when: task needs many tools, architectural decisions,
full project context, or judgment-heavy review.
