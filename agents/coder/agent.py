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
    - Claude Code / OpenCode
    - Git operations
    - Test frameworks
    """
    
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
        Execute a single subtask.
        
        Returns:
            Dict with status, output, and any error info
        """
        self.current_subtask = subtask
        subtask_id = subtask.get("id")
        description = subtask.get("description", "")
        
        self.logger.info(f"Executing subtask {subtask_id}: {description}")
        
        # TODO: Connect to Claude Code / OpenCode for actual implementation
        # For Phase 1, this is a stub
        
        result = {
            "subtask_id": subtask_id,
            "status": "completed",
            "output": f"Stub: Would execute '{description}'",
            "error": None
        }
        
        self.logger.info(f"Subtask {subtask_id} {result['status']}")
        return result
    
    def write_code(self, file_path: str, content: str, branch: str) -> bool:
        """Write code to a file in the repository."""
        try:
            self.logger.info(f"Writing code to {file_path} on branch {branch}")
            
            # Check if file exists to get SHA for update
            sha = None
            try:
                existing = self.github_client.get_file_content(file_path, ref=branch)
                # Would need to get SHA from response
            except:
                pass
            
            # Create or update file
            self.github_client.create_or_update_file(
                path=file_path,
                content=content,
                message=f"Update {file_path}",
                branch=branch
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
        # TODO: Use Claude Code to analyze errors and fix
        self.logger.info("Attempting to fix errors...")
        return False
