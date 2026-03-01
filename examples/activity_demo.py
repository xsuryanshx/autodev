"""Demo of Activity Logger - shows how to track all actions."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.activity_logger import ActivityLogger, EventType

def demo():
    """Demonstrate the activity logger."""
    
    print("🎯 AutoDev Activity Logger Demo\n")
    
    # Create logger
    logger = ActivityLogger(repo="xsuryanshx/demo-app", log_dir="/tmp/autodev_logs")
    
    # Demo: Simulate a coding session
    print("1. Session Start")
    logger.session_start(issue_number=1, issue_title="Add user authentication")
    
    print("2. Fetching Issue")
    logger.issue_fetched(
        issue_number=1,
        title="Add user authentication",
        labels=["feature", "security"]
    )
    
    print("3. Parsing Issue")
    logger.issue_parsed(issue_number=1, features=3, subtasks=8)
    
    print("4. Spawning Agents")
    logger.agent_spawned(agent_id="coder_1", agent_type="coder", worktree="/path/to/worktree")
    logger.agent_spawned(agent_id="coder_2", agent_type="coder", worktree="/path/to/worktree2")
    
    print("5. Creating Tasks")
    logger.task_created(task_id="task_1", description="Create User model", feature="User Model")
    logger.task_created(task_id="task_2", description="Create auth endpoints", feature="Auth API")
    
    print("6. Starting Task")
    logger.task_started(task_id="task_1", agent_id="coder_1")
    
    print("7. LLM Calls (with token tracking)")
    call_id = logger.llm_call_start(
        prompt="Write a User model with email and password fields...",
        model="gpt-4o"
    )
    logger.llm_call_end(
        call_id=call_id,
        model="gpt-4o",
        prompt_tokens=150,
        completion_tokens=300,
        latency_ms=2500,
        success=True
    )
    
    print("8. Writing Code")
    logger.code_written(file_path="models/user.py", lines=50, action="created")
    logger.code_written(file_path="tests/test_user.py", lines=30, action="created")
    
    print("9. Git Operations")
    logger.git_commit(branch="feature/auth", message="feat: add user model", files_changed=3)
    logger.git_push(branch="feature/auth")
    
    print("10. Task Completed")
    logger.task_completed(task_id="task_1", duration_seconds=45.2)
    
    print("11. Creating PR")
    logger.git_pr_created(pr_number=5, title="feat: add user authentication", branch="feature/auth")
    
    print("12. Session End")
    logger.session_end(status="completed")
    
    # Get summary
    summary = logger.get_summary()
    print("\n📊 Session Summary:")
    print(f"   Session ID: {summary['session_id']}")
    print(f"   Total Events: {summary['events']}")
    print(f"   Tasks: {summary['tasks']['completed']}/{summary['tasks']['created']}")
    print(f"   LLM Calls: {summary['llm']['calls']}")
    print(f"   Tokens Used: {summary['llm']['tokens']:,}")
    print(f"   Commits: {summary['commits']}")
    print(f"   Duration: {summary['duration']:.1f}s")
    
    # Close logger
    logger.close()
    
    print(f"\n✅ Logs saved to: /tmp/autodev_logs/")
    print(f"   - events_{logger.session_id}.jsonl")
    print(f"   - trajectory_{logger.session_id}.json")
    
    return logger.session_id


if __name__ == "__main__":
    session_id = demo()
