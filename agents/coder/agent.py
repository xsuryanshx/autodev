"""Coder Agent - implements subtasks using coding tools."""
import os
import subprocess
from typing import Dict, Any, Optional, List
from utils.logger import get_logger


class CoderAgent:
    """
    Coder Agent responsibilities:
    - Implement subtasks sequentially
    - Write code
    - Write comprehensive tests
    - Run tests and fix failures
    - Report status back to initiator
    
    Skills:
    - OpenCode (primary)
    - Claude Code (fallback)
    - Git operations
    - Test frameworks
    """
    
    OPENCODE_PATH = "opencode"
    
    def __init__(self, agent_id: str, config: Optional[Dict[str, Any]] = None):
        self.agent_id = agent_id
        self.config = config or {}
        self.logger = get_logger(f"autodev.coder.{agent_id}")
        self.github_client = None
        self.current_subtask = None
    
    def initialize(self, github_client):
        """Initialize with dependencies."""
        self.github_client = github_client
        self.logger.info(f"Coder Agent {self.agent_id} initialized")
    
    def execute_subtask(self, subtask: Dict[str, Any], repo_path: str) -> Dict[str, Any]:
        """
        Execute a single subtask using OpenCode.
        
        Returns:
            Dict with status, output, and any error info
        """
        self.current_subtask = subtask
        subtask_id = subtask.get("id")
        description = subtask.get("description", "")
        
        self.logger.info(f"Executing subtask {subtask_id}: {description}")
        
        # Build prompt for OpenCode
        prompt = self._build_prompt(subtask)
        
        # Execute using OpenCode
        result = self._run_opencode(prompt, repo_path)
        
        self.logger.info(f"Subtask {subtask_id} result: {result['status']}")
        return result
    
    def _build_prompt(self, subtask: Dict[str, Any]) -> str:
        """Build the prompt for the coding agent."""
        description = subtask.get("description", "")
        file_path = subtask.get("file", "")
        
        prompt = description
        
        # Add file-specific instructions
        if file_path:
            if "test" in file_path.lower():
                prompt += f"\nWrite comprehensive unit tests in {file_path}."
            else:
                prompt += f"\nImplement the code in {file_path}."
        
        prompt += "\nCommit your changes with a descriptive message."
        
        return prompt
    
    def _run_opencode(self, prompt: str, repo_path: str, timeout: int = 300) -> Dict[str, Any]:
        """
        Run OpenCode to execute the task.
        
        Args:
            prompt: Task description
            repo_path: Path to the repository
            timeout: Timeout in seconds
            
        Returns:
            Dict with status, output, error
        """
        self.logger.info(f"Running OpenCode in {repo_path}")
        
        try:
            # Use opencode run with the prompt
            cmd = [
                self.OPENCODE_PATH,
                "run",
                "--print-logs",  # Enable logging output
                prompt
            ]
            
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            # Check if it succeeded
            if result.returncode == 0:
                return {
                    "subtask_id": self.current_subtask.get("id") if self.current_subtask else "unknown",
                    "status": "completed",
                    "output": result.stdout + result.stderr,
                    "error": None
                }
            else:
                return {
                    "subtask_id": self.current_subtask.get("id") if self.current_subtask else "unknown",
                    "status": "failed",
                    "output": result.stdout + result.stderr,
                    "error": f"Exit code: {result.returncode}"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "subtask_id": self.current_subtask.get("id") if self.current_subtask else "unknown",
                "status": "failed",
                "output": "",
                "error": "Timeout"
            }
        except FileNotFoundError:
            return {
                "subtask_id": self.current_subtask.get("id") if self.current_subtask else "unknown",
                "status": "failed",
                "output": "",
                "error": "OpenCode not found"
            }
        except Exception as e:
            return {
                "subtask_id": self.current_subtask.get("id") if self.current_subtask else "unknown",
                "status": "failed",
                "output": "",
                "error": str(e)
            }
    
    def write_code(self, file_path: str, content: str, branch: str) -> bool:
        """Write code to a file in the repository."""
        try:
            self.logger.info(f"Writing code to {file_path} on branch {branch}")
            
            # Check if file exists to get SHA for update
            sha = None
            try:
                existing = self.github_client.get_file_content(file_path, ref=branch)
            except:
                pass
            
            # Create or update file
            self.github_client.create_or_update_file(
                path=file_path,
                content=content,
                message=f"Update {file_path}",
                branch=branch,
                sha=sha
            )
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to write code: {e}")
            return False
    
    def write_tests(self, test_file: str, test_content: str, branch: str) -> bool:
        """Write tests for implemented code."""
        return self.write_code(test_file, test_content, branch)
    
    def run_tests(self, repo_path: str, test_command: Optional[str] = None) -> Dict[str, Any]:
        """Run tests and return results."""
        cmd = test_command or self._detect_test_command(repo_path)
        
        if not cmd:
            return {
                "passed": False,
                "output": "No test command detected",
                "failed_count": 0
            }
        
        self.logger.info(f"Running tests: {cmd}")
        
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.config.get("agents", {}).get("timeout_per_subtask", 300)
            )
            
            return {
                "passed": result.returncode == 0,
                "output": result.stdout + result.stderr,
                "failed_count": self._parse_test_failures(result.stdout + result.stderr),
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "output": "Test execution timed out",
                "failed_count": 0
            }
        except Exception as e:
            return {
                "passed": False,
                "output": str(e),
                "failed_count": 0
            }
    
    def _detect_test_command(self, repo_path: str) -> Optional[str]:
        """Detect the appropriate test command based on project files."""
        if os.path.exists(os.path.join(repo_path, "package.json")):
            return "npm test"
        elif os.path.exists(os.path.join(repo_path, "pyproject.toml")):
            return "pytest"
        elif os.path.exists(os.path.join(repo_path, "requirements.txt")):
            return "pytest"
        elif os.path.exists(os.path.join(repo_path, "Cargo.toml")):
            return "cargo test"
        return None
    
    def _parse_test_failures(self, output: str) -> int:
        """Parse test output to extract failure count."""
        import re
        
        # Common patterns: "5 failed", "Failures: 3", "FAILED (failures=2)"
        patterns = [
            r"(\d+)\s+failed",
            r"failures?[:\s]+(\d+)",
            r"FAILED.*failures?=(\d+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return 0
    
    def fix_errors(self, error_output: str) -> bool:
        """Attempt to fix errors based on test output."""
        # Use OpenCode to analyze and fix
        if not self.current_subtask:
            return False
        
        prompt = f"Fix the following errors in the code:\n{error_output}"
        result = self._run_opencode(prompt, os.path.dirname(self.current_subtask.get("file", ".")))
        
        return result["status"] == "completed"
