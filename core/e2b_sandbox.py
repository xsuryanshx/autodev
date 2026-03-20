"""E2B cloud sandbox backend.

Provides real kernel-level isolation via Firecracker microVMs.
Each task gets its own E2B sandbox with a full Linux environment,
isolated filesystem, network, and process namespace.

Uses the sync E2B SDK to stay compatible with ThreadPoolExecutor.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from core.sandbox_backend import (
    SandboxCreationError,
    SandboxError,
    SandboxTimeoutError,
    ToolResult,
)

logger = logging.getLogger(__name__)

try:
    from e2b import Sandbox as E2BSandbox
except ImportError:
    E2BSandbox = None

_WORKSPACE_DIR = "/home/user/repo"

_SAFE_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL", "TERM",
    "PYTHONPATH", "NODE_PATH", "GOPATH",
})


def _require_e2b() -> None:
    if E2BSandbox is None:
        raise ImportError(
            "e2b package not installed. Run: pip install e2b"
        )


class E2BSandboxedTools:
    """Sandbox tools backed by an E2B cloud microVM.

    Every file operation and command runs inside the VM, not on the host.
    No path-checking is needed — the sandbox IS the boundary.
    """

    def __init__(
        self,
        sandbox: "E2BSandbox",
        workspace: str = _WORKSPACE_DIR,
        timeout_seconds: int = 300,
        task_id: Optional[str] = None,
    ):
        self._sandbox = sandbox
        self._workspace = workspace
        self.timeout_seconds = timeout_seconds
        self.task_id = task_id
        self._destroyed = False

    @property
    def workspace(self) -> str:
        return self._workspace

    @property
    def sandbox_id(self) -> str:
        return self._sandbox.sandbox_id

    @classmethod
    def create(
        cls,
        task_id: str,
        template: str = "base",
        timeout_seconds: int = 900,
        api_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        envs: Optional[Dict[str, str]] = None,
    ) -> "E2BSandboxedTools":
        """Create a new E2B sandbox.

        Args:
            task_id: Unique identifier for the task.
            template: E2B template ID or name.
            timeout_seconds: Max sandbox lifetime.
            api_key: E2B API key. Falls back to E2B_API_KEY env var.
            metadata: Metadata attached to the sandbox.
            envs: Environment variables to set inside the sandbox.
        """
        _require_e2b()

        resolved_key = api_key or os.environ.get("E2B_API_KEY")
        if not resolved_key:
            raise SandboxCreationError(
                "E2B API key required. Set E2B_API_KEY env var or pass api_key."
            )

        meta = {"task_id": task_id, **(metadata or {})}
        sandbox_envs = envs or {}

        try:
            sandbox = E2BSandbox(
                template=template,
                timeout=timeout_seconds,
                metadata=meta,
                envs=sandbox_envs,
                api_key=resolved_key,
            )
        except Exception as e:
            raise SandboxCreationError(f"Failed to create E2B sandbox: {e}") from e

        logger.info(
            f"[{task_id}] E2B sandbox created: id={sandbox.sandbox_id}, "
            f"template={template}, timeout={timeout_seconds}s"
        )

        instance = cls(
            sandbox=sandbox,
            timeout_seconds=timeout_seconds,
            task_id=task_id,
        )
        instance._ensure_workspace()
        return instance

    @classmethod
    def from_snapshot(
        cls,
        task_id: str,
        snapshot_id: str,
        timeout_seconds: int = 900,
        api_key: Optional[str] = None,
    ) -> "E2BSandboxedTools":
        """Create a sandbox from a pre-built snapshot (repo already cloned + deps installed)."""
        return cls.create(
            task_id=task_id,
            template=snapshot_id,
            timeout_seconds=timeout_seconds,
            api_key=api_key,
            metadata={"from_snapshot": snapshot_id},
        )

    def _ensure_workspace(self) -> None:
        self._sandbox.commands.run(f"mkdir -p {self._workspace}", timeout=10)

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return f"{self._workspace}/{path}"

    def read_file(self, path: str) -> Dict[str, Any]:
        try:
            resolved = self._resolve_path(path)
            content = self._sandbox.files.read(resolved)
            return ToolResult(status="success", content=content).to_dict()
        except Exception as e:
            error_str = str(e)
            if "not found" in error_str.lower() or "no such file" in error_str.lower():
                return ToolResult(status="error", message=f"File not found: {path}").to_dict()
            return ToolResult(status="error", message=error_str).to_dict()

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        try:
            resolved = self._resolve_path(path)
            parent = "/".join(resolved.rsplit("/", 1)[:-1])
            if parent:
                self._sandbox.commands.run(f"mkdir -p {parent}", timeout=10)
            self._sandbox.files.write(resolved, content)
            return ToolResult(status="success", message=f"Written to {path}").to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def bash(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Execute a command inside the sandbox VM.

        Unlike LocalSandboxedTools, this is fully isolated — the command
        runs in its own kernel with no access to the host.
        """
        try:
            run_cwd = cwd or self._workspace
            result = self._sandbox.commands.run(
                command,
                cwd=run_cwd,
                timeout=self.timeout_seconds,
            )
            status = "success" if result.exit_code == 0 else "error"
            tr = ToolResult(
                status=status,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
            )
            if result.exit_code != 0:
                tr.message = f"Command exited with code {result.exit_code}"
            return tr.to_dict()
        except Exception as e:
            error_str = str(e).lower()
            if "timeout" in error_str:
                return ToolResult(
                    status="error",
                    message=f"Command timed out after {self.timeout_seconds}s",
                ).to_dict()
            return ToolResult(status="error", message=str(e)).to_dict()

    def glob(self, pattern: str) -> Dict[str, Any]:
        try:
            result = self._sandbox.commands.run(
                f"find {self._workspace} -path '{self._workspace}/{pattern}' -type f 2>/dev/null"
                if not pattern.startswith("/")
                else f"find {pattern} -type f 2>/dev/null",
                timeout=30,
            )
            files = [f for f in result.stdout.strip().split("\n") if f]
            return ToolResult(status="success", files=files).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def grep(self, pattern: str, path: Optional[str] = None) -> Dict[str, Any]:
        try:
            search_path = self._resolve_path(path) if path else self._workspace
            result = self._sandbox.commands.run(
                f"grep -rn '{pattern}' {search_path} 2>/dev/null || true",
                timeout=60,
            )
            return ToolResult(
                status="success",
                stdout=result.stdout,
                files=[search_path],
            ).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def setup(
        self,
        repo_url: Optional[str] = None,
        branch: Optional[str] = None,
        clone_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Clone a repo and checkout a branch inside the sandbox."""
        results = []

        if repo_url:
            if clone_token:
                authed_url = repo_url.replace(
                    "https://", f"https://x-access-token:{clone_token}@"
                )
            else:
                authed_url = repo_url

            clone_result = self.bash(
                f"git clone {authed_url} {self._workspace}",
                cwd="/home/user",
            )
            results.append(("clone", clone_result))
            if clone_result.get("exit_code", 1) != 0:
                return ToolResult(
                    status="error",
                    message=f"Git clone failed: {clone_result.get('stderr', '')}",
                ).to_dict()

        if branch:
            checkout_result = self.bash(f"git checkout -b {branch}")
            results.append(("checkout", checkout_result))

        deps_result = self._install_deps()
        if deps_result:
            results.append(("deps", deps_result))

        return ToolResult(
            status="success",
            message=f"Sandbox setup complete ({len(results)} steps)",
        ).to_dict()

    def _install_deps(self) -> Optional[Dict[str, Any]]:
        """Auto-detect and install dependencies."""
        check = self._sandbox.commands.run(
            f"ls {self._workspace}/requirements.txt {self._workspace}/package.json 2>/dev/null",
            timeout=5,
        )
        stdout = check.stdout.strip()

        if "requirements.txt" in stdout:
            return self.bash(f"pip install -r {self._workspace}/requirements.txt")
        elif "package.json" in stdout:
            return self.bash(f"cd {self._workspace} && npm install")
        return None

    def pause(self) -> str:
        """Pause the sandbox (preserves full state, stops billing)."""
        try:
            self._sandbox.pause()
            logger.info(f"[{self.task_id}] Sandbox {self.sandbox_id} paused")
            return self.sandbox_id
        except Exception as e:
            raise SandboxError(f"Failed to pause sandbox: {e}") from e

    def resume(self, timeout_seconds: Optional[int] = None) -> None:
        """Resume a paused sandbox."""
        _require_e2b()
        try:
            self._sandbox = E2BSandbox.connect(
                self.sandbox_id,
                timeout=timeout_seconds or self.timeout_seconds,
            )
            logger.info(f"[{self.task_id}] Sandbox {self.sandbox_id} resumed")
        except Exception as e:
            raise SandboxError(f"Failed to resume sandbox: {e}") from e

    def create_snapshot(self) -> str:
        """Snapshot current state. Returns snapshot ID for fast reuse."""
        try:
            snapshot_id = self._sandbox.snapshot()
            logger.info(
                f"[{self.task_id}] Snapshot created: {snapshot_id} "
                f"from sandbox {self.sandbox_id}"
            )
            return snapshot_id
        except Exception as e:
            raise SandboxError(f"Failed to create snapshot: {e}") from e

    def destroy(self) -> None:
        """Kill the sandbox and release all resources."""
        if self._destroyed:
            return
        try:
            self._sandbox.kill()
            self._destroyed = True
            logger.info(f"[{self.task_id}] Sandbox {self.sandbox_id} destroyed")
        except Exception as e:
            logger.warning(f"[{self.task_id}] Failed to destroy sandbox: {e}")

    def __del__(self):
        if not self._destroyed:
            try:
                self.destroy()
            except Exception:
                pass
