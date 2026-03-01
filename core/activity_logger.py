"""Activity Logger - tracks all AutoDev actions with full observability."""
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid


class EventType(Enum):
    """Types of events to track."""
    # Session events
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    
    # Issue events
    ISSUE_FETCHED = "issue_fetched"
    ISSUE_PARSED = "issue_parsed"
    
    # Task events
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRY = "task_retry"
    
    # Agent events
    AGENT_SPAWNED = "agent_spawned"
    AGENT_ASSIGNED = "agent_assigned"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    
    # LLM events
    LLM_CALL_START = "llm_call_start"
    LLM_CALL_END = "llm_call_end"
    LLM_TOKEN_USAGE = "llm_token_usage"
    
    # Git events
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    GIT_PR_CREATED = "git_pr_created"
    GIT_PR_MERGED = "git_pr_merged"
    GIT_WORKTREE_CREATED = "git_worktree_created"
    GIT_WORKTREE_REMOVED = "git_worktree_removed"
    
    # Code events
    CODE_WRITTEN = "code_written"
    TEST_WRITTEN = "test_written"
    FILE_MODIFIED = "file_modified"
    
    # Error events
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Event:
    """Single event in the activity log."""
    id: str
    timestamp: str
    event_type: str
    repo: str
    session_id: str
    
    # Task/Agent info
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    
    # Details
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # LLM specifics
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    
    # Git specifics
    commit_sha: Optional[str] = None
    branch: Optional[str] = None
    pr_number: Optional[int] = None
    
    # Error info
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None


@dataclass
class Trajectory:
    """Complete trajectory of a session."""
    session_id: str
    repo: str
    started_at: str
    ended_at: Optional[str]
    issue_number: Optional[int]
    issue_title: str
    
    # Summary stats
    total_events: int = 0
    tasks_created: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    llm_calls: int = 0
    tokens_used: int = 0
    commits: int = 0
    
    # Events
    events: List[Dict] = field(default_factory=list)
    
    # Final status
    status: str = "running"  # running, completed, failed


class ActivityLogger:
    """
    Comprehensive activity logger for AutoDev.
    
    Tracks:
    - All LLM calls with token usage
    - Task creation/completion/failure
    - Agent spawn/complete
    - Git operations
    - Code changes
    - Errors and warnings
    
    Provides:
    - Real-time trajectory tracking
    - Full observability
    - Debugging capabilities
    """
    
    def __init__(self, repo: str, log_dir: str = ".autodev/logs"):
        self.repo = repo
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate session ID
        self.session_id = f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Current trajectory
        self.trajectory = Trajectory(
            session_id=self.session_id,
            repo=repo,
            started_at=datetime.utcnow().isoformat() + "Z",
            ended_at=None,
            issue_number=None,
            issue_title=""
        )
        
        # Event counter
        self.event_count = 0
        
        # Current task/agent context
        self.current_task_id: Optional[str] = None
        self.current_agent_id: Optional[str] = None
        self.current_issue: Optional[int] = None
        
        # File handles
        self.events_file = open(self.log_dir / f"events_{self.session_id}.jsonl", "w")
        self.trajectory_file = open(self.log_dir / f"trajectory_{self.session_id}.json", "w")
    
    def _create_event(
        self,
        event_type: EventType,
        description: str,
        **kwargs
    ) -> Event:
        """Create a new event."""
        self.event_count += 1
        
        # Build event data
        event_data = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type.value,
            "repo": self.repo,
            "session_id": self.session_id,
            "task_id": self.current_task_id,
            "agent_id": self.current_agent_id,
            "description": description,
        }
        
        # Add any additional metadata
        event_data.update(kwargs)
        
        event = Event(**event_data)
        
        # Write to events file immediately
        self.events_file.write(json.dumps(asdict(event)) + "\n")
        self.events_file.flush()
        
        # Add to trajectory
        self.trajectory.events.append(asdict(event))
        self.trajectory.total_events = self.event_count
        
        # Update summary stats
        self._update_stats(event_type)
        
        # Save trajectory periodically
        if self.event_count % 10 == 0:
            self._save_trajectory()
        
        return event
    
    def _update_stats(self, event_type: EventType):
        """Update trajectory statistics."""
        if event_type == EventType.TASK_CREATED:
            self.trajectory.tasks_created += 1
        elif event_type == EventType.TASK_COMPLETED:
            self.trajectory.tasks_completed += 1
        elif event_type == EventType.TASK_FAILED:
            self.trajectory.tasks_failed += 1
        elif event_type == EventType.LLM_CALL_END:
            self.trajectory.llm_calls += 1
        elif event_type == EventType.GIT_COMMIT:
            self.trajectory.commits += 1
    
    def _save_trajectory(self):
        """Save current trajectory to file."""
        self.trajectory_file.seek(0)
        self.trajectory_file.write(json.dumps(asdict(self.trajectory), indent=2))
        self.trajectory_file.flush()
    
    # ============== Session Events ==============
    
    def session_start(self, issue_number: int, issue_title: str):
        """Log session start."""
        self.current_issue = issue_number
        self.trajectory.issue_number = issue_number
        self.trajectory.issue_title = issue_title
        
        return self._create_event(
            EventType.SESSION_START,
            f"Started session for issue #{issue_number}: {issue_title}",
            metadata={"issue_number": issue_number, "issue_title": issue_title}
        )
    
    def session_end(self, status: str = "completed"):
        """Log session end."""
        self.trajectory.ended_at = datetime.utcnow().isoformat() + "Z"
        self.trajectory.status = status
        self._save_trajectory()
        
        return self._create_event(
            EventType.SESSION_END,
            f"Session ended: {status}",
            metadata={"status": status, "total_events": self.event_count}
        )
    
    # ============== Issue Events ==============
    
    def issue_fetched(self, issue_number: int, title: str, labels: List[str]):
        """Log issue fetched from GitHub."""
        return self._create_event(
            EventType.ISSUE_FETCHED,
            f"Fetched issue #{issue_number}: {title}",
            metadata={"issue_number": issue_number, "title": title, "labels": labels}
        )
    
    def issue_parsed(self, issue_number: int, features: int, subtasks: int):
        """Log issue parsed into features/subtasks."""
        return self._create_event(
            EventType.ISSUE_PARSED,
            f"Parsed issue into {features} features, {subtasks} subtasks",
            metadata={"features": features, "subtasks": subtasks}
        )
    
    # ============== Task Events ==============
    
    def task_created(self, task_id: str, description: str, feature: str):
        """Log task created."""
        old_task = self.current_task_id
        self.current_task_id = task_id
        
        event = self._create_event(
            EventType.TASK_CREATED,
            f"Created task {task_id}: {description}",
            metadata={"task_id": task_id, "description": description, "feature": feature}
        )
        
        self.current_task_id = old_task
        return event
    
    def task_started(self, task_id: str, agent_id: str):
        """Log task started by agent."""
        self.current_task_id = task_id
        self.current_agent_id = agent_id
        
        return self._create_event(
            EventType.TASK_STARTED,
            f"Task {task_id} started by {agent_id}",
            task_id=task_id,
            agent_id=agent_id,
            metadata={"task_id": task_id, "agent_id": agent_id}
        )
    
    def task_completed(self, task_id: str, duration_seconds: float):
        """Log task completed."""
        return self._create_event(
            EventType.TASK_COMPLETED,
            f"Task {task_id} completed in {duration_seconds:.1f}s",
            task_id=task_id,
            metadata={"task_id": task_id, "duration_seconds": duration_seconds}
        )
    
    def task_failed(self, task_id: str, error: str, attempts: int):
        """Log task failed."""
        return self._create_event(
            EventType.TASK_FAILED,
            f"Task {task_id} failed: {error}",
            task_id=task_id,
            error_message=error,
            metadata={"task_id": task_id, "error": error, "attempts": attempts}
        )
    
    # ============== Agent Events ==============
    
    def agent_spawned(self, agent_id: str, agent_type: str, worktree: str):
        """Log agent spawned."""
        return self._create_event(
            EventType.AGENT_SPAWNED,
            f"Spawned {agent_type} agent: {agent_id}",
            agent_id=agent_id,
            metadata={"agent_id": agent_id, "agent_type": agent_type, "worktree": worktree}
        )
    
    def agent_completed(self, agent_id: str, tasks_completed: int):
        """Log agent completed."""
        return self._create_event(
            EventType.AGENT_COMPLETED,
            f"Agent {agent_id} completed {tasks_completed} tasks",
            agent_id=agent_id,
            metadata={"agent_id": agent_id, "tasks_completed": tasks_completed}
        )
    
    # ============== LLM Events ==============
    
    def llm_call_start(self, prompt: str, model: str) -> str:
        """Log LLM call started. Returns call ID."""
        call_id = f"llm_{self.event_count + 1}"
        
        # Truncate prompt for storage
        prompt_preview = prompt[:500] if len(prompt) > 500 else prompt
        
        self._create_event(
            EventType.LLM_CALL_START,
            f"LLM call started: {model}",
            model=model,
            metadata={
                "call_id": call_id,
                "model": model,
                "prompt_length": len(prompt),
                "prompt_preview": prompt_preview
            }
        )
        
        return call_id
    
    def llm_call_end(
        self,
        call_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        success: bool = True
    ):
        """Log LLM call ended."""
        total_tokens = prompt_tokens + completion_tokens
        self.trajectory.tokens_used += total_tokens
        
        return self._create_event(
            EventType.LLM_CALL_END,
            f"LLM call completed: {model} ({prompt_tokens + completion_tokens} tokens, {latency_ms}ms)",
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            metadata={
                "call_id": call_id,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "latency_ms": latency_ms,
                "success": success
            }
        )
    
    # ============== Git Events ==============
    
    def git_commit(self, branch: str, message: str, files_changed: int):
        """Log git commit."""
        return self._create_event(
            EventType.GIT_COMMIT,
            f"Git commit on {branch}: {message[:50]}",
            branch=branch,
            commit_sha=message[:8],  # Rough estimate
            metadata={
                "branch": branch,
                "message": message,
                "files_changed": files_changed
            }
        )
    
    def git_push(self, branch: str, remote: str = "origin"):
        """Log git push."""
        return self._create_event(
            EventType.GIT_PUSH,
            f"Pushed {branch} to {remote}",
            branch=branch,
            metadata={"branch": branch, "remote": remote}
        )
    
    def git_pr_created(self, pr_number: int, title: str, branch: str):
        """Log PR created."""
        return self._create_event(
            EventType.GIT_PR_CREATED,
            f"Created PR #{pr_number}: {title}",
            branch=branch,
            pr_number=pr_number,
            metadata={"pr_number": pr_number, "title": title, "branch": branch}
        )
    
    def git_worktree_created(self, branch: str, path: str):
        """Log worktree created."""
        return self._create_event(
            EventType.GIT_WORKTREE_CREATED,
            f"Created worktree for {branch} at {path}",
            branch=branch,
            metadata={"branch": branch, "path": path}
        )
    
    # ============== Code Events ==============
    
    def code_written(self, file_path: str, lines: int, action: str = "created"):
        """Log code written to file."""
        return self._create_event(
            EventType.CODE_WRITTEN,
            f"{action.capitalize()} {lines} lines in {file_path}",
            metadata={"file_path": file_path, "lines": lines, "action": action}
        )
    
    def test_written(self, file_path: str, tests: int):
        """Log tests written."""
        return self._create_event(
            EventType.TEST_WRITTEN,
            f"Wrote {tests} tests in {file_path}",
            metadata={"file_path": file_path, "tests": tests}
        )
    
    # ============== Error Events ==============
    
    def error(self, message: str, context: Dict[str, Any] = None):
        """Log error."""
        return self._create_event(
            EventType.ERROR,
            message,
            error_message=message,
            metadata=context or {}
        )
    
    def warning(self, message: str, context: Dict[str, Any] = None):
        """Log warning."""
        return self._create_event(
            EventType.WARNING,
            message,
            metadata=context or {}
        )
    
    # ============== Utility Methods ==============
    
    def get_summary(self) -> Dict[str, Any]:
        """Get session summary."""
        return {
            "session_id": self.session_id,
            "repo": self.repo,
            "issue": self.trajectory.issue_title,
            "status": self.trajectory.status,
            "events": self.event_count,
            "tasks": {
                "created": self.trajectory.tasks_created,
                "completed": self.trajectory.tasks_completed,
                "failed": self.trajectory.tasks_failed
            },
            "llm": {
                "calls": self.trajectory.llm_calls,
                "tokens": self.trajectory.tokens_used
            },
            "commits": self.trajectory.commits,
            "duration": self._get_duration()
        }
    
    def _get_duration(self) -> float:
        """Get session duration in seconds."""
        start = datetime.fromisoformat(self.trajectory.started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(
            (self.trajectory.ended_at or datetime.utcnow().isoformat()).replace("Z", "+00:00")
        )
        return (end - start).total_seconds()
    
    def close(self):
        """Close log files."""
        self._save_trajectory()
        self.events_file.close()
        self.trajectory_file.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def load_trajectory(log_dir: str, session_id: str) -> Trajectory:
    """Load a trajectory from file."""
    with open(f"{log_dir}/trajectory_{session_id}.json") as f:
        data = json.load(f)
        return Trajectory(**data)
