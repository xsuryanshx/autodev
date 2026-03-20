# Pipeline Telemetry Schema

This document defines the telemetry metrics collected during AutoDev pipeline execution.

## Overview

Pipeline telemetry tracks phase-level metrics for all 8 AutoDev phases, enabling performance analysis and bottleneck identification.

## Telemetry Schema

```json
{
  "pipeline_id": "run-uuid",
  "issue_url": "https://github.com/owner/repo/issues/123",
  "started_at": "2026-03-20T10:00:00.000Z",
  "completed_at": "2026-03-20T12:00:00.000Z",
  "total_duration_seconds": 7200,
  "status": "success|failed|partial",
  "phases": {
    "1": { "name": "Parse", ... },
    "2": { "name": "Validate", ... },
    "3": { "name": "Explore", ... },
    "4": { "name": "Plan", ... },
    "5": { "name": "Implement", ... },
    "6": { "name": "Merge", ... },
    "7": { "name": "Review", ... },
    "8": { "name": "Report", ... }
  }
}
```

## Per-Phase Metrics

### Phase 1: Parse

```json
{
  "phase": 1,
  "name": "Parse",
  "duration_seconds": 5,
  "input_type": "github_url|free_text",
  "issue_detected": {
    "issue_number": 123,
    "owner": "owner",
    "repo": "repo",
    "title": "Issue title"
  },
  "status": "success"
}
```

### Phase 2: Validate

```json
{
  "phase": 2,
  "name": "Validate",
  "duration_seconds": 120,
  "decision": "VALID|LIKELY_VALID|FEATURE_REQUEST|INVALID|NEEDS_INFO",
  "validation_steps": {
    "error_search": "found|not_found|skipped",
    "file_check": "passed|failed|skipped",
    "test_suite": "passed|failed|skipped|no_tests",
    "reproduction": "success|failed|not_attempted|skipped"
  },
  "status": "success"
}
```

### Phase 3: Explore

```json
{
  "phase": 3,
  "name": "Explore",
  "duration_seconds": 300,
  "files_scanned": 150,
  "documentation_read": {
    "CLAUDE_md": true,
    "AGENTS_md": false,
    "README_md": true
  },
  "relevant_files_identified": 12,
  "test_files_identified": 4,
  "build_system": "npm|pytest|make|none",
  "status": "success"
}
```

### Phase 4: Plan

```json
{
  "phase": 4,
  "name": "Plan",
  "duration_seconds": 180,
  "feature_count": 3,
  "subtask_count": 15,
  "features": [
    {
      "id": "feat-1",
      "slug": "descriptive-name",
      "subtask_count": 5,
      "estimated_complexity": "low|medium|high"
    }
  ],
  "status": "success"
}
```

### Phase 5: Implement

```json
{
  "phase": 5,
  "name": "Implement",
  "duration_seconds": 3600,
  "agents_dispatched": 3,
  "agents_completed": 3,
  "agents_failed": 0,
  "worktrees_created": 3,
  "commits_total": 12,
  "features": [
    {
      "id": "feat-1",
      "duration_seconds": 1200,
      "subtasks_completed": 5,
      "commits": 4,
      "status": "completed"
    }
  ],
  "status": "success"
}
```

### Phase 6: Merge

```json
{
  "phase": 6,
  "name": "Merge",
  "duration_seconds": 600,
  "merges_attempted": 3,
  "merges_successful": 3,
  "merges_failed": 0,
  "conflicts_encountered": 2,
  "conflicts_resolved": 2,
  "merge_details": [
    {
      "source_branch": "autodev/feat-1-feature",
      "target_branch": "autodev/issue-123",
      "conflicts": 1,
      "status": "success"
    }
  ],
  "status": "success"
}
```

### Phase 7: Review

```json
{
  "phase": 7,
  "name": "Review",
  "duration_seconds": 300,
  "cycles": 1,
  "verdict": "APPROVED|CHANGES_REQUESTED",
  "issues_found": 0,
  "issues_fixed_in_cycle": 0,
  "review_details": {
    "bugs_found": 0,
    "style_issues": 0,
    "security_issues": 0,
    "performance_issues": 0
  },
  "status": "success"
}
```

### Phase 8: Report

```json
{
  "phase": 8,
  "name": "Report",
  "duration_seconds": 30,
  "branch_pushed": true,
  "push_url": "https://github.com/owner/repo/tree/autodev/issue-123",
  "summary_generated": true,
  "status": "success"
}
```

## Telemetry Collection

### Storage

Telemetry is stored in `.autodev/pipeline-telemetry.json`.

### Collection Points

1. **Phase start/end**: Captured by orchestrator at each phase transition
2. **Agent metrics**: Captured by coder/reviewer agents and reported back
3. **Merge metrics**: Captured during Phase 6 merge operations
4. **Final summary**: Generated at end of Phase 8

### Performance Benchmarks

Reference timings for typical AutoDev runs:

| Phase | Fast | Typical | Slow |
|-------|------|---------|------|
| Parse | <1s | 1-5s | >10s |
| Validate | <30s | 30-120s | >300s |
| Explore | <60s | 2-5min | >10min |
| Plan | <30s | 1-3min | >5min |
| Implement | <10min | 30-60min | >2hr |
| Merge | <1min | 5-15min | >30min |
| Review | <5min | 10-30min | >1hr |
| Report | <10s | 10-30s | >60s |

### Bottleneck Detection

A phase is flagged as a bottleneck if:
- Duration exceeds typical benchmark by 3x
- Or duration exceeds 50% of total pipeline time

Example bottleneck alert:
```json
{
  "alert": "bottleneck_detected",
  "phase": 5,
  "name": "Implement",
  "duration_seconds": 7200,
  "typical_duration_seconds": 1800,
  "ratio": 4.0
}
```