"""Tests for E2BSandboxedTools with mocked E2B SDK.

These tests verify the E2B sandbox wrapper logic without requiring
an actual E2B account or API key.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass


@dataclass
class FakeCommandResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class FakeFiles:
    def __init__(self):
        self._files = {}

    def read(self, path):
        if path in self._files:
            return self._files[path]
        raise Exception(f"No such file: {path}")

    def write(self, path, content):
        self._files[path] = content


class FakeCommands:
    def __init__(self):
        self.history = []

    def run(self, command, cwd=None, timeout=None):
        self.history.append({"command": command, "cwd": cwd, "timeout": timeout})
        if "fail" in command:
            return FakeCommandResult(stderr="command failed", exit_code=1)
        if "echo" in command:
            return FakeCommandResult(stdout="hello\n")
        if "grep" in command:
            return FakeCommandResult(stdout="file.py:1: match")
        if "find" in command:
            return FakeCommandResult(stdout="/home/user/repo/src/app.py\n/home/user/repo/test.py\n")
        if "ls" in command:
            return FakeCommandResult(stdout="requirements.txt\n")
        if "pip install" in command:
            return FakeCommandResult(stdout="Successfully installed deps")
        if "git clone" in command:
            return FakeCommandResult(stdout="Cloning...")
        if "git checkout" in command:
            return FakeCommandResult(stdout="Switched to branch")
        return FakeCommandResult()


class FakeSandbox:
    def __init__(self, template="base", timeout=900, metadata=None, envs=None, api_key=None):
        self.sandbox_id = "sbx-fake-123"
        self.template = template
        self.files = FakeFiles()
        self.commands = FakeCommands()
        self._killed = False
        self._paused = False

    def kill(self):
        self._killed = True

    def pause(self):
        self._paused = True

    def snapshot(self):
        return "snap-fake-456"

    @classmethod
    def connect(cls, sandbox_id, timeout=None):
        instance = cls()
        instance.sandbox_id = sandbox_id
        return instance


@pytest.fixture
def mock_e2b():
    """Patch e2b.Sandbox with our fake."""
    with patch("core.e2b_sandbox.E2BSandbox", FakeSandbox):
        yield FakeSandbox


@pytest.fixture
def e2b_tools(mock_e2b):
    from core.e2b_sandbox import E2BSandboxedTools
    sandbox = FakeSandbox(api_key="test-key")
    return E2BSandboxedTools(
        sandbox=sandbox,
        timeout_seconds=300,
        task_id="test-task",
    )


class TestE2BCreate:
    def test_create_returns_instance(self, mock_e2b):
        from core.e2b_sandbox import E2BSandboxedTools
        with patch.dict("os.environ", {"E2B_API_KEY": "test-key"}):
            tools = E2BSandboxedTools.create(
                task_id="task-1",
                template="base",
                timeout_seconds=300,
                api_key="test-key",
            )
            assert tools.task_id == "task-1"
            assert tools.sandbox_id == "sbx-fake-123"
            assert tools.workspace == "/home/user/repo"

    def test_create_requires_api_key(self, mock_e2b):
        from core.e2b_sandbox import E2BSandboxedTools
        from core.sandbox_backend import SandboxCreationError
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(SandboxCreationError, match="API key"):
                E2BSandboxedTools.create(task_id="task-1", api_key=None)

    def test_from_snapshot(self, mock_e2b):
        from core.e2b_sandbox import E2BSandboxedTools
        with patch.dict("os.environ", {"E2B_API_KEY": "test-key"}):
            tools = E2BSandboxedTools.from_snapshot(
                task_id="task-1",
                snapshot_id="snap-123",
                api_key="test-key",
            )
            assert tools.task_id == "task-1"


class TestE2BReadWrite:
    def test_read_file(self, e2b_tools):
        e2b_tools._sandbox.files._files["/home/user/repo/test.txt"] = "hello world"
        result = e2b_tools.read_file("test.txt")
        assert result["status"] == "success"
        assert result["content"] == "hello world"

    def test_read_file_not_found(self, e2b_tools):
        result = e2b_tools.read_file("nonexistent.txt")
        assert result["status"] == "error"

    def test_read_file_absolute_path(self, e2b_tools):
        e2b_tools._sandbox.files._files["/etc/config"] = "data"
        result = e2b_tools.read_file("/etc/config")
        assert result["status"] == "success"

    def test_write_file(self, e2b_tools):
        result = e2b_tools.write_file("output.py", "print('hi')")
        assert result["status"] == "success"
        assert e2b_tools._sandbox.files._files["/home/user/repo/output.py"] == "print('hi')"

    def test_write_file_nested_path(self, e2b_tools):
        result = e2b_tools.write_file("src/deep/module.py", "code")
        assert result["status"] == "success"
        mkdir_cmds = [c for c in e2b_tools._sandbox.commands.history if "mkdir -p" in c["command"]]
        assert any("/home/user/repo/src/deep" in c["command"] for c in mkdir_cmds)


class TestE2BBash:
    def test_bash_success(self, e2b_tools):
        result = e2b_tools.bash("echo hello")
        assert result["status"] == "success"
        assert "hello" in result["stdout"]

    def test_bash_failure(self, e2b_tools):
        result = e2b_tools.bash("fail now")
        assert result["status"] == "error"
        assert result["exit_code"] == 1

    def test_bash_uses_workspace_as_default_cwd(self, e2b_tools):
        e2b_tools.bash("echo test")
        last_cmd = e2b_tools._sandbox.commands.history[-1]
        assert last_cmd["cwd"] == "/home/user/repo"

    def test_bash_custom_cwd(self, e2b_tools):
        e2b_tools.bash("ls", cwd="/tmp")
        last_cmd = e2b_tools._sandbox.commands.history[-1]
        assert last_cmd["cwd"] == "/tmp"


class TestE2BGlobGrep:
    def test_glob(self, e2b_tools):
        result = e2b_tools.glob("**/*.py")
        assert result["status"] == "success"
        assert len(result["files"]) == 2

    def test_grep(self, e2b_tools):
        result = e2b_tools.grep("match", "src/")
        assert result["status"] == "success"
        assert "match" in result["stdout"]


class TestE2BSetup:
    def test_setup_clones_repo(self, e2b_tools):
        result = e2b_tools.setup(
            repo_url="https://github.com/owner/repo.git",
            branch="feature-branch",
        )
        assert result["status"] == "success"
        commands = [c["command"] for c in e2b_tools._sandbox.commands.history]
        assert any("git clone" in c for c in commands)
        assert any("git checkout" in c for c in commands)

    def test_setup_with_token(self, e2b_tools):
        e2b_tools.setup(
            repo_url="https://github.com/owner/repo.git",
            clone_token="ghp_secret",
        )
        commands = [c["command"] for c in e2b_tools._sandbox.commands.history]
        clone_cmd = [c for c in commands if "git clone" in c][0]
        assert "x-access-token:ghp_secret" in clone_cmd

    def test_setup_installs_deps(self, e2b_tools):
        e2b_tools.setup(repo_url="https://github.com/owner/repo.git")
        commands = [c["command"] for c in e2b_tools._sandbox.commands.history]
        assert any("pip install" in c for c in commands)


class TestE2BLifecycle:
    def test_pause(self, e2b_tools):
        sandbox_id = e2b_tools.pause()
        assert sandbox_id == "sbx-fake-123"
        assert e2b_tools._sandbox._paused

    def test_resume(self, mock_e2b, e2b_tools):
        e2b_tools.resume()
        assert e2b_tools._sandbox.sandbox_id == "sbx-fake-123"

    def test_create_snapshot(self, e2b_tools):
        snap_id = e2b_tools.create_snapshot()
        assert snap_id == "snap-fake-456"

    def test_destroy(self, e2b_tools):
        e2b_tools.destroy()
        assert e2b_tools._sandbox._killed
        assert e2b_tools._destroyed

    def test_destroy_idempotent(self, e2b_tools):
        e2b_tools.destroy()
        e2b_tools.destroy()
        assert e2b_tools._destroyed
