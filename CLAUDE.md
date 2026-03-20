# AutoDev - Autonomous Coding Agent Harness

AutoDev is a self-improving autonomous coding agent harness inspired by OpenAI's Harness Engineering approach. Given a GitHub repository and an issue, AutoDev can autonomously understand the problem, plan a solution, implement it with tests, iterate on failures, and create mergeable PRs with zero human intervention.

## Architecture

### Core Components

| Component | Path | Description |
|-----------|------|-------------|
| **Orchestrator** | `core/orchestrator.py` | Coordinates entire workflow: fetch issue, decompose, create worktrees, dispatch to agents, merge results |
| **GitHub Client** | `core/github_client.py` | GitHub API interactions - issues, PRs, branches, rate limiting with retry logic |
| **Task Decomposer** | `core/task_decomposer.py` | Decomposes GitHub issues into features and subtasks using keyword detection |
| **State Manager** | `core/state_manager.py` | Tracks task plan state, persists to JSON, generates markdown views |
| **Parallel Executor** | `core/parallel_executor.py` | Executes tasks in parallel using Claude Code/OpenCode agents, manages git worktrees |
| **PR Manager** | `core/pr_manager.py` | Creates PRs, runs agent-to-agent review, waits for CI, merges |

### Agents

| Agent | Path | Description |
|-------|------|-------------|
| **Initiator** | `agents/initiator/agent.py` | Parses GitHub issues, decomposes into features, tracks progress, creates PRs |
| **Coder** | `agents/coder/agent.py` | Executes subtasks using Claude Code, writes code/tests, runs tests |
| **Researcher** | `agents/researcher/agent.py` | Web searches for error solutions using Tavily, provides fix recommendations |
| **Reviewer** | `agents/reviewer/agent.py` | Agent-to-agent code review - checks for bugs, quality, tests, approves or requests changes |

### Entry Points

| File | Purpose |
|------|---------|
| `run_autodev.py` | Primary orchestrator - runs full pipeline end-to-end |
| `autodev.py` | Main CLI entry point - parses args, loads config, runs initiator |
| `listen.py` | Slack bot integration - listens for bugs, asks for approval |
| `run_dashboard.py` | Dashboard web server |

## Configuration

Configuration is loaded from `config/default.yaml` with environment variable overrides.

### Environment Variables

| Variable | Config Path | Description |
|----------|-------------|-------------|
| `AUTODEV_GITHUB_TOKEN` | `github.token` | GitHub API token |
| `AUTODEV_GITHUB_OWNER` | `repo.owner` | Repository owner |
| `AUTODEV_GITHUB_REPO` | `repo.name` | Repository name |
| `AUTODEV_MAX_PARALLEL` | `agents.max_parallel` | Max parallel agents |
| `AUTODEV_TIMEOUT` | `agents.timeout_per_subtask` | Timeout per subtask (seconds) |
| `TAVILY_API_KEY` | - | For research agent (optional) |

### Default Config (config/default.yaml)

```yaml
repo:
  owner: ""
  name: ""
  branch: "main"

issue:
  number: null

agents:
  max_parallel: 4
  timeout_per_subtask: 600

research:
  trigger_after_failures: 3
  max_research_time: 300

github:
  auto_create_pr: true
  auto_merge: false
  add_reviewers: []

testing:
  run_before_pr: true
  coverage_threshold: 80
```

## Commands

### Run AutoDev

```bash
# Full pipeline with Claude Code (default)
python run_autodev.py --repo owner/repo --issue 123 --local-repo /path/to/repo

# With OpenCode agent
python run_autodev.py --repo owner/repo --issue 123 --local-repo /path --agent-type opencode

# Skip Claude permissions (for CI)
python run_autodev.py --repo owner/repo --issue 123 --local-repo /path --claude-skip-permissions

# With upstream repo (for forks)
python run_autodev.py --repo owner/repo --issue 123 --local-repo /path --upstream-repo upstream/repo
```

### Other Commands

```bash
# Slack bot
python listen.py

# Dashboard
python run_dashboard.py
```

## Development

### Project Structure

```
autodev/
├── agents/           # Agent implementations
├── config/           # Configuration loading
├── core/             # Core orchestration
├── dashboard/        # Web dashboard
├── docs/             # Documentation
├── examples/         # Example scripts
├── tests/            # Test suite
├── utils/            # Utilities
└── run_*.py          # Entry points
```

### Conventions

- **Files**: Snake_case (e.g., `github_client.py`)
- **Classes**: PascalCase (e.g., `GitHubClient`)
- **Functions**: Snake_case (e.g., `create_pr()`)
- **Logging**: `get_logger("autodev.module")`
- **Config**: Dataclasses for configuration objects

### AI/LLM Integration

- **Default Agent**: Claude Code CLI (`claude-code`)
- **Alternative**: OpenCode CLI (`opencode`)
- **Model**: `MiniMax-M2.5-highspeed` (configurable)
- **Permissions**: Use `--claude-skip-permissions` for CI automation

### Generated Files

AutoDev creates these files during execution:
- `.autodev/subtask_plan.json` - Task tracking
- `.autodev/subtask_plan.md` - Human-readable plan
- `.autodev/memory/` - Agent shared memory
- `CLAUDE.md` - Project context for agents (auto-generated in target repo)

## Lessons Learned (Critical)

### NEVER Auto-Create PRs to Main Repo
- **Rule**: Always push changes to user's fork only
- **Output**: Show branch URLs for user to review
- **User Workflow**: User creates PR manually after reviewing changes
- **Why**: AutoDev may introduce bugs; user needs to review before any PR

### ALWAYS Reproduce Issues First
Before fixing any issue, the agent must:
1. Analyze the issue to understand expected vs actual behavior
2. Try to reproduce the issue locally
3. Verify it's a real bug (not user error)
4. Understand the root cause
5. THEN plan the fix
6. Verify fix works before committing

### Test on Dummy Issues First
Before real issues, test on:
- Simple documentation fixes
- Obvious typo fixes
- Issues where the fix is clearly defined

This validates the system works before tackling complex issues.

### Fork Push Authentication
When pushing to forks, include token in push URL:
```python
push_url = f"https://{github_token}@github.com/{fork_owner}/{repo_name}.git"
```

### Reviewer Agent Status
The reviewer agent (`agents/reviewer/agent.py`) has known issues:
- Parses positive feedback as negative issues
- Creates noise instead of useful reviews
- Currently disabled by default - rely on user review

