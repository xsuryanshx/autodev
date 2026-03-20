# Observability Dashboard

This document defines the real-time dashboard output format for AutoDev execution monitoring.

## Dashboard Overview

The AutoDev dashboard provides real-time visibility into:
- Live agent status (running/idle/complete/failed)
- Progress bars per feature
- Error feed with timestamps
- Final summary statistics

## Output Format

### Header

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                           AUTODEV EXECUTION DASHBOARD                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Issue: #123 - Fix authentication bug                                        ║
║ URL:   https://github.com/owner/repo/issues/123                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Phase Progress

```
┌─ PHASE 1: PARSE ────────────────────────────────────────────────────────────┐
│ Status: ✓ COMPLETED | Duration: 3.2s                                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─ PHASE 2: VALIDATE ─────────────────────────────────────────────────────────┐
│ Status: ✓ COMPLETED | Duration: 45.1s | Decision: VALID                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─ PHASE 3: EXPLORE ──────────────────────────────────────────────────────────┐
│ Status: ✓ COMPLETED | Duration: 2m 15s | Files scanned: 147                │
└─────────────────────────────────────────────────────────────────────────────┘

┌─ PHASE 4: PLAN ─────────────────────────────────────────────────────────────┐
│ Status: ✓ COMPLETED | Duration: 1m 32s | Features: 3 | Subtasks: 12         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Status Table

```
┌─ AGENT STATUS ──────────────────────────────────────────────────────────────┐
│  Agent ID      │ Type     │ Feature        │ Status    │ Duration │ Progress │
├────────────────┼──────────┼────────────────┼───────────┼──────────┼──────────┤
│  agent-a1b2c3  │ coder    │ feat-1-events  │ running   │ 5m 32s   │ ████░░░░ │
│  agent-d4e5f6  │ coder    │ feat-2-telemetry│ waiting  │ --       │ ░░░░░░░░ │
│  agent-g7h8i9  │ coder    │ feat-3-dashboard│ pending  │ --       │ ░░░░░░░░ │
│  agent-j1k2l3  │ reviewer │ (all features) │ pending   │ --       │ ░░░░░░░░ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Progress Bars

Feature-level progress bars:

```
feat-1: event-logging      [████████████████████░░░░] 80% (4/5 subtasks)
feat-2: pipeline-telemetry [░░░░░░░░░░░░░░░░░░░░░░░] 0% (not started)
feat-3: observability-dash [░░░░░░░░░░░░░░░░░░░░░░░] 0% (not started)
```

### Error Feed

Errors are displayed in real-time:

```
┌─ ERRORS ─────────────────────────────────────────────────────────────────────┐
│ [10:35:42] agent-a1b2c3: Merge conflict in src/auth.py - resolving manually │
│ [10:36:15] agent-a1b2c3: Failed to write test for auth.py - retrying     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Live Updates

The dashboard updates:
- Every 30 seconds during active execution
- On significant events (phase completion, agent completion, errors)
- On user request via status command

## ASCII Progress Bar Legend

```
░ = Not started (0%)
▒ = In progress (1-99%)
█ = Complete (100%)

Colors (if terminal supports):
- White: Not started
- Cyan: In progress
- Green: Complete
- Red: Failed
- Yellow: Waiting/Blocked
```

## Status Indicators

| Symbol | Meaning |
|--------|---------|
| ●      | Running |
| ◐      | Waiting |
| ✓      | Complete |
| ✗      | Failed |
| ○      | Pending |

## Final Summary Block

After execution completes, a summary block is displayed:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                              EXECUTION SUMMARY                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Total Duration:    45m 23s                                                  ║
║  Features:          3 completed, 0 failed                                    ║
║  Subtasks:          12 completed, 0 failed                                   ║
║  Commits:           15 total                                                 ║
║                                                                              ║
║  PHASE BREAKDOWN:                                                            ║
║    Phase 1 (Parse):     3.2s  ████░░░░░░░░░░░░░░░░░░░  0.1%                  ║
║    Phase 2 (Validate): 45.1s  ████████████████░░░░░░░░  1.7%                ║
║    Phase 3 (Explore):  2m15s  ████████████████████░░░░░░  5.0%               ║
║    Phase 4 (Plan):      1m32s  ████████████░░░░░░░░░░░░░  3.4%               ║
║    Phase 5 (Implement): 35m   ██████████████████████████ 77.1%              ║
║    Phase 6 (Merge):     4m12s  ████████░░░░░░░░░░░░░░░░░  9.2%               ║
║    Phase 7 (Review):    2m10s  █████░░░░░░░░░░░░░░░░░░░░  4.8%               ║
║    Phase 8 (Report):    0m28s  █░░░░░░░░░░░░░░░░░░░░░░░░  0.7%               ║
║                                                                              ║
║  BOTTLENECK: Phase 5 (Implement) - 77.1% of total time                       ║
║                                                                              ║
║  Review Verdict: APPROVED                                                     ║
║  Branch: autodev/issue-123                                                   ║
║  URL: https://github.com/owner/repo/tree/autodev/issue-123                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

## Dashboard Output Integration

### Into `autodev-progress.txt`

The dashboard format is written to `.autodev/autodev-progress.txt` in append-only mode:

```
2026-03-20T10:30:00Z [dashboard] Phase 1 PARSE started
2026-03-20T10:30:03Z [dashboard] Phase 1 PARSE completed (3.2s)
2026-03-20T10:30:03Z [dashboard] Phase 2 VALIDATE started
...
```

### Into CLI Output

During active execution, the dashboard is rendered to stdout for real-time monitoring.

### JSON Export

For programmatic access, the same data is available in `.autodev/dashboard-state.json`:

```json
{
  "issue": { "number": 123, "title": "Fix authentication bug" },
  "phases": {
    "1": { "name": "Parse", "status": "completed", "duration_seconds": 3.2 },
    "2": { "name": "Validate", "status": "completed", "duration_seconds": 45.1 }
  },
  "agents": [
    {
      "id": "agent-a1b2c3",
      "type": "coder",
      "feature_id": "feat-1",
      "status": "running",
      "progress": 0.8,
      "subtasks_completed": 4,
      "subtasks_total": 5
    }
  ],
  "errors": [],
  "summary": null
}
```