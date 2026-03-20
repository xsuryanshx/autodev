"""ThreadPoolExecutor-based subagent dispatcher.

Dispatches tasks to sandboxed environments (local or E2B) via SandboxManager,
runs handlers in concurrent threads with per-task context isolation.
"""
import concurrent.futures
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any

from core.sandbox_backend import SandboxBackend, SandboxConfig
from core.sandbox_manager import SandboxManager
from core.task_context import TaskContext, task_scope

logger = logging.getLogger(__name__)


@dataclass
class SubagentTask:
    task_id: str
    description: str
    prompt: str
    skill: str
    context: Optional[Dict[str, Any]] = None
    timeout_seconds: int = 900
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    task_id: str
    status: str
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class SubagentExecutor:
    """Dispatches subagent tasks with pluggable sandbox backends.

    Supports two modes:
    - backend="local": path-checked local sandboxes (fast, no isolation)
    - backend="e2b": E2B cloud microVMs (slower, full kernel isolation)

    The sandbox_manager handles all sandbox lifecycle (create, setup, destroy).
    """

    def __init__(
        self,
        workspace: str,
        max_parallelism: int = 3,
        timeout_per_task: int = 900,
        sandbox_config: Optional[SandboxConfig] = None,
    ):
        self.workspace = Path(workspace).resolve()
        self.max_parallelism = max_parallelism
        self.timeout_per_task = timeout_per_task

        config = sandbox_config or SandboxConfig(
            backend="local",
            local_base_dir=str(self.workspace),
            timeout_seconds=timeout_per_task,
        )
        self._sandbox_manager = SandboxManager(config)

        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_parallelism,
            thread_name_prefix="subagent-",
        )
        self._handlers: Dict[str, Callable] = {}
        self._results: Dict[str, AgentResult] = {}
        self._results_lock = threading.Lock()

    @property
    def sandbox_manager(self) -> SandboxManager:
        return self._sandbox_manager

    def register_handler(self, skill: str, handler: Callable) -> None:
        self._handlers[skill] = handler

    def _get_handler_for_skill(self, skill: str) -> Optional[Callable]:
        return self._handlers.get(skill)

    def _run_task(self, task: SubagentTask) -> AgentResult:
        timeout = task.timeout_seconds or self.timeout_per_task
        task_ctx = TaskContext(
            task_id=task.task_id,
            description=task.description,
            prompt=task.prompt,
            timeout_seconds=timeout,
            context=task.context,
        )

        sandbox: Optional[SandboxBackend] = None
        try:
            sandbox = self._sandbox_manager.create_sandbox(
                task_id=task.task_id,
                timeout_seconds=timeout,
            )
            task_ctx.tools = sandbox
        except Exception as e:
            logger.error(f"[{task.task_id}] Failed to create sandbox: {e}")
            task_ctx.set_error(f"Sandbox creation failed: {e}")
            return AgentResult(
                task_id=task.task_id,
                status="failed",
                error=f"Sandbox creation failed: {e}",
            )

        handler = self._get_handler_for_skill(task.skill)
        if handler is None:
            task_ctx.set_error(f"No handler registered for skill: {task.skill}")
            self._cleanup_sandbox(task.task_id)
            return AgentResult(
                task_id=task.task_id,
                status="failed",
                error=f"No handler for skill: {task.skill}",
            )

        started = time.time()

        try:
            with task_scope(task_ctx):
                result_value = handler(task_ctx)
        except Exception as e:
            duration = time.time() - started
            task_ctx.set_error(str(e))
            self._cleanup_sandbox(task.task_id)
            return AgentResult(
                task_id=task.task_id,
                status="failed",
                error=f"{type(e).__name__}: {e}",
                files_created=list(task_ctx.files_created),
                files_modified=list(task_ctx.files_modified),
                duration_seconds=duration,
            )

        duration = time.time() - started
        self._cleanup_sandbox(task.task_id)
        return AgentResult(
            task_id=task.task_id,
            status="completed",
            output=result_value or {},
            files_created=list(task_ctx.files_created),
            files_modified=list(task_ctx.files_modified),
            duration_seconds=duration,
        )

    def _cleanup_sandbox(self, task_id: str) -> None:
        try:
            self._sandbox_manager.destroy_sandbox(task_id)
        except Exception as e:
            logger.warning(f"[{task_id}] Sandbox cleanup failed: {e}")

    def submit_and_wait(self, tasks: List[SubagentTask]) -> List[AgentResult]:
        futures = {}
        for task in tasks:
            future = self._executor.submit(self._run_task, task)
            futures[future] = task.task_id

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
                self._cleanup_sandbox(task_id)
            except Exception as e:
                result = AgentResult(
                    task_id=task_id,
                    status="failed",
                    error=f"Task raised: {type(e).__name__}: {e}",
                )
                self._cleanup_sandbox(task_id)

            with self._results_lock:
                self._results[task_id] = result

        return [self._results[t.task_id] for t in tasks]

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown executor and destroy all sandboxes."""
        self._executor.shutdown(wait=wait)
        self._sandbox_manager.shutdown()
