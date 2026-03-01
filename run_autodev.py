#!/usr/bin/env python3
"""Complete AutoDev orchestrator - runs the full pipeline."""
import argparse
import sys
import os
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from config.loader import load_config
from core.github_client import GitHubClient
from core.state_manager import StateManager
from core.task_decomposer import TaskDecomposer
from core.parallel_executor import ParallelExecutor
from core.session_history import SessionHistory
from core.pr_manager import PRManager
from agents.researcher.agent import ResearcherAgent
from utils.logger import setup_logger


def run_autodev(
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    github_token: str,
    local_repo_path: str,
    max_agents: int = 4
):
    """Run AutoDev end-to-end on a GitHub issue."""
    logger = setup_logger()
    logger.info(f"Starting AutoDev for {repo_owner}/{repo_name} issue #{issue_number}")
    
    # Initialize components
    github = GitHubClient(token=github_token, owner=repo_owner, repo=repo_name)
    state_manager = StateManager()
    session_history = SessionHistory()
    pr_manager = PRManager(github)
    researcher = ResearcherAgent()
    
    # Step 1: Fetch issue
    logger.info("Fetching issue from GitHub...")
    issue = github.get_issue(issue_number)
    logger.info(f"Issue: {issue['title']}")
    
    # Step 2: Create task plan
    logger.info("Decomposing issue into tasks...")
    decomposer = TaskDecomposer()
    plan = decomposer.decompose_issue(issue)
    state_manager.current_plan = plan
    state_manager.save()
    
    # Initialize session
    session_history.init_session(
        issue=f"#{issue_number}: {issue['title']}",
        total_subtasks=plan['metadata']['total_subtasks']
    )
    
    logger.info(f"Created plan with {plan['metadata']['total_subtasks']} subtasks")
    logger.info(f"Features: {[f['name'] for f in plan['features']]}")
    
    # Step 3: Execute in parallel using OpenCode
    logger.info(f"Starting parallel execution with {max_agents} agents...")
    executor = ParallelExecutor(local_repo_path, max_agents=max_agents)
    
    # Build tasks for each feature
    tasks = []
    for feature in plan['features']:
        branch_name = f"feature/{feature['id']}"
        
        # Build prompt for this feature
        prompt = f"""Implement the following feature: {feature['name']}

Requirements:
"""
        for subtask in feature.get('subtasks', []):
            prompt += f"- {subtask.get('description', '')}\n"
        
        prompt += """
Write comprehensive code and tests. Commit your changes with descriptive messages."""
        
        tasks.append({
            'branch': branch_name,
            'prompt': prompt,
            'task_id': feature['id'],
            'description': feature['name']
        })
    
    # Run tasks in parallel
    logger.info(f"Running {len(tasks)} features in parallel...")
    results = executor.run_parallel(tasks, wait=True, check_interval=15)
    
    # Check results
    logger.info("Checking results...")
    for result in results:
        status = "✅" if result.status == "completed" else "❌"
        logger.info(f"  {status} {result.agent_id}: {result.task_id}")
    
    # Update state
    completed = sum(1 for r in results if r.status == "completed")
    logger.info(f"Completed: {completed}/{len(results)} features")
    
    # Step 4: Create PR
    logger.info("Creating pull request...")
    try:
        # Get first feature branch for PR
        first_branch = tasks[0]['branch']
        
        body = f"""## AutoDev Generated PR

**Issue:** #{issue_number}: {issue['title']}

### Features Implemented
"""
        for feature in plan['features']:
            body += f"- {feature['name']}\n"
        
        pr = pr_manager.create_pr(
            branch=first_branch,
            title=f"AutoDev: {issue['title']}",
            body=body
        )
        
        logger.info(f"PR created: {pr['html_url']}")
    except Exception as e:
        logger.error(f"Failed to create PR: {e}")
    
    # Close session
    session_history.close_session(status="completed")
    
    # Cleanup
    executor.cleanup_worktrees()
    
    logger.info("AutoDev execution complete!")
    return {
        "issue": issue['title'],
        "features": len(plan['features']),
        "completed": completed,
        "total": len(results)
    }


def main():
    parser = argparse.ArgumentParser(description="AutoDev - Autonomous Coding Agent")
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument("--token", help="GitHub token (or GITHUB_TOKEN env)")
    parser.add_argument("--local-repo", required=True, help="Local repo path")
    parser.add_argument("--agents", type=int, default=4, help="Max parallel agents")
    
    args = parser.parse_args()
    
    # Get token
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GitHub token required. Set --token or GITHUB_TOKEN")
        sys.exit(1)
    
    # Parse repo
    owner, repo = args.repo.split("/")
    
    # Run
    result = run_autodev(
        repo_owner=owner,
        repo_name=repo,
        issue_number=args.issue,
        github_token=token,
        local_repo_path=args.local_repo,
        max_agents=args.agents
    )
    
    print(f"\n✅ AutoDev Complete!")
    print(f"   Issue: {result['issue']}")
    print(f"   Features: {result['completed']}/{result['total']}")


if __name__ == "__main__":
    main()
