# 🤖 Self-Improving Coding Agent Harness

## Project Overview

**Name:** AutoDev - Autonomous Coding Agent Harness

**Mission:** Build a system that, given a GitHub repository and an issue, can autonomously understand the problem, plan a solution, implement it with tests, iterate on failures, and create mergeable PRs — with minimal human intervention.

**Inspiration:** 
- [OpenAI: Harnessing Engineering](https://openai.com/index/harness-engineering/)
- Anthropic's agentic patterns

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER                                        │
│                   (Provides GitHub Issue / Task)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       INITIATOR AGENT                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ Issue       │  │ Task        │  │ PR          │  │ Quality     │   │
│  │ Parser      │  │ Decomposer  │  │ Manager     │  │ Gatekeeper  │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│  CODER AGENT 1   │   │  CODER AGENT 2   │   │  CODER AGENT N   │
│  (Feature A)     │   │  (Feature B)     │   │  (Feature N)     │
│                   │   │                   │   │                   │
│ - Write code     │   │ - Write code     │   │ - Write code     │
│ - Write tests    │   │ - Write tests    │   │ - Write tests    │
│ - Run tests      │   │ - Run tests      │   │ - Run tests      │
│ - Fix failures   │   │ - Fix failures   │   │ - Fix failures   │
└───────────────────┘   └───────────────────┘   └───────────────────┘
        │                         │                         │
        └─────────────────────────┼─────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       RESEARCH AGENT                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │ Web         │  │ Code        │  │ Error       │                 │
│  │ Search      │  │ Analysis    │  │ Debugging   │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      SUBTASK PLAN.md                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Feature: Login Feature                                          │   │
│  │  ├─ Subtask 1: Add user model ✓ DONE                         │   │
│  │  ├─ Subtask 2: Create auth endpoints ✓ DONE                  │   │
│  │  ├─ Subtask 3: Write unit tests ◐ IN_PROGRESS               │   │
│  │  └─ Subtask 4: Integration tests ✗ FAILED                    │   │
│  │                                                              │   │
│  │ Feature: Dashboard                                            │   │
│  │  ├─ Subtask 1: Create React components ○ PENDING             │   │
│  │  └─ Subtask 2: Connect API ◐ IN_PROGRESS                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Initiator Agent

**Responsibilities:**
- Parse GitHub issues
- Decompose into features
- Assign features to coder agents
- Track overall progress
- Create PRs
- Quality gate (tests pass, code review)

**Skills:**
- GitHub API
- Issue parsing
- PR creation/merging

### 2. Coder Agent (Multiple Instances)

**Responsibilities:**
- Implement subtasks sequentially
- Write code
- Write comprehensive tests
- Run tests and fix failures
- Report status back to initiator

**Skills:**
- Claude Code / OpenCode
- Git operations
- Test frameworks

### 3. Research Agent

**Responsibilities:**
- When subtask fails repeatedly
- Web search for solutions
- Deep research on errors
- Feed learnings back to coder

**Skills:**
- Tavily search
- Web browsing
- Error analysis

### 4. Subtask Plan (JSON + Markdown)

**Structure:**

```json
{
  "project": "my-awesome-repo",
  "issue": "#123 - Add user authentication",
  "features": [
    {
      "id": "feat_1",
      "name": "User Model",
      "status": "completed",
      "subtasks": [
        {
          "id": "subtask_1",
          "description": "Create User model with fields",
          "status": "completed",
          "agent": "coder_1",
          "attempts": 1,
          "error": null
        },
        {
          "id": "subtask_2", 
          "description": "Add validation to User model",
          "status": "failed",
          "agent": "coder_1",
          "attempts": 3,
          "error": "ValidationError: email format",
          "research_needed": true
        }
      ]
    }
  ],
  "metadata": {
    "created": "2026-02-28T10:00:00Z",
    "updated": "2026-02-28T12:30:00Z",
    "total_subtasks": 10,
    "completed": 4,
    "failed": 1,
    "in_progress": 2,
    "pending": 3
  }
}
```

**Markdown View (subtask_plan.md):**

```markdown
# Subtask Plan: Issue #123 - Add User Authentication

## Progress: 4/10 completed

## Feature 1: User Model ✓
- [x] subtask_1: Create User model - DONE (coder_1)
- [x] subtask_2: Add validation - DONE (coder_1)

## Feature 2: Auth Endpoints ◐
- [x] subtask_3: POST /register - DONE (coder_2)
- [ ] subtask_4: POST /login - IN_PROGRESS (coder_2)
- [ ] subtask_5: JWT middleware - PENDING

## Feature 3: Tests ✗
- [x] subtask_6: Unit tests - DONE (coder_1)
- [ ] subtask_7: Integration tests - FAILED (coder_1) ⚠️
  - Error: 3 failed tests
  - Research: triggered for error analysis
```

---

## Execution Flow

### Step 1: Issue Received

```
User → Issue #123: "Add user authentication"
```

### Step 2: Issue Parsing

```
Initiator:
├── Parse issue title & body
├── Extract requirements
├── Identify tech stack
└── Create feature list
```

### Step 3: Feature Decomposition

```
Feature 1: User Model
├── Subtask 1.1: Create database schema
├── Subtask 1.2: Add validation
└── Subtask 1.3: Add indexes

Feature 2: Auth Endpoints  
├── Subtask 2.1: POST /register
├── Subtask 2.2: POST /login
└── Subtask 2.3: JWT middleware

Feature 3: Testing
├── Subtask 3.1: Unit tests
├── Subtask 3.2: Integration tests
└── Subtask 3.3: E2E tests
```

### Step 4: Parallel Execution

```
┌──────────────────────────────────────────────────────┐
│              CODER AGENT POOL (N agents)             │
├──────────────────────────────────────────────────────┤
│ Agent 1: Feature 1 ──► subtask_1.1 → 1.2 → 1.3    │
│ Agent 2: Feature 2 ──► subtask_2.1 → 2.2 → 2.3    │
│ Agent 3: Feature 3 ──► subtask_3.1 → 3.2 → 3.3    │
└──────────────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
    ┌─────────────────────────────────────────┐
    │         SUBTASK PLAN (JSON)             │
    │    Updates in real-time as work        │
    │    progresses/fails/succeeds            │
    └─────────────────────────────────────────┘
```

### Step 5: Error Handling

```
Subtask FAILED:
├── Increment attempt count
├── Log error details
├── If attempts < 3: Retry
├── If attempts >= 3:
│   └── Trigger RESEARCH AGENT
│       ├── Search web for solutions
│       ├── Analyze similar code
│       └── Provide fix suggestions
│
└── Coder receives research findings
    └── Retry with new insights
```

### Step 6: PR Creation

```
All subtasks complete:
├── Run full test suite
├── Lint and format check
├── Create feature branch
├── Commit changes
├── Create PR with description
└── Add reviewers (if configured)
```

---

## Parallel Execution Strategy

### Independent Tasks (Run in Parallel)
- Features that don't depend on each other
- Different files/modules
- Tests for different components

### Sequential Tasks (Run in Order)
- Subtasks within same feature
- Database migrations
- Parent-child dependencies

### Decision Logic

```python
def can_run_parallel(subtask_a, subtask_b):
    """Check if two subtasks can run in parallel"""
    
    # Same file? Can't parallelize
    if subtask_a.file == subtask_b.file:
        return False
    
    # Dependency exists? Can't parallelize  
    if subtask_b.depends_on(subtask_a):
        return False
    
    # Uses same resource? Maybe can't
    if subtask_a.resource == subtask_b.resource:
        return False
        
    return True
```

---

## Research Agent Integration

### When Triggered

- Subtask fails 3+ times
- Error is unknown/uncommon
- Needs external knowledge

### Research Process

```
1. Analyze error message
2. Extract key terms
3. Search:
   - Stack Overflow
   - GitHub issues
   - Documentation
   - Blog posts
4. Synthesize findings
5. Provide actionable fix
```

### Output Format

```json
{
  "research_id": "research_123",
  "triggered_by": "subtask_2.3",
  "query": "TypeScript async/await testing Jest",
  "findings": [
    {
      "source": "stackoverflow.com/...",
      "title": "How to test async functions",
      "relevance": 0.9,
      "solution": "Use async/await in test..."
    }
  ],
  "recommended_fix": "Add 'async' to test function...",
  "confidence": 0.85
}
```

---

## File Structure

```
autodev/
├── README.md
├── docs/                    # Documentation
│   ├── harness_comparison.md
│   └── bugs_and_improvements.md
├── subtask_plan.md          # Current task plan
├── config/
│   ├── default.yaml         # Default config
│   └── repos/              # Repo-specific configs
│       └── my-repo.yaml
├── agents/
│   ├── initiator/           # Orchestrates workflow
│   ├── coder/               # Writes code
│   ├── reviewer/            # Agent-to-agent review ⭐ NEW
│   └── researcher/          # Web search for errors
├── core/
│   ├── github_client.py
│   ├── task_decomposer.py
│   ├── parallel_executor.py
│   ├── pr_manager.py
│   ├── activity_logger.py
│   └── session_history.py
├── dashboard/               # Web dashboard
├── integrations/
│   └── slack_bot.py         # Slack integration
└── utils/
    └── logger.py
```

---

## Configuration Example

```yaml
# config/repos/my-app.yaml

repo:
  owner: "my-org"
  name: "my-app"
  branch: "main"

issue:
  number: 123
  
agents:
  max_parallel: 4
  timeout_per_subtask: 600  # seconds
  
research:
  trigger_after_failures: 3
  max_research_time: 300
  
github:
  auto_create_pr: true
  auto_merge: false
  add_reviewers:
    - "tech-lead"
    
testing:
  run_before_pr: true
  coverage_threshold: 80
  
skills:
  - code_review
  - write_tests
  - run_tests
  - fix_errors
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Task completion rate | >90% |
| Research effectiveness | >70% |
| PR merge rate | >80% |
| Avg subtask attempts | <2 |
| Human intervention | <5% |

---

## Phase Roadmap

### Phase 1: Foundation ✅ DONE
- [x] Set up project structure
- [x] Implement GitHub client
- [x] Create task decomposer
- [x] Basic subtask tracking

### Phase 2: Single Agent ✅ DONE
- [x] Implement Coder agent
- [x] Connect to Claude Code / OpenCode
- [x] Basic test execution
- [x] Error handling

### Phase 3: Multi-Agent ✅ DONE
- [x] Implement Initiator
- [x] Task queue system
- [x] Parallel execution
- [x] Real-time updates

### Phase 4: Research Integration ✅ DONE
- [x] Implement Research agent
- [x] Web search integration
- [x] Error analysis
- [x] Feedback loop

### Phase 5: PR Pipeline ✅ DONE
- [x] PR creation
- [x] Agent-to-agent code review ⭐
- [ ] Auto-merge after CI
- [x] Full end-to-end test

### Phase 6: Polish 🔄
- [x] Enhanced logging
- [ ] Error handling improvements
- [ ] Rate limiting
- [ ] Test coverage
- [ ] Production deployment

---

## Agent Selection

AutoDev supports multiple agent backends. You can choose which agent to use based on your setup.

### Available Agents

- **opencode** - Uses OpenCode CLI (default)
- **claude-code** - Uses Claude Code CLI

### Command-Line Flags

| Flag | Description |
|------|-------------|
| `--agent-type` | Choose agent backend: `opencode` or `claude-code` |
| `--claude-skip-permissions` | Skip permission prompts for Claude Code (useful for CI/CD) |

### Shared Memory Context

AutoDev maintains a shared memory context across agent sessions using `core/agent_memory.py`. This allows:
- Context preservation between tasks
- Cross-agent knowledge sharing
- Persistent conversation history

The memory is stored in `.agent_memory/` directory and persists between runs.

---

## Usage Examples

### Example 1: Start from Issue (OpenCode)

```bash
python autodev.py --repo owner/repo --issue 123
```

### Example 2: Start from Issue (Claude Code)

```bash
python autodev.py --repo owner/repo --issue 123 --agent-type claude-code
```

### Example 3: Claude Code with Skip Permissions

```bash
python autodev.py --repo owner/repo --issue 123 --agent-type claude-code --claude-skip-permissions
```

### Example 4: Resume from Plan

```bash
python autodev.py --resume subtask_plan.json
```

### Example 5: Run Specific Feature

```bash
python autodev.py --feature user-auth --agent coder_1
```

---

## Dependencies

- Python 3.10+
- GitHub API
- Claude Code / OpenAI API
- Tavily (research)
- Redis (optional, for queue)

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Rate limits | Add delays, use multiple tokens |
| Infinite loops | Max attempts per subtask |
| Bad code | Quality gate before PR |
| Wrong direction | Human approval checkpoints |
| Lost progress | Save state frequently |

---

## Next Steps

1. ⬜ Review and refine this plan
2. ⬜ Set up project repo
3. ⬜ Implement core components
4. ⬜ Test with simple repo
5. ⬜ Scale up complexity

---

## Current Status & Roadmap

### ✅ Implemented

| Component | Status |
|-----------|--------|
| GitHub issue fetching & parsing | ✅ Done |
| Task decomposition | ✅ Done |
| Parallel execution with OpenCode | ✅ Done |
| Worktree management | ✅ Done |
| Activity logger + Dashboard | ✅ Done |
| PR creation | ✅ Done |
| Agent-to-agent code review | ✅ Done |
| Research agent | ✅ Done |
| Slack bot integration | ✅ Done |
| Enhanced logging | ✅ Done |

### 📋 Roadmap

#### 🔴 High Priority (Next)
1. **Auto-merge after CI** - Wait for CI → merge PR
2. **Knowledge base** - Update AGENTS.md, structured docs/
3. **Fix bugs** - See bugs_and_improvements.md

#### 🟡 Medium Priority
4. Chrome DevTools - UI bug reproduction
5. PromQL/LogQL access - Agents query metrics
6. Architecture linters - Enforce structure

#### 🟢 Future
7. Garbage collection agent - Auto-cleanup
8. Doc-gardening agent - Fix stale docs
9. Cost tracking - API spend per run

---

## OpenAI Harness Alignment

See [harness_comparison.md](./docs/harness_comparison.md) for detailed comparison with OpenAI's approach.

### Key Features Matching OpenAI
- ✅ Humans steer, agents execute
- ✅ Issue → Code → PR workflow
- ✅ Parallel agents with worktrees
- ✅ Agent-to-agent code review
- ✅ Activity logging & observability
- 🔲 Auto-merge after CI (in progress)
- 🔲 Chrome DevTools for UI testing

---

*Plan Version: 1.2*
*Updated: 2026-03-01*
*Based on OpenAI Harness Engineering + Anthropic Agent Patterns*
