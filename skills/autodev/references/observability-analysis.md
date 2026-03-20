# Post-Hoc Analysis Schema

This document defines the post-execution analysis and reporting format for AutoDev.

## Overview

After each AutoDev execution completes, a comprehensive analysis report is generated that includes:
- Total execution time breakdown
- Cost estimation (token usage)
- Bottleneck identification
- Success/failure patterns
- Recommendations for future runs

## Analysis Report Schema

```json
{
  "report_id": "analysis-uuid",
  "pipeline_id": "run-uuid",
  "generated_at": "2026-03-20T12:00:00.000Z",
  "execution": {
    "issue_url": "https://github.com/owner/repo/issues/123",
    "issue_title": "Fix authentication bug",
    "issue_type": "bug|feature|docs|question",
    "status": "success|failed|partial",
    "started_at": "2026-03-20T10:00:00.000Z",
    "completed_at": "2026-03-20T12:00:00.000Z",
    "total_duration_seconds": 7200
  },
  "phase_breakdown": {
    "1": { "name": "Parse", "duration_seconds": 3, "percentage": 0.04 },
    "2": { "name": "Validate", "duration_seconds": 45, "percentage": 0.63 },
    "3": { "name": "Explore", "duration_seconds": 135, "percentage": 1.88 },
    "4": { "name": "Plan", "duration_seconds": 92, "percentage": 1.28 },
    "5": { "name": "Implement", "duration_seconds": 5550, "percentage": 77.08 },
    "6": { "name": "Merge", "duration_seconds": 252, "percentage": 3.50 },
    "7": { "name": "Review", "duration_seconds": 130, "percentage": 1.81 },
    "8": { "name": "Report", "duration_seconds": 28, "percentage": 0.39 }
  },
  "bottleneck": {
    "phase": 5,
    "name": "Implement",
    "duration_seconds": 5550,
    "percentage": 77.08,
    "severity": "critical|high|medium|low",
    "reason": "Largest phase - 3 parallel agents completing work"
  },
  "features": [
    {
      "id": "feat-1",
      "duration_seconds": 1800,
      "subtasks_completed": 5,
      "subtasks_total": 5,
      "commits": 3,
      "status": "completed"
    }
  ],
  "cost_estimation": {
    "token_usage": {
      "input_tokens": 150000,
      "output_tokens": 450000,
      "total_tokens": 600000
    },
    "estimated_cost_usd": 18.50,
    "cost_breakdown": {
      "parse": 0.05,
      "validate": 0.15,
      "explore": 0.50,
      "plan": 0.35,
      "implement": 15.00,
      "merge": 1.50,
      "review": 2.00,
      "report": 0.10
    }
  },
  "patterns": {
    "success_rate": 1.0,
    "total_runs": 5,
    "successful_runs": 5,
    "common_issues": [],
    "average_duration_seconds": 6800
  },
  "recommendations": [
    {
      "category": "performance",
      "priority": "high",
      "description": "Phase 5 (Implement) takes 77% of time - consider reducing parallel agents to 2",
      "action": "Modify Phase 5 concurrency in autodev.md"
    }
  ]
}
```

## Bottleneck Detection

### Detection Criteria

A phase is flagged as a bottleneck when:

1. **Duration threshold**: Phase takes >50% of total execution time
2. **Absolute threshold**: Phase takes >30 minutes regardless of percentage
3. **Trend threshold**: Phase duration is 2x the rolling average for similar issues

### Severity Levels

| Severity | Criteria |
|----------|----------|
| critical | >80% of total time OR >2 hours |
| high     | >60% of total time OR >1 hour |
| medium   | >40% of total time OR >30 minutes |
| low      | >30% of total time OR >15 minutes |

### Bottleneck Report Entry

```json
{
  "bottleneck": {
    "phase": 5,
    "name": "Implement",
    "duration_seconds": 5550,
    "percentage": 77.08,
    "severity": "critical",
    "reason": "Phase 5 is the longest phase due to parallel agent execution",
    "recommendations": [
      "Consider reducing parallel agents from 3 to 2",
      "Batch small features into single agents",
      "Use faster models for simple subtasks"
    ]
  }
}
```

## Cost Estimation

### Token Usage Tracking

```json
{
  "token_usage": {
    "per_phase": {
      "1": { "input": 500, "output": 200, "total": 700 },
      "2": { "input": 2000, "output": 5000, "total": 7000 },
      "3": { "input": 15000, "output": 8000, "total": 23000 },
      "4": { "input": 10000, "output": 5000, "total": 15000 },
      "5": { "input": 80000, "output": 350000, "total": 430000 },
      "6": { "input": 10000, "output": 20000, "total": 30000 },
      "7": { "input": 20000, "output": 30000, "total": 50000 },
      "8": { "input": 5000, "output": 5000, "total": 10000 }
    },
    "total_input": 142500,
    "total_output": 439200,
    "total_tokens": 581700
  }
}
```

### Cost Calculation

Using Claude API pricing (example rates):
- Input tokens: $0.015 per 1K tokens
- Output tokens: $0.075 per 1K tokens

```json
{
  "estimated_cost_usd": 33.45,
  "cost_breakdown": {
    "input_cost": 2.14,
    "output_cost": 32.94,
    "total": 33.45
  }
}
```

## Success/Failure Patterns

### Pattern Analysis

```json
{
  "patterns": {
    "total_runs": 10,
    "successful_runs": 8,
    "success_rate": 0.80,
    "failure_reasons": [
      { "reason": "merge_conflicts", "count": 1 },
      { "reason": "test_failures", "count": 1 }
    ],
    "average_duration_seconds": 7200,
    "fastest_run_seconds": 3600,
    "slowest_run_seconds": 14400
  }
}
```

### Common Issue Detection

```json
{
  "common_issues": [
    {
      "issue_type": "merge_conflicts",
      "occurrences": 3,
      "severity": "medium",
      "typical_phase": 6,
      "recommendation": "Add pre-merge conflict detection in Phase 5"
    }
  ]
}
```

## Recommendations

### Category Types

| Category | Description |
|----------|-------------|
| performance | Optimizations for faster execution |
| cost       | Reductions in token/API usage |
| quality    | Improvements to output quality |
| reliability| Better error handling and recovery |

### Priority Levels

| Priority | Description |
|----------|-------------|
| critical | Immediate action needed |
| high     | Address in next sprint |
| medium   | Consider for future improvements |
| low      | Nice to have |

### Recommendation Schema

```json
{
  "recommendations": [
    {
      "id": "rec-001",
      "category": "performance",
      "priority": "high",
      "title": "Reduce parallel agents in Phase 5",
      "description": "Phase 5 (Implement) takes 77% of execution time due to 3 parallel agents",
      "expected_impact": "Reduce total time by 20-30%",
      "implementation_effort": "low",
      "action_items": [
        "Modify Phase 5 in autodev.md to limit concurrent agents to 2",
        "Update feature decomposition guidance in Phase 4"
      ]
    }
  ]
}
```

## Report Generation

### Trigger Points

1. **Automatic**: After Phase 8 (Report) completes
2. **On demand**: Via `/autodev --report-only` flag
3. **Historical**: Via `/autodev --analyze <pipeline-id>` for past runs

### Output Formats

1. **Console**: Human-readable formatted output (default)
2. **JSON**: Machine-parseable via `--format json`
3. **Markdown**: For documentation via `--format markdown`

### Storage

Analysis reports are stored in `.autodev/analysis/` directory:
- `.autodev/analysis/run-{uuid}.json` - Full analysis
- `.autodev/analysis/latest.json` - Symlink to most recent