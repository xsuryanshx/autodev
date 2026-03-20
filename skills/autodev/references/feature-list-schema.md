# Feature List Schema

## Overview

The feature list is the central task-tracking artifact for an AutoDev session. It lives at `.autodev/feature_list.json` in the target repository's root.

**Key principle: use JSON, not markdown.** A language model is far less likely to accidentally edit or overwrite a structured JSON file than a markdown file with prose. JSON also enables reliable programmatic reads and writes by the orchestrator, without parsing ambiguity.

---

## Full Schema

```json
{
  "issue": {
    "number": 42,
    "title": "Add JWT authentication to API endpoints",
    "url": "https://github.com/owner/repo/issues/42"
  },
  "features": [
    {
      "id": "feat-1",
      "name": "Add user auth",
      "status": "pending|in_progress|completed|failed",
      "assigned_agent": "agent-1",
      "branch": "autodev/feat-1-user-auth",
      "subtasks": [
        {
          "id": "sub-1",
          "description": "Create JWT middleware in src/middleware/auth.py",
          "status": "pending|in_progress|completed|failed"
        },
        {
          "id": "sub-2",
          "description": "Write unit tests for JWT middleware",
          "status": "pending"
        }
      ]
    }
  ],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T11:45:22Z"
}
```

---

## Field Reference

### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `issue` | object | The GitHub issue this session is solving |
| `features` | array | Decomposed features, one per parallel agent |
| `created_at` | ISO8601 string | When this session was initialized |
| `updated_at` | ISO8601 string | Last time any field was modified |

### `issue` Object

| Field | Type | Description |
|-------|------|-------------|
| `number` | integer | GitHub issue number |
| `title` | string | Issue title, verbatim from GitHub |
| `url` | string | Full URL to the issue on GitHub |

### `feature` Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier, format `feat-N` |
| `name` | string | Short human-readable name for the feature |
| `status` | string | One of the valid statuses below |
| `assigned_agent` | string | Agent identifier, format `agent-N`. Set when agent picks up the feature. |
| `branch` | string | Git branch where this feature is implemented. Format: `autodev/<feat-id>-<slug>`. |
| `subtasks` | array | Ordered list of concrete implementation steps |

### `subtask` Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier, format `sub-N` (scoped to the parent feature) |
| `description` | string | Concrete, actionable description of what to implement or change |
| `status` | string | One of the valid statuses below |

---

## Valid Statuses

Both features and subtasks share the same status vocabulary:

| Status | Meaning |
|--------|---------|
| `pending` | Not yet started |
| `in_progress` | Agent is actively working on this |
| `completed` | Successfully finished (tests pass) |
| `failed` | Attempted but could not complete; see agent logs |

---

## Orchestrator / Agent Interaction Model

### Initiator Agent (writes)

1. Fetches the GitHub issue.
2. Decomposes it into features and subtasks.
3. Writes the initial `feature_list.json` with all statuses set to `pending`.
4. Creates one git worktree per feature, naming the branch per the `branch` field.

### Orchestrator (reads and coordinates)

1. Reads `feature_list.json` to determine which features to dispatch.
2. Assigns an agent to each `pending` feature — sets `assigned_agent` and changes status to `in_progress`.
3. Monitors for status changes by periodically re-reading the file.
4. After all features reach `completed` or `failed`, proceeds to the merge phase.

### Coder Agent (reads, updates)

1. Reads `feature_list.json` at startup to understand its assigned feature and subtasks.
2. Updates its feature's `status` to `in_progress`.
3. As each subtask completes, updates `subtasks[N].status` to `completed`.
4. On completion, updates the feature `status` to `completed`.
5. On unrecoverable failure, updates the feature `status` to `failed` and records context in `.autodev/agent-state.json`.

### Write Discipline

- Only the orchestrator or the agent assigned to a feature should write that feature's entry.
- Always read the current file before writing — never overwrite the whole file, only update the relevant fields.
- Update `updated_at` on every write.
- Do NOT change another agent's feature entry unless you are the orchestrator.

---

## Example: Mid-Session State

```json
{
  "issue": {
    "number": 99,
    "title": "Implement rate limiting",
    "url": "https://github.com/acme/api/issues/99"
  },
  "features": [
    {
      "id": "feat-1",
      "name": "Rate limit middleware",
      "status": "completed",
      "assigned_agent": "agent-1",
      "branch": "autodev/feat-1-rate-limit-middleware",
      "subtasks": [
        { "id": "sub-1", "description": "Create RateLimiter class", "status": "completed" },
        { "id": "sub-2", "description": "Integrate into request pipeline", "status": "completed" },
        { "id": "sub-3", "description": "Write integration tests", "status": "completed" }
      ]
    },
    {
      "id": "feat-2",
      "name": "Rate limit config",
      "status": "in_progress",
      "assigned_agent": "agent-2",
      "branch": "autodev/feat-2-rate-limit-config",
      "subtasks": [
        { "id": "sub-1", "description": "Add config schema for limits per endpoint", "status": "completed" },
        { "id": "sub-2", "description": "Write config loader", "status": "in_progress" },
        { "id": "sub-3", "description": "Document config options", "status": "pending" }
      ]
    }
  ],
  "created_at": "2024-01-15T09:00:00Z",
  "updated_at": "2024-01-15T09:47:11Z"
}
```
