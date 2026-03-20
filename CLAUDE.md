# AutoDev — Autonomous Coding Harness

AutoDev is a Claude Code plugin that autonomously implements GitHub issues and feature requests. Given a repository and an issue, it validates the problem, decomposes work into parallel tasks, implements each feature in isolated git worktrees, and delivers a branch ready for human review.

## Architecture

AutoDev is a **Claude Code plugin** — it runs entirely within Claude Code as a `/autodev` command. There is no Python code, no separate server, and no external orchestrator. The plugin coordinates multiple Claude Code agent sessions to implement features in parallel.

### Plugin Structure

```
autodev/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── commands/
│   └── autodev.md           # /autodev command definition (8 phases)
├── agents/
│   ├── coder.md             # Coder agent skill
│   ├── researcher.md         # Researcher agent skill
│   └── reviewer.md          # Reviewer agent skill
└── skills/autodev/references/
    ├── harness-principles.md      # Core operational rules
    ├── issue-validation.md        # Pre-implementation validation
    ├── feature-list-schema.md     # Task tracking JSON schema
    ├── shared-state-protocol.md   # Multi-agent coordination
    └── merge-strategy.md          # Branch merging protocol
```

## How to Use

### Invocation

```
/autodev <github-issue-url>
/autodev <feature-description>
```

**Examples:**
```
/autodev https://github.com/owner/repo/issues/123
/autodev Add JWT authentication to all API endpoints
```

### What Happens

1. **Parse** — Extract issue information (GitHub API or free text)
2. **Validate** — Confirm the issue is real before writing code
3. **Explore** — Understand project structure, conventions, test system
4. **Plan** — Decompose into features and subtasks, write `feature_list.json`
5. **Implement** — Dispatch parallel coder agents in isolated worktrees
6. **Merge** — Combine all feature branches, run full test suite
7. **Review** — Run reviewer agent for quality gate
8. **Report** — Push to fork, present branch URL for human review

## Runtime Files

AutoDev writes state files to `.autodev/` in the target repository:

| File | Purpose |
|------|---------|
| `.autodev/feature_list.json` | Task tracking — features, subtasks, statuses |
| `.autodev/agent-state.json` | Multi-agent coordination — claims, messages |
| `.autodev/autodev-progress.txt` | Human-readable progress log (append-only) |

### Feature List Schema

The `feature_list.json` is the **source of truth** for task state. Always use JSON, never markdown.

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
      "status": "completed",
      "assigned_agent": "agent-1",
      "branch": "autodev/feat-1-user-auth",
      "subtasks": [
        { "id": "sub-1", "description": "Create JWT middleware", "status": "completed" },
        { "id": "sub-2", "description": "Write unit tests", "status": "completed" }
      ]
    }
  ],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T11:45:22Z"
}
```

### Shared State Protocol

When multiple coder agents run in parallel, they coordinate through `agent-state.json`. This file is **advisory** — agents work in isolated git worktrees, so physical file conflicts are impossible. The state file helps agents avoid duplicating work and prepares the orchestrator for merge conflicts.

**Key rules:**
1. Read `agent-state.json` before starting — know what other agents claim
2. Post `claim` messages for shared files (config.py, settings.py, etc.)
3. Post `done` messages when your feature is complete
4. Never delete messages — the log is append-only

## Agent Types

### Coder Agent

**Role:** Implements features in isolated git worktrees.

- Reads assigned feature from `feature_list.json`
- Implements subtasks incrementally — commits after each logical unit
- Writes tests alongside implementation
- Runs full test suite before marking complete
- Updates `agent-state.json` with files modified and status

**Model:** Claude Sonnet

### Researcher Agent

**Role:** Read-only research on errors, APIs, and technical questions.

- Called when coder gets stuck (3+ failed attempts)
- Searches web for error solutions, API documentation, best practices
- Returns structured findings with code snippets
- Never modifies code

**Model:** Claude Haiku

### Reviewer Agent

**Role:** Quality gate before merge.

- Runs after all features are merged
- Checks for bugs, logic errors, convention violations
- Verifies test coverage
- Returns structured verdict: `APPROVED` or `CHANGES_REQUESTED`

**Model:** Claude Opus

## Issue Validation

Before writing any code, the initiator validates the issue to avoid wasted effort.

### Validation Phases

1. **Parse** — Extract expected/actual behavior, error messages, reproduction steps
2. **Classify** — Bug report, feature request, documentation, question
3. **Validate (bugs only)** — Reproduce the issue, run test suite, search for error strings
4. **Decision Gate** — `VALID`, `LIKELY_VALID`, `INVALID`, `FEATURE_REQUEST`, `NEEDS_INFO`

### Decision Outcomes

| Outcome | Condition | Action |
|---------|-----------|--------|
| `VALID` | Bug reproduced or clearly buggy code | Proceed to implementation |
| `LIKELY_VALID` | Bug plausible but cannot reproduce | Proceed with uncertainty flagged |
| `FEATURE_REQUEST` | Enhancement or new functionality | Proceed to implementation |
| `INVALID` | Cannot find relevant code or bug doesn't exist | STOP, report findings |
| `NEEDS_INFO` | Missing reproduction steps | STOP, request clarification |

**Critical rule:** If you cannot reproduce a bug and cannot find related code, mark it `INVALID`. Do not change code on the assumption that there might be a bug somewhere.

## Key Conventions

### Never Auto-Create PRs

- Always push to the user's fork only
- Output the branch URL for human review
- User creates the PR manually after reviewing changes

**Why:** AutoDev may introduce subtle bugs. A human must review before any code reaches the main repository.

### Validate Before Coding

- Reproduce bugs before implementing fixes
- Run existing test suite to establish baseline
- Only proceed when issue is confirmed real

### Use JSON for Task Tracking

- `feature_list.json` is the source of truth — not markdown
- Read-modify-write discipline: update only changed fields
- Generate human-readable views from JSON as secondary artifacts

### Git History as Checkpoints

- Commit after every completed subtask
- Use descriptive commit messages: `feat(auth): implement JWT middleware`
- Commits enable recovery if later changes are wrong

### Worktree Isolation

- Each feature gets its own git worktree
- Feature branches: `autodev/feat-1-user-auth`
- Unified branch: `autodev/issue-42`
- Isolation prevents agents from interfering with each other

## Harness Principles

### Feature List as JSON

JSON is rigid and unambiguous. Markdown is editable by LLMs and prone to accidental corruption. Always store task state in JSON.

### Progress File for Context Recovery

Write to `autodev-progress.txt` at every checkpoint:

```
2024-01-15T10:30:00Z [initiator] Issue #42 parsed: 3 features, 9 subtasks
2024-01-15T10:35:22Z [agent-1] feat-1 subtask sub-1 completed
2024-01-15T10:41:05Z [agent-1] feat-1 completed — branch autodev/feat-1-user-auth
```

Append-only log enables recovery after interruption.

### Two-Agent Pattern

**Initiator** decomposes and plans:
- Parse and validate issue
- Decompose into features (2-5 independent chunks)
- Write `feature_list.json`, create worktrees, stop — do not write code

**Coder** implements:
- Read assigned feature from `feature_list.json`
- Implement exactly what subtasks describe
- Write tests, run test suite, fix failures
- Do not re-decompose or change scope unilaterally

### Test as End-Users Would

- Run the actual test suite, not just syntax checks
- Establish baseline: how many tests pass before changes
- Verify no regressions after implementing
- If test suite is missing, write tests as part of implementation

### Ralph Loop (Stop Hook Pattern)

Define explicit stopping conditions. Loop through:
1. **RUN** — Execute the current action
2. **ANALYZE** — Did it succeed? Did tests pass?
3. **LOOP** or **HALT** — Retry on failure (max 3 attempts), stop on success

Hard limits:
- 3 consecutive failures on same subtask → escalate or fail
- Test suite hangs >5 minutes → kill and report
- Destructive git operations outside plan → stop immediately

## Pipeline Phases

### Phase 1: Parse Request
Extract issue from GitHub API or free-text description.

### Phase 2: Validate Issue
Confirm issue is real before coding. Skip for feature requests.

### Phase 3: Explore Codebase
Read project documentation, understand structure, find relevant files.

### Phase 4: Create Feature List
Decompose work into features and subtasks. Write `feature_list.json`. Create worktrees.

### Phase 5: Dispatch Parallel Coder Agents
Each agent implements its feature in an isolated worktree.

### Phase 6: Merge Results
Combine feature branches into unified branch. Handle conflicts. Run full test suite.

### Phase 7: Review
Reviewer agent checks code quality. `APPROVED` or `CHANGES_REQUESTED`.

### Phase 8: Report
Push unified branch to fork. Output branch URL for human review.

## Lessons Learned

### Reproduce Issues First
Before fixing any bug:
1. Analyze expected vs actual behavior
2. Reproduce the issue locally
3. Verify it's a real bug (not user error)
4. Understand the root cause
5. THEN plan the fix

### Test on Simple Issues First
Before complex issues, validate the system on:
- Documentation fixes
- Obvious typo fixes
- Issues where the fix is clearly defined

### Fork Push Authentication
When pushing to forks, include token in push URL:
```
https://${GITHUB_TOKEN}@github.com/${FORK_OWNER}/${REPO_NAME}.git
```

### Reviewer Agent Output Format
The reviewer uses structured output parsed programmatically:
```
VERDICT: APPROVED | CHANGES_REQUESTED
CONFIDENCE: 0.0-1.0

ISSUES:
1. [SEVERITY: critical|major|minor] Description
   FILE: path/to/file.py:42
   FIX: Recommended fix

SUMMARY: One paragraph assessment.
```

Do not list things you liked — only actual problems.
