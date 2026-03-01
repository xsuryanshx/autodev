"""Parallel executor using OpenCode for multi-agent execution."""
import subprocess
import os
import signal
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from core.session_history import SessionHistory
from utils.logger import get_logger


@dataclass
class AgentResult:
    """Result from an agent execution."""
    agent_id: str
    task_id: str
    status: str  # running, completed, failed, cancelled
    output: str
    error: Optional[str] = None
    exit_code: Optional[int] = None


class ParallelExecutor:
    """
    Executes tasks in parallel using OpenCode agents.
    Manages multiple worktrees and agent sessions.
    """
    
    def __init__(
        self,
        base_repo: str,
        max_agents: int = 4,
        session_dir: str = ".autodev/sessions"
    ):
        self.base_repo = Path(base_repo)
        self.max_agents = max_agents
        self.session_history = SessionHistory(session_dir)
        self.logger = get_logger("autodev.executor")
        
        # Active agent processes
        self.active_agents: Dict[str, subprocess.Popen] = {}
        
        # Worktree paths
        self.worktrees: Dict[str, Path] = {}
    
    def create_worktree(self, branch_name: str) -> Path:
        """Create a new worktree for a feature branch."""
        worktree_path = self.base_repo.parent / f"{self.base_repo.name}-{branch_name}"
        
        if worktree_path.exists():
            self.logger.info(f"Worktree already exists: {worktree_path}")
            return worktree_path
        
        # Create worktree
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path), "main"],
            cwd=self.base_repo,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {result.stderr}")
        
        self.worktrees[branch_name] = worktree_path
        self.logger.info(f"Created worktree: {worktree_path}")
        return worktree_path
    
    def spawn_agent(
        self,
        agent_id: str,
        branch: str,
        prompt: str,
        timeout: int = 300
    ) -> Tuple[AgentResult, subprocess.Popen]:
        """
        Spawn an OpenCode agent to work on a branch.
        
        Returns:
            Tuple of (AgentResult, process)
        """
        # Ensure worktree exists
        if branch not in self.worktrees:
            self.create_worktree(branch)
        
        worktree = self.worktrees[branch]
        
        self.logger.info(f"Spawning agent {agent_id} on branch {branch}")
        
        # Build command - use opencode run
        cmd = [
            "opencode",
            "run",
            "--print-logs",
            prompt
        ]
        
        # Start process
        process = subprocess.Popen(
            cmd,
            cwd=str(worktree),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid
        )
        
        # Record in session history
        self.session_history.register_agent(agent_id, "coder", str(worktree))
        
        result = AgentResult(
            agent_id=agent_id,
            task_id=branch,
            status="running",
            output=f"Started in {worktree}",
            exit_code=None
        )
        
        self.active_agents[agent_id] = process
        return result, process
    
    def check_agent(self, agent_id: str) -> Optional[AgentResult]:
        """Check if an agent has completed."""
        if agent_id not in self.active_agents:
            return None
        
        process = self.active_agents[agent_id]
        
        # Check if process is done
        returncode = process.poll()
        
        if returncode is not None:
            stdout, stderr = process.communicate()
            output = stdout + stderr
            
            result = AgentResult(
                agent_id=agent_id,
                task_id="",
                status="completed" if returncode == 0 else "failed",
                output=output,
                exit_code=returncode
            )
            
            del self.active_agents[agent_id]
            return result
        
        return None
    
    def run_parallel(
        self,
        tasks: List[Dict[str, Any]],
        wait: bool = True,
        check_interval: int = 10
    ) -> List[AgentResult]:
        """
        Run multiple tasks in parallel using OpenCode agents.
        
        Args:
            tasks: List of {branch, prompt, task_id}
            wait: Whether to wait for completion
            check_interval: How often to check for completion
            
        Returns:
            List of AgentResults
        """
        results = []
        
        # Start agents up to max parallel
        i = 0
        for task in tasks:
            if i >= self.max_agents:
                break
            
            agent_id = f"agent_{i+1}"
            result, process = self.spawn_agent(
                agent_id=agent_id,
                branch=task["branch"],
                prompt=task["prompt"],
                timeout=task.get("timeout", 300)
            )
            
            # Record start in session history
            self.session_history.agent_start_task(
                agent_id,
                task.get("task_id", task["branch"]),
                task.get("description", "")
            )
            
            results.append(result)
            i += 1
        
        # Wait for completion if requested
        if wait:
            while self.active_agents:
                time.sleep(check_interval)
                
                # Check each agent
                for agent_id in list(self.active_agents.keys()):
                    result = self.check_agent(agent_id)
                    if result:
                        # Update session history
                        self.session_history.agent_complete_task(
                            agent_id,
                            "",
                            success=(result.status == "completed"),
                            message=result.output[:200]
                        )
                        
                        # Replace in results
                        for i, r in enumerate(results):
                            if r.agent_id == agent_id:
                                results[i] = result
                                break
        
        return results
    
    def cleanup_worktrees(self):
        """Clean up all worktrees."""
        for branch, path in self.worktrees.items():
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(path)],
                    capture_output=True
                )
                self.logger.info(f"Removed worktree: {path}")
            except Exception as e:
                self.logger.error(f"Failed to remove worktree {path}: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get execution status."""
        return {
            "active_agents": len(self.active_agents),
            "max_agents": self.max_agents,
            "worktrees": list(self.worktrees.keys()),
            "session": self.session_history.get_status()
        }
