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

    def test_glob_enforces_workspace(self):
        result = self.tools.glob("/etc/**/*.txt")
        assert result["status"] == "error"
