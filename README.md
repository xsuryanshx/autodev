# AutoDev — Autonomous Coding Harness

AutoDev is a [Claude Code](https://claude.ai/code) plugin that autonomously implements GitHub issues and feature requests. Given a repository and an issue, AutoDev validates the problem, decomposes work into parallel tasks, implements each feature in isolated git worktrees, and delivers a branch ready for human review.

**No Python required.** AutoDev runs as a Claude Code plugin — it coordinates multiple Claude Code agent sessions to do the work.

---

## Architecture Overview

AutoDev is a **Claude Code plugin**, not a Python application. There is no separate server or orchestrator process. The plugin uses Claude Code's built-in agent dispatch system to run multiple agents in parallel, each in its own git worktree.

```
                    ┌─────────────────────────────────────┐
                    │           /autodev                  │
                    │     (Claude Code Plugin Command)     │
                    └─────────────────┬───────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
     │  Initiator      │     │  Coder Agent 1  │     │  Coder Agent N  │
     │  (Phase 1-4)    │     │  (Worktree 1)   │     │  (Worktree N)   │
     │                 │     │                 │     │                 │
     │ - Parse issue   │     │ - Implement     │     │ - Implement     │
     │ - Validate      │     │   feat-1        │     │   feat-N        │
     │ - Explore       │     │ - Write tests   │     │ - Write tests   │
     │ - Create plan   │     │ - Run tests     │     │ - Run tests     │
     └─────────────────┘     └─────────────────┘     └─────────────────┘
              │                       │                       │
              │                       ▼                       ▼
              │              ┌─────────────────────────────────┐
              │              │   .autodev/feature_list.json   │
              │              │   (Shared task state)         │
              │              └─────────────────────────────────┘
              │                       │
              ▼                       ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │                     Phase 6-8                                   │
     │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
     │  │    Merge     │  │   Reviewer   │  │    Report    │         │
     │  │  (unified    │─▶│   (quality   │─▶│  (push to    │         │
     │  │   branch)    │  │    gate)     │  │   fork)      │         │
     │  └──────────────┘  └──────────────┘  └──────────────┘         │
     └─────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                            ┌─────────────────┐
                            │  Branch URL     │
                            │  (human review) │
                            └─────────────────┘
```

## How It Works — 8 Phases

### Phase 1: Parse Request

AutoDev accepts either:
- A GitHub issue URL: `https://github.com/owner/repo/issues/123`
- A free-text feature description: `Add JWT authentication to all API endpoints`

For GitHub issues, it fetches title, body, labels, and comments via the GitHub API.

### Phase 2: Validate Issue

Before writing any code, AutoDev confirms the issue is real:

- **Bug reports:** Reproduce the bug, run the test suite, search for error messages
- **Feature requests:** Skip validation (no bug to reproduce)
- **Questions:** Mark as `NEEDS_INFO`, stop — a human needs to clarify

If AutoDev cannot reproduce a bug and cannot find related code, it reports the issue as invalid and makes no changes.

### Phase 3: Explore Codebase

AutoDev reads project documentation and understands the codebase:
- Project structure and conventions
- Relevant files for the issue
- Test framework and how to run tests
- Build system and configuration

### Phase 4: Create Feature List

AutoDev decomposes the work into discrete features (2-5 independent chunks), each with concrete subtasks. This is written to `.autodev/feature_list.json` in the repository.

```
feat-1: User authentication
  ├── sub-1: Create User model
  ├── sub-2: Add validation
  └── sub-3: Write unit tests

feat-2: JWT middleware
  ├── sub-1: Create JWT utility functions
  ├── sub-2: Add auth decorator
  └── sub-3: Integration tests
```

AutoDev creates one git worktree per feature branch.

### Phase 5: Parallel Implementation

Each feature is implemented in parallel by a separate Coder agent, each in its own isolated git worktree. Agents coordinate through shared state files to avoid stepping on each other.

For each feature:
1. Implement subtasks
2. Write tests
3. Run test suite
4. Commit changes with descriptive messages

### Phase 6: Merge Results

AutoDev merges all feature branches into a unified branch (`autodev/issue-{N}`):
1. Merge each feature branch sequentially
2. Handle any merge conflicts
3. Run the full test suite
4. Fix regressions if they occur

### Phase 7: Review

A Reviewer agent performs a quality gate check:
- Bug detection and logic errors
- Convention compliance
- Test coverage and quality
- Security issues

Returns structured verdict: `APPROVED` or `CHANGES_REQUESTED`.

### Phase 8: Report

AutoDev pushes the unified branch to your fork and provides the branch URL. **It never creates a PR automatically.** You review the branch and create the PR yourself.

---

## Plugin Structure

```
autodev/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── commands/
│   └── autodev.md           # /autodev command (8 phases)
├── agents/
│   ├── coder.md             # Coder agent skill
│   ├── researcher.md         # Researcher agent (on-demand)
│   └── reviewer.md          # Reviewer agent (quality gate)
└── skills/autodev/references/
    ├── harness-principles.md      # Core operational rules
    ├── issue-validation.md        # Pre-implementation validation
    ├── feature-list-schema.md     # Task tracking schema
    ├── shared-state-protocol.md   # Multi-agent coordination
    └── merge-strategy.md          # Branch merging protocol
```

---

## Installation

### Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- GitHub CLI (`gh`) authenticated: `gh auth login`
- Git configured with push access to your fork of the target repository

### Step 1: Clone AutoDev

```bash
git clone https://github.com/xsuryanshx/autodev.git ~/autodev
```

### Step 2: Install as a Claude Code Plugin

**Option A — Symlink (recommended for daily use):**

```bash
# Create the plugins directory if it doesn't exist
mkdir -p ~/.claude/plugins/cache/local

# Symlink autodev into the plugins directory
ln -sfn ~/autodev ~/.claude/plugins/cache/local/autodev
```

Then add to your Claude Code settings (`~/.claude/settings.json`):
```json
{
  "enabledPlugins": {
    "autodev@local": true
  }
}
```

Restart Claude Code or run `/reload-plugins` to pick up the plugin.

**Option B — Direct load (for development/testing):**

```bash
claude --plugin-dir ~/autodev
```

This loads AutoDev for a single session without permanent installation.

### Step 3: Verify Installation

```bash
# Open Claude Code in any project
cd ~/projects/my-project
claude

# Type /autodev — it should autocomplete
/autodev --help
```

If `/autodev` doesn't appear, check that the symlink points to the directory containing `.claude-plugin/plugin.json`.

### Step 4: Enable Auto Mode (Recommended)

AutoDev runs best with **auto mode**, which lets the pipeline execute without permission prompts:

```bash
# Start with auto mode enabled
claude --permission-mode auto

# Or add it to the Shift+Tab cycle so you can toggle it
claude --enable-auto-mode
```

Auto mode requires a Team, Enterprise, or API plan with Sonnet 4.6 or Opus 4.6. A background classifier reviews each action for safety — it's not the same as bypassing permissions entirely.

Without auto mode, you'll need to manually approve permission prompts during the pipeline (especially during agent dispatch and test execution).

---

## Using AutoDev on Any Repository

AutoDev works on **whatever repository you're currently in**. It explores the codebase in your current working directory, creates worktrees from it, and pushes branches to its origin.

### Using it on your own project

```bash
# 1. cd into your project
cd ~/projects/my-cool-app

# 2. Start Claude Code (if using Option A, it loads automatically)
claude

# 3. Run autodev with a GitHub issue or feature description
/autodev https://github.com/you/my-cool-app/issues/42
# or
/autodev Add dark mode support to the settings page
```

### Using it on a different repo than where AutoDev is installed

AutoDev is a plugin — it's installed once and available everywhere. You do NOT run it from inside the autodev repo itself.

```bash
# Wrong — this would try to implement features on the autodev plugin itself
cd ~/autodev
/autodev https://github.com/other/repo/issues/5

# Correct — cd to the target repo first
cd ~/projects/other-repo
claude
/autodev https://github.com/other/repo/issues/5
```

### Cross-repo workflow example

```bash
# Say you maintain 3 projects and have issues to fix in each:

# Project 1
cd ~/projects/api-server
claude
/autodev https://github.com/you/api-server/issues/15
# AutoDev explores api-server/, creates worktrees in api-server/, pushes to api-server fork

# Project 2
cd ~/projects/frontend
claude
/autodev Add responsive sidebar navigation
# AutoDev explores frontend/, creates worktrees in frontend/

# Project 3
cd ~/projects/data-pipeline
claude
/autodev https://github.com/you/data-pipeline/issues/8
```

### What AutoDev needs from your repo

AutoDev works best when your repository has:
- A test suite it can discover and run (pytest, npm test, cargo test, etc.)
- A `CLAUDE.md` or `README.md` describing conventions (optional but helps)
- A remote origin it can push branches to

If your repo has no tests, AutoDev will still implement features but cannot verify correctness automatically.

---

## Usage

### Basic Usage

```bash
# From a GitHub issue URL
/autodev https://github.com/owner/repo/issues/123

# From a free-text feature description
/autodev Add rate limiting to all API endpoints
```

### Workflow

1. **Invoke** `/autodev` with an issue URL or feature description
2. **AutoDev validates** the issue (runs tests, tries to reproduce bugs)
3. **AutoDev explores** the codebase and creates a task plan
4. **AutoDev implements** each feature in parallel worktrees
5. **AutoDev merges** results and runs the full test suite
6. **AutoDev reviews** code quality
7. **AutoDev reports** with a branch URL — you create the PR

---

## Key Principles

### No Auto-PRs

AutoDev **never creates pull requests automatically**. It pushes to your fork and provides the branch URL. You review the changes and create the PR yourself.

### Validate Before Coding

For bug reports, AutoDev reproduces the issue before fixing it. If it cannot reproduce the bug or find related code, it reports the issue as invalid and makes no changes.

### JSON for Task State

Task tracking lives in `.autodev/feature_list.json` — a structured JSON file, not markdown. This prevents accidental corruption by LLMs and enables reliable programmatic updates.

### Git Worktree Isolation

Each feature is implemented in a separate git worktree. This isolation prevents parallel agents from interfering with each other and provides clean, auditable branch history.

---

## Runtime Files

AutoDev creates files in `.autodev/` in the target repository:

| File | Purpose |
|------|---------|
| `.autodev/feature_list.json` | Task tracking — features, subtasks, statuses |
| `.autodev/agent-state.json` | Multi-agent coordination — claims, messages |
| `.autodev/autodev-progress.txt` | Human-readable progress log |

These files are committed to the branch alongside the implementation changes.

---

## Agents

### Coder Agent

Implements features in isolated git worktrees. Reads its assigned feature from `feature_list.json`, implements subtasks, writes tests, and runs the test suite before marking complete.

### Researcher Agent

On-demand agent for researching errors, APIs, and technical questions. Called when a coder gets stuck after 3+ failed attempts. Returns structured findings with code snippets and links to documentation.

### Reviewer Agent

Quality gate that runs after all features are merged. Checks for bugs, logic errors, convention violations, and test coverage. Returns a structured verdict (`APPROVED` or `CHANGES_REQUESTED`) with specific issue descriptions and fix recommendations.

---

## Git Branching

AutoDev uses a two-level branch structure:

| Branch | Purpose |
|--------|---------|
| `autodev/feat-N-<slug>` | Feature branch per agent |
| `autodev/issue-{N}` | Unified branch with all features |

Example:
```
main                           # Base branch
├── autodev/issue-123          # Unified branch (merged features)
│   ├── autodev/feat-1-user-auth      # Feature 1 branch
│   ├── autodev/feat-2-jwt-middleware # Feature 2 branch
│   └── autodev/feat-3-tests          # Feature 3 branch
```

---

## Lessons Learned

### Reproduce Before Fixing

Always verify a bug is real before implementing a fix:
1. Run the existing test suite
2. Search for error messages in the codebase
3. Try to follow the reproduction steps
4. Only then implement the fix

### Test on Simple Issues First

Before tackling complex issues, validate the system works on:
- Documentation fixes
- Typo corrections
- Issues where the fix is clearly defined

### Fork Push Only

AutoDev pushes changes to your fork, never to the upstream repository. This gives you a chance to review before anything reaches the main codebase.

---

## References

- [Harness Principles](skills/autodev/references/harness-principles.md) — Core operational rules
- [Issue Validation](skills/autodev/references/issue-validation.md) — Pre-implementation validation protocol
- [Feature List Schema](skills/autodev/references/feature-list-schema.md) — JSON schema for task tracking
- [Shared State Protocol](skills/autodev/references/shared-state-protocol.md) — Multi-agent coordination
- [Merge Strategy](skills/autodev/references/merge-strategy.md) — Branch merging protocol

---

*AutoDev is inspired by [OpenAI's Harness Engineering](https://openai.com/index/harness-engineering/) approach to autonomous coding agents.*
