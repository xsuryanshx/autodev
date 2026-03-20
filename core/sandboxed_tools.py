"""Local sandboxed tool implementations for subagent execution.

Provides path-checked file operations and a hardened bash executor.
This is the LOCAL backend — it runs on the host but restricts access
to the task workspace directory. For true isolation, use E2B backend.
"""
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.sandbox_backend import SandboxError, ToolResult

_SAFE_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
    "TERM", "TMPDIR", "TZ",
    "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONHOME",
    "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
    "NODE_PATH", "NODE_ENV",
    "GOPATH", "GOROOT",
})

_BLOCKED_COMMAND_PATTERNS = [
    re.compile(r"\brm\s+-rf\s+/\s*$"),
    re.compile(r"\brm\s+-rf\s+/\w"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+.*of=/dev/"),
    re.compile(r"\b:(){ :|:& };:"),
    re.compile(r"\bchmod\s+.*\s+/"),
    re.compile(r"\bchown\s+.*\s+/"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bsu\s+"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\bsystemctl\b"),
    re.compile(r"\bnc\s+-[el]"),
    re.compile(r"\bpython.*-m\s+http\.server\b"),
]


class SandboxedTools:
    """Local sandbox with path-checking and hardened bash.

    Security model:
    - File ops (read/write/glob/grep): restricted to workspace via _check_path
    - Bash: cwd locked to workspace, sanitized env, command blocklist
    - NOT a real sandbox: bash can still access host filesystem via absolute paths

    For true isolation, use E2BSandboxedTools instead.
    """

    def __init__(
        self,
        workspace: str,
        timeout_seconds: int = 300,
        sanitize_env: bool = True,
        allowed_env_keys: Optional[frozenset] = None,
    ):
        self._workspace = Path(workspace).resolve()
        self.timeout_seconds = timeout_seconds
        self._sanitize_env = sanitize_env
        self._allowed_env_keys = allowed_env_keys or _SAFE_ENV_KEYS
        self._destroyed = False

    @property
    def workspace(self) -> str:
        return str(self._workspace)

    def _check_path(self, path: str) -> Path:
        if os.path.isabs(path):
            resolved = Path(path).resolve()
        else:
            resolved = (self._workspace / path).resolve()
        if not str(resolved).startswith(str(self._workspace)):
            raise SandboxError(
                f"Access denied: {path} is outside workspace {self._workspace}"
            )
        return resolved

    def _make_safe_env(self) -> Optional[Dict[str, str]]:
        """Build a sanitized environment dict that strips secrets."""
        if not self._sanitize_env:
            return None
        safe = {}
        for key in self._allowed_env_keys:
            val = os.environ.get(key)
            if val is not None:
                safe[key] = val
        safe["HOME"] = str(self._workspace)
        safe["TMPDIR"] = str(self._workspace / ".tmp")
        return safe

    def _check_command(self, command: str) -> Optional[str]:
        """Check command against blocklist. Returns rejection reason or None."""
        for pattern in _BLOCKED_COMMAND_PATTERNS:
            if pattern.search(command):
                return f"Blocked command pattern: {pattern.pattern}"
        return None

    def read_file(self, path: str) -> Dict[str, Any]:
        try:
            resolved = self._check_path(path)
            with open(resolved, "r", encoding="utf-8") as f:
                content = f.read()
            return ToolResult(status="success", content=content).to_dict()
        except FileNotFoundError:
            return ToolResult(status="error", message=f"File not found: {path}").to_dict()
        except SandboxError as e:
            return ToolResult(status="error", message=str(e)).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        try:
            resolved = self._check_path(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(status="success", message=f"Written to {path}").to_dict()
        except SandboxError as e:
            return ToolResult(status="error", message=str(e)).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def bash(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        try:
            rejection = self._check_command(command)
            if rejection:
                return ToolResult(
                    status="error",
                    message=f"Command blocked: {rejection}",
                ).to_dict()

            if cwd is not None:
                resolved_cwd = Path(cwd).resolve()
                if not str(resolved_cwd).startswith(str(self._workspace)):
                    return ToolResult(
                        status="error",
                        message=f"cwd {cwd} is outside workspace {self._workspace}",
                    ).to_dict()
                run_cwd = str(resolved_cwd)
            else:
                run_cwd = str(self._workspace)

            env = self._make_safe_env()

            result = subprocess.run(
                command,
                shell=True,
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
            )
            if result.returncode == 0:
                return ToolResult(
                    status="success",
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                ).to_dict()
            else:
                return ToolResult(
                    status="error",
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                    message=f"Command exited with code {result.returncode}",
                ).to_dict()
        except subprocess.TimeoutExpired:
            return ToolResult(
                status="error",
                message=f"Command timed out after {self.timeout_seconds}s",
            ).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def glob(self, pattern: str) -> Dict[str, Any]:
        try:
            if pattern.startswith("/"):
                return ToolResult(
                    status="error", message="Absolute paths not allowed in glob"
                ).to_dict()
            matches = list(self._workspace.glob(pattern))
            workspace_str = str(self._workspace)
            files = [
                str(m) for m in matches
                if m.is_file() and str(m.resolve()).startswith(workspace_str)
            ]
            return ToolResult(status="success", files=files).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def grep(self, pattern: str, path: Optional[str] = None) -> Dict[str, Any]:
        try:
            if path:
                search_dir = self._check_path(path)
            else:
                search_dir = self._workspace
            workspace_str = str(self._workspace)
            results = []
            for match in search_dir.rglob("*"):
                if not match.is_file():
                    continue
                if not str(match.resolve()).startswith(workspace_str):
                    continue
                try:
                    text = match.read_text(encoding="utf-8")
                    for i, line in enumerate(text.splitlines(), 1):
                        if re.search(pattern, line):
                            results.append(f"{match}:{i}: {line.rstrip()}")
                except (UnicodeDecodeError, PermissionError):
                    continue
            return ToolResult(
                status="success",
                stdout="\n".join(results),
                files=[str(search_dir)],
            ).to_dict()
        except SandboxError as e:
            return ToolResult(status="error", message=str(e)).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def setup(
        self,
        repo_url: Optional[str] = None,
        branch: Optional[str] = None,
        clone_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bootstrap local workspace: clone repo and checkout branch."""
        if repo_url:
            if clone_token:
                authed_url = repo_url.replace(
                    "https://", f"https://x-access-token:{clone_token}@"
                )
            else:
                authed_url = repo_url

            clone_result = subprocess.run(
                f"git clone {authed_url} .",
                shell=True,
                cwd=str(self._workspace),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if clone_result.returncode != 0:
                return ToolResult(
                    status="error",
                    message=f"Git clone failed: {clone_result.stderr}",
                ).to_dict()

        if branch:
            subprocess.run(
                f"git checkout -b {branch}",
                shell=True,
                cwd=str(self._workspace),
                capture_output=True,
                text=True,
                timeout=30,
            )

        return ToolResult(
            status="success", message="Local workspace setup complete"
        ).to_dict()

    def destroy(self) -> None:
        """Mark as destroyed. Does not delete workspace files (caller's responsibility)."""
        self._destroyed = True
