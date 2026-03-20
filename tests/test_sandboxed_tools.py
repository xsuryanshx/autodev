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
        result = self.tools.read_file("nonexistent/file.txt")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_read_file_enforces_workspace(self):
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

    def test_bash_rejects_cwd_outside_workspace(self):
        result = self.tools.bash("pwd", cwd="/tmp")
        assert result["status"] == "error"
        assert "outside workspace" in result["message"]

    def test_bash_allows_cwd_inside_workspace(self):
        subdir = os.path.join(self.tempdir, "subdir")
        os.makedirs(subdir)
        result = self.tools.bash("pwd", cwd=subdir)
        assert result["status"] == "success"
        assert "subdir" in result["stdout"]


class TestSandboxedToolsGlob:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()
        self.tools = SandboxedTools(workspace=self.tempdir)
        Path(self.tempdir, "src").mkdir(parents=True, exist_ok=True)
        Path(self.tempdir, "src", "app.py").touch()
        Path(self.tempdir, "src", "util.py").touch()
        Path(self.tempdir, "tests").mkdir(parents=True, exist_ok=True)
        Path(self.tempdir, "tests", "test_app.py").touch()

    def test_glob_finds_files(self):
        result = self.tools.glob("**/*.py")
        assert result["status"] == "success"
        files = result["files"]
        assert any("app.py" in f for f in files)

    def test_glob_rejects_absolute_paths(self):
        result = self.tools.glob("/etc/**/*.conf")
        assert result["status"] == "error"
        assert "Absolute" in result["message"]


class TestEnvSanitization:
    """Tests for environment variable sanitization in bash()."""

    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def test_sanitized_env_strips_secrets(self):
        tools = SandboxedTools(workspace=self.tempdir, sanitize_env=True)
        os.environ["SUPER_SECRET_TOKEN"] = "should-not-leak"
        try:
            result = tools.bash("env")
            assert result["status"] == "success"
            assert "SUPER_SECRET_TOKEN" not in result["stdout"]
        finally:
            del os.environ["SUPER_SECRET_TOKEN"]

    def test_sanitized_env_keeps_path(self):
        tools = SandboxedTools(workspace=self.tempdir, sanitize_env=True)
        result = tools.bash("echo $PATH")
        assert result["status"] == "success"
        assert result["stdout"].strip() != ""

    def test_unsanitized_env_passes_everything(self):
        tools = SandboxedTools(workspace=self.tempdir, sanitize_env=False)
        os.environ["TEST_MARKER_XYZ"] = "visible"
        try:
            result = tools.bash("echo $TEST_MARKER_XYZ")
            assert result["status"] == "success"
            assert "visible" in result["stdout"]
        finally:
            del os.environ["TEST_MARKER_XYZ"]

    def test_github_token_not_leaked(self):
        tools = SandboxedTools(workspace=self.tempdir, sanitize_env=True)
        os.environ["GITHUB_TOKEN"] = "ghp_secret123"
        try:
            result = tools.bash("env")
            assert "ghp_secret123" not in result["stdout"]
        finally:
            del os.environ["GITHUB_TOKEN"]


class TestCommandBlocking:
    """Tests for dangerous command blocking in bash()."""

    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()
        self.tools = SandboxedTools(workspace=self.tempdir)

    def test_blocks_rm_rf_root(self):
        result = self.tools.bash("rm -rf /")
        assert result["status"] == "error"
        assert "blocked" in result["message"].lower()

    def test_blocks_sudo(self):
        result = self.tools.bash("sudo apt-get install something")
        assert result["status"] == "error"
        assert "blocked" in result["message"].lower()

    def test_blocks_shutdown(self):
        result = self.tools.bash("shutdown -h now")
        assert result["status"] == "error"
        assert "blocked" in result["message"].lower()

    def test_blocks_reboot(self):
        result = self.tools.bash("reboot")
        assert result["status"] == "error"
        assert "blocked" in result["message"].lower()

    def test_blocks_mkfs(self):
        result = self.tools.bash("mkfs.ext4 /dev/sda1")
        assert result["status"] == "error"
        assert "blocked" in result["message"].lower()

    def test_allows_normal_commands(self):
        result = self.tools.bash("echo 'safe command'")
        assert result["status"] == "success"

    def test_allows_rm_within_workspace(self):
        test_file = Path(self.tempdir) / "deleteme.txt"
        test_file.write_text("temp")
        result = self.tools.bash(f"rm {test_file}")
        assert result["status"] == "success"

    def test_allows_python(self):
        result = self.tools.bash("python3 -c 'print(42)'")
        assert result["status"] == "success"
        assert "42" in result["stdout"]


class TestWorkspaceProperty:
    def test_workspace_returns_string(self):
        tempdir = tempfile.mkdtemp()
        tools = SandboxedTools(workspace=tempdir)
        assert isinstance(tools.workspace, str)
        assert tools.workspace == str(Path(tempdir).resolve())

    def test_setup_returns_success(self):
        tempdir = tempfile.mkdtemp()
        tools = SandboxedTools(workspace=tempdir)
        result = tools.setup()
        assert result["status"] == "success"

    def test_destroy_marks_destroyed(self):
        tempdir = tempfile.mkdtemp()
        tools = SandboxedTools(workspace=tempdir)
        tools.destroy()
        assert tools._destroyed
