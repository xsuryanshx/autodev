"""Sandboxed tool implementations for subagent execution."""
import subprocess
import os
import glob as glob_module
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


class SandboxError(Exception):
    """Tool execution violated workspace boundary."""
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
        return {
            "status": self.status,
            **{k: v for k, v in self.__dict__.items() if v is not None}
        }


class SandboxedTools:
    def __init__(self, workspace: str, timeout_seconds: int = 300):
        self.workspace = Path(workspace).resolve()
        self.timeout_seconds = timeout_seconds

    def _check_path(self, path: str) -> Path:
        # Handle absolute paths (starting with /) - resolve directly
        if os.path.isabs(path):
            resolved = Path(path).resolve()
        else:
            # Relative path - resolve relative to workspace
            resolved = (self.workspace / path).resolve()
        if not str(resolved).startswith(str(self.workspace)):
            raise SandboxError(f"Access denied: {path} is outside workspace {self.workspace}")
        return resolved

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
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd or str(self.workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
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
            if pattern.startswith("/") and ".." in pattern:
                return ToolResult(status="error", message="Absolute paths not allowed").to_dict()
            matches = list(self.workspace.glob(pattern))
            files = [str(m) for m in matches if m.is_file()]
            return ToolResult(status="success", files=files).to_dict()
        except Exception as e:
            return ToolResult(status="error", message=str(e)).to_dict()

    def grep(self, pattern: str, path: Optional[str] = None) -> Dict[str, Any]:
        try:
            import re
            search_dir = Path(path) if path else self.workspace
            self._check_path(str(search_dir))
            results = []
            for match in search_dir.rglob("*"):
                if not match.is_file():
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
