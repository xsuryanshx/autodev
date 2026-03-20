---
name: opencode-executor
description: "OpenCode backend that spawns 'opencode run' as BACKGROUND subprocesses in isolated git worktrees. Manages a pool of concurrent agents, handles retries with learnings, and persists errors to error-history.json."
---

# OpenCode Executor

## Overview

Spawns `opencode run` as **background subprocesses** (detached `subprocess.Popen`) in isolated git worktrees. Manages a pool of concurrent agents, handles retry with learned context, and persists errors to `.autodev/error-history.json`.

**Key design:**
- Background agents = detached subprocesses, not Claude Code subagents
- Each agent runs in its own worktree (isolation via git worktree)
- Pool size limited by `max_parallel_agents` config
- All agents run truly in parallel (not sequential)

## Key Methods

### init(config: dict)

Initialize with config from `.autodev/config.json`.

### spawn_worktree(agent_id: string, branch: string, repo_path: string) -> dict

Create worktree and spawn background opencode agent. **CRITICAL SEQUENCE:**
1. Push branch to origin FIRST (prevents git lock errors)
2. Create worktree with remote tracking
3. Spawn background agent in worktree

### send_message(agent_id: string, message: string) -> dict

Send prompt to background agent, collect result. Prepends learnings if available.

### spawn_and_run_parallel(tasks: list, repo_path: str) -> list

Main entry point. Spawns multiple background agents in parallel, each in its own worktree.

## Error Classification

- `syntax` — Python syntax errors, retryable
- `import` — Module not found, retryable
- `test` — Test failures, retryable
- `network` — Connection issues, retryable
- `timeout` — Agent exceeded time limit, retryable with longer timeout
- `worktree` — Worktree creation/cleanup failures, may need manual intervention
- `auth` — Credential/token errors when pushing, not retryable
- `disk` — Disk space or file permission issues, not retryable
- `conflict` — Git merge conflicts, retryable with conflict resolution
- `unknown` — Unclassified errors, not retryable

## Learning System

Learnings are matched to new errors by category. When retrying, the system:
1. Looks up previous errors of the same category
2. Prepends the learnings to the retry prompt
3. Marks the error as resolved on successful retry
