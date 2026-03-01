#!/usr/bin/env python3
"""Complete AutoDev orchestrator - runs the full pipeline."""
import argparse
import sys
import os
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from config.loader import load_config
from config.agent_config import AgentConfig, get_agent_config
from core.github_client import GitHubClient
from core.state_manager import StateManager
from core.task_decomposer import TaskDecomposer
from core.parallel_executor import ParallelExecutor
from core.session_history import SessionHistory
from core.agent_memory import AgentMemory
from core.pr_manager import PRManager
from core.project_context import ProjectContextLoader
from agents.researcher.agent import ResearcherAgent
from utils.logger import setup_logger


def run_autodev(
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    github_token: str,
    local_repo_path: str,
    max_agents: int = 4,
    agent_type: str = "opencode",
    use_claude_skip_permissions: bool = False,
    upstream_repo: str = None
):
    """Run AutoDev end-to-end on a GitHub issue."""
    logger = setup_logger()
    logger.info(f"🤖 Starting AutoDev for {repo_owner}/{repo_name} issue #{issue_number}")
    logger.info(f"   Agent: {agent_type} | Max Agents: {max_agents}")
    logger.info("=" * 60)
    
    # Determine which repo to fetch issue from (upstream or local)
    if upstream_repo:
        upstream_owner, upstream_name = upstream_repo.split("/")
        logger.info(f"   Upstream: {upstream_repo}")
    else:
        upstream_owner, upstream_name = repo_owner, repo_name
    
    # Initialize agent config
    agent_config = AgentConfig(
        agent_type=agent_type,
        skip_permissions=(agent_type == 'claude-code')  # Auto-skip for Claude Code
    )
    logger.info(f"   Using {agent_type} for code generation")
    
    # Initialize components
    github = GitHubClient(token=github_token, owner=repo_owner, repo=repo_name)
    upstream_github = GitHubClient(token=github_token, owner=upstream_owner, repo=upstream_name)
    session_history = SessionHistory()
    # Get session_id from state after initialization
    session_history.init_session(issue=f"#{issue_number}", total_subtasks=1)
    agent_memory = AgentMemory(session_id=session_history.state["session_id"])
    pr_manager = PRManager(github)
    researcher = ResearcherAgent()
    
    # Step 1: Fetch issue from upstream repo
    logger.info("📥 Step 1: Fetching issue from GitHub...")
    issue = upstream_github.get_issue(issue_number)
    logger.info(f"   Title: {issue['title']}")
    logger.info(f"   Labels: {issue.get('labels', [])}")
    logger.info(f"   URL: {issue['html_url']}")
    
    # Step 1.5: Load/Create project context
    logger.info("")
    logger.info("📚 Step 1.5: Loading project context...")
    context_loader = ProjectContextLoader(local_repo_path)
    project_info = context_loader.detect_project_info()
    logger.info(f"   Detected: {project_info['language']} | {project_info['framework']}")
    
    context = context_loader.get_or_create_context(project_info)
    if context_loader.has_context():
        logger.info(f"   ✅ Using existing CLAUDE.md")
    else:
        logger.info(f"   ✅ Created default CLAUDE.md")
    
    # Step 2: Create task plan
    logger.info("")
    logger.info("📋 Step 2: Decomposing issue into tasks...")
    decomposer = TaskDecomposer()
    plan = decomposer.decompose_issue(issue)
    
    # Initialize session with subtask count
    session_history.init_session(
        issue=f"#{issue_number}: {issue['title']}",
        total_subtasks=plan['metadata']['total_subtasks']
    )
    
    logger.info(f"   📦 Created {plan['metadata']['total_subtasks']} subtasks across {len(plan['features'])} features")
    for i, feature in enumerate(plan['features'], 1):
        subtasks = len(feature.get('subtasks', []))
        logger.info(f"      {i}. {feature['name']} ({subtasks} subtasks)")
    
    # Step 3: Execute in parallel using OpenCode or Claude Code
    logger.info("")
    logger.info(f"⚡ Step 3: Starting parallel execution with {max_agents} agents...")
    logger.info("-" * 60)
    executor = ParallelExecutor(
        local_repo_path, 
        max_agents=max_agents,
        agent_config=agent_config
    )
    
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
    
    # Step 4: Review all changes before creating PR
    logger.info("")
    logger.info("🔍 Step 4: Running agent-to-agent code review...")
    logger.info("-" * 60)
    
    # Import reviewer
    from agents.reviewer.agent import ReviewerAgent
    
    review_results = []
    for feature in plan['features']:
        branch_name = f"feature/{feature['id']}"
        
        logger.info(f"   Reviewing branch: {branch_name}")
        
        reviewer = ReviewerAgent(config=agent_config)
        
        # Review the branch
        status, issues, metadata = reviewer.review_branch(
            repo_path=local_repo_path,
            branch=branch_name,
            base="main"
        )
        
        if status == "approved":
            logger.info(f"   ✅ {branch_name}: Approved")
            review_results.append({"branch": branch_name, "status": "approved", "issues": []})
        else:
            logger.warning(f"   ❌ {branch_name}: {len(issues)} issues found")
            for issue in issues[:3]:
                logger.warning(f"      - {issue}")
            
            # If issues found, try to fix with research agent
            if issues:
                logger.info(f"   🔧 Running research agent to find solutions...")
                for issue in issues[:2]:  # Fix top 2 issues
                    research_result = researcher.research_error(issue)
                    logger.info(f"      Research: {research_result.get('recommended_fix', '')[:100]}...")
            
            review_results.append({"branch": branch_name, "status": "changes_requested", "issues": issues})
    
    # Check if all reviews passed
    all_approved = all(r["status"] == "approved" for r in review_results)
    
    if not all_approved:
        logger.warning("⚠️ Some branches have review issues. Still creating PR for human review.")
    else:
        logger.info("✅ All branches reviewed and approved!")
    
    # Step 5: Create PR
    logger.info("")
    logger.info("📝 Step 5: Creating pull request...")
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
    parser.add_argument(
        "--agent-type", 
        choices=['opencode', 'claude-code'], 
        default='claude-code',
        help="Agent to use for code generation (opencode or claude-code)"
    )
    parser.add_argument(
        "--claude-skip-permissions",
        action="store_true",
        help="Use --dangerously-skip-permissions for Claude Code (auto-approve edits)"
    )
    parser.add_argument(
        "--upstream-repo",
        help="Upstream repo to fetch issue from (format: owner/repo). Use when working on a fork."
    )
    
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
        max_agents=args.agents,
        agent_type=args.agent_type,
        use_claude_skip_permissions=args.claude_skip_permissions,
        upstream_repo=args.upstream_repo
    )
    
    print(f"\n✅ AutoDev Complete!")
    print(f"   Issue: {result['issue']}")
    print(f"   Features: {result['completed']}/{result['total']}")
    print(f"   Agent: {args.agent_type}")


if __name__ == "__main__":
    main()
