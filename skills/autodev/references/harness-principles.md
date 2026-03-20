# Harness Principles

Practical patterns distilled from Anthropic's harness engineering approach. These are not abstract guidelines — they are operational rules that determine whether a session succeeds or fails.

---

## Principle 1: Feature List as JSON (Not Markdown)

### Why

Markdown is ambiguous and LLM-editable by nature. When an agent reads a markdown checklist, it may rewrite the whole file to update one item, corrupting other entries. JSON has a rigid schema — a model is far less likely to accidentally restructure it, and parsers will reject malformed output immediately.

Markdown is also harder to update atomically: you have to find a specific line and change it. JSON fields have unambiguous keys.

### How to Apply

- Store all task tracking in `.autodev/feature_list.json` and `.autodev/agent-state.json`.
- Never create a `TODO.md` or `PLAN.md` for agent consumption. If you need a human-readable view, generate it from the JSON as a secondary artifact (`.autodev/subtask_plan.md`), but agents must treat the JSON as the source of truth.
- When updating the feature list, read the current JSON, modify only the relevant fields, write it back. Never overwrite the whole file from scratch.

---

## Principle 2: Progress File for Context Recovery

### Why

Claude Code sessions can be interrupted — by timeout, by the user stopping the process, or by the agent hitting an error. Without a written record, a restarted session has no idea what was already done and will repeat work or miss steps.

The progress file is a simple append-only log that lets any agent (or a human) see exactly where the session left off.

### How to Apply

- Write to `.autodev/autodev-progress.txt` at every meaningful checkpoint.
- Format: one line per event, with ISO8601 timestamp prefix.
  ```
  2024-01-15T10:30:00Z [initiator] Issue #42 parsed: 3 features, 9 subtasks
  2024-01-15T10:30:05Z [orchestrator] Worktrees created for feat-1, feat-2, feat-3
  2024-01-15T10:35:22Z [agent-1] feat-1 subtask sub-1 completed
  2024-01-15T10:41:05Z [agent-1] feat-1 completed — branch autodev/feat-1-user-auth
  ```
- On startup, always read this file first. If it shows a prior session for the same issue, resume from the last checkpoint rather than starting over.
- The file is append-only. Never delete or truncate it within a session.

---

## Principle 3: Git History as State — Commits Are Checkpoints

### Why

Each git commit is a recoverable snapshot. If an agent's later changes are wrong, the orchestrator can reset to the last good commit without losing previous work. This also gives the human reviewer a clean, readable history of what the agent did and why.

An agent that makes one massive commit at the end provides no recovery points and a useless diff.

### How to Apply

- Commit after every completed subtask, not just after completing a feature.
- Use descriptive commit messages: `feat(auth): implement JWT middleware` rather than `progress`.
- The commit message is the agent's record of what it did. Write it for a human reviewer who will read it during PR review.
- Never force-push or rewrite history in a shared branch. Squash only if explicitly asked.
- The orchestrator can use `git log --oneline` to determine the last known-good state when recovering a failed session.

---

## Principle 4: Two-Agent Pattern — Initializer Decomposes, Coder Implements

### Why

Decomposition and implementation require different mental modes. An agent that decomposes and implements simultaneously tends to either over-plan (analysis paralysis) or under-plan (missing subtasks). Separating concerns produces better results.

The initializer's output becomes the coder's specification. This creates a natural review gate: the initializer's feature list can be inspected before any code is written.

### How to Apply

- **Initiator agent** responsibilities:
  1. Parse the GitHub issue.
  2. Validate the issue (see `issue-validation.md`).
  3. Decompose into features (2-5 independent chunks of work).
  4. For each feature, write 3-6 concrete, testable subtasks.
  5. Write `feature_list.json` and stop. Do not write code.

- **Coder agent** responsibilities:
  1. Read its assigned feature from `feature_list.json`.
  2. Implement exactly what the subtasks describe.
  3. Write tests alongside the implementation.
  4. Run the test suite and fix failures before marking `completed`.
  5. Do not re-decompose or change the feature scope unilaterally.

- If the coder finds the feature spec is wrong or incomplete, it should update `agent-state.json` with a `warning` message rather than silently changing scope.

---

## Principle 5: Test as End-Users Would — Run the Actual Test Suite

### Why

An agent that only checks "does my code syntax-check" or "does Python import without error" is not verifying correctness. The test suite is the ground truth for whether the change works.

Tests also prevent regression: changes that break existing behavior are caught immediately rather than at PR review.

### How to Apply

- Before writing any code, run the full test suite and note how many tests pass. This is your baseline.
- After implementing a subtask, run the relevant subset of tests.
- Before marking a feature `completed`, run the full test suite and verify:
  - All pre-existing tests still pass (no regressions).
  - New tests for the implemented functionality pass.
- If tests fail, do not mark the subtask or feature `completed`. Fix the failure first.
- If the test suite is missing (no test command found), note it in the progress file and write tests as part of the implementation.
- Use the project's existing test runner (`pytest`, `npm test`, `go test ./...`, etc.) — do not invent a new way to run tests.

---

## Principle 6: Stop Hook Pattern for Continuous Iteration (Ralph Loop)

### Why

Claude Code runs until it decides it's done. Without a formal stopping condition, it may stop prematurely (after writing code but before running tests) or run indefinitely (retrying a failing test without escalating).

The "ralph loop" (run, analyze, loop, produce, halt) provides a structured iteration pattern that continues until a clear success or failure condition is reached.

### How to Apply

Define explicit stopping conditions at the start of each agent task. The agent should loop through this cycle:

```
WHILE not done:
  1. RUN — Execute the current action (implement subtask, run tests)
  2. ANALYZE — Inspect output: did it succeed? did tests pass?
  3. IF success:
       mark subtask completed, move to next
  4. IF failure:
       attempt_count += 1
       IF attempt_count <= 3:
         diagnose failure, apply fix, LOOP
       ELSE:
         mark subtask failed
         write failure details to agent-state.json
         escalate (trigger researcher agent or stop)
  5. IF all subtasks completed: mark feature completed, HALT
```

Hard limits that must trigger a stop:
- More than 3 consecutive failures on the same subtask.
- Test suite takes longer than 5 minutes (likely hung process — kill and report).
- Any destructive git operation that wasn't part of the plan (e.g., unexpected branch deletion).

Never loop indefinitely. If the stopping condition is not reached within the attempt limit, fail explicitly so the orchestrator can decide what to do next.
