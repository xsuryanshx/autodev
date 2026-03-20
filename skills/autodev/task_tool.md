# task() — Subagent Dispatch Tool

## Purpose

The `task()` tool dispatches subagents for concurrent execution. It is the primary mechanism for parallelism in AutoDev's parallel subagent architecture (DeerFlow-style).

## Interface

```
task(description: string, prompt: string, skill: string, context?: object) -> task_id: string
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | string | Short human-readable description of the task |
| `prompt` | string | Detailed instructions for the subagent |
| `skill` | string | The skill type: "coder", "researcher" |
| `context` | object | Optional context: `{files?: string[], repo_path?: string}` |
| `returns` | string | A task_id string that can be used to wait for results |

## Behavior

1. Creates a `SubagentTask` with a unique task_id
2. Submits task to the `SubagentExecutor` thread pool
3. Returns the task_id immediately (non-blocking)
4. Task runs concurrently with other dispatched tasks (up to max_parallelism=3)
5. Each task has a 15-minute default timeout

## Usage Constraints

- Maximum **3 concurrent tasks** per turn (enforced by executor semaphore)
- Maximum **15-minute timeout** per task
- Tasks are **sandboxed** — no filesystem access outside workspace
- Tasks coordinate via **shared state file** (`.autodev/agent-state.json`)

## Result Aggregation

To wait for task results, use `wait_for_tasks(task_ids: string[])` after dispatching:

```
results = wait_for_tasks(["task-1", "task-2", "task-3"])
```

Each result contains:
- `status`: "completed" | "failed" | "timeout"
- `output`: task's return value
- `files_created`: list of files created
- `files_modified`: list of files modified
- `error`: error message if failed
