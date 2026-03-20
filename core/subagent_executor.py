"""ThreadPoolExecutor-based subagent dispatcher."""
import concurrent.futures
import threading
import time
from contextvars import copy_context
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Callable, Optional, Any, Dict

from core.task_context import TaskContext, _current_task_context
from core.sandboxed_tools import SandboxedTools


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
        self._handlers: Dict[str, Callable] = {}
        self._results: Dict[str, AgentResult] = {}
        self._results_lock = threading.Lock()

    def register_handler(self, skill: str, handler: Callable) -> None:
        self._handlers[skill] = handler

    def _get_handler_for_skill(self, skill: str) -> Optional[Callable]:
        return self._handlers.get(skill)

    def _run_task(self, task: SubagentTask) -> AgentResult:
        task_ctx = TaskContext(
            task_id=task.task_id,
            description=task.description,
            timeout_seconds=task.timeout_seconds or self.timeout_per_task,
        )
        task_workspace = self.workspace / f"task_{task.task_id}"
        task_workspace.mkdir(parents=True, exist_ok=True)
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

        timeout = task.timeout_seconds or self.timeout_per_task
        started = time.time()

        # Set up context for the handler
        prev_ctx = _current_task_context.set(task_ctx)
        task_ctx.set_status("running")

        # Run handler with timeout enforcement using a cancellable thread
        result_holder = {}
        exception_holder = {}
        lock = threading.Lock()

        def target():
            try:
                result_holder["value"] = handler(task_ctx)
            except Exception as e:
                with lock:
                    exception_holder["exception"] = e
            finally:
                _current_task_context.set(prev_ctx)

        thread = threading.Thread(target=target)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Timeout exceeded - thread is still running
            _current_task_context.set(prev_ctx)
            duration = time.time() - started
            return AgentResult(
                task_id=task.task_id,
                status="timeout",
                error=f"Task exceeded timeout of {timeout}s",
                files_created=list(task_ctx.files_created),
                files_modified=list(task_ctx.files_modified),
                duration_seconds=duration,
            )

        duration = time.time() - started

        if exception_holder.get("exception"):
            e = exception_holder["exception"]
            task_ctx.set_error(str(e))
            return AgentResult(
                task_id=task.task_id,
                status="failed",
                error=f"{type(e).__name__}: {e}",
                files_created=list(task_ctx.files_created),
                files_modified=list(task_ctx.files_modified),
                duration_seconds=duration,
            )

        return AgentResult(
            task_id=task.task_id,
            status="completed",
            output=result_holder.get("value") or {},
            files_created=list(task_ctx.files_created),
            files_modified=list(task_ctx.files_modified),
            duration_seconds=duration,
        )

    def submit_and_wait(self, tasks: List[SubagentTask]) -> List[AgentResult]:
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

            results.append(result)

        return [self._results[t.task_id] for t in tasks]

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
