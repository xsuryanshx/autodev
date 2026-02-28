"""Validators for AutoDev configuration and inputs."""
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ValidationError:
    """Represents a validation error."""
    field: str
    message: str


class ConfigValidator:
    """Validates AutoDev configuration."""
    
    REQUIRED_FIELDS = {
        "repo": ["owner", "name"],
    }
    
    def validate_config(self, config: Dict[str, Any]) -> List[ValidationError]:
        """Validate configuration dictionary."""
        errors = []
        
        # Check required fields
        for section, fields in self.REQUIRED_FIELDS.items():
            if section not in config:
                errors.append(ValidationError(section, f"Missing required section: {section}"))
                continue
            
            for field in fields:
                if not config[section].get(field):
                    errors.append(ValidationError(
                        f"{section}.{field}",
                        f"Missing required field: {field}"
                    ))
        
        # Validate agent settings
        agents = config.get("agents", {})
        if agents.get("max_parallel", 0) < 1:
            errors.append(ValidationError(
                "agents.max_parallel",
                "Must be at least 1"
            ))
        
        if agents.get("timeout_per_subtask", 0) < 60:
            errors.append(ValidationError(
                "agents.timeout_per_subtask",
                "Should be at least 60 seconds"
            ))
        
        # Validate research settings
        research = config.get("research", {})
        if research.get("trigger_after_failures", 0) < 1:
            errors.append(ValidationError(
                "research.trigger_after_failures",
                "Must be at least 1"
            ))
        
        # Validate testing settings
        testing = config.get("testing", {})
        cov = testing.get("coverage_threshold", 0)
        if cov < 0 or cov > 100:
            errors.append(ValidationError(
                "testing.coverage_threshold",
                "Must be between 0 and 100"
            ))
        
        return errors
    
    def validate_github_token(self, token: Optional[str]) -> bool:
        """Validate GitHub token format."""
        if not token:
            return False
        
        # GitHub tokens are either classic (40 chars, ghp_ prefix) or fine-grained
        if token.startswith("ghp_"):
            return len(token) >= 40
        return len(token) >= 20  # Generic check


class IssueValidator:
    """Validates GitHub issue data."""
    
    def validate_issue(self, issue: Dict[str, Any]) -> List[ValidationError]:
        """Validate GitHub issue structure."""
        errors = []
        
        required = ["title", "number"]
        for field in required:
            if field not in issue:
                errors.append(ValidationError(field, f"Missing required field: {field}"))
        
        if "title" in issue:
            title = issue["title"]
            if not title or len(title.strip()) < 3:
                errors.append(ValidationError(
                    "title",
                    "Title must be at least 3 characters"
                ))
        
        if "number" in issue:
            number = issue["number"]
            if not isinstance(number, int) or number < 1:
                errors.append(ValidationError(
                    "number",
                    "Issue number must be a positive integer"
                ))
        
        return errors


class PlanValidator:
    """Validates task plan structure."""
    
    def validate_plan(self, plan: Dict[str, Any]) -> List[ValidationError]:
        """Validate task plan structure."""
        errors = []
        
        # Check required top-level fields
        if "issue" not in plan:
            errors.append(ValidationError("issue", "Missing required field"))
        
        if "features" not in plan:
            errors.append(ValidationError("features", "Missing required field"))
            return errors
        
        # Validate features
        features = plan["features"]
        if not isinstance(features, list):
            errors.append(ValidationError("features", "Must be a list"))
            return errors
        
        feature_ids = set()
        for i, feature in enumerate(features):
            if "id" not in feature:
                errors.append(ValidationError(f"features[{i}].id", "Missing required field"))
            else:
                fid = feature["id"]
                if fid in feature_ids:
                    errors.append(ValidationError(f"features[{i}].id", f"Duplicate ID: {fid}"))
                feature_ids.add(fid)
            
            if "subtasks" not in feature:
                errors.append(ValidationError(f"features[{i}].subtasks", "Missing required field"))
                continue
            
            # Validate subtasks
            subtask_ids = set()
            for j, subtask in enumerate(feature["subtasks"]):
                if "id" not in subtask:
                    errors.append(ValidationError(
                        f"features[{i}].subtasks[{j}].id",
                        "Missing required field"
                    ))
                else:
                    sid = subtask["id"]
                    if sid in subtask_ids:
                        errors.append(ValidationError(
                            f"features[{i}].subtasks[{j}].id",
                            f"Duplicate ID: {sid}"
                        ))
                    subtask_ids.add(sid)
                
                # Validate status
                valid_statuses = ["pending", "in_progress", "completed", "failed"]
                status = subtask.get("status", "pending")
                if status not in valid_statuses:
                    errors.append(ValidationError(
                        f"features[{i}].subtasks[{j}].status",
                        f"Invalid status: {status}. Must be one of: {', '.join(valid_statuses)}"
                    ))
        
        return errors
