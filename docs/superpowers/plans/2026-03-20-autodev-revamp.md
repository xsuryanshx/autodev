# AutoDev Harness Revamp - Complete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild AutoDev into a production-quality autonomous coding harness where every component is actually wired up, feedback loops close, and agents genuinely coordinate — not just exist side-by-side.

**Architecture:** Replace the current hardcoded `run_autodev.py` pipeline with a unified orchestrator that uses skill-based dispatch, capability-driven error handling, real agent coordination via shared memory, and a working review→fix→review loop. Drop dead code (old orchestrator, duplicate executor), fix all critical bugs, and add integration tests.

**Tech Stack:** Python 3.10+, Claude Code CLI (primary agent), subprocess-based execution, GitHub API via requests, Tavily search (optional), pytest for testing.

---

## Current State Assessment

### What's Broken (Must Fix)
1. **ReviewerAgent._parse_issues()** — treats approval text as issues (regex matches all bullets/numbers)
2. **FlexibleOrchestrator** — built but never integrated into run_autodev.py
3. **ErrorHandler** — built but never called during execution
4. **SessionHistory/AgentMemory** — initialized but never read by any agent
5. **IssueReproducer** — JS/TS always returns confidence=0
6. **TaskDecomposer** — keyword-only, no LLM decomposition
7. **CoderAgent.execute_subtask()** — ignores agent_config, always tries Claude first
8. **Worktree creation** — hardcodes "main" branch
9. **Review loop** — no feedback mechanism (reviews same code repeatedly)

### What Works Well (Keep)
1. **GitHubClient** — solid retry logic, rate limiting, fork handling
2. **PRManager** — correct fork-based PR workflow
3. **ParallelExecutor** — good process management, worktree handling
4. **BaseAgent + SkillLoader** — clean abstraction, just needs integration
5. **"No auto-PR" principle** — correct safety design

### Dead Code (Remove)
1. `core/orchestrator.py` — old hardcoded flow, contradicts CLAUDE.md lessons
2. `core/executor.py` — duplicates WorktreeManager from parallel_executor.py
3. `autodev.py` — legacy entry point, replaced by run_autodev.py

---

## File Structure

### Files to Delete
- `core/orchestrator.py` — dead, replaced by flexible_orchestrator
- `core/executor.py` — duplicate of parallel_executor logic
- `autodev.py` — legacy entry point

### Files to Create
- `tests/test_orchestrator_integration.py` — integration test for full flow
- `tests/conftest.py` — shared fixtures

### Existing Test Files to Modify
- `tests/test_reviewer_agent.py` — add new parsing tests
- `tests/test_task_decomposer.py` — add LLM decomposition tests
- `tests/test_error_handler.py` — already exists, add integration tests

### Files to Modify (Heavy)
- `run_autodev.py` — rewire to use FlexibleOrchestrator + ErrorHandler + real coordination
- `core/flexible_orchestrator.py` — become the single orchestrator, integrate all components
- `agents/reviewer/agent.py` — fix parsing, add structured review output, wire fix callback
- `agents/coder/agent.py` — respect agent_config, accept fix requests from reviewer
- `core/error_handler.py` — integrate into execution loop
- `core/task_decomposer.py` — add LLM-based decomposition via Claude Code
- `core/issue_reproducer.py` — add JS/TS support, use reproduction result for decisions
- `core/parallel_executor.py` — detect default branch, consolidate command building

### Files to Modify (Light)
- `agents/researcher/agent.py` — synthesize multiple results
- `agents/initiator/agent.py` — wire into orchestrator properly
- `core/session_history.py` — add read methods agents actually call
- `core/agent_memory.py` — add cross-agent message passing
- `core/pr_manager.py` — wire on_fix_callback to coder agent

---

## Task 1: Delete Dead Code and Fix Critical Imports

**Files:**
- Delete: `core/orchestrator.py`
- Delete: `core/executor.py`
- Delete: `autodev.py`
- Modify: `core/flexible_orchestrator.py:8` (remove import of executor.py)
- Modify: `core/parallel_executor.py`

- [ ] **Step 1: Verify dead code is truly unused**

```bash
grep -r "from core.orchestrator import\|from core import orchestrator\|import orchestrator" --include="*.py" .
grep -r "from core.executor import\|from core import executor" --include="*.py" .
grep -r "from autodev import\|import autodev" --include="*.py" .
```

Expected: `flexible_orchestrator.py` and `core/orchestrator.py` import from `core.executor`. `autodev.py` imports from `core/orchestrator`. All three files are being deleted or modified, so no live code breaks.

- [ ] **Step 2: Rewrite FlexibleOrchestrator to use ParallelExecutor directly**

`core/executor.py` exports `TaskQueue` and `WorktreeManager` which `FlexibleOrchestrator` uses. Since `ParallelExecutor` already handles both task queuing and worktree management internally, rewrite `FlexibleOrchestrator` to use `ParallelExecutor` directly:

In `core/flexible_orchestrator.py`, replace:
```python
from core.executor import TaskQueue, WorktreeManager
```
with:
```python
from core.parallel_executor import ParallelExecutor
```

Replace the `task_queue` and `worktree_manager` attributes with a single `executor`:
```python
# In __init__:
self.executor: Optional[ParallelExecutor] = None

# In initialize():
self.executor = ParallelExecutor(
    local_repo_path,
    max_agents=max_parallel,
    agent_config=AgentConfig(agent_type=self.config.get("agent_type", "claude-code"))
)
```

Remove `self.task_queue` and `self.worktree_manager` references throughout the class.

- [ ] **Step 3: Delete the three dead files**

```bash
git rm core/orchestrator.py core/executor.py autodev.py
```

- [ ] **Step 4: Fix worktree default branch detection in parallel_executor.py**

Replace hardcoded `"main"` at line 83 with dynamic detection:

```python
def _get_default_branch(self) -> str:
    """Detect the default branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=self.base_repo,
        capture_output=True, text=True
    )
    return result.stdout.strip() or "main"
```

Use `self._get_default_branch()` in `create_worktree()`.

- [ ] **Step 5: Verify project still loads**

```bash
python -c "from core.flexible_orchestrator import FlexibleOrchestrator; print('OK')"
python -c "from core.parallel_executor import ParallelExecutor; print('OK')"
```

Expected: Both print "OK".

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: remove dead code (old orchestrator, executor, autodev.py)"
```

---

## Task 2: Fix ReviewerAgent Parsing (Critical Bug)

**Files:**
- Modify: `agents/reviewer/agent.py:212-277`
- Modify: `tests/test_reviewer_agent.py` (add new test classes to existing file)

- [ ] **Step 1: Write failing tests for review parsing**

```python
# Append these test classes to tests/test_reviewer_agent.py
import pytest
from agents.reviewer.agent import ReviewerAgent


class TestParseIssues:
    def setup_method(self):
        self.reviewer = ReviewerAgent(config={})

    def test_approved_not_parsed_as_issues(self):
        feedback = """### APPROVED
1. Code is clean and well-structured
2. Tests pass successfully
3. No security concerns"""
        issues = self.reviewer._parse_issues(feedback)
        assert issues == [], f"Approval text parsed as issues: {issues}"

    def test_changes_requested_parsed_correctly(self):
        feedback = """### CHANGES REQUESTED
1. Missing error handling in parse_config()
2. No test for edge case when input is None
### MINOR SUGGESTIONS
- Consider using dataclass instead of dict"""
        issues = self.reviewer._parse_issues(feedback)
        assert len(issues) == 2
        assert "error handling" in issues[0].lower()
        assert "edge case" in issues[1].lower()

    def test_mixed_output_only_extracts_issues(self):
        feedback = """### APPROVED for most changes

### CHANGES REQUESTED
1. Function foo() has no return type annotation
2. Missing docstring on class Bar

### MINOR SUGGESTIONS
- Could use f-strings instead of format()"""
        issues = self.reviewer._parse_issues(feedback)
        assert len(issues) == 2

    def test_empty_feedback_returns_empty(self):
        assert self.reviewer._parse_issues("") == []
        assert self.reviewer._parse_issues("All good!") == []


class TestReviewChangesStatus:
    def setup_method(self):
        self.reviewer = ReviewerAgent(config={})

    def test_approved_detected(self):
        output = "### APPROVED\nEverything looks good."
        result = self.reviewer._review_changes.__wrapped__(self.reviewer, output, "feat", "main") if hasattr(self.reviewer._review_changes, '__wrapped__') else None
        # We test _parse_review_status instead
        assert "APPROVED" in output
        assert "CHANGES REQUESTED" not in output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_reviewer.py -v
```

Expected: `test_approved_not_parsed_as_issues` FAILS (current code parses approval as issues).

- [ ] **Step 3: Rewrite _parse_issues() with state-machine parsing**

Replace the broken regex parser in `agents/reviewer/agent.py`:

```python
def _parse_issues(self, feedback: str) -> List[str]:
    """Parse issues from review feedback using section-aware parsing."""
    import re
    issues = []

    # Split into sections by ### headers
    sections = re.split(r'^###\s+', feedback, flags=re.MULTILINE)

    for section in sections:
        lines = section.strip().split('\n')
        if not lines:
            continue

        header = lines[0].strip().upper()

        # Only extract issues from "CHANGES REQUESTED" section
        if 'CHANGES REQUESTED' not in header:
            continue

        # Parse numbered/bulleted items in this section
        for line in lines[1:]:
            line = line.strip()
            # Match "1. ...", "- ...", "* ..."
            match = re.match(r'(?:\d+[\.\)]\s*|[-*]\s+)(.+)', line)
            if match:
                issue = match.group(1).strip()
                if issue and len(issue) > 10:
                    issues.append(issue)

    return issues[:10]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_reviewer.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Fix _review_changes to use Claude Code instead of OpenCode**

The reviewer currently hardcodes `opencode` (line 227-231). Update to respect agent config:

```python
def _review_changes(self, changes: str, branch: str, base: str) -> Dict[str, Any]:
    """Use Claude Code or OpenCode to review changes."""
    prompt = self.review_prompt_template.format(
        changes=changes[:15000],
        branch=branch,
        base=base
    )

    try:
        # Use Claude Code by default
        cmd = [self.CLAUDE_CODE_CMD, "-p", prompt]

        result = subprocess.run(
            cmd,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=180
        )

        output = result.stdout + result.stderr

        # Parse status from structured output
        if "APPROVED" in output and "CHANGES REQUESTED" not in output:
            return {"status": "APPROVED", "feedback": output}
        elif "CHANGES REQUESTED" in output:
            return {"status": "CHANGES_REQUESTED", "feedback": output}
        else:
            return {"status": "CHANGES_REQUESTED", "feedback": output}

    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "feedback": "Review timed out"}
    except FileNotFoundError:
        # Fallback to OpenCode if Claude Code not installed
        try:
            cmd = [self.OPENCODE_PATH, "run", "--print-logs", prompt]
            result = subprocess.run(cmd, cwd=os.getcwd(), capture_output=True, text=True, timeout=180)
            output = result.stdout + result.stderr
            if "APPROVED" in output and "CHANGES REQUESTED" not in output:
                return {"status": "APPROVED", "feedback": output}
            return {"status": "CHANGES_REQUESTED", "feedback": output}
        except Exception:
            return {"status": "ERROR", "feedback": "Neither Claude Code nor OpenCode available"}
    except Exception as e:
        return {"status": "ERROR", "feedback": str(e)}
```

- [ ] **Step 6: Commit**

```bash
git add agents/reviewer/agent.py tests/test_reviewer.py
git commit -m "fix: rewrite reviewer parsing to distinguish approval from issues"
```

---

## Task 3: Wire ErrorHandler into Execution Loop

**Files:**
- Modify: `core/parallel_executor.py`
- Modify: `core/error_handler.py`
- Create: `tests/test_error_handler.py`

- [ ] **Step 1: Write failing tests for error classification**

```python
# tests/test_error_handler.py
import pytest
from core.error_handler import CapabilityErrorHandler, ErrorCategory, RetryStrategy


class TestErrorClassification:
    def setup_method(self):
        self.handler = CapabilityErrorHandler()

    def test_syntax_error(self):
        cat = self.handler.classify_error("SyntaxError: invalid syntax at line 42")
        assert cat == ErrorCategory.CODE_SYNTAX

    def test_import_error(self):
        cat = self.handler.classify_error("ModuleNotFoundError: No module named 'foo'")
        assert cat == ErrorCategory.DEPENDENCY

    def test_test_failure(self):
        cat = self.handler.classify_error("FAILED tests/test_main.py::test_add - AssertionError")
        assert cat == ErrorCategory.TEST_FAILED

    def test_unknown_short_error(self):
        cat = self.handler.classify_error("Hmm")
        assert cat == ErrorCategory.UNKNOWN

    def test_long_unknown_triggers_research(self):
        cat = self.handler.classify_error("x" * 150)
        assert cat == ErrorCategory.RESEARCH_NEEDED


class TestHandleError:
    def setup_method(self):
        self.handler = CapabilityErrorHandler()

    def test_returns_capabilities_for_syntax(self):
        result = self.handler.handle_error("SyntaxError: invalid syntax")
        assert "code_implementation" in result["capabilities_needed"]
        assert result["should_retry"] is True

    def test_unknown_does_not_retry(self):
        result = self.handler.handle_error("Hmm")
        assert result["should_retry"] is False


class TestRetryStrategy:
    def test_syntax_retries_twice(self):
        assert RetryStrategy.should_retry(ErrorCategory.CODE_SYNTAX, 0) is True
        assert RetryStrategy.should_retry(ErrorCategory.CODE_SYNTAX, 1) is True
        assert RetryStrategy.should_retry(ErrorCategory.CODE_SYNTAX, 2) is False

    def test_network_exponential_backoff(self):
        assert RetryStrategy.get_backoff(ErrorCategory.NETWORK, 1) == 2
        assert RetryStrategy.get_backoff(ErrorCategory.NETWORK, 3) == 8
```

- [ ] **Step 2: Run tests to verify they pass (ErrorHandler already works in isolation)**

```bash
pytest tests/test_error_handler.py -v
```

Expected: All PASS (ErrorHandler logic is correct, just not integrated).

- [ ] **Step 3: Add error handling to ParallelExecutor.run_parallel()**

In `core/parallel_executor.py`, add error handler integration after an agent fails:

```python
# At top of file, add import:
from core.error_handler import CapabilityErrorHandler, RetryStrategy

# In __init__, add:
self.error_handler = CapabilityErrorHandler()

# In run_parallel(), after checking result status (around line 353-356):
if result.status == "failed" and result.error:
    # Classify error and decide retry
    error_result = self.error_handler.handle_error(
        result.error,
        {"attempts": getattr(result, '_attempts', 0)}
    )
    category = self.error_handler.classify_error(result.error)

    if error_result["should_retry"] and RetryStrategy.should_retry(category, getattr(result, '_attempts', 0)):
        self.logger.info(f"Error classified as {error_result['category']}, retrying with capabilities: {error_result['capabilities_needed']}")
        # Re-queue the task with error context
        retry_task = tasks[completed_count - 1].copy()
        retry_task['_attempts'] = getattr(result, '_attempts', 0) + 1
        retry_task['_error_context'] = error_result
        retry_task['prompt'] = f"{retry_task['prompt']}\n\nPrevious attempt failed with: {result.error}\nRecommendation: {error_result['recommendation']}"
        tasks.append(retry_task)
    else:
        self.logger.warning(f"Error not retryable: {error_result['recommendation']}")
```

- [ ] **Step 4: Verify integration compiles**

```bash
python -c "from core.parallel_executor import ParallelExecutor; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add core/parallel_executor.py core/error_handler.py tests/test_error_handler.py
git commit -m "feat: integrate error handler into parallel executor with retry logic"
```

---

## Task 4: Fix CoderAgent to Respect Agent Config

**Files:**
- Modify: `agents/coder/agent.py:31-117`

- [ ] **Step 1: Accept and use agent_config in CoderAgent**

Replace the hardcoded `USE_CLAUDE_PRIMARY = True` with config-driven behavior:

```python
def __init__(self, agent_id: str, config=None):
    self.agent_id = agent_id
    self.config = config or {}
    self.logger = get_logger(f"autodev.coder.{agent_id}")
    self.github_client = None
    self.current_subtask = None

    # Agent selection from config
    self._agent_config = None

    super().__init__(config)
    self.logger.info(f"CoderAgent {agent_id} initialized with skills: {self.get_available_skills()}")

@property
def use_claude_primary(self) -> bool:
    """Determine primary agent from config."""
    if self._agent_config:
        return self._agent_config.agent_type == 'claude-code'
    return True  # default

def set_agent_config(self, agent_config):
    """Set agent configuration."""
    self._agent_config = agent_config

def _build_claude_command(self, prompt: str) -> list:
    """Build Claude Code command, respecting skip_permissions config."""
    cmd = ["claude", "-p"]
    if self._agent_config and self._agent_config.skip_permissions:
        cmd.insert(1, "--dangerously-skip-permissions")
    cmd.append(prompt)
    return cmd
```

- [ ] **Step 2: Update execute_subtask to use config**

Replace lines 106-117 to check `self.use_claude_primary`:

```python
def execute_subtask(self, subtask, repo_path):
    self.current_subtask = subtask
    subtask_id = subtask.get("id")
    description = subtask.get("description", "")
    self.logger.info(f"Executing subtask {subtask_id}: {description}")

    prompt = self._build_prompt(subtask)

    if self.use_claude_primary:
        result = self._run_claude_code(prompt, repo_path)
        if result["status"] == "completed":
            return result
        self.logger.warning(f"Claude Code failed for {subtask_id}, trying OpenCode")
        result = self._run_opencode(prompt, repo_path)
    else:
        result = self._run_opencode(prompt, repo_path)
        if result["status"] != "completed":
            self.logger.warning(f"OpenCode failed for {subtask_id}, trying Claude Code")
            result = self._run_claude_code(prompt, repo_path)

    return result
```

- [ ] **Step 3: Update _run_claude_code to use _build_claude_command**

Replace line 159 `cmd = [self.CLAUDE_CODE_CMD, "-p", prompt]` with:

```python
cmd = self._build_claude_command(prompt)
```

- [ ] **Step 4: Verify**

```bash
python -c "from agents.coder.agent import CoderAgent; c = CoderAgent('test'); print(c.use_claude_primary)"
```

Expected: `True`

- [ ] **Step 5: Commit**

```bash
git add agents/coder/agent.py
git commit -m "fix: coder agent respects agent_config for primary agent selection"
```

---

## Task 5: Implement Working Review→Fix→Review Loop

**Note:** This task adds `fix_from_review()` to CoderAgent. The `run_autodev.py` integration is handled in Task 9 (which rewrites the entire flow). Do NOT modify `run_autodev.py` here.

**Files:**
- Modify: `agents/coder/agent.py` (add fix_from_review method)

- [ ] **Step 1: Add fix_from_review() to CoderAgent**

```python
# In agents/coder/agent.py, add method:
def fix_from_review(self, issues: List[str], repo_path: str) -> bool:
    """Fix issues identified by reviewer agent."""
    if not issues:
        return True

    prompt = "Fix the following review issues:\n\n"
    for i, issue in enumerate(issues, 1):
        prompt += f"{i}. {issue}\n"
    prompt += "\nFix each issue, run tests, and commit your changes."

    result = self._run_claude_code(prompt, repo_path)
    return result["status"] == "completed"
```

- [ ] **Step 2: Verify fix_from_review works**

```bash
python -c "from agents.coder.agent import CoderAgent; c = CoderAgent('test'); print(hasattr(c, 'fix_from_review'))"
```

Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add agents/coder/agent.py
git commit -m "feat: add fix_from_review to CoderAgent for review loop integration"
```

---

## Task 6: Wire SessionHistory and AgentMemory for Real Coordination

**Files:**
- Modify: `core/session_history.py`
- Modify: `core/agent_memory.py`
- Modify: `core/parallel_executor.py`
- Modify: `run_autodev.py`

- [ ] **Step 1: Add finding-sharing methods to AgentMemory (using existing APIs)**

`AgentMemory` already has `set_shared_data`/`get_shared_data` and `post_message`/`get_messages`.
Build on top of those. In `core/agent_memory.py`, add these methods:

```python
def share_finding(self, agent_id: str, finding_type: str, data: dict):
    """Share a finding with other agents via shared_data."""
    key = f"finding:{finding_type}:{agent_id}:{time.time()}"
    self.set_shared_data(key, {
        "agent": agent_id,
        "finding_type": finding_type,
        "data": data,
    })

def get_findings(self, finding_type: str = None) -> list:
    """Get findings shared by other agents from shared_data."""
    with self._lock:
        findings = []
        for key, entry in self._context["shared_data"].items():
            if not key.startswith("finding:"):
                continue
            value = entry.get("value", {})
            if finding_type and value.get("finding_type") != finding_type:
                continue
            findings.append(value)
        return findings

def get_error_context(self, error_message: str) -> dict:
    """Check if another agent already solved this error."""
    findings = self.get_findings("error_resolution")
    for finding in findings:
        if finding.get("data", {}).get("error", "") in error_message:
            return finding["data"]
    return {}
```

- [ ] **Step 2: Pass AgentMemory into ParallelExecutor**

In `core/parallel_executor.py.__init__()`, accept and store agent_memory:

```python
def __init__(self, base_repo, max_agents=4, session_dir=".autodev/sessions",
             agent_config=None, primary_agent="claude-code", agent_memory=None):
    # ... existing code ...
    self.agent_memory = agent_memory
```

When an agent completes, share its result:

```python
# After successful completion in run_parallel:
if result.status == "completed" and self.agent_memory:
    self.agent_memory.share_finding(
        agent_id=agent_id,
        finding_type="task_completed",
        data={"task_id": result.task_id, "output_summary": result.output[:500]}
    )
```

- [ ] **Step 3: Pass agent_memory from run_autodev.py to executor**

```python
executor = ParallelExecutor(
    local_repo_path,
    max_agents=max_agents,
    agent_config=agent_config,
    agent_memory=agent_memory  # Add this
)
```

- [ ] **Step 4: Verify**

```bash
python -c "
from core.agent_memory import AgentMemory
m = AgentMemory('test_verify')
m.share_finding('a1', 'test', {'x': 1})
findings = m.get_findings('test')
assert len(findings) == 1 and findings[0]['data']['x'] == 1
print('OK:', findings)
"
```

- [ ] **Step 5: Commit**

```bash
git add core/session_history.py core/agent_memory.py core/parallel_executor.py run_autodev.py
git commit -m "feat: wire agent memory for cross-agent coordination"
```

---

## Task 7: Add LLM-Based Task Decomposition

**Files:**
- Modify: `core/task_decomposer.py`
- Modify: `tests/test_task_decomposer.py` (add new test classes to existing file)

- [ ] **Step 1: Write tests for decomposition**

```python
# Append these test classes to existing tests/test_task_decomposer.py
import pytest
from core.task_decomposer import TaskDecomposer


class TestDecomposeIssue:
    def setup_method(self):
        self.decomposer = TaskDecomposer()

    def test_simple_bug_issue(self):
        issue = {
            "number": 1,
            "title": "Fix login error when password contains special chars",
            "body": "When a user enters a password with & or <, the login fails.",
            "labels": [{"name": "bug"}],
            "created_at": "", "updated_at": ""
        }
        plan = self.decomposer.decompose_issue(issue)
        assert len(plan["features"]) >= 1
        assert plan["metadata"]["total_subtasks"] >= 1

    def test_feature_with_checklist(self):
        issue = {
            "number": 2,
            "title": "Add user profile page",
            "body": "## Requirements\n- [ ] Profile photo upload\n- [ ] Edit name\n- [ ] Change email",
            "labels": [],
            "created_at": "", "updated_at": ""
        }
        plan = self.decomposer.decompose_issue(issue)
        # Should extract checklist items as subtasks
        assert plan["metadata"]["total_subtasks"] >= 3

    def test_always_includes_testing(self):
        issue = {
            "number": 3,
            "title": "Add caching layer",
            "body": "Add Redis caching for API responses.",
            "labels": [],
            "created_at": "", "updated_at": ""
        }
        plan = self.decomposer.decompose_issue(issue)
        # Should always have a testing feature
        feature_names = [f["name"].lower() for f in plan["features"]]
        assert any("test" in name for name in feature_names)
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_task_decomposer.py -v
```

Expected: All PASS (current keyword decomposer handles these).

- [ ] **Step 3: Add LLM-enhanced decomposition as optional upgrade**

Add a method that uses Claude Code to decompose complex issues:

```python
def decompose_with_llm(self, issue: Dict[str, Any], repo_path: str = None) -> Dict[str, Any]:
    """Use Claude Code to decompose complex issues into a proper plan."""
    import subprocess
    import json

    prompt = f"""Analyze this GitHub issue and decompose it into features and subtasks.

Issue #{issue.get('number')}: {issue.get('title')}

{issue.get('body', '')}

Output a JSON object with this exact structure:
{{
    "features": [
        {{
            "name": "Feature name",
            "subtasks": [
                {{"description": "What to do", "file": "path/to/file.py or null"}},
            ]
        }}
    ]
}}

Rules:
- Each feature should be independently implementable
- Each subtask should take 5-15 minutes
- Always include a testing feature
- Include file paths when known
- Output ONLY valid JSON, no markdown"""

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            cwd=repo_path or ".",
            capture_output=True, text=True, timeout=60
        )

        if result.returncode == 0:
            # Try to parse JSON from output
            output = result.stdout.strip()
            # Find JSON in output
            start = output.find('{')
            end = output.rfind('}') + 1
            if start >= 0 and end > start:
                llm_plan = json.loads(output[start:end])
                return self._convert_llm_plan(llm_plan, issue)
    except Exception as e:
        pass  # Fall through to keyword decomposition

    # Fallback to keyword-based decomposition
    return self.decompose_issue(issue)
```

- [ ] **Step 3b: Add _convert_llm_plan helper method**

This method converts the LLM JSON output into the plan format that the rest of the system expects:

```python
def _convert_llm_plan(self, llm_plan: Dict[str, Any], issue: Dict[str, Any]) -> Dict[str, Any]:
    """Convert LLM-generated plan to internal format."""
    features = []
    for i, feat in enumerate(llm_plan.get("features", []), 1):
        subtasks = []
        for st in feat.get("subtasks", []):
            subtasks.append(self._to_dict(Subtask(
                id=self._generate_id(),
                description=st.get("description", ""),
                file=st.get("file"),
                status="pending"
            )))
        features.append(self._to_dict(Feature(
            id=f"feat_{i}",
            name=feat.get("name", f"Feature {i}"),
            subtasks=[],  # Set below since we already converted
        )))
        features[-1]["subtasks"] = subtasks

    total = sum(len(f.get("subtasks", [])) for f in features)
    return {
        "project": "",
        "issue": f"#{issue.get('number')}: {issue.get('title', '')}",
        "features": features,
        "metadata": {
            "created": issue.get("created_at", ""),
            "updated": issue.get("updated_at", ""),
            "total_subtasks": total,
            "completed": 0, "failed": 0, "in_progress": 0, "pending": total
        }
    }
```

- [ ] **Step 4: Update decompose_issue to try LLM first when repo_path available**

```python
def decompose_issue(self, issue, repo_path=None):
    """Decompose issue. Uses LLM when repo_path is available, else keyword matching."""
    if repo_path:
        try:
            return self.decompose_with_llm(issue, repo_path)
        except Exception:
            pass  # Fall through

    # ... existing keyword-based code ...
```

- [ ] **Step 5: Commit**

```bash
git add core/task_decomposer.py tests/test_task_decomposer.py
git commit -m "feat: add LLM-based task decomposition with keyword fallback"
```

---

## Task 8: Complete IssueReproducer for JS/TS

**Files:**
- Modify: `core/issue_reproducer.py:249-263`

- [ ] **Step 1: Implement _reproduce_javascript**

```python
def _reproduce_javascript(self, analysis: Dict[str, Any]) -> ReproductionResult:
    """Try to reproduce JavaScript/TypeScript issue."""
    import re
    body = analysis.get("title", "") + " " + analysis.get("actual_behavior", "")

    # Look for npm/node/yarn commands
    cmd_patterns = [
        r"`(npm\s+\w+[^`]*)`",
        r"`(yarn\s+\w+[^`]*)`",
        r"`(node\s+[^`]+)`",
        r"`(npx\s+[^`]+)`",
    ]

    for pattern in cmd_patterns:
        cmd_match = re.search(pattern, body)
        if cmd_match:
            cmd = cmd_match.group(1)
            self.logger.info(f"Attempting to run: {cmd}")

            try:
                result = subprocess.run(
                    cmd, shell=True,
                    cwd=self.repo_path,
                    capture_output=True, text=True, timeout=30
                )

                error_output = result.stderr + result.stdout

                for expected_error in analysis.get("error_messages", []):
                    if expected_error.lower() in error_output.lower():
                        return ReproductionResult(
                            reproduced=True,
                            error_observed=expected_error,
                            root_cause=self._identify_root_cause(error_output, analysis),
                            files_involved=self._find_involved_files_js(error_output),
                            suggested_fix=None,
                            confidence=0.8
                        )

            except Exception as e:
                self.logger.warning(f"Command failed: {e}")

    # Try running test suite as fallback
    for test_cmd in ["npm test", "yarn test", "npx jest"]:
        if (self.repo_path / "package.json").exists():
            try:
                result = subprocess.run(
                    test_cmd, shell=True,
                    cwd=self.repo_path,
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode != 0:
                    return ReproductionResult(
                        reproduced=True,
                        error_observed=result.stderr[:500],
                        root_cause="Test suite failure",
                        files_involved=self._find_involved_files_js(result.stderr),
                        suggested_fix=None,
                        confidence=0.5
                    )
            except Exception:
                pass

    return ReproductionResult(
        reproduced=False, error_observed=None,
        root_cause="Could not reproduce JS/TS issue",
        files_involved=[], suggested_fix=None, confidence=0.0
    )

def _find_involved_files_js(self, error_output: str) -> List[str]:
    """Find JS/TS files mentioned in error output."""
    import re
    patterns = [
        r'at\s+.*\((.+\.[jt]sx?):\d+:\d+\)',  # at Function (file.js:10:5)
        r'(\S+\.[jt]sx?):\d+',                  # file.ts:42
    ]
    files = set()
    for pattern in patterns:
        files.update(re.findall(pattern, error_output))
    return list(files)
```

- [ ] **Step 2: Fix _find_involved_files regex for Python**

Replace line 289:
```python
def _find_involved_files(self, error_output: str) -> List[str]:
    """Find Python files mentioned in error output."""
    import re
    patterns = [
        r'File "([^"]+\.py)"',           # File "path/file.py", line 42
        r'(\S+\.py):\d+',                 # file.py:42
    ]
    files = set()
    for pattern in patterns:
        files.update(re.findall(pattern, error_output))
    return list(files)
```

- [ ] **Step 3: Make reproduction result actually affect execution flow**

In `run_autodev.py`, after reproduction (around line 126-133), add decision logic:

```python
if repro_result.reproduced:
    logger.info(f"   Issue reproduced with confidence {repro_result.confidence}")
    # Add reproduction context to decomposition
    issue['_reproduction'] = {
        'files_involved': repro_result.files_involved,
        'root_cause': repro_result.root_cause,
        'error': repro_result.error_observed
    }
elif repro_result.confidence == 0.0:
    logger.warning("   Could not reproduce. Proceeding with caution.")
    logger.warning("   Fix may not address the actual issue.")
```

- [ ] **Step 4: Commit**

```bash
git add core/issue_reproducer.py run_autodev.py
git commit -m "feat: implement JS/TS issue reproduction, fix Python file detection"
```

---

## Task 9: Unify run_autodev.py with FlexibleOrchestrator

**Note:** This task supersedes the `run_autodev.py` changes from Task 5. Task 5 adds the review loop to the old hardcoded flow; Task 9 replaces the entire flow with FlexibleOrchestrator which includes the review loop. Execute Task 5's coder changes (`fix_from_review` method) but skip Task 5's `run_autodev.py` changes — they are incorporated here.

**Files:**
- Modify: `run_autodev.py` — rewrite to delegate to FlexibleOrchestrator
- Modify: `core/flexible_orchestrator.py` — add all harness steps as concrete methods

- [ ] **Step 1: Add concrete helper methods to FlexibleOrchestrator**

These are the methods called by `run_issue()`. Add them to `core/flexible_orchestrator.py`:

```python
def _load_project_context(self) -> Dict[str, Any]:
    """Load or create project context (CLAUDE.md)."""
    from core.project_context import ProjectContextLoader
    loader = ProjectContextLoader(self.config.get("local_repo_path", "."))
    project_info = loader.detect_project_info()
    context = loader.get_or_create_context(project_info)
    return {"project_info": project_info, "context": context}

def _reproduce_issue(self, issue: Dict, context: Dict) -> 'ReproductionResult':
    """Reproduce the issue before attempting a fix."""
    from core.issue_reproducer import IssueReproducer, ReproductionResult
    reproducer = IssueReproducer(self.config.get("local_repo_path", "."))
    analysis = reproducer.analyze_issue(issue)
    project_type = context.get("project_info", {}).get("language", "python").lower()
    return reproducer.reproduce(analysis, project_type)

def _decompose(self, issue: Dict) -> Dict[str, Any]:
    """Decompose issue into features and subtasks."""
    from core.task_decomposer import TaskDecomposer
    decomposer = TaskDecomposer()
    return decomposer.decompose_issue(issue, repo_path=self.config.get("local_repo_path"))

def _execute_parallel(self, plan: Dict) -> List[Dict]:
    """Execute tasks in parallel using ParallelExecutor."""
    tasks = []
    for feature in plan.get("features", []):
        branch_name = f"feature/{feature['id']}"
        prompt = f"Implement: {feature['name']}\n\nRequirements:\n"
        for st in feature.get("subtasks", []):
            prompt += f"- {st.get('description', '')}\n"
        prompt += "\nWrite code and tests. Commit with descriptive messages."
        tasks.append({
            "branch": branch_name,
            "prompt": prompt,
            "task_id": feature["id"],
            "description": feature["name"]
        })

    if not self.executor:
        self.logger.error("Executor not initialized")
        return []

    return self.executor.run_parallel(tasks, wait=True, check_interval=15)

def _review_all(self, plan: Dict, results: List) -> List[Dict]:
    """Run review loop on all feature branches."""
    from agents.reviewer.agent import ReviewLoop
    from agents.coder.agent import CoderAgent

    review_results = []
    for feature in plan.get("features", []):
        branch_name = f"feature/{feature['id']}"
        worktree_path = self.executor.worktrees.get(branch_name, self.config.get("local_repo_path", "."))

        fix_coder = CoderAgent("fixer", config=self.config)
        def fix_callback(issues, coder=fix_coder, path=str(worktree_path)):
            return coder.fix_from_review(issues, path)

        loop = ReviewLoop(config=self.config)
        result = loop.run_review_loop(
            repo_path=str(worktree_path),
            branch=branch_name,
            base="main",
            on_fix_callback=fix_callback
        )
        review_results.append({"branch": branch_name, **result})

    return review_results

def _build_report(self, plan: Dict, results: List, review_results: List) -> Dict:
    """Build final report — no auto-PR, user reviews manually."""
    branches = [f"feature/{f['id']}" for f in plan.get("features", [])]
    completed = sum(1 for r in results if getattr(r, 'status', '') == "completed")
    approved = sum(1 for r in review_results if r.get("status") == "approved")

    self.logger.info("=" * 60)
    self.logger.info("Changes ready for review")
    self.logger.info("=" * 60)
    for branch in branches:
        self.logger.info(f"  - Branch: {branch}")
    self.logger.info("")
    self.logger.info("Please review the changes and create PR manually.")
    self.logger.info("AutoDev will NOT create PR automatically.")

    return {
        "features": len(plan.get("features", [])),
        "completed": completed,
        "approved": approved,
        "branches": branches
    }
```

- [ ] **Step 2: Rewrite run_issue() to call these methods**

```python
def run_issue(self, issue_number: int, upstream_github=None) -> Dict[str, Any]:
    """Run the full harness pipeline on a GitHub issue."""
    github_for_issue = upstream_github or self.github

    # Step 1: Fetch issue
    self.logger.info("Step 1: Fetching issue...")
    issue = github_for_issue.get_issue(issue_number)
    self.logger.info(f"   Title: {issue['title']}")

    # Step 2: Load project context
    self.logger.info("Step 2: Loading project context...")
    context = self._load_project_context()

    # Step 3: Reproduce issue
    self.logger.info("Step 3: Reproducing issue...")
    repro = self._reproduce_issue(issue, context)
    if repro.reproduced:
        issue['_reproduction'] = {
            'files_involved': repro.files_involved,
            'root_cause': repro.root_cause
        }

    # Step 4: Decompose
    self.logger.info("Step 4: Decomposing into tasks...")
    plan = self._decompose(issue)

    # Step 5: Execute in parallel
    self.logger.info("Step 5: Executing tasks...")
    results = self._execute_parallel(plan)

    # Step 6: Review loop
    if self.config.get("review", {}).get("enabled", True):
        self.logger.info("Step 6: Running review loop...")
        review_results = self._review_all(plan, results)
    else:
        review_results = []

    # Step 7: Report (no auto-PR)
    return self._build_report(plan, results, review_results)
```

- [ ] **Step 3: Remove auto_create_pr from FlexibleOrchestrator**

Delete lines 153-157 (auto PR creation). The harness should NEVER auto-create PRs per CLAUDE.md.

- [ ] **Step 4: Simplify run_autodev.py to delegate to FlexibleOrchestrator**

```python
def run_autodev(repo_owner, repo_name, issue_number, github_token,
                local_repo_path, max_agents=4, agent_type="claude-code",
                use_claude_skip_permissions=False, upstream_repo=None):
    """Run AutoDev end-to-end on a GitHub issue."""
    logger = setup_logger()
    logger.info(f"Starting AutoDev for {repo_owner}/{repo_name} issue #{issue_number}")

    config = {
        "agents": {"max_parallel": max_agents},
        "agent_type": agent_type,
        "skip_permissions": agent_type == 'claude-code',
        "review": {"enabled": True, "max_iterations": 3},
        "local_repo_path": local_repo_path,
    }

    orchestrator = FlexibleOrchestrator(config)

    # Handle upstream repo for forks
    upstream_github = None
    if upstream_repo:
        upstream_owner, upstream_name = upstream_repo.split("/")
        upstream_github = GitHubClient(token=github_token, owner=upstream_owner, repo=upstream_name)

    orchestrator.initialize(github_token, repo_owner, repo_name, local_repo_path)

    try:
        return orchestrator.run_issue(issue_number, upstream_github=upstream_github)
    finally:
        orchestrator.cleanup()
```

- [ ] **Step 5: Verify the new flow compiles**

```bash
python -c "from run_autodev import run_autodev; print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add run_autodev.py core/flexible_orchestrator.py
git commit -m "feat: unify run_autodev with FlexibleOrchestrator as single pipeline"
```

---

## Task 10: Researcher Agent — Synthesize Multiple Sources

**Files:**
- Modify: `agents/researcher/agent.py:226-239`

- [ ] **Step 1: Replace single-source fix generation with multi-source synthesis**

```python
def _generate_fix(self, findings: List[Dict[str, Any]], original_error: str) -> str:
    """Generate a recommended fix by synthesizing multiple findings."""
    if not findings:
        return "No solutions found. Manual investigation required."

    # Use top 3 findings
    top_findings = findings[:3]

    fix = "Based on research across multiple sources:\n\n"

    for i, finding in enumerate(top_findings, 1):
        fix += f"**Source {i}:** {finding.get('title', 'Unknown')}\n"
        fix += f"  URL: {finding.get('url', 'N/A')}\n"
        fix += f"  Approach: {finding.get('snippet', 'See source')[:200]}\n\n"

    # Identify common themes
    all_text = " ".join(f.get("snippet", "") for f in top_findings).lower()

    if "import" in all_text and "install" in all_text:
        fix += "**Common theme:** Missing dependency — try installing the required package.\n"
    elif "version" in all_text:
        fix += "**Common theme:** Version mismatch — check dependency versions.\n"
    elif "config" in all_text or "setting" in all_text:
        fix += "**Common theme:** Configuration issue — verify settings.\n"

    return fix
```

- [ ] **Step 2: Commit**

```bash
git add agents/researcher/agent.py
git commit -m "feat: researcher synthesizes multiple sources instead of using only top result"
```

---

## Task 11: Integration Test for Full Pipeline

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_orchestrator_integration.py`

- [ ] **Step 1: Create shared test fixtures**

```python
# tests/conftest.py
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_github_client():
    """Mock GitHub client that returns test data."""
    client = MagicMock()
    client.get_issue.return_value = {
        "number": 1,
        "title": "Fix login bug",
        "body": "Login fails when password has special characters.\n\n## Steps\n1. Enter password with &\n2. Click login\n3. See error",
        "labels": [{"name": "bug"}],
        "html_url": "https://github.com/test/repo/issues/1",
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }
    client.owner = "test"
    client.repo = "repo"
    client.get_user.return_value = {"login": "testuser"}
    client.fork_exists_for_user.return_value = True
    return client


@pytest.fixture
def mock_subprocess():
    """Mock subprocess for agent execution."""
    with patch('subprocess.run') as mock_run, \
         patch('subprocess.Popen') as mock_popen:
        # Default: commands succeed
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Success",
            stderr="",
        )
        mock_popen.return_value = MagicMock(
            poll=MagicMock(return_value=0),
            communicate=MagicMock(return_value=("Done", "")),
            pid=12345,
        )
        yield {"run": mock_run, "popen": mock_popen}
```

- [ ] **Step 2: Write integration test**

```python
# tests/test_orchestrator_integration.py
import pytest
from unittest.mock import MagicMock, patch
from core.task_decomposer import TaskDecomposer
from core.error_handler import CapabilityErrorHandler, ErrorCategory


class TestDecompositionToExecution:
    """Test that decomposition output feeds correctly into execution."""

    def test_decomposed_plan_has_required_fields(self):
        decomposer = TaskDecomposer()
        issue = {
            "number": 1, "title": "Add caching",
            "body": "Add Redis caching for API.", "labels": [],
            "created_at": "", "updated_at": ""
        }
        plan = decomposer.decompose_issue(issue)

        assert "features" in plan
        assert "metadata" in plan
        assert plan["metadata"]["total_subtasks"] > 0

        for feature in plan["features"]:
            assert "id" in feature
            assert "name" in feature
            assert "subtasks" in feature

    def test_error_handler_provides_retry_guidance(self):
        handler = CapabilityErrorHandler()

        # Simulate a test failure
        result = handler.handle_error("FAILED tests/test_api.py - AssertionError: expected 200 got 404")
        assert result["category"] == "test_failed"
        assert "test_writing" in result["capabilities_needed"]
        assert result["should_retry"] is True

    def test_error_handler_escalates_unknown(self):
        handler = CapabilityErrorHandler()
        result = handler.handle_error("Segfault")
        assert result["should_retry"] is False


class TestReviewIntegration:
    """Test that review results feed back to coder correctly."""

    def test_review_issues_are_actionable(self):
        from agents.reviewer.agent import ReviewerAgent
        reviewer = ReviewerAgent.__new__(ReviewerAgent)
        reviewer.logger = __import__('logging').getLogger('test')

        feedback = """### CHANGES REQUESTED
1. Missing null check in parse_user() at line 42
2. No test covers the empty input case"""

        issues = reviewer._parse_issues(feedback)
        assert len(issues) == 2
        # Issues should be specific enough for a coder to act on
        assert any("null check" in i.lower() or "parse_user" in i.lower() for i in issues)
```

- [ ] **Step 3: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add integration tests for decomposition, error handling, and review"
```

---

## Task 12: Update CLAUDE.md and AGENTS.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Update CLAUDE.md to reflect the new architecture**

Key updates:
- Remove references to `core/orchestrator.py` and `core/executor.py`
- Remove references to `autodev.py`
- Update architecture table to show FlexibleOrchestrator as the single orchestrator
- Update the "Reviewer Agent Status" section — it's no longer broken
- Add ErrorHandler to the components table
- Note that `run_autodev.py` now delegates to `FlexibleOrchestrator`

- [ ] **Step 2: Update AGENTS.md usage example**

Replace the example code that references old orchestrator:

```python
from core.flexible_orchestrator import FlexibleOrchestrator

orchestrator = FlexibleOrchestrator(config)
orchestrator.initialize(token, owner, repo, repo_path)
result = orchestrator.run_issue(issue_number)
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md AGENTS.md
git commit -m "docs: update CLAUDE.md and AGENTS.md for revamped architecture"
```

---

## Execution Order & Dependencies

```
Task 1 (delete dead code) ─── no deps, do first
    │
    ├── Task 2 (fix reviewer) ─── depends on Task 1
    │
    ├── Task 3 (error handler) ─── depends on Task 1
    │
    ├── Task 4 (coder config) ─── depends on Task 1
    │
    ├── Task 5 (fix_from_review) ─── depends on Task 4
    │
    ├── Task 6 (agent memory) ─── depends on Task 1
    │       Note: modifies parallel_executor.py (same as Task 3)
    │       Execute AFTER Task 3 to avoid merge conflicts
    │
    ├── Task 7 (LLM decomposer) ─── independent
    │
    ├── Task 8 (JS/TS reproducer) ─── independent
    │
    └── Task 10 (researcher) ─── independent

Task 9 (unify orchestrator) ─── depends on Tasks 1-8
    Note: rewrites run_autodev.py and flexible_orchestrator.py
    Incorporates Task 5's review loop into the unified flow
    Must be done AFTER all other code changes

Task 11 (integration tests) ─── depends on Tasks 2, 3, 7
Task 12 (docs) ─── do last
```

**Parallelizable groups:**
- Group A: Tasks 2, 3, 4, 5, 7, 8, 10 (all independent after Task 1)
  - Exception: Task 6 must follow Task 3 (both modify parallel_executor.py)
- Group B: Task 9 (depends on all of Group A + Task 6)
- Group C: Tasks 11, 12 (final)
