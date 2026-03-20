---
name: agent-backend
description: "Abstract interface for agent execution backends. Defines how to invoke, manage, and communicate with agent sessions."
---

# Agent Backend Interface

## Overview

All agent backends (OpenCode, Claude Code, sandbox executor, etc.) implement this conceptual interface. The harness calls through a backend so implementations can be swapped without changing orchestration logic.

## Interface Contract

### `backend:init(config: dict) -> void`

Initialize the backend with config from `.autodev/config.json`.

### `backend:spawn_worktree(agent_id: string, branch: string, repo_path: string) -> dict`

Create a new git worktree and spawn an agent session in it (OpenCode / Claude Code style).

**Returns:**

```json
{
  "worktree_path": "/path/to/worktree",
  "agent_pid": 12345,
  "status": "running"
}
```

### `backend:send_message(agent_id: string, message: string) -> dict`

Send a message/prompt to a running agent session.

**Returns:**

```json
{
  "status": "completed|failed|running|timeout",
  "output": "agent response...",
  "error": "error message if failed"
}
```

### `backend:kill(agent_id: string) -> void`

Terminate an agent session and clean up its worktree.

### `backend:get_status(agent_id: string) -> dict`

**Example return:**

```json
{
  "status": "running",
  "worktree_path": "/path/to/worktree",
  "branch": "feat-1",
  "agent_pid": 12345
}
```

## Backend discovery

The harness reads `.autodev/config.json`:

```json
{
  "backend": "opencode"
}
```

Backend implementations are loaded as skills or invoked via CLI:

| `backend` value | Implementation |
|-----------------|----------------|
| `"opencode"` | `skills/autodev/opencode-executor.md` — `opencode run` in git worktrees |
| `"claude-code"` | (future) `skills/autodev/claude-executor.md` |
| `"sandbox"` | **Parallel sandbox executor** — `core/subagent_executor.py` + `SandboxManager`; local or E2B sandboxes; dispatch via `python -m core run` or `core/driver.py`. See `skills/autodev/parallel-sandbox-executor.md`. |

When `backend` is `"sandbox"`, Phase 5 uses JSON config + `python -m core run` (or `python -m core.driver`) instead of spawning separate CLI agent processes per feature. Handlers live in `agents/subagent_handlers.py`; sandboxes are created per `task_id`.

## Sandbox backend specifics

- **Isolation:** `SandboxBackend` protocol (`core/sandbox_backend.py`) — `local` (path-checked + env sanitization) or `e2b` (Firecracker VM).
- **Repo targeting:** `SandboxConfig.repo_url`, `branch`, `clone_token` — applied in `SandboxManager.create_sandbox()` via `sandbox.setup()`.
- **CLI:** `python -m core run`, `python -m core snapshot`, `python -m core status`.
- **JSON driver:** `core/driver.py` — stdin/file in, JSON results out.
