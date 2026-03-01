"""Session history manager for multi-agent coordination."""
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from utils.logger import get_logger


class SessionHistory:
    """
    Manages shared session history that all agents can read.
    Stores current work state, what each agent is doing, and what's next.
    """
    
    def __init__(self, session_dir: str = ".autodev/sessions"):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.session_dir / "current.json"
        self.history_file = self.session_dir / "history.jsonl"
        self.logger = get_logger("autodev.session")
        
        # Current session state
        self.state: Dict[str, Any] = {
            "session_id": datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
            "started_at": datetime.utcnow().isoformat() + "Z",
            "agents": {},  # agent_id -> {status, current_task, last_update}
            "task_queue": [],  # List of pending tasks
            "completed": [],  # Completed tasks
            "failed": [],  # Failed tasks
            "current_work": {},  # What each agent is working on
            "next_tasks": [],  # Tasks ready to be picked up
            "notes": []  # Notes from agents
        }
    
    def init_session(self, issue: str, total_subtasks: int):
        """Initialize a new session."""
        self.state["issue"] = issue
        self.state["total_subtasks"] = total_subtasks
        self.state["status"] = "running"
        self.save()
        self.logger.info(f"Session initialized: {self.state['session_id']}")
    
    def register_agent(self, agent_id: str, agent_type: str, worktree: str = ""):
        """Register an agent in the session."""
        self.state["agents"][agent_id] = {
            "type": agent_type,
            "status": "idle",
            "worktree": worktree,
            "current_task": None,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "last_update": datetime.utcnow().isoformat() + "Z",
            "completed_count": 0,
            "failed_count": 0
        }
        self.save()
    
    def agent_start_task(self, agent_id: str, task_id: str, description: str):
        """Record that an agent started a task."""
        if agent_id in self.state["agents"]:
            self.state["agents"][agent_id]["status"] = "working"
            self.state["agents"][agent_id]["current_task"] = task_id
            self.state["agents"][agent_id]["last_update"] = datetime.utcnow().isoformat() + "Z"
            
            self.state["current_work"][task_id] = {
                "agent_id": agent_id,
                "description": description,
                "started_at": datetime.utcnow().isoformat() + "Z",
                "status": "in_progress"
            }
            
            # Remove from next_tasks if present
            if task_id in self.state["next_tasks"]:
                self.state["next_tasks"].remove(task_id)
            
            self.save()
            self.logger.info(f"Agent {agent_id} started task {task_id}")
    
    def agent_complete_task(self, agent_id: str, task_id: str, success: bool = True, message: str = ""):
        """Record that an agent completed a task."""
        if agent_id in self.state["agents"]:
            self.state["agents"][agent_id]["last_update"] = datetime.utcnow().isoformat() + "Z"
            self.state["agents"][agent_id]["current_task"] = None
            self.state["agents"][agent_id]["status"] = "idle"
            
            if success:
                self.state["agents"][agent_id]["completed_count"] += 1
                self.state["completed"].append({
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "completed_at": datetime.utcnow().isoformat() + "Z",
                    "message": message
                })
            else:
                self.state["agents"][agent_id]["failed_count"] += 1
                self.state["failed"].append({
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "failed_at": datetime.utcnow().isoformat() + "Z",
                    "message": message
                })
            
            # Remove from current_work
            if task_id in self.state["current_work"]:
                del self.state["current_work"][task_id]
            
            self.save()
            self.logger.info(f"Agent {agent_id} completed task {task_id} (success={success})")
    
    def add_note(self, agent_id: str, note: str):
        """Add a note to the session."""
        self.state["notes"].append({
            "agent_id": agent_id,
            "note": note,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
        self.save()
    
    def get_ready_agents(self) -> List[str]:
        """Get list of agents that are idle and ready for work."""
        return [
            agent_id for agent_id, info in self.state["agents"].items()
            if info["status"] == "idle"
        ]
    
    def get_status(self) -> Dict[str, Any]:
        """Get current session status."""
        return {
            "session_id": self.state["session_id"],
            "status": self.state.get("status", "unknown"),
            "issue": self.state.get("issue", ""),
            "progress": {
                "total": self.state.get("total_subtasks", 0),
                "completed": len(self.state["completed"]),
                "failed": len(self.state["failed"]),
                "in_progress": len(self.state["current_work"]),
                "pending": len(self.state["next_tasks"])
            },
            "agents": {
                agent_id: {
                    "status": info["status"],
                    "current_task": info["current_task"],
                    "completed": info.get("completed_count", 0),
                    "failed": info.get("failed_count", 0)
                }
                for agent_id, info in self.state["agents"].items()
            },
            "current_work": list(self.state["current_work"].keys()),
            "next_tasks": self.state["next_tasks"][:5]  # First 5
        }
    
    def save(self):
        """Save current state to file."""
        with open(self.session_file, "w") as f:
            json.dump(self.state, f, indent=2)
    
    def append_history(self, event_type: str, data: Dict[str, Any]):
        """Append event to history file."""
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "type": event_type,
            "data": data
        }
        with open(self.history_file, "a") as f:
            f.write(json.dumps(event) + "\n")
    
    def close_session(self, status: str = "completed"):
        """Close the session."""
        self.state["status"] = status
        self.state["ended_at"] = datetime.utcnow().isoformat() + "Z"
        self.save()
        
        # Append to history
        self.append_history("session_closed", {
            "session_id": self.state["session_id"],
            "status": status
        })
        
        self.logger.info(f"Session closed: {status}")
    
    def get_agent_context(self, agent_id: str) -> str:
        """Get context string for an agent - what's happening and what's next."""
        status = self.get_status()
        
        context = f"""Current Session Status:
- Issue: {status['issue']}
- Progress: {status['progress']['completed']}/{status['progress']['total']} completed
- Failed: {status['progress']['failed']}

Agents Working:
"""
        for ag_id, ag_status in status["agents"].items():
            context += f"- {ag_id}: {ag_status['status']}"
            if ag_status["current_task"]:
                context += f" -> {ag_status['current_task']}"
            context += f" (completed: {ag_status['completed']}, failed: {ag_status['failed']})\n"
        
        context += f"""
Your Status: {status['agents'].get(agent_id, {}).get('status', 'unknown')}
Current Task: {status['agents'].get(agent_id, {}).get('current_task', 'none')}

Pending Tasks: {status['next_tasks']}
"""
        return context
