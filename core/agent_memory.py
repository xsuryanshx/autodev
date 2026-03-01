"""Shared context memory for parallel agents."""
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from threading import Lock
from datetime import datetime


class AgentMemory:
    """
    Shared memory context for parallel agents.
    
    Allows agents to:
    - Share progress updates
    - Access shared context
    - Coordinate via messages
    - Store intermediate results
    """
    
    def __init__(self, session_id: str, memory_dir: str = ".autodev/memory"):
        self.session_id = session_id
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        self._lock = Lock()
        self._context: Dict[str, Any] = {
            "session_id": session_id,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "agents": {},
            "shared_data": {},
            "messages": [],
            "progress": {}
        }
        
        # Persist to disk
        self._persist()
    
    def _persist(self):
        """Save memory to disk."""
        with open(self.memory_dir / f"{self.session_id}.json", "w") as f:
            json.dump(self._context, f, indent=2)
    
    def register_agent(self, agent_id: str, agent_type: str, worktree: str):
        """Register a new agent."""
        with self._lock:
            self._context["agents"][agent_id] = {
                "type": agent_type,
                "worktree": worktree,
                "registered_at": datetime.utcnow().isoformat() + "Z",
                "status": "running"
            }
            self._persist()
    
    def update_agent_status(self, agent_id: str, status: str, message: str = ""):
        """Update agent status."""
        with self._lock:
            if agent_id in self._context["agents"]:
                self._context["agents"][agent_id]["status"] = status
                self._context["agents"][agent_id]["last_update"] = datetime.utcnow().isoformat() + "Z"
                if message:
                    self._context["agents"][agent_id]["last_message"] = message
                self._persist()
    
    def set_shared_data(self, key: str, value: Any):
        """Store shared data accessible by all agents."""
        with self._lock:
            self._context["shared_data"][key] = {
                "value": value,
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "updated_by": "system"
            }
            self._persist()
    
    def get_shared_data(self, key: str, default: Any = None) -> Any:
        """Retrieve shared data."""
        with self._lock:
            return self._context["shared_data"].get(key, {}).get("value", default)
    
    def post_message(self, from_agent: str, to_agent: Optional[str], message: str):
        """Post a message between agents."""
        with self._lock:
            msg = {
                "from": from_agent,
                "to": to_agent or "all",
                "message": message,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            self._context["messages"].append(msg)
            self._persist()
    
    def get_messages(self, agent_id: Optional[str] = None) -> List[Dict]:
        """Get messages for an agent."""
        with self._lock:
            if agent_id:
                return [m for m in self._context["messages"] 
                       if m["to"] == agent_id or m["to"] == "all"]
            return self._context["messages"]
    
    def update_progress(self, agent_id: str, task_id: str, status: str, details: Dict = None):
        """Update task progress."""
        with self._lock:
            progress_key = f"{agent_id}:{task_id}"
            self._context["progress"][progress_key] = {
                "agent_id": agent_id,
                "task_id": task_id,
                "status": status,  # started, completed, failed
                "details": details or {},
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }
            self._persist()
    
    def get_progress(self) -> Dict[str, Any]:
        """Get overall progress."""
        with self._lock:
            return self._context["progress"].copy()
    
    def get_agent_status(self, agent_id: str) -> Optional[Dict]:
        """Get status of a specific agent."""
        with self._lock:
            return self._context["agents"].get(agent_id)
    
    def get_all_agents(self) -> Dict[str, Dict]:
        """Get all registered agents."""
        with self._lock:
            return self._context["agents"].copy()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get memory summary."""
        with self._lock:
            agents = self._context["agents"]
            progress = self._context["progress"]
            
            return {
                "session_id": self.session_id,
                "agent_count": len(agents),
                "agents": {
                    aid: {"type": a["type"], "status": a["status"]}
                    for aid, a in agents.items()
                },
                "progress": {
                    k: {"status": v["status"], "task_id": v["task_id"]}
                    for k, v in progress.items()
                },
                "messages_count": len(self._context["messages"]),
                "shared_keys": list(self._context["shared_data"].keys())
            }


def load_agent_memory(session_id: str, memory_dir: str = ".autodev/memory") -> Optional[AgentMemory]:
    """Load existing agent memory if it exists."""
    memory_path = Path(memory_dir) / f"{session_id}.json"
    if memory_path.exists():
        # Return a read-only view (would need to implement properly)
        return None  # Not implemented yet
    return None
