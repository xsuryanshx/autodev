"""Abstract sandbox backend protocol and factory.

Defines the interface that all sandbox backends (local, E2B, Docker)
must implement so SubagentExecutor can swap backends transparently.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class SandboxError(Exception):
    """Base error for sandbox operations."""
    pass


class SandboxCreationError(SandboxError):
    pass


class SandboxTimeoutError(SandboxError):
    pass


@dataclass
class ToolResult:
    status: str
    message: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    content: Optional[str] = None
    files: Optional[List[str]] = None

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if v is not None:
                d[k] = v
        return d


class SandboxState(str, Enum):
    CREATING = "creating"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class SandboxInfo:
    sandbox_id: str
    task_id: str
    backend: str
    state: SandboxState
    workspace: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SandboxBackend(Protocol):
    """Interface that all sandbox tool implementations must satisfy.

    Both LocalSandboxedTools and E2BSandboxedTools implement this.
    The SubagentExecutor only depends on this protocol, not on concrete classes.
    """

    @property
    def workspace(self) -> str:
        """Root workspace path inside the sandbox."""
        ...

    def read_file(self, path: str) -> Dict[str, Any]:
        """Read a file's contents. Path is relative to workspace."""
        ...

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write content to a file. Path is relative to workspace."""
        ...

    def bash(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Execute a shell command."""
        ...

    def glob(self, pattern: str) -> Dict[str, Any]:
        """Find files matching a glob pattern."""
        ...

    def grep(self, pattern: str, path: Optional[str] = None) -> Dict[str, Any]:
        """Search for regex pattern in files."""
        ...

    def setup(self, repo_url: Optional[str] = None, branch: Optional[str] = None,
              clone_token: Optional[str] = None) -> Dict[str, Any]:
        """Bootstrap the sandbox: clone repo, install deps, checkout branch."""
        ...

    def destroy(self) -> None:
        """Tear down the sandbox and release resources."""
        ...


@dataclass
class SandboxConfig:
    """Configuration for sandbox creation."""
    backend: str = "local"
    timeout_seconds: int = 900
    repo_url: Optional[str] = None
    branch: Optional[str] = None
    clone_token: Optional[str] = None

    # E2B-specific
    e2b_template: str = "base"
    e2b_api_key: Optional[str] = None
    e2b_snapshot_id: Optional[str] = None
    e2b_auto_pause: bool = True

    # Local-specific
    local_base_dir: Optional[str] = None
    local_sanitize_env: bool = True

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SandboxConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_file(cls, path: str) -> "SandboxConfig":
        p = Path(path)
        if not p.exists():
            logger.warning(f"Config file {path} not found, using defaults")
            return cls()
        data = json.loads(p.read_text())
        sandbox_cfg = data.get("sandbox", data)
        return cls.from_dict(sandbox_cfg)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}
