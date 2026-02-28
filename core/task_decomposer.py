"""Task decomposition logic for AutoDev."""
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class Subtask:
    """Represents a single subtask."""
    id: str
    description: str
    status: str = "pending"  # pending, in_progress, completed, failed
    agent: Optional[str] = None
    attempts: int = 0
    error: Optional[str] = None
    research_needed: bool = False
    file: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    resource: Optional[str] = None


@dataclass
class Feature:
    """Represents a feature containing multiple subtasks."""
    id: str
    name: str
    status: str = "pending"
    subtasks: List[Subtask] = field(default_factory=list)


class TaskDecomposer:
    """Decomposes GitHub issues into features and subtasks."""
    
    # Keywords that suggest specific types of work
    WORK_PATTERNS = {
        "api": ["endpoint", "route", "api", "controller", "handler"],
        "model": ["model", "schema", "database", "table", "entity"],
        "test": ["test", "spec", "unittest", "integration"],
        "ui": ["component", "page", "screen", "view", "frontend"],
        "auth": ["auth", "login", "jwt", "token", "password"],
        "bug": ["fix", "bug", "issue", "error", "broken"],
        "refactor": ["refactor", "improve", "cleanup", "restructure"],
    }
    
    def __init__(self):
        self.current_task_id = 0
    
    def _generate_id(self, prefix: str = "subtask") -> str:
        """Generate a unique task ID."""
        self.current_task_id += 1
        return f"{prefix}_{self.current_task_id}"
    
    def _to_dict(self, obj):
        """Convert dataclass to dict recursively."""
        import dataclasses
        if dataclasses.is_dataclass(obj):
            result = {}
            for field in dataclasses.fields(obj):
                value = getattr(obj, field.name)
                if isinstance(value, list):
                    result[field.name] = [self._to_dict(item) for item in value]
                elif dataclasses.is_dataclass(value):
                    result[field.name] = self._to_dict(value)
                else:
                    result[field.name] = value
            return result
        return obj
    
    def decompose_issue(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decompose a GitHub issue into features and subtasks.
        
        Args:
            issue: GitHub issue dict with title, body, labels, etc.
            
        Returns:
            Dict containing features and subtasks structure
        """
        title = issue.get("title", "")
        body = issue.get("body", "")
        labels = issue.get("labels", [])
        
        # Identify features based on issue content
        features_data = self._identify_features(title, body, labels)
        
        # Convert dataclasses to dicts
        features = [self._to_dict(f) for f in features_data]
        
        # Create the task plan
        plan = {
            "project": "",
            "issue": f"#{issue.get('number')}: {title}",
            "features": features,
            "metadata": {
                "created": issue.get("created_at", ""),
                "updated": issue.get("updated_at", ""),
                "total_subtasks": sum(len(f.get("subtasks", [])) for f in features),
                "completed": 0,
                "failed": 0,
                "in_progress": 0,
                "pending": sum(len(f.get("subtasks", [])) for f in features)
            }
        }
        
        return plan
    
    def _identify_features(self, title: str, body: str, labels: List) -> List[Feature]:
        """Identify features from issue content."""
        features = []
        
        # Check for labels that indicate feature types
        label_names = []
        if labels:
            label_names = [l.get("name", "") for l in labels] if isinstance(labels[0], dict) else labels
        
        # Feature 1: Based on main issue title
        main_feature = Feature(
            id="feat_1",
            name=self._extract_feature_name(title),
            subtasks=self._generate_subtasks(title, body)
        )
        features.append(main_feature)
        
        # Additional features based on body sections or labels
        body_features = self._extract_features_from_body(body)
        for i, feat in enumerate(body_features, start=2):
            feat.id = f"feat_{i}"
            features.append(feat)
        
        # Add testing feature if not present
        if not any("test" in f.name.lower() for f in features):
            test_feature = Feature(
                id=f"feat_{len(features) + 1}",
                name="Testing",
                subtasks=[
                    Subtask(
                        id=self._generate_id(),
                        description="Write unit tests for new functionality",
                        file="tests/test_main.py"
                    ),
                    Subtask(
                        id=self._generate_id(),
                        description="Run tests and verify all pass",
                    )
                ]
            )
            features.append(test_feature)
        
        return features
    
    def _extract_feature_name(self, title: str) -> str:
        """Extract feature name from issue title."""
        # Remove common prefixes
        cleaned = re.sub(r'^(fix|add|implement|update|create|refactor)\s+', '', title.lower())
        # Capitalize
        return cleaned.title()
    
    def _extract_features_from_body(self, body: str) -> List[Feature]:
        """Extract additional features from issue body."""
        features = []
        
        # Look for headers/sections in body
        sections = re.split(r'^##\s+', body, flags=re.MULTILINE)
        
        for section in sections[1:]:  # Skip first (before any header)
            lines = section.strip().split('\n')
            if lines:
                feature_name = lines[0].strip()
                subtasks = []
                
                # Extract bullet points as subtasks
                for line in lines[1:]:
                    if line.strip().startswith(('- ', '* ', '- [ ] ', '- [x] ')):
                        task_text = line.strip().lstrip('- *').lstrip('[ ] ').lstrip('[x] ').strip()
                        subtasks.append(Subtask(
                            id=self._generate_id(),
                            description=task_text
                        ))
                
                if subtasks:
                    features.append(Feature(
                        id=f"feat_temp_{len(features)}",
                        name=feature_name,
                        subtasks=subtasks
                    ))
        
        return features
    
    def _generate_subtasks(self, title: str, body: str) -> List[Subtask]:
        """Generate subtasks for a feature based on keywords."""
        subtasks = []
        text = (title + " " + body).lower()
        
        # Detect work types from text
        detected_types = []
        for work_type, keywords in self.WORK_PATTERNS.items():
            if any(kw in text for kw in keywords):
                detected_types.append(work_type)
        
        # Default subtasks based on detected work
        if "model" in detected_types or "api" in detected_types:
            subtasks.append(Subtask(
                id=self._generate_id(),
                description="Implement the core functionality",
                status="pending"
            ))
        
        if "test" in detected_types or not detected_types:
            subtasks.append(Subtask(
                id=self._generate_id(),
                description="Write unit tests",
                file="tests/test_main.py",
                status="pending"
            ))
            subtasks.append(Subtask(
                id=self._generate_id(),
                description="Run tests and fix any failures",
                status="pending"
            ))
        
        # Always add a documentation subtask
        subtasks.append(Subtask(
            id=self._generate_id(),
            description="Update documentation if needed",
            status="pending"
        ))
        
        # If no specific types detected, add generic subtasks
        if not detected_types:
            subtasks = [
                Subtask(
                    id=self._generate_id(),
                    description="Understand requirements and plan implementation",
                    status="pending"
                ),
                Subtask(
                    id=self._generate_id(),
                    description="Implement the solution",
                    status="pending"
                ),
                Subtask(
                    id=self._generate_id(),
                    description="Write tests to verify the implementation",
                    file="tests/test_main.py",
                    status="pending"
                ),
                Subtask(
                    id=self._generate_id(),
                    description="Run tests and fix any issues",
                    status="pending"
                )
            ]
        
        return subtasks
    
    def can_run_parallel(self, subtask_a: Subtask, subtask_b: Subtask) -> bool:
        """Check if two subtasks can run in parallel."""
        # Same file? Can't parallelize
        if subtask_a.file and subtask_b.file:
            if subtask_a.file == subtask_b.file:
                return False
        
        # Dependency exists? Can't parallelize
        if subtask_b.id in subtask_a.depends_on or subtask_a.id in subtask_b.depends_on:
            return False
        
        # Uses same resource? Maybe can't
        if subtask_a.resource and subtask_b.resource:
            if subtask_a.resource == subtask_b.resource:
                return False
        
        return True
    
    def get_ready_subtasks(self, plan: Dict) -> List[Subtask]:
        """Get subtasks that are ready to execute (no pending dependencies)."""
        ready = []
        
        for feature in plan.get("features", []):
            for subtask in feature.get("subtasks", []):
                if subtask.status != "pending":
                    continue
                
                # Check if all dependencies are completed
                deps = subtask.depends_on or []
                deps_completed = all(
                    self._find_subtask(plan, dep).status == "completed"
                    for dep in deps
                )
                
                if deps_completed or not deps:
                    ready.append(subtask)
        
        return ready
    
    def _find_subtask(self, plan: Dict, subtask_id: str) -> Optional[Subtask]:
        """Find a subtask by ID in the plan."""
        for feature in plan.get("features", []):
            for subtask in feature.get("subtasks", []):
                if subtask.id == subtask_id:
                    return subtask
        return None
