# Shared State Protocol

## Overview

When multiple coder agents run in parallel, they need a way to coordinate without directly communicating. The shared state protocol uses `.autodev/agent-state.json` as an advisory coordination file.

**Key distinction:** This file is *advisory*, not *locking*. Each agent works in its own git worktree — physical file conflicts are impossible during execution. Conflicts are detected at merge time. The state file helps agents be aware of each other's work so they can make better decisions about file ownership and scope.

---

## Schema

```json
{
  "session_id": "a3f7c2d1-8e4b-4f9a-b231-0d9e7c8a4b12",
  "agents": {
    "agent-1": {
      "feature_id": "feat-1",
      "status": "coding|testing|completed|failed",
      "files_modified": ["src/auth.py", "tests/test_auth.py"],
      "files_created": ["src/middleware/jwt.py"],
      "last_update": "2024-01-15T10:45:00Z",
      "summary": "Implementing JWT auth middleware — created jwt.py, modifying auth.py to use it"
    },
    "agent-2": {
      "feature_id": "feat-2",
      "status": "coding",
      "files_modified": ["src/config.py"],
      "files_created": [],
      "last_update": "2024-01-15T10:43:00Z",
      "summary": "Adding rate limit config schema to src/config.py"
    }
  },
  "conflicts": [
    {
      "file": "src/config.py",
      "agents": ["agent-1", "agent-2"],
      "reported_at": "2024-01-15T10:46:00Z",
      "status": "reported"
    }
  ],
  "messages": [
    {
      "from": "agent-1",
      "to": "all",
      "type": "claim",
      "content": "I'm modifying src/auth.py and src/config.py — please avoid these files if possible",
      "timestamp": "2024-01-15T10:30:00Z"
    },
    {
      "from": "agent-2",
      "to": "agent-1",
      "type": "warning",
      "content": "I also need to modify src/config.py for rate limit settings. Proceeding — expect merge conflict.",
      "timestamp": "2024-01-15T10:31:00Z"
    },
    {
      "from": "agent-1",
      "to": "all",
      "type": "done",
      "content": "feat-1 complete. Modified: src/auth.py, src/config.py, tests/test_auth.py. Created: src/middleware/jwt.py",
      "timestamp": "2024-01-15T11:02:00Z"
    }
  ]
}
```

---

## Field Reference

### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | UUID string | Unique identifier for this AutoDev session. Set by the orchestrator at session start. |
| `agents` | object | Map of agent ID to agent state. Keys are `agent-1`, `agent-2`, etc. |
| `conflicts` | array | Known file conflicts detected by agents. The orchestrator uses this to prepare the merge phase. |
| `messages` | array | Append-only message log. Never delete messages. |

### Agent State Object

| Field | Type | Description |
|-------|------|-------------|
| `feature_id` | string | The feature this agent is responsible for (e.g., `feat-1`) |
| `status` | string | Current status — see valid values below |
| `files_modified` | array | Files the agent has changed. Updated as work progresses. |
| `files_created` | array | New files the agent created. |
| `last_update` | ISO8601 | Timestamp of the last write to this agent's entry |
| `summary` | string | One-sentence description of what the agent is currently doing |

### Agent Status Values

| Status | Meaning |
|--------|---------|
| `coding` | Actively writing or modifying code |
| `testing` | Running the test suite |
| `completed` | Feature done, all tests pass |
| `failed` | Could not complete — see messages for details |

### Message Object

| Field | Type | Description |
|-------|------|-------------|
| `from` | string | Agent ID that sent the message (or `orchestrator`) |
| `to` | string | Target agent ID, or `all` for broadcast |
| `type` | string | Message type — see valid values below |
| `content` | string | Human-readable message body |
| `timestamp` | ISO8601 | When the message was posted |

### Message Type Values

| Type | When to Use |
|------|-------------|
| `claim` | When starting work on a file that other agents might also need |
| `update` | Informational progress update (optional, not required) |
| `warning` | When you detect a potential conflict with another agent's work |
| `done` | When your feature is fully complete |

---

## Protocol Rules

### Rule 1: Read Before Starting

At the start of your task, before writing any code, read `agent-state.json`. Check:
- Which files do other agents have in their `files_modified` or `files_created` lists?
- Are there any `claim` messages for files you need to touch?

If another agent has claimed a file you need:
- If your change is additive (e.g., adding a new function), proceed but post a `warning`.
- If your change modifies the same section of the file, consider whether you can restructure your implementation to minimize overlap.
- Always proceed — do not block waiting. Record the potential conflict.

### Rule 2: Claim Shared Files

Before modifying a file that other agents are likely to also need (e.g., `config.py`, `settings.py`, `__init__.py`, `main.py`), post a `claim` message.

A "shared file" is any file that:
- Multiple features logically depend on
- Is a central config or registry
- Has fewer than 100 lines (high chance of overlapping edits)

Post the claim, then proceed with your work.

### Rule 3: Update Your Status

After each subtask completes, update your agent entry:
- Add any newly modified or created files to `files_modified` / `files_created`.
- Update `status` if it changed.
- Update `summary` to reflect what you just finished.
- Update `last_update`.

### Rule 4: Post Done Message When Complete

When your feature is fully complete (all subtasks done, tests pass), post a `done` message listing every file you modified or created. This is what the orchestrator reads to prepare the merge.

### Rule 5: Never Delete Messages or Agent Entries

The message log is append-only. The orchestrator and post-session debugging rely on the full history. Do not delete messages or remove other agents' entries from the `agents` map.

---

## Orchestrator Responsibilities

The orchestrator (not individual agents) is responsible for:

1. **Initializing the file** at session start with `session_id` and empty `agents`, `conflicts`, and `messages`.
2. **Writing each agent's initial entry** when dispatching them (setting `feature_id`, `status: "coding"`).
3. **Reading `done` messages** to know when to start the merge phase.
4. **Reading `conflicts`** before the merge phase to prepare resolution strategies.
5. **Final write** — after all agents complete, update all statuses to reflect the session outcome.

---

## Implementation Notes

### File Location

The file lives in the main worktree at `.autodev/agent-state.json`. Each coder agent's worktree does not have this file — agents must read it from the main worktree path or via the path passed to them at startup.

The orchestrator passes the absolute path to `agent-state.json` to each agent when dispatching.

### Write Discipline

All writes to `agent-state.json` must be atomic read-modify-write operations:
1. Read the current file.
2. Apply the specific change (add a message, update a status field).
3. Write the full updated JSON back.

Never write only a partial structure. Always preserve the complete schema.

### Example: Agent Startup Sequence

```python
# At agent startup:
state = read_json(".autodev/agent-state.json")
other_claimed_files = set()
for msg in state["messages"]:
    if msg["type"] == "claim" and msg["from"] != my_agent_id:
        # Extract files from claim message (by convention, files are listed in content)
        other_claimed_files.update(parse_files_from_claim(msg["content"]))

# Log awareness
if other_claimed_files & my_planned_files:
    post_warning(f"I also need: {other_claimed_files & my_planned_files}")

# Claim my files
post_claim(f"I'm modifying: {', '.join(my_planned_files)}")
```
