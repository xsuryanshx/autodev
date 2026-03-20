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
    """Per-task isolated execution context."""
    task_id: str
    description: str
    status: str = "pending"
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None
    timeout_seconds: int = 900
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def set_status(self, status: str) -> None:
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
    """Context manager that sets the current task context."""
    _lock = threading.Lock()
    _current_owner = None

    def __init__(self, ctx: TaskContext):
        self.ctx = ctx
        self._prev_owner = None

    def __enter__(self):
        thread_id = threading.current_thread().ident
        with task_scope._lock:
            if task_scope._current_owner is not None and task_scope._current_owner != thread_id:
                raise RuntimeError(
                    f"task_scope cannot cross thread boundaries. "
                    f"Owned by thread {task_scope._current_owner}, "
                    f"called from {thread_id}"
                )
            self._prev_owner = task_scope._current_owner
            task_scope._current_owner = thread_id
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
            task_scope._current_owner = self._prev_owner
        _current_task_context.set(None)
        if exc_type is not None:
            self.ctx.set_error(f"{exc_type.__name__}: {exc_val}")
        elif self.ctx.status == "running":
            self.ctx.set_status("completed")
        return False


def get_current_task_context() -> TaskContext:
    ctx = _current_task_context.get()
    if ctx is None:
        raise TaskContextError(
            "No current task context. Are you running inside a task_scope?"
        )
    return ctx