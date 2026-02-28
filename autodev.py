#!/usr/bin/env python3
"""AutoDev - Autonomous Coding Agent Harness

Usage:
    python autodev.py --repo owner/repo --issue 123
    python autodev.py --repo owner/repo --issue 123 --run-orchestrator --local-repo /path/to/repo
    python autodev.py --resume subtask_plan.json
"""
import argparse
import sys
import os
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config.loader import load_config
from core.github_client import GitHubClient
from core.state_manager import StateManager
from core.orchestrator import AutoDevOrchestrator
from agents.initiator.agent import InitiatorAgent
from utils.logger import setup_logger


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="AutoDev - Autonomous Coding Agent Harness"
    )
    
    parser.add_argument(
        "--repo", "-r",
        help="Repository in format 'owner/repo'"
    )
    
    parser.add_argument(
        "--issue", "-i",
        type=int,
        help="GitHub issue number"
    )
    
    parser.add_argument(
        "--resume",
        help="Resume from a saved task plan"
    )
    
    parser.add_argument(
        "--config", "-c",
        help="Path to custom config file"
    )
    
    parser.add_argument(
        "--token", "-t",
        help="GitHub token (or set GITHUB_TOKEN env var)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    parser.add_argument(
        "--log-file",
        help="Path to log file"
    )
    
    parser.add_argument(
        "--run-orchestrator", "-o",
        action="store_true",
        help="Run full orchestrator (requires --local-repo)"
    )
    
    parser.add_argument(
        "--local-repo",
        help="Local path to the repository (required for orchestrator)"
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    # Setup logging
    log_level = 10 if args.verbose else 20  # DEBUG if verbose
    logger = setup_logger(level=log_level, log_file=args.log_file)
    
    logger.info("AutoDev v0.1.0 starting...")
    
    # Validate arguments
    if not args.repo and not args.resume:
        logger.error("Must provide either --repo or --resume")
        print(__doc__)
        sys.exit(1)
    
    # Load configuration
    repo_name = args.repo.split("/")[1] if args.repo and "/" in args.repo else None
    try:
        config = load_config(args.config, repo_name)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)
    
    # Initialize GitHub client
    token = args.token or config.get("github", {}).get("token")
    if not token:
        logger.warning("No GitHub token provided. Set --token or GITHUB_TOKEN")
    
    # Get repo info
    if args.repo:
        owner, repo_name = args.repo.split("/")
    else:
        owner = None
        repo_name = None
    
    github = GitHubClient(token=token, owner=owner, repo=repo_name)
    
    # Initialize state manager
    state_manager = StateManager()
    
    # Initialize initiator agent
    initiator = InitiatorAgent(config)
    initiator.initialize(github, state_manager)
    
    # Main execution
    if args.run_orchestrator:
        # Run full orchestrator
        if not args.local_repo:
            logger.error("--local-repo required for orchestrator mode")
            sys.exit(1)
        
        if not args.repo or not args.issue:
            logger.error("--repo and --issue required for orchestrator mode")
            sys.exit(1)
        
        if not token:
            logger.error("GitHub token required for orchestrator. Set --token or GITHUB_TOKEN")
            sys.exit(1)
        
        logger.info(f"Running orchestrator for {owner}/{repo_name} issue #{args.issue}")
        
        orchestrator = AutoDevOrchestrator(config)
        orchestrator.initialize(token, owner, repo_name, args.local_repo)
        
        try:
            result = orchestrator.run_issue(args.issue)
            logger.info(f"Orchestrator result: {result['status']}")
            
            if result.get("pr"):
                logger.info(f"PR created: {result['pr']['html_url']}")
        finally:
            orchestrator.cleanup()
    
    elif args.resume:
        # Resume from existing plan
        logger.info(f"Resuming from {args.resume}")
        try:
            state_manager.load(args.resume)
        except Exception as e:
            logger.error(f"Failed to load plan: {e}")
            sys.exit(1)
    elif args.repo and args.issue:
        # Process new issue
        logger.info(f"Processing issue #{args.issue} from {args.repo}")
        
        if not owner or not repo_name:
            logger.error("Invalid repo format. Use 'owner/repo'")
            sys.exit(1)
        
        # Set repo on GitHub client
        github.set_repo(owner, repo_name)
        
        # Run initiator
        try:
            ready_subtasks = initiator.run(args.issue, owner, repo_name)
            logger.info(f"Found {len(ready_subtasks)} ready subtasks")
            
            # Show plan summary
            summary = state_manager.get_summary()
            logger.info(f"Plan created: {summary['metadata']}")
            
        except Exception as e:
            logger.error(f"Failed to process issue: {e}")
            sys.exit(1)
    else:
        logger.error("Invalid arguments")
        print(__doc__)
        sys.exit(1)
    
    logger.info("AutoDev execution complete")


if __name__ == "__main__":
    main()
