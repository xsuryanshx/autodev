"""Main orchestrator for AutoDev - coordinates agents and execution."""
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from core.github_client import GitHubClient
from core.state_manager import StateManager
from core.task_decomposer import TaskDecomposer
from core.executor import TaskQueue, WorktreeManager
from agents.initiator.agent import InitiatorAgent
from agents.coder.agent import CoderAgent
from agents.researcher.agent import ResearcherAgent
from utils.logger import get_logger, setup_logger


class AutoDevOrchestrator:
    """
    Main orchestrator that coordinates the entire AutoDev workflow.
    
    Flow:
    1. Fetch issue from GitHub
    2. Decompose into features/subtasks
    3. Create worktrees for parallel execution
    4. Dispatch subtasks to coder agents
    5. Monitor progress and handle failures
    6. Merge results and create PR
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = get_logger("autodev.orchestrator")
        
        # Core components
        self.github: Optional[GitHubClient] = None
        self.state_manager: Optional[StateManager] = None
        self.task_queue: Optional[TaskQueue] = None
        self.worktree_manager: Optional[WorktreeManager] = None
        
        # Agents
        self.initiator: Optional[InitiatorAgent] = None
        self.coder_agents: List[CoderAgent] = []
        self.researcher: Optional[ResearcherAgent] = None
        
        # State
        self.current_worktrees: Dict[str, str] = {}  # branch -> path
    
    def initialize(
        self,
        github_token: str,
        repo_owner: str,
        repo_name: str,
        local_repo_path: str
    ):
        """Initialize all components."""
        self.logger.info(f"Initializing AutoDev for {repo_owner}/{repo_name}")
        
        # GitHub client
        self.github = GitHubClient(token=github_token, owner=repo_owner, repo=repo_name)
        
        # State manager
        self.state_manager = StateManager()
        
        # Task queue
        max_parallel = self.config.get("agents", {}).get("max_parallel", 4)
        self.task_queue = TaskQueue(max_parallel=max_parallel)
        
        # Worktree manager
        self.worktree_manager = WorktreeManager(local_repo_path)
        
        # Initiator agent
        self.initiator = InitiatorAgent(self.config)
        self.initiator.initialize(self.github, self.state_manager)
        
        # Coder agents
        for i in range(max_parallel):
            agent = CoderAgent(f"coder_{i+1}", self.config)
            agent.initialize(self.github)
            self.coder_agents.append(agent)
        
        # Researcher agent
        self.researcher = ResearcherAgent(self.config)
        
        self.logger.info("Initialization complete")
    
    def run_issue(self, issue_number: int) -> Dict[str, Any]:
        """Run AutoDev on a GitHub issue."""
        self.logger.info(f"Processing issue #{issue_number}")
        
        # Step 1: Fetch issue
        issue = self.github.get_issue(issue_number)
        
        # Step 2: Create task plan
        plan = self.state_manager.create_plan(issue, f"{self.github.owner}/{self.github.repo}")
        self.logger.info(f"Created plan with {plan['metadata']['total_subtasks']} subtasks")
        
        # Step 3: Execute subtasks
        return self._execute_subtasks(plan)
    
    def _execute_subtasks(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute all subtasks with parallelization."""
        self.logger.info("Starting subtask execution")
        
        # Get pending subtasks
        pending = self.state_manager.get_pending_subtasks()
        
        # Group by feature for parallel execution
        features = {}
        for subtask in pending:
            feature_id = subtask.get("feature_id", "default")
            if feature_id not in features:
                features[feature_id] = []
            features[feature_id].append(subtask)
        
        # Execute each feature's subtasks
        for feature_id, subtasks in features.items():
            self._execute_feature(feature_id, subtasks)
        
        # Check completion
        if self.state_manager.is_complete():
            self.logger.info("All subtasks completed!")
            return {"status": "complete", "plan": self.state_manager.current_plan}
        else:
            # Check for failed subtasks that need research
            failed = self.state_manager.get_failed_subtasks()
            if failed:
                self._handle_failures(failed)
            
            return {"status": "partial", "plan": self.state_manager.current_plan}
    
    def _execute_feature(self, feature_id: str, subtasks: List[Dict[str, Any]]):
        """Execute subtasks for a single feature."""
        # Create worktree for this feature
        branch_name = f"feature/{feature_id}"
        
        try:
            worktree_path = self.worktree_manager.create_worktree(branch_name)
            self.current_worktrees[feature_id] = str(worktree_path)
        except Exception as e:
            self.logger.error(f"Failed to create worktree: {e}")
            return
        
        # Execute subtasks
        for subtask in subtasks:
            self._execute_subtask(subtask, worktree_path)
    
    def _execute_subtask(self, subtask: Dict[str, Any], worktree_path: Path):
        """Execute a single subtask."""
        subtask_id = subtask["id"]
        description = subtask["description"]
        
        self.logger.info(f"Executing {subtask_id}: {description}")
        
        # Update status
        self.state_manager.update_subtask(subtask_id, status="in_progress")
        
        # Get available coder agent
        agent = self._get_available_agent()
        if not agent:
            self.logger.warning("No coder agents available")
            return
        
        # Execute
        result = agent.execute_subtask(subtask, str(worktree_path))
        
        # Update status
        if result["status"] == "completed":
            self.state_manager.update_subtask(subtask_id, status="completed")
        else:
            # Increment attempts
            attempts = subtask.get("attempts", 0) + 1
            if attempts >= self.config.get("research", {}).get("trigger_after_failures", 3):
                self.state_manager.update_subtask(subtask_id, status="failed", research_needed=True)
            else:
                self.state_manager.update_subtask(subtask_id, status="pending", error=result.get("error"))
    
    def _get_available_agent(self) -> Optional[CoderAgent]:
        """Get an available coder agent."""
        for agent in self.coder_agents:
            if agent.current_subtask is None:
                return agent
        return None
    
    def _handle_failures(self, failed_subtasks: List[Dict[str, Any]]):
        """Handle failed subtasks - trigger research."""
        self.logger.info(f"Handling {len(failed_subtasks)} failed subtasks")
        
        for subtask in failed_subtasks:
            error = subtask.get("error", "Unknown error")
            self.logger.info(f"Researching: {subtask['id']} - {error[:100]}")
            
            # Run research
            research = self.researcher.research_error(error)
            
            self.logger.info(f"Research complete. Confidence: {research['confidence']:.2f}")
            # TODO: Feed research back to coder for retry
            # self.coder.retry_with_context(subtask_id=subtask['id'], research=research)
    
    def create_pull_request(self, branch: str = "main") -> Dict[str, Any]:
        """Create a PR after all tasks complete."""
        if not self.state_manager.is_complete():
            raise RuntimeError("Cannot create PR: tasks not complete")
        
        # Get summary
        summary = self.state_manager.get_summary()
        
        # Create PR title and body
        title = f"AutoDev: {summary['issue']}"
        body = self._generate_pr_body(summary)
        
        # Create PR
        pr = self.github.create_pull_request(
            title=title,
            body=body,
            head=branch,
            base="main"
        )
        
        self.logger.info(f"Created PR #{pr['number']}")
        return pr
    
    def _generate_pr_body(self, summary: Dict[str, Any]) -> str:
        """Generate PR body from task summary."""
        body = f"""# AutoDev Task Summary

**Issue:** {summary['issue']}
**Project:** {summary['project']}

## Progress
- Total: {summary['metadata']['total_subtasks']}
- Completed: {summary['metadata']['completed']}
- Failed: {summary['metadata']['failed']}

## Features
"""
        for feature in summary['features']:
            body += f"- **{feature['name']}**: {feature['status']} ({feature['subtask_count']} subtasks)\n"
        
        body += "\---\n*Generated by AutoDev*"
        return body
    
    def cleanup(self):
        """Clean up worktrees after completion."""
        self.logger.info("Cleaning up worktrees")
        
        for feature_id, path in self.current_worktrees.items():
            try:
                self.worktree_manager.cleanup_worktree(f"feature/{feature_id}")
            except Exception as e:
                self.logger.error(f"Failed to cleanup {feature_id}: {e}")


def run_autodev(
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    github_token: str,
    local_repo_path: str,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Main entry point for AutoDev."""
    # Setup logging
    setup_logger()
    
    # Default config
    if config is None:
        config = {
            "agents": {"max_parallel": 4, "timeout_per_subtask": 600},
            "research": {"trigger_after_failures": 3, "max_research_time": 300},
            "github": {"auto_create_pr": True}
        }
    
    # Create orchestrator
    orchestrator = AutoDevOrchestrator(config)
    orchestrator.initialize(github_token, repo_owner, repo_name, local_repo_path)
    
    # Run
    try:
        result = orchestrator.run_issue(issue_number)
        
        # Create PR if complete
        if result["status"] == "complete" and config.get("github", {}).get("auto_create_pr"):
            pr = orchestrator.create_pull_request()
            result["pr"] = pr
        
        return result
    finally:
        orchestrator.cleanup()
