"""Tests for SandboxManager lifecycle management."""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.sandbox_backend import SandboxConfig, SandboxState, SandboxCreationError
from core.sandbox_manager import SandboxManager


class TestSandboxManagerLocal:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()
        self.config = SandboxConfig(
            backend="local",
            local_base_dir=self.tempdir,
            timeout_seconds=60,
        )

    def test_create_local_sandbox(self):
        mgr = SandboxManager(self.config)
        sandbox = mgr.create_sandbox("task-1")

        assert sandbox is not None
        assert Path(sandbox.workspace).exists()
        assert "task_task-1" in sandbox.workspace

    def test_tracks_sandbox_info(self):
        mgr = SandboxManager(self.config)
        mgr.create_sandbox("task-1")

        info = mgr.get_sandbox_info("task-1")
        assert info is not None
        assert info.task_id == "task-1"
        assert info.backend == "local"
        assert info.state == SandboxState.RUNNING

    def test_list_sandboxes(self):
        mgr = SandboxManager(self.config)
        mgr.create_sandbox("task-1")
        mgr.create_sandbox("task-2")

        sandboxes = mgr.list_sandboxes()
        assert len(sandboxes) == 2

    def test_destroy_sandbox(self):
        mgr = SandboxManager(self.config)
        mgr.create_sandbox("task-1")
        mgr.destroy_sandbox("task-1")

        assert mgr.get_sandbox("task-1") is None
        assert mgr.active_count == 0

    def test_active_count(self):
        mgr = SandboxManager(self.config)
        mgr.create_sandbox("task-1")
        mgr.create_sandbox("task-2")
        assert mgr.active_count == 2

        mgr.destroy_sandbox("task-1")
        assert mgr.active_count == 1

    def test_shutdown_destroys_all(self):
        mgr = SandboxManager(self.config)
        mgr.create_sandbox("task-1")
        mgr.create_sandbox("task-2")
        mgr.create_sandbox("task-3")

        mgr.shutdown()
        assert mgr.active_count == 0

    def test_cannot_create_after_shutdown(self):
        mgr = SandboxManager(self.config)
        mgr.shutdown()

        with pytest.raises(SandboxCreationError, match="shut down"):
            mgr.create_sandbox("task-1")

    def test_setup_local_sandbox(self):
        mgr = SandboxManager(self.config)
        mgr.create_sandbox("task-1")

        result = mgr.setup_sandbox("task-1")
        assert result["status"] == "success"

    def test_setup_nonexistent_sandbox(self):
        mgr = SandboxManager(self.config)
        result = mgr.setup_sandbox("no-such-task")
        assert result["status"] == "error"


class TestSandboxManagerE2B:
    """Tests for E2B backend with mocked SDK."""

    def setup_method(self):
        self.config = SandboxConfig(
            backend="e2b",
            e2b_template="base",
            e2b_api_key="test-key",
            timeout_seconds=60,
        )

    @patch("core.sandbox_manager.SandboxManager._create_e2b_sandbox")
    def test_create_e2b_sandbox(self, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.workspace = "/home/user/repo"
        mock_sandbox.sandbox_id = "sbx-123"
        mock_create.return_value = mock_sandbox

        mgr = SandboxManager(self.config)
        sandbox = mgr.create_sandbox("task-1")

        assert sandbox is mock_sandbox
        mock_create.assert_called_once()

    @patch("core.sandbox_manager.SandboxManager._create_e2b_sandbox")
    def test_e2b_sandbox_tracked(self, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.workspace = "/home/user/repo"
        mock_sandbox.sandbox_id = "sbx-123"
        mock_create.return_value = mock_sandbox

        mgr = SandboxManager(self.config)
        mgr.create_sandbox("task-1")

        info = mgr.get_sandbox_info("task-1")
        assert info is not None
        assert info.backend == "e2b"

    @patch("core.sandbox_manager.SandboxManager._create_e2b_sandbox")
    def test_e2b_shutdown_destroys(self, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.workspace = "/home/user/repo"
        mock_sandbox.sandbox_id = "sbx-123"
        mock_create.return_value = mock_sandbox

        mgr = SandboxManager(self.config)
        mgr.create_sandbox("task-1")
        mgr.shutdown()

        mock_sandbox.destroy.assert_called_once()


class TestSandboxConfig:
    def test_from_dict(self):
        config = SandboxConfig.from_dict({
            "backend": "e2b",
            "e2b_template": "custom-template",
            "e2b_api_key": "key-123",
            "timeout_seconds": 1800,
        })
        assert config.backend == "e2b"
        assert config.e2b_template == "custom-template"
        assert config.timeout_seconds == 1800

    def test_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "sandbox": {
                    "backend": "e2b",
                    "e2b_template": "autodev-coder",
                    "timeout_seconds": 600,
                }
            }, f)
            f.flush()

            config = SandboxConfig.from_file(f.name)
            assert config.backend == "e2b"
            assert config.e2b_template == "autodev-coder"

    def test_from_missing_file_uses_defaults(self):
        config = SandboxConfig.from_file("/nonexistent/config.json")
        assert config.backend == "local"
        assert config.timeout_seconds == 900

    def test_to_dict(self):
        config = SandboxConfig(backend="e2b", e2b_template="base")
        d = config.to_dict()
        assert d["backend"] == "e2b"
        assert "e2b_api_key" not in d


class TestSandboxManagerWarmSnapshot:
    @patch("core.sandbox_manager.SandboxManager._create_e2b_sandbox")
    def test_warm_snapshot_not_supported_for_local(self, _):
        config = SandboxConfig(backend="local")
        mgr = SandboxManager(config)
        with pytest.raises(SandboxCreationError, match="E2B"):
            mgr.create_warm_snapshot(repo_url="https://github.com/owner/repo.git")

    @patch("core.e2b_sandbox.E2BSandboxedTools")
    def test_warm_snapshot_creates_and_stores_id(self, MockE2BTools):
        mock_instance = MagicMock()
        mock_instance.setup.return_value = {"status": "success"}
        mock_instance.create_snapshot.return_value = "snap-warm-789"
        MockE2BTools.create.return_value = mock_instance

        config = SandboxConfig(backend="e2b", e2b_api_key="test-key")
        mgr = SandboxManager(config)
        snap_id = mgr.create_warm_snapshot(
            repo_url="https://github.com/owner/repo.git",
            branch="main",
        )

        assert snap_id == "snap-warm-789"
        assert mgr._snapshot_id == "snap-warm-789"
        mock_instance.destroy.assert_called_once()
