"""Task queue for managing subtask execution."""
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from utils.logger import get_logger


@dataclass
class TaskResult:
    """Result of a task execution."""
    subtask_id: str
    status: str  # success, failed, running
    output: str
    error: Optional[str] = None
    session_id: Optional[str] = None


class TaskQueue:
    """Manages task queue and parallel execution."""
    
    def __init__(self, max_parallel: int = 4):
        self.max_parallel = max_parallel
        self.running_tasks: Dict[str, TaskResult] = {}
        self.completed_tasks: Dict[str, TaskResult] = {}
        self.logger = get_logger("autodev.queue")
    
    def can_run_parallel(self) -> bool:
        """Check if we can start another task."""
        return len(self.running_tasks) < self.max_parallel
    
    def start_task(
        self,
        subtask_id: str,
        worktree_path: str,
        command: str,
        session_id: str
    ) -> TaskResult:
        """Start a task in a worktree."""
        result = TaskResult(
            subtask_id=subtask_id,
            status="running",
            output=f"Started in {worktree_path}",
            session_id=session_id
        )
        self.running_tasks[subtask_id] = result
        self.logger.info(f"Started task {subtask_id} in {worktree_path}")
        return result
    
    def complete_task(self, subtask_id: str, status: str, output: str, error: Optional[str] = None):
        """Mark a task as completed."""
        if subtask_id in self.running_tasks:
            result = self.running_tasks.pop(subtask_id)
            result.status = status
            result.output = output
            result.error = error
            self.completed_tasks[subtask_id] = result
            self.logger.info(f"Task {subtask_id} {status}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get queue status."""
        return {
            "running": len(self.running_tasks),
            "completed": len(self.completed_tasks),
            "max_parallel": self.max_parallel,
            "tasks": {
                "running": list(self.running_tasks.keys()),
                "completed": list(self.completed_tasks.keys())
            }
        }


class WorktreeManager:
    """Manages git worktrees for parallel execution."""
    
    def __init__(self, base_repo: str):
        self.base_repo = Path(base_repo)
        self.worktrees: Dict[str, Path] = {}
        self.logger = get_logger("autodev.worktree")
    
    def create_worktree(self, branch_name: str, path: Optional[str] = None) -> Path:
        """Create a new worktree for a feature branch."""
        if path:
            worktree_path = Path(path)
        else:
            worktree_path = self.base_repo.parent / f"{self.base_repo.name}-{branch_name}"
        
        if worktree_path.exists():
            self.logger.warning(f"Worktree already exists: {worktree_path}")
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
    
    def get_worktree(self, branch_name: str) -> Optional[Path]:
        """Get worktree path for a branch."""
        return self.worktrees.get(branch_name)
    
    def cleanup_worktree(self, branch_name: str):
        """Remove a worktree after merging."""
        if branch_name not in self.worktrees:
            return
        
        worktree_path = self.worktrees[branch_name]
        
        # Remove worktree
        result = subprocess.run(
            ["git", "worktree", "remove", str(worktree_path)],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            del self.worktrees[branch_name]
            self.logger.info(f"Removed worktree: {worktree_path}")
    
    def merge_branch(self, branch_name: str, target: str = "main") -> bool:
        """Merge a branch into target."""
        result = subprocess.run(
            ["git", "merge", branch_name, "--no-edit"],
            cwd=self.base_repo,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            self.logger.error(f"Merge failed: {result.stderr}")
            return False
        
        self.logger.info(f"Merged {branch_name} into {target}")
        return True
