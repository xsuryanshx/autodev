"""State management for AutoDev task tracking."""
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path


class StateManager:
    """Manages task plan state and persistence."""
    
    def __init__(self, state_dir: str = ".autodev"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
        self.plan_file = self.state_dir / "subtask_plan.json"
        self.current_plan: Dict[str, Any] = {}
    
    def create_plan(self, issue: Dict[str, Any], project: str = "") -> Dict[str, Any]:
        """Create a new task plan from a GitHub issue."""
        from core.task_decomposer import TaskDecomposer
        
        decomposer = TaskDecomposer()
        plan = decomposer.decompose_issue(issue)
        plan["project"] = project
        plan["metadata"]["created"] = datetime.utcnow().isoformat() + "Z"
        plan["metadata"]["updated"] = datetime.utcnow().isoformat() + "Z"
        
        self.current_plan = plan
        self.save()
        
        return plan
    
    def load(self, plan_path: Optional[str] = None) -> Dict[str, Any]:
        """Load a task plan from file."""
        path = Path(plan_path) if plan_path else self.plan_file
        
        if not path.exists():
            raise FileNotFoundError(f"Plan file not found: {path}")
        
        with open(path, "r") as f:
            self.current_plan = json.load(f)
        
        return self.current_plan
    
    def save(self, plan_path: Optional[str] = None):
        """Save current plan to file."""
        path = Path(plan_path) if plan_path else self.plan_file
        
        # Update timestamp
        self.current_plan["metadata"]["updated"] = datetime.utcnow().isoformat() + "Z"
        
        # Update counts
        self._update_counts()
        
        with open(path, "w") as f:
            json.dump(self.current_plan, f, indent=2)
        
        # Also generate markdown view
        self._save_markdown()
    
    def _update_counts(self):
        """Update metadata counts based on subtask statuses."""
        total = 0
        completed = 0
        failed = 0
        in_progress = 0
        
        for feature in self.current_plan.get("features", []):
            for subtask in feature.get("subtasks", []):
                total += 1
                status = subtask.get("status", "pending")
                if status == "completed":
                    completed += 1
                elif status == "failed":
                    failed += 1
                elif status == "in_progress":
                    in_progress += 1
        
        self.current_plan["metadata"]["total_subtasks"] = total
        self.current_plan["metadata"]["completed"] = completed
        self.current_plan["metadata"]["failed"] = failed
        self.current_plan["metadata"]["in_progress"] = in_progress
        self.current_plan["metadata"]["pending"] = total - completed - failed - in_progress
    
    def _save_markdown(self):
        """Generate markdown view of the plan."""
        md_path = self.state_dir / "subtask_plan.md"
        
        plan = self.current_plan
        issue = plan.get("issue", "Unknown Issue")
        meta = plan.get("metadata", {})
        
        lines = [
            f"# Subtask Plan: {issue}",
            "",
            f"## Progress: {meta.get('completed', 0)}/{meta.get('total_subtasks', 0)} completed",
            ""
        ]
        
        status_icons = {
            "completed": "✓",
            "in_progress": "◐",
            "failed": "✗",
            "pending": "○"
        }
        
        for feature in plan.get("features", []):
            feat_status = feature.get("status", "pending")
            icon = status_icons.get(feat_status, "○")
            lines.append(f"## {feature.get('name', 'Feature')} {icon}")
            
            for subtask in feature.get("subtasks", []):
                sub_status = subtask.get("status", "pending")
                sub_icon = status_icons.get(sub_status, "○")
                desc = subtask.get("description", "")
                agent = subtask.get("agent", "")
                error = subtask.get("error", "")
                
                agent_str = f" ({agent})" if agent else ""
                lines.append(f"- [{sub_icon}] {subtask.get('id')}: {desc}{agent_str}")
                
                if error and sub_status == "failed":
                    lines.append(f"  - Error: {error}")
            
            lines.append("")
        
        with open(md_path, "w") as f:
            f.write("\n".join(lines))
    
    def update_subtask(
        self,
        subtask_id: str,
        status: Optional[str] = None,
        agent: Optional[str] = None,
        error: Optional[str] = None,
        research_needed: Optional[bool] = None
    ):
        """Update a subtask's status and details."""
        for feature in self.current_plan.get("features", []):
            for subtask in feature.get("subtasks", []):
                if subtask.get("id") == subtask_id:
                    if status:
                        subtask["status"] = status
                        if status == "in_progress":
                            subtask["attempts"] = subtask.get("attempts", 0) + 1
                    if agent:
                        subtask["agent"] = agent
                    if error is not None:
                        subtask["error"] = error
                    if research_needed is not None:
                        subtask["research_needed"] = research_needed
                    
                    # Update feature status
                    self._update_feature_status(feature)
                    self.save()
                    return
        
        raise ValueError(f"Subtask {subtask_id} not found")
    
    def _update_feature_status(self, feature: Dict):
        """Update feature status based on subtasks."""
        subtasks = feature.get("subtasks", [])
        if not subtasks:
            return
        
        statuses = [s.get("status", "pending") for s in subtasks]
        
        if all(s == "completed" for s in statuses):
            feature["status"] = "completed"
        elif any(s == "failed" for s in statuses):
            feature["status"] = "failed"
        elif any(s == "in_progress" for s in statuses):
            feature["status"] = "in_progress"
        else:
            feature["status"] = "pending"
    
    def get_subtask(self, subtask_id: str) -> Optional[Dict]:
        """Get a specific subtask by ID."""
        for feature in self.current_plan.get("features", []):
            for subtask in feature.get("subtasks", []):
                if subtask.get("id") == subtask_id:
                    return subtask
        return None
    
    def get_pending_subtasks(self) -> List[Dict]:
        """Get all pending subtasks."""
        pending = []
        for feature in self.current_plan.get("features", []):
            for subtask in feature.get("subtasks", []):
                if subtask.get("status") == "pending":
                    pending.append(subtask)
        return pending
    
    def get_failed_subtasks(self) -> List[Dict]:
        """Get all failed subtasks that need research."""
        failed = []
        for feature in self.current_plan.get("features", []):
            for subtask in feature.get("subtasks", []):
                if subtask.get("status") == "failed":
                    failed.append(subtask)
        return failed
    
    def is_complete(self) -> bool:
        """Check if all subtasks are completed."""
        for feature in self.current_plan.get("features", []):
            for subtask in feature.get("subtasks", []):
                if subtask.get("status") != "completed":
                    return False
        return True
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the current plan state."""
        return {
            "issue": self.current_plan.get("issue"),
            "project": self.current_plan.get("project"),
            "metadata": self.current_plan.get("metadata", {}),
            "features": [
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "status": f.get("status"),
                    "subtask_count": len(f.get("subtasks", []))
                }
                for f in self.current_plan.get("features", [])
            ]
        }
