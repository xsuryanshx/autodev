# Parallel Subagent Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a DeerFlow-style parallel subagent execution model to AutoDev, where the lead agent dispatches concurrent subagents through a `task()` tool, runs them in a thread-pool executor with isolation, and aggregates results — without spinning up multiple Claude Code CLI sessions.

**Architecture:** Replace the current inter-process coordination model (JSON files + separate CLI invocations) with an in-process lead-agent pattern. The lead agent (Claude Code running `/autodev`) owns orchestration; subagents are dispatched via a `task()` tool that spawns concurrent executor threads with scoped context and sandboxed tool access. Isolation is achieved through per-task filesystem workspaces and a thread-scoped state store, not separate git worktrees.

**Tech Stack:** Python 3.10+, Claude Code plugin framework, concurrent.futures (ThreadPoolExecutor), threading (per-task isolation via contextvars), filesystem workspaces via temp directories or Docker (future), JSON for state.

---

## Design: Core Mental Model

```
Lead Agent (Claude Code, running /autodev)
  |
  |---> task("implement feat-A", context)  ---> ThreadPoolExecutor
  |           |
  |           +---> Subagent-A (scoped context, sandboxed tools)
  |                   |
  |                   +---> Result --> lead agent aggregates
  |
  |---> task("implement feat-B", context)  ---> ThreadPoolExecutor
  |           |
  |           +---> Subagent-B (scoped context, sandboxed tools)
  |
  +---> Results aggregated, merge, review, report
```

Key distinctions from current AutoDev:
| Aspect | Current (v1) | New (DeerFlow-style) |
|--------|-------------|----------------------|
| Parallelism | Separate Claude Code CLI processes in git worktrees | ThreadPoolExecutor threads with scoped context |
| Coordination | Shared JSON files (advisory, append-only) | In-memory thread-scoped state + shared agent-state.json |
| Subagent type | Full Claude Code session with full tool access | Scoped tool subset + context per task |
| Isolation | Git worktrees (filesystem) | ContextVars + workspace temp dirs |
| Concurrency cap | Per-agent worktree count | `max_parallelism=3` per turn, 15-min timeout per task |

---

## File Structure

### New Files to Create
- `skills/autodev/task_tool.md` — The `task()` tool definition (lead agent uses this to dispatch)
- `core/subagent_executor.py` — ThreadPoolExecutor-based subagent dispatcher
- `core/task_context.py` — Per-task context isolation via contextvars
- `core/sandboxed_tools.py` — Sandboxed tool implementations for subagents (read_file, write_file, bash, grep)
- `agents/subagent.md` — The subagent skill definition (scoped, not a full CLI session)
- `tests/test_subagent_executor.py` — Tests for concurrent task execution
- `tests/test_task_context.py` — Tests for context isolation

### Files to Modify
- `commands/autodev.md` — Update Phase 5 to use new task() dispatch model
- `skills/autodev/references/shared-state-protocol.md` — Add thread-safe coordination rules
- `agents/coder.md` — May be reused for subagent implementation guidance

### Files to Delete
- None for now — new architecture is additive until validated

---

## Task 1: Implement TaskContext (Per-Task Isolation)

**Files:**
- Create: `core/task_context.py`
- Create: `tests/test_task_context.py`

- [ ] **Step 1: Write failing tests for TaskContext**

```python
# tests/test_task_context.py
import pytest
from core.task_context import TaskContext, task_scope

class TestTaskContext:
    def test_task_has_unique_id(self):
        ctx1 = TaskContext(task_id="task-1", description="Do thing A")
        ctx2 = TaskContext(task_id="task-2", description="Do thing B")
        assert ctx1.task_id != ctx2.task_id
        assert ctx1.task_id == "task-1"

    def test_task_stores_files_created(self):
        ctx = TaskContext(task_id="task-1", description="Write files")
        ctx.add_file_created("src/auth.py")
        ctx.add_file_created("tests/test_auth.py")
        assert len(ctx.files_created) == 2
        assert "src/auth.py" in ctx.files_created

    def test_task_stores_files_modified(self):
        ctx = TaskContext(task_id="task-1", description="Modify config")
        ctx.add_file_modified("config.py")
        assert "config.py" in ctx.files_modified

    def test_task_has_status(self):
        ctx = TaskContext(task_id="task-1", description="Do work")
        assert ctx.status == "pending"
        ctx.set_status("running")
        assert ctx.status == "running"
        ctx.set_status("completed")
        assert ctx.status == "completed"

    def test_task_has_timeout(self):
        ctx = TaskContext(task_id="task-1", description="Do work", timeout_seconds=300)
        assert ctx.timeout_seconds == 300

    def test_task_summary(self):
        ctx = TaskContext(task_id="task-1", description="Fix auth bug")
        ctx.add_file_created("src/auth.py")
        summary = ctx.get_summary()
        assert "task-1" in summary
        assert "auth.py" in summary


class TestTaskScope:
    def test_task_scope_sets_current_context(self):
        ctx = TaskContext(task_id="test-1", description="Test")
        with task_scope(ctx):
            from core.task_context import get_current_task_context
            assert get_current_task_context() is ctx
        # After exiting scope, no current context
        try:
            get_current_task_context()
            assert False, "Should raise - no current context"
        except RuntimeError:
            pass

    def test_nested_task_scopes_raise(self):
        ctx1 = TaskContext(task_id="outer", description="Outer")
        ctx2 = TaskContext(task_id="inner", description="Inner")
        with task_scope(ctx1):
            with pytest.raises(RuntimeError, match="Nested task_scope"):
                with task_scope(ctx2):
                    pass
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_task_context.py -v
```

Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Implement TaskContext**

```python
# core/task_context.py
import threading
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

# Module-level current task context (thread-local storage for safety)
_current_task_context: ContextVar[Optional["TaskContext"]] = ContextVar(
    "current_task_context", default=None
)


class TaskContextError(RuntimeError):
    """Raised when task context is accessed outside a task_scope."""
    pass


@dataclass
class TaskContext:
    """Per-task isolated execution context.

    Each dispatched subagent task runs within its own TaskContext.
    Context provides:
    - Unique task ID
    - Status tracking
    - File tracking (created/modified)
    - Result storage
    - Timeout configuration
    """
    task_id: str
    description: str
    status: str = "pending"
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None
    timeout_seconds: int = 900  # 15 minutes default
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def set_status(self, status: str) -> None:
        """Update task status."""
        now = datetime.utcnow().isoformat() + "Z"
        self.status = status
        if status == "running" and self.started_at is None:
            self.started_at = now
        elif status in ("completed", "failed") and self.completed_at is None:
            self.completed_at = now

    def add_file_created(self, path: str) -> None:
        if path not in self.files_created:
            self.files_created.append(path)

    def add_file_modified(self, path: str) -> None:
        if path not in self.files_modified:
            self.files_modified.append(path)

    def add_file_deleted(self, path: str) -> None:
        if path not in self.files_deleted:
            self.files_deleted.append(path)

    def set_result(self, result: dict) -> None:
        self.result = result

    def set_error(self, error: str) -> None:
        self.error = error
        self.set_status("failed")

    def get_summary(self) -> str:
        """Get human-readable task summary."""
        parts = [f"[{self.task_id}] {self.description}"]
        parts.append(f"status={self.status}")
        if self.files_created:
            parts.append(f"created={', '.join(self.files_created)}")
        if self.files_modified:
            parts.append(f"modified={', '.join(self.files_modified)}")
        if self.error:
            parts.append(f"error={self.error}")
        return " | ".join(parts)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "status": self.status,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "files_deleted": self.files_deleted,
            "result": self.result,
            "error": self.error,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class task_scope:
    """Context manager that sets the current task context for the duration of a task.

    Usage:
        ctx = TaskContext(task_id="task-1", description="Do thing")
        with task_scope(ctx):
            # Inside this block, get_current_task_context() returns ctx
            ...
    """
    _lock = threading.Lock()
    _current_owner = threading.current_thread().ident

    def __init__(self, ctx: TaskContext):
        self.ctx = ctx
        self._prev = None

    def __enter__(self):
        thread_id = threading.current_thread().ident
        with task_scope._lock:
            if task_scope._current_owner is not None and task_scope._current_owner != thread_id:
                raise RuntimeError(
                    f"task_scope cannot cross thread boundaries. "
                    f"Owned by thread {task_scope._current_owner}, "
                    f"called from {thread_id}"
                )
            task_scope._current_owner = thread_id
        # Check for nested scopes
        prev = _current_task_context.get()
        if prev is not None:
            raise RuntimeError(
                f"Nested task_scope detected for task {self.ctx.task_id}. "
                f"Each task must have a single scope."
            )
        _current_task_context.set(self.ctx)
        self.ctx.set_status("running")
        return self.ctx

    def __exit__(self, exc_type, exc_val, exc_tb):
        with task_scope._lock:
            task_scope._current_owner = None
        _current_task_context.set(None)
        if exc_type is not None:
            self.ctx.set_error(f"{exc_type.__name__}: {exc_val}")
        elif self.ctx.status == "running":
            self.ctx.set_status("completed")
        return False


def get_current_task_context() -> TaskContext:
    """Get the current task context. Raises if called outside a task_scope."""
    ctx = _current_task_context.get()
    if ctx is None:
        raise TaskContextError(
            "No current task context. Are you running inside a task_scope?"
        )
    return ctx
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_task_context.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add core/task_context.py tests/test_task_context.py
git commit -m "feat: add TaskContext for per-task isolation with contextvars"
```

---

## Task 2: Implement SandboxedTools (Subagent Tool Subset)

**Files:**
- Create: `core/sandboxed_tools.py`
- Create: `tests/test_sandboxed_tools.py`

- [ ] **Step 1: Write failing tests for SandboxedTools**

```python
# tests/test_sandboxed_tools.py
import pytest
import tempfile
import os
from pathlib import Path
from core.sandboxed_tools import SandboxedTools

class TestSandboxedToolsRead:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()
        self.tools = SandboxedTools(workspace=self.tempdir)

    def test_read_file_returns_content(self):
        path = os.path.join(self.tempdir, "hello.txt")
        with open(path, "w") as f:
            f.write("Hello, world!")
        result = self.tools.read_file(path)
        assert result["status"] == "success"
        assert result["content"] == "Hello, world!"

    def test_read_file_not_found(self):
        result = self.tools.read_file("/nonexistent/file.txt")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_read_file_enforces_workspace(self):
        # Attempt to read outside workspace
        result = self.tools.read_file("/etc/passwd")
        assert result["status"] == "error"
        assert "outside workspace" in result["message"].lower()


class TestSandboxedToolsWrite:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()
        self.tools = SandboxedTools(workspace=self.tempdir)

    def test_write_file_creates_file(self):
        path = os.path.join(self.tempdir, "output.txt")
        result = self.tools.write_file(path, "Line 1\nLine 2\n")
        assert result["status"] == "success"
        with open(path) as f:
            assert f.read() == "Line 1\nLine 2\n"

    def test_write_file_enforces_workspace(self):
        result = self.tools.write_file("/tmp/malicious.txt", "bad")
        assert result["status"] == "error"


class TestSandboxedToolsBash:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()
        self.tools = SandboxedTools(workspace=self.tempdir)

    def test_bash_returns_output(self):
        result = self.tools.bash("echo 'hello'")
        assert result["status"] == "success"
        assert "hello" in result["stdout"]

    def test_bash_returns_nonzero_exit(self):
        result = self.tools.bash("exit 1")
        assert result["status"] == "error"
        assert result["exit_code"] == 1

    def test_bash_cwd_is_workspace(self):
        result = self.tools.bash("pwd")
        assert result["status"] == "success"
        assert self.tempdir in result["stdout"]


class TestSandboxedToolsGlob:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()
        self.tools = SandboxedTools(workspace=self.tempdir)
        # Create test files
        Path(self.tempdir, "src", "app.py").touch()
        Path(self.tempdir, "src", "util.py").touch()
        Path(self.tempdir, "tests", "test_app.py").touch()

    def test_glob_finds_files(self):
        result = self.tools.glob("**/*.py")
        assert result["status"] == "success"
        files = result["files"]
        assert any("app.py" in f for f in files)

    def test_glob_enforces_workspace(self):
        result = self.tools.glob("/etc/**/*.txt")
        assert result["status"] == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_sandboxed_tools.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement SandboxedTools**

```python
# core/sandboxed_tools.py
"""Sandboxed tool implementations for subagent execution.

Each subagent gets a limited set of tools (read_file, write_file, bash, glob, grep)
that are restricted to its workspace directory. This provides isolation without
requiring separate git worktrees or Docker containers.
"""
import subprocess
import os
import glob as glob_module
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


class SandboxError(Exception):
    """Tool execution violated workspace boundary."""
    pass


@dataclass
class ToolResult:
    status: str  # "success" or "error"
    message: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    content: Optional[str] = None
    files: Optional[List[str]] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            **{k: v for k, v in self.__dict__.items() if v is not None}
        }


class SandboxedTools:
    """A set of sandboxed tools that subagents can use.

    All file operations are restricted to the workspace directory.
    Bash commands run with cwd set to the workspace.
    """
    def __init__(self, workspace: str, timeout_seconds: int = 300):
        self.workspace = Path(workspace).resolve()
        self.timeout_seconds = timeout_seconds

    def _check_path(self, path: str) -> Path:
        """Ensure a path is within the workspace."""
        resolved = (self.workspace / path).resolve()
        if not str(resolved).startswith(str(self.workspace)):
            raise SandboxError(f"Access denied: {path} is outside workspace {self.workspace}")
        return resolved

    def read_file(self, path: str) -> Dict[str, Any]:
        """Read a file's contents."""
        try:
            resolved = self._check_path(path)
            with open(resolved, "r", encoding="utf-8") as f:
                content = f.read()
            return ToolResult(status="success", content=content).to_dict()
        except FileNotFoundError:
            return ToolResult(status="error", message=f"File not found: {path}").to_dict()
        except SandboxError as e:
            return ToolResult(status="error", message=str(e)).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write content to a file."""
        try:
            resolved = self._check_path(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(status="success", message=f"Written to {path}").to_dict()
        except SandboxError as e:
            return ToolResult(status="error", message=str(e)).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def bash(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Execute a bash command in the workspace."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd or str(self.workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            if result.returncode == 0:
                return ToolResult(
                    status="success",
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                ).to_dict()
            else:
                return ToolResult(
                    status="error",
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                    message=f"Command exited with code {result.returncode}",
                ).to_dict()
        except subprocess.TimeoutExpired:
            return ToolResult(
                status="error",
                message=f"Command timed out after {self.timeout_seconds}s",
            ).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def glob(self, pattern: str) -> Dict[str, Any]:
        """Find files matching a glob pattern, restricted to workspace."""
        try:
            # Reject absolute paths that escape workspace
            if pattern.startswith("/") and ".." in pattern:
                return ToolResult(status="error", message="Absolute paths not allowed").to_dict()

            matches = list(self.workspace.glob(pattern))
            files = [str(m) for m in matches if m.is_file()]
            return ToolResult(status="success", files=files).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def grep(self, pattern: str, path: Optional[str] = None) -> Dict[str, Any]:
        """Search for pattern in files within workspace."""
        try:
            import re
            search_dir = Path(path) if path else self.workspace
            self._check_path(str(search_dir))

            results = []
            for match in search_dir.rglob("*"):
                if not match.is_file():
                    continue
                try:
                    text = match.read_text(encoding="utf-8")
                    for i, line in enumerate(text.splitlines(), 1):
                        if re.search(pattern, line):
                            results.append(f"{match}:{i}: {line.rstrip()}")
                except (UnicodeDecodeError, PermissionError):
                    continue

            return ToolResult(
                status="success",
                stdout="\n".join(results),
                files=[str(search_dir)],
            ).to_dict()
        except SandboxError as e:
            return ToolResult(status="error", message=str(e)).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_sandboxed_tools.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add core/sandboxed_tools.py tests/test_sandboxed_tools.py
git commit -m "feat: add SandboxedTools for workspace-restricted subagent execution"
```

---

## Task 3: Implement SubagentExecutor (ThreadPool-Based Dispatch)

**Files:**
- Create: `core/subagent_executor.py`
- Create: `tests/test_subagent_executor.py`

- [ ] **Step 1: Write failing tests for SubagentExecutor**

```python
# tests/test_subagent_executor.py
import pytest
import tempfile
import time
from unittest.mock import MagicMock, patch
from core.subagent_executor import SubagentExecutor, SubagentTask, AgentResult

class TestSubagentExecutorBasics:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def test_executor_initializes(self):
        executor = SubagentExecutor(
            workspace=self.tempdir,
            max_parallelism=2,
            timeout_per_task=300,
        )
        assert executor.max_parallelism == 2
        assert executor.timeout_per_task == 300

    def test_submit_single_task(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=1)
        task = SubagentTask(
            task_id="task-1",
            description="Simple task",
            prompt="Return immediately",
            skill="coder",
        )

        def simple_handler(context):
            return {"status": "completed", "output": "done"}

        with patch.object(executor, "_get_handler_for_skill") as mock:
            mock.return_value = simple_handler
            result = executor.submit_and_wait([task])

        assert len(result) == 1
        assert result[0].task_id == "task-1"
        assert result[0].status == "completed"

    def test_submit_multiple_tasks_concurrent(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=3)
        tasks = [
            SubagentTask(task_id=f"task-{i}", description=f"Task {i}", prompt="", skill="coder")
            for i in range(3)
        ]

        start = time.time()
        with patch.object(executor, "_get_handler_for_skill") as mock:
            call_order = []

            def make_handler(task_id):
                def handler(ctx):
                    call_order.append(task_id)
                    time.sleep(0.1)
                    return {"status": "completed", "task_id": task_id}
                return handler

            mock.side_effect = lambda skill: make_handler(task_id=tasks[call_order.__len__()])

            # This test needs real threading to verify concurrency
            # For now just verify tasks complete
            mock.side_effect = [
                make_handler("task-0"),
                make_handler("task-1"),
                make_handler("task-2"),
            ]
            result = executor.submit_and_wait(tasks)

        elapsed = time.time() - start
        assert len(result) == 3
        assert all(r.status == "completed" for r in result)
        # With max_parallelism=3 and 3 tasks sleeping 0.1s each, should take ~0.1s not ~0.3s
        assert elapsed < 0.25, f"Took {elapsed}s, expected < 0.25s (tasks should run concurrently)"


class TestConcurrencyLimits:
    def test_max_parallelism_respected(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=2)
        assert executor.max_parallelism == 2
        # Verify semaphore is created with correct size
        assert executor._semaphore._value == 2

    def test_task_timeout_applied(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=1, timeout_per_task=5)
        task = SubagentTask(
            task_id="slow-task",
            description="Slow task",
            prompt="",
            skill="coder",
            timeout_seconds=1,  # Override per-task timeout
        )

        def slow_handler(ctx):
            time.sleep(2)  # Will exceed timeout
            return {"status": "completed"}

        with patch.object(executor, "_get_handler_for_skill", return_value=slow_handler):
            result = executor.submit_and_wait([task])

        assert result[0].status == "failed"
        assert "timeout" in result[0].error.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_subagent_executor.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement SubagentExecutor**

```python
# core/subagent_executor.py
"""ThreadPoolExecutor-based subagent dispatcher.

Dispatches subagent tasks as threads in a thread pool, with:
- Concurrency cap (max_parallelism)
- Per-task timeout
- Task context isolation via TaskContext + contextvars
- Result aggregation back to the lead agent
"""
import concurrent.futures
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Callable, Optional, Any, Dict

from core.task_context import TaskContext, task_scope, get_current_task_context
from core.sandboxed_tools import SandboxedTools


@dataclass
class SubagentTask:
    """A task to be dispatched to a subagent."""
    task_id: str
    description: str
    prompt: str
    skill: str  # "coder", "researcher", etc.
    context: Optional[Dict[str, Any]] = None  # Additional context (files, repo info)
    timeout_seconds: int = 900  # 15 minutes default
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Result from a subagent execution."""
    task_id: str
    status: str  # "completed", "failed", "timeout"
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class SubagentExecutor:
    """Dispatches subagent tasks using a ThreadPoolExecutor.

    Key features:
    - Concurrency capped at max_parallelism
    - Per-task timeout (default 15 minutes)
    - Task context isolation via contextvars
    - Sandboxed tools per task
    - Aggregates results to caller
    """
    def __init__(
        self,
        workspace: str,
        max_parallelism: int = 3,
        timeout_per_task: int = 900,
    ):
        self.workspace = Path(workspace).resolve()
        self.max_parallelism = max_parallelism
        self.timeout_per_task = timeout_per_task
        self._semaphore = threading.Semaphore(max_parallelism)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_parallelism,
            thread_name_prefix="subagent-"
        )
        # Registry of skill handlers
        self._handlers: Dict[str, Callable] = {}
        self._results: Dict[str, AgentResult] = {}
        self._results_lock = threading.Lock()

    def register_handler(self, skill: str, handler: Callable[[TaskContext], Dict[str, Any]]) -> None:
        """Register a handler function for a skill type.

        Handler signature: (context: TaskContext) -> Dict[str, Any]
        The handler receives a TaskContext with sandboxed tools accessible via context.tools.
        """
        self._handlers[skill] = handler

    def _get_handler_for_skill(self, skill: str) -> Optional[Callable]:
        return self._handlers.get(skill)

    def _run_task(self, task: SubagentTask) -> AgentResult:
        """Run a single task within a task_scope context."""
        task_ctx = TaskContext(
            task_id=task.task_id,
            description=task.description,
            timeout_seconds=task.timeout_seconds or self.timeout_per_task,
        )

        # Create per-task workspace
        task_workspace = self.workspace / f"task_{task.task_id}"
        task_workspace.mkdir(parents=True, exist_ok=True)

        # Attach sandboxed tools to the context
        task_ctx.tools = SandboxedTools(
            workspace=str(task_workspace),
            timeout_seconds=task_ctx.timeout_seconds,
        )

        handler = self._get_handler_for_skill(task.skill)
        if handler is None:
            task_ctx.set_error(f"No handler registered for skill: {task.skill}")
            return AgentResult(
                task_id=task.task_id,
                status="failed",
                error=f"No handler for skill: {task.skill}",
            )

        started = time.time()
        try:
            with task_scope(task_ctx):
                result = handler(task_ctx)

            duration = time.time() - started
            return AgentResult(
                task_id=task.task_id,
                status="completed",
                output=result or {},
                files_created=list(task_ctx.files_created),
                files_modified=list(task_ctx.files_modified),
                duration_seconds=duration,
            )
        except Exception as e:
            duration = time.time() - started
            task_ctx.set_error(str(e))
            return AgentResult(
                task_id=task.task_id,
                status="failed",
                error=f"{type(e).__name__}: {e}",
                files_created=list(task_ctx.files_created),
                files_modified=list(task_ctx.files_modified),
                duration_seconds=duration,
            )

    def submit_and_wait(self, tasks: List[SubagentTask]) -> List[AgentResult]:
        """Submit multiple tasks for concurrent execution and wait for all to complete.

        Tasks are submitted to the thread pool and run concurrently, up to max_parallelism.
        Results are returned in the same order as the input tasks.

        Args:
            tasks: List of SubagentTasks to execute.

        Returns:
            List of AgentResult, one per task, in input order.
        """
        futures = {}
        for task in tasks:
            future = self._executor.submit(self._run_task, task)
            futures[future] = task.task_id

        results = []
        for future in concurrent.futures.as_completed(futures):
            task_id = futures[future]
            try:
                result = future.result(timeout=self.timeout_per_task)
            except concurrent.futures.TimeoutError:
                result = AgentResult(
                    task_id=task_id,
                    status="timeout",
                    error=f"Task exceeded global timeout of {self.timeout_per_task}s",
                )
            except Exception as e:
                result = AgentResult(
                    task_id=task_id,
                    status="failed",
                    error=f"Task raised: {type(e).__name__}: {e}",
                )

            with self._results_lock:
                self._results[task_id] = result

            # Map back to input order
            results.append(result)

        # Return results in same order as input tasks
        return [self._results[t.task_id] for t in tasks]

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor."""
        self._executor.shutdown(wait=wait)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_subagent_executor.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add core/subagent_executor.py tests/test_subagent_executor.py
git commit -m "feat: add SubagentExecutor with ThreadPoolExecutor and task context isolation"
```

---

## Task 4: Create Subagent Skill Definition

**Files:**
- Create: `agents/subagent.md`

- [ ] **Step 1: Write the subagent skill definition**

```markdown
# Subagent Skill

You are a subagent executing a task within an AutoDev parallel execution session. You run inside a scoped context with sandboxed tools — not a full Claude Code CLI session.

## Your Role

You receive a task assignment (task_id, description, prompt, skill) from the lead agent and implement it using your assigned skill. You coordinate with other subagents through shared state.

## Preamble

You have access to:
- `context.task_id` — your unique task identifier
- `context.description` — what you need to do
- `context.prompt` — detailed instructions
- `context.tools` — sandboxed tool interface (read_file, write_file, bash, glob, grep)
- `context.files_created` — list files you've created
- `context.files_modified` — list files you've modified

## Skills

### implement

Execute the assigned implementation task.

**Workflow:**
1. Read the repository context (CLAUDE.md, relevant source files)
2. Understand the current codebase structure
3. Implement the feature or fix described in your prompt
4. Write tests for your implementation
5. Run the test suite
6. Update context.files_created and context.files_modified

**Important:** You are in a sandboxed workspace. File operations are restricted to your task workspace. Use `context.tools.read_file()` and `context.tools.write_file()` for file access.

### test

Run tests and report results into context.

**Workflow:**
1. Find relevant test files
2. Run the test suite
3. If tests fail, fix and retry (up to 3 attempts)
4. Report results back to lead agent

## State Coordination

Before starting, read the shared agent state:
```
.main_repo/.autodev/agent-state.json
```

Post a `claim` message for files you intend to modify:
```
context.post_message({
    "type": "claim",
    "content": "Modifying: file1.py, file2.py",
    "from": context.task_id,
    "to": "all"
})
```

When done, post a `done` message:
```
context.post_message({
    "type": "done",
    "content": "Completed feature X. Created: file1.py. Modified: file2.py",
    "from": context.task_id,
    "to": "lead"
})
```

## Exit Criteria

- All implementation complete
- Tests pass
- Shared state updated
- Result returned to lead agent via context.set_result()
```

---

## Task 5: Create task() Tool Definition

**Files:**
- Create: `skills/autodev/task_tool.md`

This tool definition is what the lead agent uses to dispatch subagents.

```markdown
# task() — Subagent Dispatch Tool

## Purpose

The `task()` tool dispatches subagents for concurrent execution. It is the primary mechanism for parallelism in AutoDev's parallel subagent architecture (DeerFlow-style).

## Interface

```
task(description: string, prompt: string, skill: string, context?: object) -> task_id: string
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | string | Short human-readable description of the task |
| `prompt` | string | Detailed instructions for the subagent |
| `skill` | string | The skill type: "coder", "researcher" |
| `context` | object | Optional context: `{files?: string[], repo_path?: string}` |
| `returns` | string | A task_id string that can be used to wait for results |

## Behavior

1. Creates a `SubagentTask` with a unique task_id
2. Submits task to the `SubagentExecutor` thread pool
3. Returns the task_id immediately (non-blocking)
4. Task runs concurrently with other dispatched tasks (up to max_parallelism=3)
5. Each task has a 15-minute default timeout

## Usage Constraints

- Maximum **3 concurrent tasks** per turn (enforced by executor semaphore)
- Maximum **15-minute timeout** per task
- Tasks are **sandboxed** — no filesystem access outside workspace
- Tasks coordinate via **shared state file** (`.autodev/agent-state.json`)

## Result Aggregation

To wait for task results, use `wait_for_tasks(task_ids: string[])` after dispatching:

```
results = wait_for_tasks(["task-1", "task-2", "task-3"])
```

Each result contains:
- `status`: "completed" | "failed" | "timeout"
- `output`: task's return value
- `files_created`: list of files created
- `files_modified`: list of files modified
- `error`: error message if failed
```

---

## Task 6: Update commands/autodev.md — Phase 5 with task() Dispatch

**Files:**
- Modify: `commands/autodev.md`

Replace Phase 5 (Dispatch Parallel Coder Agents) with the new task()-based dispatch.

- [ ] **Step 1: Update Phase 5 in commands/autodev.md**

Replace the existing Phase 5 steps with:

```markdown
## Phase 5: Dispatch Parallel Subagents

**Goal:** Implement each feature concurrently using subagent tasks dispatched via `task()` tool.

### Steps

1. **Initialize the SubagentExecutor**

   ```python
   from core.subagent_executor import SubagentExecutor

   executor = SubagentExecutor(
       workspace=str(Path(repo_path) / ".autodev" / "workspaces"),
       max_parallelism=3,
       timeout_per_task=900,  # 15 minutes
   )
   ```

2. **Register skill handlers**

   ```python
   from agents.subagent_handlers import CoderHandler, ResearcherHandler

   executor.register_handler("coder", CoderHandler().execute)
   executor.register_handler("researcher", ResearcherHandler().execute)
   ```

3. **For each feature, dispatch a task via task() tool**

   Use the `task()` tool for each feature:

   ```
   task(
     description="Implement JWT authentication feature",
     prompt="Implement JWT middleware for auth. Read CLAUDE.md first. Subtasks: ...",
     skill="coder",
     context={"repo_path": "/path/to/repo"}
   )
   ```

   Collect the returned task_ids:
   ```
   task_ids = ["feat-1", "feat-2", "feat-3"]
   ```

4. **Wait for all tasks to complete**

   ```
   results = wait_for_tasks(task_ids)
   ```

5. **Process results**

   For each result in results:
   - If status == "completed": update feature_list.json
   - If status == "failed" or "timeout": mark feature as failed, note error
   - Aggregate files_created and files_modified for merge phase

### Concurrency Rules

- Maximum 3 concurrent subagents per AutoDev session
- 15-minute timeout per subagent task
- Tasks run in isolated workspace directories
- Subagents coordinate via shared agent-state.json
```

---

## Task 7: Implement CoderHandler (Subagent Skill Handler)

**Files:**
- Create: `agents/subagent_handlers.py`
- Create: `tests/test_subagent_handlers.py`

- [ ] **Step 1: Write failing tests for CoderHandler**

```python
# tests/test_subagent_handlers.py
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.subagent_handlers import CoderHandler

class TestCoderHandler:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def test_coder_handler_implements_coder_skill(self):
        handler = CoderHandler()
        assert hasattr(handler, 'execute')
        assert callable(handler.execute)

    def test_coder_handler_returns_result_dict(self):
        handler = CoderHandler()
        mock_context = MagicMock()
        mock_context.task_id = "test-1"
        mock_context.description = "Test task"
        mock_context.tools.read_file.return_value = {"status": "success", "content": ""}
        mock_context.files_created = []
        mock_context.files_modified = []

        with patch.object(handler, '_execute_impl', return_value={"status": "completed"}):
            result = handler.execute(mock_context)

        assert isinstance(result, dict)
        assert result["status"] == "completed"
```

- [ ] **Step 2: Implement CoderHandler**

```python
# agents/subagent_handlers.py
"""Skill handlers for subagent execution.

Each handler implements a specific skill (coder, researcher) for subagent tasks.
Handlers receive a TaskContext and return a result dict.
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from core.task_context import TaskContext


class CoderHandler:
    """Handler for the 'coder' skill.

    Executes implementation tasks in a subagent context:
    - Reads task prompt and context
    - Uses sandboxed tools to read existing code
    - Implements the feature
    - Writes tests and implementation
    - Returns result
    """

    def __init__(self):
        self.logger = logging.getLogger("autodev.coder_handler")

    def execute(self, context: TaskContext) -> Dict[str, Any]:
        """Execute a coding task within a subagent context."""
        self.logger.info(f"[{context.task_id}] Starting coder task: {context.description}")

        try:
            # The context.prompt contains the detailed instructions
            # context.tools provides sandboxed file access
            # context.context contains repo_path, relevant files, etc.

            task_context = context.context or {}

            # Get the implementation prompt
            prompt = getattr(context, 'prompt', context.description)

            # Execute implementation
            result = self._execute_impl(context, prompt, task_context)

            context.set_result(result)
            return result

        except Exception as e:
            self.logger.error(f"[{context.task_id}] Coder task failed: {e}")
            context.set_error(str(e))
            return {"status": "failed", "error": str(e)}

    def _execute_impl(self, context: TaskContext, prompt: str, task_context: Dict[str, Any]) -> Dict[str, Any]:
        """Core implementation logic.

        This method is designed to be replaced by the skill loader
        or to call out to Claude Code with a focused prompt.
        For now, it returns a stub — real implementation uses Claude Code.
        """
        # TODO: In the full implementation, this calls Claude Code with
        # a focused implementation prompt using context.tools
        #
        # For integration with Claude Code:
        # result = subprocess.run(
        #     ["claude", "-p", self._build_claude_prompt(prompt, task_context)],
        #     cwd=context.tools.workspace,
        #     capture_output=True, text=True, timeout=context.timeout_seconds
        # )
        # return {"status": "completed" if result.returncode == 0 else "failed", "output": result.stdout}

        self.logger.warning(f"[{context.task_id}] _execute_impl called but not yet connected to Claude Code")
        return {
            "status": "completed",
            "message": f"CoderHandler stub for task {context.task_id}",
            "prompt_summary": prompt[:200],
        }


class ResearcherHandler:
    """Handler for the 'researcher' skill.

    Executes research tasks:
    - Searches for error solutions
    - Looks up API documentation
    - Returns structured findings
    """

    def __init__(self):
        self.logger = logging.getLogger("autodev.researcher_handler")

    def execute(self, context: TaskContext) -> Dict[str, Any]:
        """Execute a research task within a subagent context."""
        self.logger.info(f"[{context.task_id}] Starting researcher task: {context.description}")

        try:
            task_context = context.context or {}
            prompt = getattr(context, 'prompt', context.description)
            result = self._research(context, prompt, task_context)
            context.set_result(result)
            return result
        except Exception as e:
            self.logger.error(f"[{context.task_id}] Researcher task failed: {e}")
            context.set_error(str(e))
            return {"status": "failed", "error": str(e)}

    def _research(self, context: TaskContext, prompt: str, task_context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute research using web search."""
        # TODO: Integrate with web search tools
        self.logger.warning(f"[{context.task_id}] _research called but not yet connected to web search")
        return {
            "status": "completed",
            "message": f"ResearcherHandler stub for task {context.task_id}",
            "findings": [],
        }
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_subagent_handlers.py -v
```

- [ ] **Step 4: Commit**

```bash
git add agents/subagent_handlers.py tests/test_subagent_handlers.py
git commit -m "feat: add CoderHandler and ResearcherHandler for subagent skill dispatch"
```

---

## Task 8: Add wait_for_tasks to commands/autodev.md

**Files:**
- Modify: `commands/autodev.md` — add Phase 5b for result aggregation

- [ ] **Step 1: Add result aggregation section**

After Phase 5 steps, add a Phase 5b:

```markdown
## Phase 5b: Aggregate Results

After `wait_for_tasks()` returns, aggregate all subagent results.

### Steps

1. **Collect all results**

   ```python
   results = wait_for_tasks(task_ids)

   for i, result in enumerate(results):
       feature = features[i]
       if result.status == "completed":
           feature["status"] = "completed"
           feature["files_created"] = result.files_created
           feature["files_modified"] = result.files_modified
       else:
           feature["status"] = "failed"
           feature["error"] = result.error
   ```

2. **Update feature_list.json**

   ```python
   # Read-modify-write feature_list.json
   update_feature_statuses(features)
   ```

3. **Log progress**

   ```
   Append to .autodev/autodev-progress.txt:
   2026-03-20T10:35:00Z [lead] All subagent tasks completed
   2026-03-20T10:35:01Z [lead] feat-1: completed (3 files created, 2 modified)
   2026-03-20T10:35:01Z [lead] feat-2: failed (timeout)
   ```

4. **Handle failures**

   For any failed or timed-out tasks:
   - Log the error
   - Mark feature as failed
   - If time permits, retry once (max 1 retry per failed task)
```

---

## Task 9: Update Shared State Protocol for Thread-Safe Coordination

**Files:**
- Modify: `skills/autodev/references/shared-state-protocol.md`

- [ ] **Step 1: Add thread-safe coordination rules**

Add a new section at the end:

```markdown
## Thread-Safe Coordination

When using the parallel subagent executor (ThreadPoolExecutor), the shared state protocol must handle concurrent reads and writes safely.

### Thread-Safety Rules

1. **Use atomic read-modify-write**: Always read the full file, modify in memory, write back atomically
2. **Use file locking** for writes: Use a lock file `.autodev/agent-state.json.lock`
3. **Append-only messages**: Never delete or modify existing messages
4. **Optimistic reads for agents**: Agents can read state without locking; conflicts are resolved at merge time

### Lock File Protocol

Before writing to agent-state.json:
```bash
# Acquire lock
flock .autodev/agent-state.json.lock -c "atomic update"
```

Python implementation:
```python
import fcntl

def atomic_write_state(state_path: Path, update_fn):
    lock_path = state_path.with_suffix(".json.lock")
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            state = json.loads(state_path.read_text())
            state = update_fn(state)
            state_path.write_text(json.dumps(state, indent=2))
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
```

### Subagent Claim Protocol

When running in threads, claims are made to the shared state file:
```
POST claim: {from: "task-1", type: "claim", content: "Modifying: src/auth.py"}
```

Each subagent should post a claim before starting and a done message when complete.
```

---

## Task 10: Integration Test — Full Pipeline with Mocked Subagents

**Files:**
- Create: `tests/test_parallel_subagent_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_parallel_subagent_integration.py
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.subagent_executor import SubagentExecutor, SubagentTask


class TestParallelSubagentIntegration:
    """Integration test for the full parallel subagent pipeline."""

    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def test_multiple_tasks_run_concurrently(self):
        """Verify 3 tasks complete in ~parallel time, not sequential."""
        executor = SubagentExecutor(
            workspace=self.tempdir,
            max_parallelism=3,
            timeout_per_task=60,
        )

        task_timings = []

        def slow_handler(ctx):
            tid = ctx.task_id
            time.sleep(0.2)
            task_timings.append((tid, time.time()))
            return {"status": "completed", "task_id": tid}

        executor.register_handler("coder", slow_handler)

        tasks = [
            SubagentTask(task_id=f"task-{i}", description=f"Task {i}", prompt="", skill="coder")
            for i in range(3)
        ]

        start = time.time()
        results = executor.submit_and_wait(tasks)
        elapsed = time.time() - start

        assert len(results) == 3
        assert all(r.status == "completed" for r in results)
        # Should take ~0.2s (parallel), not ~0.6s (sequential)
        assert elapsed < 0.4, f"Took {elapsed:.2f}s — tasks may not be running concurrently"

    def test_failed_task_returns_error(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=1)

        def failing_handler(ctx):
            raise ValueError("Intentional failure")

        executor.register_handler("coder", failing_handler)

        task = SubagentTask(task_id="fail-1", description="Failing task", prompt="", skill="coder")
        results = executor.submit_and_wait([task])

        assert results[0].status == "failed"
        assert "ValueError" in results[0].error

    def test_unknown_skill_returns_error(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=1)
        task = SubagentTask(task_id="unknown-1", description="Unknown skill", prompt="", skill="nonexistent")
        results = executor.submit_and_wait([task])

        assert results[0].status == "failed"
        assert "No handler" in results[0].error
```

- [ ] **Step 2: Run integration tests**

```bash
pytest tests/test_parallel_subagent_integration.py -v
```

Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_parallel_subagent_integration.py
git commit -m "test: add integration test for concurrent subagent execution"
```

---

## Task 11: Update commands/autodev.md — Phase 6-8 with New Architecture

**Files:**
- Modify: `commands/autodev.md` — update merge, review, and report phases

- [ ] **Step 1: Update Phase 6 (Merge) for new architecture**

Replace the git-merge approach with subagent result aggregation:

```markdown
## Phase 6: Merge Results

**Goal:** Combine all subagent results into a unified branch.

### Steps

1. **Aggregate all files from subagent results**

   ```python
   all_created = []
   all_modified = []
   for result in results:
       all_created.extend(result.files_created)
       all_modified.extend(result.files_modified)
   ```

2. **Copy all modified files to main worktree**

   Each subagent's workspace is at `.autodev/workspaces/task_{task_id}/`
   Copy files that were created or modified:

   ```python
   import shutil
   from pathlib import Path

   workspaces = Path(repo_path) / ".autodev" / "workspaces"
   for result in results:
       task_workspace = workspaces / f"task_{result.task_id}"
       for f in result.files_created + result.files_modified:
           src = task_workspace / f
           if src.exists():
               dst = Path(repo_path) / f
               dst.parent.mkdir(parents=True, exist_ok=True)
               shutil.copy2(src, dst)
   ```

3. **Run full test suite**

   ```bash
   pytest tests/ -v
   ```

4. **Handle conflicts**

   If tests fail due to conflicting changes to the same file:
   - Identify which subagents modified the same file
   - Dispatch a reconciliation subagent to merge the changes
   - Re-run tests

5. **Update progress file**
```

- [ ] **Step 2: Commit**

```bash
git add commands/autodev.md
git commit -m "feat: update Phase 5-6 for task()-based subagent dispatch"
```

---

## Task 12: Add DeerFlow Learnings Reference Doc

**Files:**
- Create: `docs/deerflow_subagents_learnings.md`

This document captures what DeerFlow does and how AutoDev's new architecture maps to it.

```markdown
# DeerFlow vs AutoDev: Architecture Mapping

## DeerFlow Model

- **Lead agent** — main orchestrator, coordinates work
- **task() tool** — spawns subagents
- **Background concurrent execution** — thread pool
- **Sandboxed tools** — read_file, write_file, bash, etc.
- **Per-thread workspace** — isolation per task
- **Max 3 subagents per turn, 15-min timeout**

## AutoDev New Architecture (Parallel Subagent Model)

| DeerFlow Component | AutoDev Equivalent |
|--------------------|-------------------|
| Lead agent | `/autodev` command (Claude Code) |
| task() tool | `SubagentExecutor.submit_and_wait()` |
| ThreadPoolExecutor | `concurrent.futures.ThreadPoolExecutor` |
| Sandboxed tools | `SandboxedTools` class |
| Per-thread context | `TaskContext` + contextvars |
| Max 3 per turn | `max_parallelism=3` |
| 15-min timeout | `timeout_per_task=900` |
| Result aggregation | Lead agent collects `AgentResult[]` |
```

---

## Execution Order

```
Task 1 (TaskContext) — no deps
Task 2 (SandboxedTools) — no deps
Task 3 (SubagentExecutor) — depends on Tasks 1, 2
Task 4 (subagent.md) — no deps
Task 5 (task_tool.md) — no deps
Task 6 (autodev.md Phase 5 update) — depends on Tasks 3, 4, 5
Task 7 (CoderHandler) — depends on Tasks 1, 2
Task 8 (Phase 5b aggregation) — depends on Task 6
Task 9 (shared-state thread safety) — depends on Task 3
Task 10 (integration tests) — depends on Tasks 1, 2, 3, 7
Task 11 (Phase 6-8 update) — depends on Task 6
Task 12 (reference doc) — no deps
```

**Parallelizable groups:**
- Group A: Tasks 1, 2, 4, 5, 12 (all independent)
- Group B: Task 3 (depends on 1, 2)
- Group C: Task 7 (depends on 1, 2)
- Group D: Tasks 6, 8, 9 (depend on 3, 4, 5)
- Group E: Tasks 10, 11 (depend on all above)
