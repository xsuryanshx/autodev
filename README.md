# AutoDev — Autonomous Coding Harness

AutoDev is a [Claude Code](https://claude.ai/code) plugin that autonomously implements GitHub issues and feature requests. Given a repository and an issue, AutoDev validates the problem, decomposes work into parallel tasks, implements each feature in sandboxed environments, and delivers a branch ready for human review.

---

## Architecture Overview

AutoDev runs as a Claude Code plugin. The lead agent orchestrates the 8-phase pipeline, dispatching parallel subagents via a `ThreadPoolExecutor`. Each subagent runs in an isolated sandbox — either a local path-checked workspace or an [E2B](https://e2b.dev) cloud microVM.

```
                    ┌─────────────────────────────────────┐
                    │           /autodev                   │
                    │     (Claude Code Plugin Command)     │
                    └─────────────────┬───────────────────┘
                                      │
                         ┌────────────┴────────────┐
                         │    SubagentExecutor      │
                         │   (ThreadPoolExecutor)   │
                         │    max_parallelism=3     │
                         └────────────┬────────────┘
                                      │
                         ┌────────────┴────────────┐
                         │    SandboxManager        │
                         │  (lifecycle, snapshots)  │
                         └──┬──────────┬──────────┬┘
                            │          │          │
                   ┌────────▼──┐ ┌─────▼─────┐ ┌──▼────────┐
                   │ Sandbox 1 │ │ Sandbox 2 │ │ Sandbox 3 │
                   │ (feat-1)  │ │ (feat-2)  │ │ (feat-3)  │
                   └───────────┘ └───────────┘ └───────────┘
                        │              │              │
              ┌─────────┴──────────────┴──────────────┴─────────┐
              │  Backend: "local" (path-checked subprocess)     │
              │       OR: "e2b"  (Firecracker microVM)          │
              └─────────────────────────────────────────────────┘
                                      │
                                      ▼
                        ┌─────────────────────────┐
                        │   Merge → Review → Push │
                        │   (unified branch)      │
                        └─────────────────────────┘
```

### Sandbox Backends

| Backend | Isolation Level | Latency | Cost | Best For |
|---------|----------------|---------|------|----------|
| `local` | Path-checking + env sanitization + command blocklist | Zero (local subprocess) | Free | Development, trusted agents |
| `e2b` | Full kernel isolation (Firecracker microVM) | ~200ms boot | ~$0.05/hr/vCPU | Production, untrusted code, scaling beyond local |

---

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

If AutoDev cannot reproduce a bug or find related code, it reports the issue as invalid and makes no changes.

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

### Phase 5: Parallel Implementation

Each feature is dispatched to a sandboxed subagent via the `SubagentExecutor`:

1. `SandboxManager` creates an isolated sandbox per task (local dir or E2B VM)
2. The sandbox is bootstrapped with the repo clone and dependencies
3. The `CoderHandler` implements subtasks, writes tests, runs the test suite
4. Results are collected and the sandbox is torn down

Up to 3 subagents run concurrently with a 15-minute timeout per task.

### Phase 6: Merge Results

AutoDev aggregates files from all subagent workspaces into the unified branch:
1. Collect created/modified files from each sandbox
2. Copy to the main working tree
3. Run the full test suite
4. Handle conflicts if multiple agents modified the same file

### Phase 7: Review

A Reviewer agent performs a quality gate check:
- Bug detection and logic errors
- Convention compliance
- Test coverage and quality
- Security issues

Returns structured verdict: `APPROVED` or `CHANGES_REQUESTED`.

### Phase 8: Report

AutoDev pushes the unified branch to your fork and provides the branch URL. **It never creates a PR automatically.** You review the changes and create the PR yourself.

---

## Project Structure

```
autodev/
├── .claude-plugin/
│   └── plugin.json                  # Plugin manifest
├── commands/
│   └── autodev.md                   # /autodev command (8 phases)
├── agents/
│   ├── coder.md                     # Coder agent skill
│   ├── researcher.md                # Researcher agent (on-demand)
│   ├── reviewer.md                  # Reviewer agent (quality gate)
│   ├── subagent.md                  # Subagent skill definition
│   └── subagent_handlers.py         # CoderHandler, ResearcherHandler
├── core/
│   ├── sandbox_backend.py           # SandboxBackend protocol, SandboxConfig, ToolResult
│   ├── sandboxed_tools.py           # Local sandbox (path-checked, env-sanitized)
│   ├── e2b_sandbox.py               # E2B cloud sandbox (Firecracker microVM)
│   ├── sandbox_manager.py           # Lifecycle manager (create, track, snapshot, destroy)
│   ├── subagent_executor.py         # ThreadPoolExecutor-based dispatcher
│   └── task_context.py              # Per-task context isolation via ContextVar
├── skills/autodev/
│   ├── task_tool.md                 # task() tool specification
│   └── references/
│       ├── harness-principles.md    # Core operational rules
│       ├── issue-validation.md      # Pre-implementation validation
│       ├── feature-list-schema.md   # Task tracking schema
│       ├── shared-state-protocol.md # Multi-agent coordination
│       └── merge-strategy.md        # Branch merging protocol
├── tests/                           # 100+ tests
│   ├── test_sandboxed_tools.py      # Local sandbox tests (env, command blocking)
│   ├── test_e2b_sandbox.py          # E2B sandbox tests (mocked SDK)
│   ├── test_sandbox_manager.py      # Lifecycle manager tests
│   ├── test_subagent_executor.py    # Executor concurrency tests
│   ├── test_task_context.py         # ContextVar isolation tests
│   ├── test_subagent_handlers.py    # Handler tests
│   ├── test_parallel_subagent_integration.py
│   └── test_e2e_executor.py         # Full pipeline E2E tests
└── requirements.txt                 # e2b>=1.2.0, pytest>=7.0.0
```

---

## Installation

```bash
git clone https://github.com/suryanshrawat/autodev.git
cd autodev

# Install Python dependencies
pip install -r requirements.txt
```

### Requirements

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- GitHub CLI (`gh`) authenticated: `gh auth login`
- A target repository with write access (for pushing to fork)
- **For E2B backend:** An [E2B account](https://e2b.dev) and API key

---

## Usage

### As a Claude Code Plugin

```bash
# From a GitHub issue URL
/autodev https://github.com/owner/repo/issues/123

# From a free-text feature description
/autodev Add rate limiting to all API endpoints
```

### Running the Executor Directly (Python)

#### Local Backend (default)

```python
from core.subagent_executor import SubagentExecutor, SubagentTask
from agents.subagent_handlers import CoderHandler

executor = SubagentExecutor(
    workspace="/tmp/autodev-workspace",
    max_parallelism=3,
    timeout_per_task=900,
)
executor.register_handler("coder", CoderHandler().execute)

tasks = [
    SubagentTask(
        task_id="feat-1",
        description="Implement user auth",
        prompt="Create JWT middleware in src/auth.py with tests",
        skill="coder",
        context={"repo_path": "/path/to/repo"},
    ),
    SubagentTask(
        task_id="feat-2",
        description="Add rate limiting",
        prompt="Add rate limiting middleware with Redis backend",
        skill="coder",
    ),
]

results = executor.submit_and_wait(tasks)
for r in results:
    print(f"{r.task_id}: {r.status} ({r.duration_seconds:.1f}s)")

executor.shutdown()
```

#### E2B Backend (cloud sandboxes)

```python
import os
from core.sandbox_backend import SandboxConfig
from core.subagent_executor import SubagentExecutor, SubagentTask
from agents.subagent_handlers import CoderHandler

config = SandboxConfig(
    backend="e2b",
    e2b_template="base",                    # or your custom template ID
    e2b_api_key=os.environ["E2B_API_KEY"],  # or set E2B_API_KEY env var
    timeout_seconds=900,
)

executor = SubagentExecutor(
    workspace="/tmp/autodev-workspace",
    max_parallelism=3,
    sandbox_config=config,
)
executor.register_handler("coder", CoderHandler().execute)

# Optional: create a warm snapshot so agents start with repo pre-cloned
snap_id = executor.sandbox_manager.create_warm_snapshot(
    repo_url="https://github.com/owner/repo.git",
    branch="main",
    clone_token=os.environ.get("GITHUB_TOKEN"),
)
print(f"Warm snapshot ready: {snap_id}")

# Dispatch tasks — each gets its own Firecracker microVM
tasks = [
    SubagentTask(task_id="feat-1", description="Auth", prompt="...", skill="coder"),
    SubagentTask(task_id="feat-2", description="API", prompt="...", skill="coder"),
]
results = executor.submit_and_wait(tasks)

executor.shutdown()  # Destroys all sandboxes
```

#### Configuration via JSON File

Create `.autodev/config.json` in your target repo:

```json
{
  "sandbox": {
    "backend": "e2b",
    "e2b_template": "base",
    "timeout_seconds": 900,
    "e2b_auto_pause": true
  }
}
```

Load it:

```python
from core.sandbox_backend import SandboxConfig
from core.subagent_executor import SubagentExecutor

config = SandboxConfig.from_file(".autodev/config.json")
executor = SubagentExecutor(workspace="/tmp/ws", sandbox_config=config)
```

### CLI (`python -m core`)

From the plugin root, with `PYTHONPATH` set to that directory (or run from the repo root):

```bash
export PYTHONPATH="$(pwd)"

# Run tasks from JSON (tasks file + optional flags)
python -m core run \
  --workspace /path/to/repo/.autodev/workspaces \
  --backend local \
  --repo https://github.com/owner/repo.git \
  --branch main \
  --tasks .autodev/tasks.json \
  --output .autodev/driver-results.json

# Merge a full driver config file
python -m core run --config .autodev/driver-config.json --output .autodev/driver-results.json

# E2B warm snapshot (requires E2B_API_KEY)
python -m core snapshot --repo https://github.com/owner/repo.git --branch main --output .autodev/e2b-snapshot.json

# In-process sandbox tracking note
python -m core status
```

### JSON driver (`core/driver.py`)

Pipe JSON on stdin or use `--config`:

```bash
python -m core.driver --config .autodev/driver-config.json --output .autodev/driver-results.json
cat .autodev/driver-config.json | python -m core.driver -o .autodev/driver-results.json
```

### Claude Code integration

- **Slash command:** [commands/autodev.md](commands/autodev.md) Phase 5 — driver JSON + `python -m core run`.
- **Skill:** [skills/autodev/parallel-sandbox-executor.md](skills/autodev/parallel-sandbox-executor.md) — dispatch procedure and result handling.
- **Backend registry:** [skills/autodev/agent-backend.md](skills/autodev/agent-backend.md) — `sandbox` backend alongside OpenCode.

---

## Running Tests

```bash
# Run the full test suite
python -m pytest tests/ -v

# Run only sandbox tests
python -m pytest tests/test_sandboxed_tools.py tests/test_e2b_sandbox.py -v

# Run only executor/integration tests
python -m pytest tests/test_subagent_executor.py tests/test_parallel_subagent_integration.py -v

# Run E2E tests (real file I/O, real subprocess execution)
python -m pytest tests/test_e2e_executor.py -v -s
```

All E2B tests use a mocked SDK — no API key or network access required.

---

## Sandboxing

### Local Sandbox (`core/sandboxed_tools.py`)

The local backend provides defense-in-depth for running on a developer's machine:

- **Path checking:** `read_file`, `write_file`, `glob`, `grep` are restricted to the task workspace directory via `_check_path()`. Symlink traversal is blocked.
- **Environment sanitization:** `bash()` runs with a stripped environment that only includes `PATH`, `HOME`, `LANG`, `PYTHONPATH`, and other safe keys. Secrets like `GITHUB_TOKEN`, `AWS_SECRET_ACCESS_KEY` are never passed to subprocesses.
- **Command blocklist:** Dangerous patterns (`rm -rf /`, `sudo`, `mkfs`, `shutdown`, `reboot`, `dd of=/dev/`, `nc -l`) are rejected before execution.
- **Timeout:** Every bash command has a configurable timeout (default 300s).

**Limitation:** `bash()` still runs on the host — a sophisticated command can access the filesystem outside the workspace. For true isolation, use E2B.

### E2B Sandbox (`core/e2b_sandbox.py`)

The E2B backend provides hardware-level isolation via Firecracker microVMs:

- **Separate kernel:** Each sandbox runs its own Linux kernel. Container escape is impossible.
- **Clean filesystem:** No access to host files, secrets, or processes.
- **Network isolation:** Configurable per-sandbox network policies.
- **Resource limits:** CPU and RAM are capped per-VM by E2B.
- **Snapshotting:** Freeze a sandbox with the repo cloned and deps installed, then start future sandboxes from that snapshot in ~1 second.
- **Auto-cleanup:** Sandboxes auto-kill on timeout. No zombie processes or orphaned workspaces.

### Sandbox Manager (`core/sandbox_manager.py`)

The `SandboxManager` handles the full lifecycle:

```python
manager = SandboxManager(config)

# Create sandboxes
sandbox = manager.create_sandbox("task-1")

# Bootstrap with repo
manager.setup_sandbox("task-1", repo_url="https://github.com/owner/repo.git")

# Track active sandboxes
print(manager.active_count)
print(manager.list_sandboxes())

# E2B-specific: pause to stop billing, resume later
manager.pause_sandbox("task-1")
manager.resume_sandbox("task-1")

# Create warm snapshot for fast starts
snap_id = manager.create_warm_snapshot(repo_url="...", branch="main")

# Cleanup
manager.destroy_sandbox("task-1")
manager.shutdown()  # Destroys all
```

---

## Key Principles

### No Auto-PRs

AutoDev **never creates pull requests automatically**. It pushes to your fork and provides the branch URL. You review the changes and create the PR yourself.

### Validate Before Coding

For bug reports, AutoDev reproduces the issue before fixing it. If it cannot reproduce the bug or find related code, it reports the issue as invalid and makes no changes.

### JSON for Task State

Task tracking lives in `.autodev/feature_list.json` — a structured JSON file, not markdown. This prevents accidental corruption by LLMs and enables reliable programmatic updates.

### Sandbox Isolation

Every subagent runs in its own sandbox. On local, this means a separate workspace directory with path-checking and env sanitization. On E2B, this means a full microVM with its own kernel. Agents cannot interfere with each other or the host.

---

## Runtime Files

AutoDev creates files in `.autodev/` in the target repository:

| File | Purpose |
|------|---------|
| `.autodev/feature_list.json` | Task tracking — features, subtasks, statuses |
| `.autodev/agent-state.json` | Multi-agent coordination — claims, messages |
| `.autodev/autodev-progress.txt` | Human-readable progress log |
| `.autodev/config.json` | Sandbox and execution configuration |

---

## Agents

### Coder Agent

Implements features in sandboxed environments. Reads its assigned feature from `feature_list.json`, implements subtasks, writes tests, and runs the test suite before marking complete.

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

```
main
├── autodev/issue-123               # Unified branch (merged features)
│   ├── autodev/feat-1-user-auth    # Feature 1 branch
│   ├── autodev/feat-2-jwt-middleware
│   └── autodev/feat-3-tests
```

---

## References

- [Harness Principles](skills/autodev/references/harness-principles.md) — Core operational rules
- [Issue Validation](skills/autodev/references/issue-validation.md) — Pre-implementation validation protocol
- [Feature List Schema](skills/autodev/references/feature-list-schema.md) — JSON schema for task tracking
- [Shared State Protocol](skills/autodev/references/shared-state-protocol.md) — Multi-agent coordination
- [Merge Strategy](skills/autodev/references/merge-strategy.md) — Branch merging protocol
- [DeerFlow Architecture Mapping](docs/deerflow_subagents_learnings.md) — How AutoDev's parallel model maps to DeerFlow

---

*AutoDev is inspired by [OpenAI's Harness Engineering](https://openai.com/index/harness-engineering/) approach to autonomous coding agents and [DeerFlow's](https://github.com/bytedance/deer-flow) parallel subagent execution model.*
