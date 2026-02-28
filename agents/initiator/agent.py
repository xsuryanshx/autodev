"""Initiator Agent - coordinates task decomposition and agent execution."""
from typing import Dict, Any, Optional
from utils.logger import get_logger


class InitiatorAgent:
    """
    Initiator Agent responsibilities:
    - Parse GitHub issues
    - Decompose into features
    - Assign features to coder agents
    - Track overall progress
    - Create PRs
    - Quality gate (tests pass, code review)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = get_logger("autodev.initiator")
        self.github_client = None
        self.state_manager = None
        self.coder_agents = []
    
    def initialize(self, github_client, state_manager):
        """Initialize with dependencies."""
        self.github_client = github_client
        self.state_manager = state_manager
        self.logger.info("Initiator Agent initialized")
    
    def process_issue(self, issue_number: int, repo_owner: str, repo_name: str) -> Dict[str, Any]:
        """Process a GitHub issue and create task plan."""
        self.logger.info(f"Processing issue #{issue_number} from {repo_owner}/{repo_name}")
        
        # Fetch issue from GitHub
        issue = self.github_client.get_issue(issue_number)
        
        # Create task plan
        plan = self.state_manager.create_plan(issue, f"{repo_owner}/{repo_name}")
        
        self.logger.info(f"Created plan with {len(plan['features'])} features")
        return plan
    
    def get_ready_subtasks(self):
        """Get subtasks ready for execution."""
        from core.task_decomposer import TaskDecomposer
        
        decomposer = TaskDecomposer()
        return decomposer.get_ready_subtasks(self.state_manager.current_plan)
    
    def assign_subtask(self, subtask_id: str, agent_id: str):
        """Assign a subtask to a coder agent."""
        self.state_manager.update_subtask(subtask_id, agent=agent_id, status="in_progress")
        self.logger.info(f"Assigned {subtask_id} to {agent_id}")
    
    def check_quality_gate(self) -> bool:
        """Check if all quality gates pass before creating PR."""
        # TODO: Implement actual quality checks
        # - Run full test suite
        # - Lint and format check
        # - Code review
        self.logger.info("Running quality gate checks...")
        return True
    
    def create_pull_request(
        self,
        title: str,
        body: str,
        branch: str,
        base: str = "main"
    ) -> Dict[str, Any]:
        """Create a pull request."""
        self.logger.info(f"Creating PR: {title}")
        
        pr = self.github_client.create_pull_request(title, body, branch, base)
        
        # Add reviewers if configured
        reviewers = self.config.get("github", {}).get("add_reviewers", [])
        if reviewers:
            self.github_client.add_pr_reviewers(pr["number"], reviewers)
        
        return pr
    
    def run(self, issue_number: int, repo_owner: str, repo_name: str):
        """Main execution loop."""
        # Process issue
        self.process_issue(issue_number, repo_owner, repo_name)
        
        # Get ready subtasks
        ready = self.get_ready_subtasks()
        
        self.logger.info(f"Found {len(ready)} ready subtasks")
        
        # This would normally dispatch to coder agents
        # For Phase 1, we just show what's ready
        
        return ready
