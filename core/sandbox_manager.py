"""Sandbox lifecycle manager.

Creates, tracks, snapshots, and destroys sandboxes. Supports both
local and E2B backends, with warm-start via snapshots.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.sandbox_backend import (
    SandboxBackend,
    SandboxConfig,
    SandboxCreationError,
    SandboxInfo,
    SandboxState,
)

logger = logging.getLogger(__name__)


class SandboxManager:
    """Manages sandbox lifecycle for parallel agent execution.

    Responsibilities:
    - Create sandboxes from config (local or E2B)
    - Track active sandboxes
    - Create warm snapshots (repo cloned + deps installed)
    - Destroy sandboxes on shutdown
    - Handle E2B-specific features (pause/resume, snapshots)
    """

    def __init__(self, config: SandboxConfig):
        self.config = config
        self._sandboxes: Dict[str, SandboxBackend] = {}
        self._sandbox_info: Dict[str, SandboxInfo] = {}
        self._lock = threading.Lock()
        self._snapshot_id: Optional[str] = config.e2b_snapshot_id
        self._shutdown = False

    @classmethod
    def from_config_file(cls, path: str) -> "SandboxManager":
        config = SandboxConfig.from_file(path)
        return cls(config)

    def create_sandbox(
        self,
        task_id: str,
        timeout_seconds: Optional[int] = None,
        extra_envs: Optional[Dict[str, str]] = None,
    ) -> SandboxBackend:
        """Create a new sandbox for a task.

        Picks the backend from config and creates the appropriate sandbox type.
        If a warm snapshot exists (E2B), uses it for fast startup.
        """
        if self._shutdown:
            raise SandboxCreationError("Manager is shut down, cannot create sandboxes")

        timeout = timeout_seconds or self.config.timeout_seconds

        if self.config.backend == "e2b":
            sandbox = self._create_e2b_sandbox(task_id, timeout, extra_envs)
        else:
            sandbox = self._create_local_sandbox(task_id, timeout)

        with self._lock:
            self._sandboxes[task_id] = sandbox
            self._sandbox_info[task_id] = SandboxInfo(
                sandbox_id=getattr(sandbox, "sandbox_id", task_id),
                task_id=task_id,
                backend=self.config.backend,
                state=SandboxState.RUNNING,
                workspace=str(sandbox.workspace),
            )

        logger.info(f"Sandbox created for task {task_id} (backend={self.config.backend})")
        return sandbox

    def _create_e2b_sandbox(
        self,
        task_id: str,
        timeout_seconds: int,
        extra_envs: Optional[Dict[str, str]] = None,
    ) -> SandboxBackend:
        from core.e2b_sandbox import E2BSandboxedTools

        template = self._snapshot_id or self.config.e2b_template

        return E2BSandboxedTools.create(
            task_id=task_id,
            template=template,
            timeout_seconds=timeout_seconds,
            api_key=self.config.e2b_api_key,
            metadata={"backend": "e2b", "task_id": task_id},
            envs=extra_envs,
        )

    def _create_local_sandbox(
        self,
        task_id: str,
        timeout_seconds: int,
    ) -> SandboxBackend:
        from core.sandboxed_tools import SandboxedTools

        base_dir = self.config.local_base_dir or "/tmp/autodev-sandboxes"
        task_workspace = Path(base_dir) / f"task_{task_id}"
        task_workspace.mkdir(parents=True, exist_ok=True)

        return SandboxedTools(
            workspace=str(task_workspace),
            timeout_seconds=timeout_seconds,
            sanitize_env=self.config.local_sanitize_env,
        )

    def setup_sandbox(
        self,
        task_id: str,
        repo_url: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bootstrap a sandbox with repo clone and dependency installation."""
        sandbox = self.get_sandbox(task_id)
        if sandbox is None:
            return {"status": "error", "message": f"No sandbox found for task {task_id}"}

        return sandbox.setup(
            repo_url=repo_url or self.config.repo_url,
            branch=branch or self.config.branch,
            clone_token=self.config.clone_token,
        )

    def get_sandbox(self, task_id: str) -> Optional[SandboxBackend]:
        with self._lock:
            return self._sandboxes.get(task_id)

    def get_sandbox_info(self, task_id: str) -> Optional[SandboxInfo]:
        with self._lock:
            return self._sandbox_info.get(task_id)

    def list_sandboxes(self) -> List[SandboxInfo]:
        with self._lock:
            return list(self._sandbox_info.values())

    def destroy_sandbox(self, task_id: str) -> None:
        """Destroy a single sandbox and remove from tracking."""
        with self._lock:
            sandbox = self._sandboxes.pop(task_id, None)
            info = self._sandbox_info.pop(task_id, None)

        if sandbox is not None:
            try:
                sandbox.destroy()
            except Exception as e:
                logger.warning(f"Error destroying sandbox for {task_id}: {e}")

        if info is not None:
            info.state = SandboxState.STOPPED

        logger.info(f"Sandbox destroyed for task {task_id}")

    def create_warm_snapshot(
        self,
        repo_url: str,
        branch: Optional[str] = None,
        clone_token: Optional[str] = None,
        install_deps: bool = True,
    ) -> str:
        """Create a reusable E2B snapshot with the repo pre-cloned and deps installed.

        This snapshot can be used to start future sandboxes instantly
        without repeating clone + install. Returns the snapshot ID.
        """
        if self.config.backend != "e2b":
            raise SandboxCreationError("Warm snapshots are only supported with E2B backend")

        from core.e2b_sandbox import E2BSandboxedTools

        setup_sandbox = E2BSandboxedTools.create(
            task_id="_snapshot_setup",
            template=self.config.e2b_template,
            timeout_seconds=600,
            api_key=self.config.e2b_api_key,
        )

        try:
            setup_result = setup_sandbox.setup(
                repo_url=repo_url,
                branch=branch,
                clone_token=clone_token,
            )
            if setup_result.get("status") != "success":
                raise SandboxCreationError(
                    f"Snapshot setup failed: {setup_result.get('message')}"
                )

            snapshot_id = setup_sandbox.create_snapshot()
            self._snapshot_id = snapshot_id

            logger.info(f"Warm snapshot created: {snapshot_id}")
            return snapshot_id
        finally:
            setup_sandbox.destroy()

    def pause_sandbox(self, task_id: str) -> None:
        """Pause an E2B sandbox (stops billing, preserves state)."""
        sandbox = self.get_sandbox(task_id)
        if sandbox is None:
            raise SandboxCreationError(f"No sandbox for task {task_id}")

        if not hasattr(sandbox, "pause"):
            logger.warning(f"Sandbox for {task_id} does not support pause")
            return

        sandbox.pause()
        with self._lock:
            if task_id in self._sandbox_info:
                self._sandbox_info[task_id].state = SandboxState.PAUSED

    def resume_sandbox(self, task_id: str) -> None:
        """Resume a paused E2B sandbox."""
        sandbox = self.get_sandbox(task_id)
        if sandbox is None:
            raise SandboxCreationError(f"No sandbox for task {task_id}")

        if not hasattr(sandbox, "resume"):
            logger.warning(f"Sandbox for {task_id} does not support resume")
            return

        sandbox.resume()
        with self._lock:
            if task_id in self._sandbox_info:
                self._sandbox_info[task_id].state = SandboxState.RUNNING

    def shutdown(self) -> None:
        """Destroy all sandboxes and prevent new creation."""
        self._shutdown = True
        with self._lock:
            task_ids = list(self._sandboxes.keys())

        for task_id in task_ids:
            try:
                self.destroy_sandbox(task_id)
            except Exception as e:
                logger.warning(f"Error during shutdown of sandbox {task_id}: {e}")

        logger.info(f"SandboxManager shut down, destroyed {len(task_ids)} sandboxes")

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for info in self._sandbox_info.values()
                if info.state == SandboxState.RUNNING
            )
