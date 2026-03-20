import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

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
    prompt: str = ""
    status: str = "pending"
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None
    timeout_seconds: int = 900
    context: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def set_status(self, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
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
            "prompt": self.prompt,
            "status": self.status,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "files_deleted": self.files_deleted,
            "result": self.result,
            "error": self.error,
            "timeout_seconds": self.timeout_seconds,
            "context": self.context,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class task_scope:
    """Context manager that sets the current task context.

    Each thread gets its own ContextVar value, so multiple task_scopes
    can be active concurrently across different threads without conflict.
    Nesting within the same thread is not allowed.
    """

    def __init__(self, ctx: TaskContext):
        self.ctx = ctx
        self._token = None

    def __enter__(self):
        prev = _current_task_context.get()
        if prev is not None:
            raise RuntimeError(
                f"Nested task_scope detected for task {self.ctx.task_id}. "
                f"Each task must have a single scope."
            )
        self._token = _current_task_context.set(self.ctx)
        self.ctx.set_status("running")
        return self.ctx

    def __exit__(self, exc_type, exc_val, exc_tb):
        _current_task_context.reset(self._token)
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