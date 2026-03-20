---
name: agent-backend
description: "Abstract interface for agent execution backends. Defines how to invoke, manage, and communicate with agent sessions."
---

# Agent Backend Interface

## Overview

All agent backends (Claude Code, OpenCode, etc.) implement this interface. The harness never calls agents directly — it calls through the backend interface. This allows swapping backends without changing agent logic.

## Interface Contract

### `backend:init(config: dict) -> void`
Initialize the backend with config from `.autodev/config.json`.

### `backend:spawn_worktree(agent_id: string, branch: string, repo_path: string) -> dict`
Create a new git worktree and spawn an agent session in it.

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
  "status": "completed|failed|running",
  "output": "agent response...",
  "error": "error message if failed"
}
```

### `backend:kill(agent_id: string) -> void`
Terminate an agent session and clean up its worktree.

### `backend:get_status(agent_id: string) -> dict`
Get current status of an agent session.

## Backend Discovery

The harness reads `.autodev/config.json` at startup:

```json
{
  "backend": "opencode"
}
```

Backend implementations are loaded as skills:
- `"opencode"` → `skills/autodev/opencode-executor.md`
- `"claude-code"` → (future) `skills/autodev/claude-executor.md`
```