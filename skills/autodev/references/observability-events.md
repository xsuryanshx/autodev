# Observability Events Schema

## Overview

This document defines the structured event schema for the AutoDev observability platform. All agent actions and pipeline phases emit events that are logged for monitoring, debugging, and analytics.

**Key principle: use JSON for machine parsing.** Events are append-only and stored in `.autodev/events.jsonl` (one JSON object per line).

---

## Event Schema

Every event follows this base schema:

```json
{
  "event_id": "uuid-v4",
  "event_type": "agent.invocation.start | agent.invocation.end | agent.invocation.error | phase.start | phase.end",
  "timestamp": "ISO8601 timestamp with timezone",
  "agent_id": "string (agent identifier)",
  "phase": "string (phase name, e.g. 'phase-1-parse-request')",
  "session_id": "string (autodev session identifier)",
  "payload": { }
}
```

### Payload by Event Type

#### `agent.invocation.start`

Emitted when an agent begins execution.

```json
{
  "payload": {
    "agent_type": "coder | reviewer | researcher",
    "model": "string (model name, e.g. 'claude-sonnet-4')",
    "feature_id": "string (for coder agents)",
    "subtask_ids": ["string"],
    "input_summary": {
      "description": "string",
      "files_affected": ["string"]
    }
  }
}
```

#### `agent.invocation.end`

Emitted when an agent completes successfully.

```json
{
  "payload": {
    "agent_type": "coder | reviewer | researcher",
    "model": "string",
    "duration_seconds": "number",
    "token_usage": {
      "input_tokens": "number",
      "output_tokens": "number",
      "total_tokens": "number"
    },
    "output_summary": {
      "files_modified": ["string"],
      "files_created": ["string"],
      "subtasks_completed": ["string"],
      "commit_sha": "string"
    }
  }
}
```

#### `agent.invocation.error`

Emitted when an agent fails.

```json
{
  "payload": {
    "agent_type": "coder | reviewer | researcher",
    "model": "string",
    "duration_seconds": "number",
    "error_details": {
      "error_type": "string (e.g. 'tool_failure', 'test_failure', 'timeout')",
      "error_message": "string",
      "stack_trace": "string (optional)",
      "failed_subtask_id": "string"
    },
    "partial_output": {
      "files_modified": ["string"],
      "subtasks_completed": ["string"]
    }
  }
}
```

#### `phase.start`

Emitted when a pipeline phase begins.

```json
{
  "payload": {
    "phase_name": "phase-1-parse-request | phase-2-validate-issue | phase-3-explore-codebase | phase-4-create-feature-list | phase-5-dispatch-coder-agents | phase-6-merge-results | phase-7-review | phase-8-report",
    "phase_number": 1-8,
    "input_summary": {
      "issue_url": "string (optional)",
      "feature_description": "string (optional)"
    }
  }
}
```

#### `phase.end`

Emitted when a pipeline phase completes.

```json
{
  "payload": {
    "phase_name": "string",
    "phase_number": 1-8,
    "duration_seconds": "number",
    "output_summary": {
      "status": "success | failed | skipped",
      "artifacts_created": ["string"],
      "artifacts_modified": ["string"]
    }
  }
}
```

---

## Event Type Reference

| Event Type | When Emitted | Who Emits |
|------------|--------------|-----------|
| `agent.invocation.start` | Agent begins execution | Orchestrator |
| `agent.invocation.end` | Agent completes successfully | Orchestrator |
| `agent.invocation.error` | Agent fails | Orchestrator |
| `phase.start` | Pipeline phase begins | Orchestrator |
| `phase.end` | Pipeline phase completes | Orchestrator |

---

## Agent Invocation Events

### Coder Agent Events

**On start:**
- Log `agent.invocation.start` with feature_id and subtask_ids
- Include model being used
- Include input_summary describing the feature

**On end:**
- Log `agent.invocation.end` with duration and token usage
- Include output_summary with files_modified, files_created, subtasks_completed, commit_sha

**On error:**
- Log `agent.invocation.error` with error_details
- Include partial_output showing what was completed before failure

### Reviewer Agent Events

**On start:**
- Log `agent.invocation.start` with agent_type="reviewer"
- Include input_summary describing the branch being reviewed

**On end:**
- Log `agent.invocation.end` with verdict (APPROVED/CHANGES_REQUESTED)
- Include token usage and duration

**On error:**
- Log `agent.invocation.error` with error_details

### Researcher Agent Events

**On start:**
- Log `agent.invocation.start` with agent_type="researcher"
- Include input_summary describing the research query

**On end:**
- Log `agent.invocation.end` with findings summary
- Include token usage and duration

---

## Phase Events

The AutoDev pipeline has 8 phases:

| Phase | Name | Events Emitted |
|-------|------|----------------|
| 1 | Parse Request | `phase.start`, `phase.end` |
| 2 | Validate Issue | `phase.start`, `phase.end` |
| 3 | Explore Codebase | `phase.start`, `phase.end` |
| 4 | Create Feature List | `phase.start`, `phase.end` |
| 5 | Dispatch Coder Agents | `phase.start`, `phase.end` |
| 6 | Merge Results | `phase.start`, `phase.end` |
| 7 | Review | `phase.start`, `phase.end` |
| 8 | Report | `phase.start`, `phase.end` |

---

## Token Usage Fields

Token counts are recorded when available from the model response:

| Field | Type | Description |
|-------|------|-------------|
| `input_tokens` | integer | Tokens in the input prompt |
| `output_tokens` | integer | Tokens in the generated response |
| `total_tokens` | integer | Sum of input and output tokens |

---

## Error Details Structure

```json
{
  "error_details": {
    "error_type": "string",
    "error_message": "string",
    "stack_trace": "string (optional)",
    "failed_subtask_id": "string (optional)"
  }
}
```

### Error Types

| Error Type | Description |
|------------|-------------|
| `tool_failure` | A tool (Bash, Read, Write, etc.) failed |
| `test_failure` | Test suite failed after max retries |
| `timeout` | Operation exceeded time limit |
| `merge_conflict` | Git merge conflict could not be resolved |
| `validation_failure` | Issue validation failed |
| `internal_error` | Unexpected internal error |

---

## JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://autodev.dev/schemas/observability-event.json",
  "title": "AutoDev Observability Event",
  "description": "Structured event schema for AutoDev agent and phase observability",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "agent_id", "session_id", "payload"],
  "properties": {
    "event_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier for this event"
    },
    "event_type": {
      "type": "string",
      "enum": [
        "agent.invocation.start",
        "agent.invocation.end",
        "agent.invocation.error",
        "phase.start",
        "phase.end"
      ]
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO8601 timestamp when event was emitted"
    },
    "agent_id": {
      "type": "string",
      "description": "Identifier of the agent or 'orchestrator'"
    },
    "phase": {
      "type": "string",
      "description": "Current phase name (e.g. 'phase-5-dispatch-coder-agents')"
    },
    "session_id": {
      "type": "string",
      "description": "AutoDev session identifier"
    },
    "payload": {
      "type": "object",
      "description": "Event-specific payload data"
    }
  }
}
```

---

## Example Event Log Entry

```
{"event_id":"550e8400-e29b-41d4-a716-446655440000","event_type":"agent.invocation.start","timestamp":"2024-01-15T10:30:00Z","agent_id":"agent-1","phase":"phase-5-dispatch-coder-agents","session_id":"sess-001","payload":{"agent_type":"coder","model":"claude-sonnet-4","feature_id":"feat-1","subtask_ids":["sub-1","sub-2"],"input_summary":{"description":"Add JWT authentication","files_affected":["src/auth/middleware.py"]}}}
{"event_id":"550e8400-e29b-41d4-a716-446655440001","event_type":"agent.invocation.end","timestamp":"2024-01-15T10:45:22Z","agent_id":"agent-1","phase":"phase-5-dispatch-coder-agents","session_id":"sess-001","payload":{"agent_type":"coder","model":"claude-sonnet-4","duration_seconds":922,"token_usage":{"input_tokens":12000,"output_tokens":8500,"total_tokens":20500},"output_summary":{"files_modified":["src/auth/middleware.py"],"files_created":["tests/test_auth.py"],"subtasks_completed":["sub-1","sub-2"],"commit_sha":"abc123def456"}}}
```
