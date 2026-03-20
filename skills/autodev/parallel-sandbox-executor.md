---
name: parallel-sandbox-executor
description: "Dispatches parallel coding tasks in sandboxed environments (local path-checked or E2B microVM). Targets any Git repository and branch via config. Use after feature_list.json is written."
---

# Parallel Sandbox Executor

## When to use

- Phase 5 of AutoDev: run multiple features concurrently with isolated sandboxes.
- You have a populated `.autodev/feature_list.json` and need to execute coders against a **specific** `repo_url` and `branch`.
- You want JSON results back for Phase 6 merge aggregation.

## Configuration

### `.autodev/config.json` (optional)

Merge or reference:

```json
{
  "sandbox": {
    "backend": "local",
    "repo_url": "https://github.com/owner/repo.git",
    "branch": "main",
    "timeout_seconds": 900
  }
}
```

For E2B, set `"backend": "e2b"`, `"e2b_template": "base"` or a snapshot ID in `e2b_snapshot_id`. Require `E2B_API_KEY` in the environment.

### Driver JSON (required for `python -m core run`)

Fields:

| Field | Purpose |
|-------|---------|
| `workspace` | Base directory for per-task sandboxes (e.g. `repo/.autodev/workspaces`) |
| `max_parallelism` | Default 3 |
| `timeout_per_task` | Seconds per task (default 900) |
| `sandbox` | Same keys as `SandboxConfig` (`backend`, `repo_url`, `branch`, `clone_token`, E2B fields) |
| `tasks` | List of `{ task_id, description, prompt, skill, timeout_seconds?, context?, metadata? }` |

Per-task `metadata`:

- `repo_url`, `branch`, `clone_token` — override config for that task only.
- `skip_setup: true` — do not clone (empty workspace; tests / pre-seeded files).

## Dispatch procedure

1. Read `skills/autodev/references/feature-list-schema.md` and build `tasks[]` from each feature and its subtasks (flatten prompts as needed).
2. Write `.autodev/driver-config.json` with `workspace`, `sandbox`, and `tasks`.
3. Set `PYTHONPATH` to the AutoDev plugin root (directory containing `core/` and `agents/`).
4. Run:

   ```bash
   python -m core run --config .autodev/driver-config.json --output .autodev/driver-results.json
   ```

5. Read `.autodev/driver-results.json`.

## Result handling

- For each `results[]` item with `status == "completed"`: mark the matching feature complete in `feature_list.json`, record `files_created` / `files_modified`.
- On `failed` or `timeout`: set feature status to `failed`, store `error`.
- Exit code of the CLI is `0` only if `summary.failed == 0`.

## Error handling

- **Setup failure** (clone / deps): task never runs; `SandboxCreationError` surfaces as a failed result if wired through executor — ensure `repo_url` and tokens are valid.
- **Retry**: at most one retry per failed feature (per AutoDev harness rules); rebuild `tasks` with only failed IDs and re-run.

## Related

- `skills/autodev/task_tool.md` — conceptual `task()` tool (orchestrator-level).
- `skills/autodev/agent-backend.md` — backend enum includes `sandbox` (this executor).
- `commands/autodev.md` Phase 5 — slash-command variant of the same flow.
