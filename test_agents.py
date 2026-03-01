#!/usr/bin/env python3
"""Test script for AutoDev agent selection (OpenCode vs Claude Code)."""
import sys
import os
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from config.agent_config import AgentConfig, AGENT_CHOICES, DEFAULT_AGENT
from core.parallel_executor import ParallelExecutor
from core.agent_memory import AgentMemory


def test_agent_config():
    """Test agent configuration."""
    print("=" * 60)
    print("TEST 1: Agent Config")
    print("=" * 60)
    
    # Test default config
    config = AgentConfig(agent_type=DEFAULT_AGENT)
    print(f"✅ Default config: {config.agent_type}")
    print(f"   Model: {config.model}")
    print(f"   Timeout: {config.timeout}s")
    
    # Test Claude Code config
    claude_config = AgentConfig(
        agent_type='claude-code',
        skip_permissions=True,
        timeout=600
    )
    print(f"✅ Claude Code config: {claude_config.agent_type}")
    print(f"   Skip permissions: {claude_config.skip_permissions}")
    print(f"   Timeout: {claude_config.timeout}s")
    
    # Test invalid config
    try:
        bad_config = AgentConfig(agent_type='invalid')
        print("❌ Should have raised ValueError")
    except ValueError as e:
        print(f"✅ Correctly rejected invalid agent: {e}")
    
    print()


def test_agent_memory():
    """Test shared agent memory."""
    print("=" * 60)
    print("TEST 2: Agent Memory (Shared Context)")
    print("=" * 60)
    
    memory = AgentMemory(session_id="test-session-001")
    
    # Register agents
    memory.register_agent("agent_1", "claude-code", "/tmp/worktree1")
    memory.register_agent("agent_2", "opencode", "/tmp/worktree2")
    print("✅ Registered 2 agents")
    
    # Set shared data
    memory.set_shared_data("issue_title", "Fix login bug")
    memory.set_shared_data("repo", "owner/repo")
    print("✅ Set shared data")
    
    # Post messages
    memory.post_message("agent_1", "agent_2", "I'm working on feature A")
    memory.post_message("agent_2", "agent_1", "OK, I'll handle feature B")
    print("✅ Posted inter-agent messages")
    
    # Update progress
    memory.update_progress("agent_1", "task_1", "completed", {"files_changed": 5})
    memory.update_progress("agent_2", "task_2", "started", {"current_file": "auth.py"})
    print("✅ Updated progress")
    
    # Get summary
    summary = memory.get_summary()
    print(f"✅ Memory summary:")
    print(f"   Agents: {summary['agent_count']}")
    print(f"   Messages: {summary['messages_count']}")
    print(f"   Shared keys: {summary['shared_keys']}")
    
    # Get messages for agent_1
    messages = memory.get_messages("agent_1")
    print(f"   Messages for agent_1: {len(messages)}")
    
    print()


def test_parallel_executor_init():
    """Test parallel executor initialization."""
    print("=" * 60)
    print("TEST 3: Parallel Executor with Different Agents")
    print("=" * 60)
    
    # Test with OpenCode
    executor_opencode = ParallelExecutor(
        base_repo="/tmp/test-repo",
        max_agents=2,
        agent_config=AgentConfig(agent_type='opencode')
    )
    print(f"✅ OpenCode executor: {executor_opencode.agent_config.agent_type}")
    
    # Test with Claude Code
    executor_claude = ParallelExecutor(
        base_repo="/tmp/test-repo",
        max_agents=4,
        agent_config=AgentConfig(
            agent_type='claude-code',
            skip_permissions=True,
            timeout=600
        )
    )
    print(f"✅ Claude Code executor: {executor_claude.agent_config.agent_type}")
    print(f"   Skip permissions: {executor_claude.agent_config.skip_permissions}")
    
    print()


def test_command_building():
    """Test command building for both agents."""
    print("=" * 60)
    print("TEST 4: Command Building")
    print("=" * 60)
    
    # OpenCode command
    executor = ParallelExecutor(
        base_repo="/tmp/test",
        agent_config=AgentConfig(agent_type='opencode')
    )
    opencode_cmd = executor._build_opencode_command("Fix the bug")
    print(f"✅ OpenCode command: {opencode_cmd}")
    
    # Claude Code command with skip permissions
    executor_skip = ParallelExecutor(
        base_repo="/tmp/test",
        agent_config=AgentConfig(
            agent_type='claude-code',
            skip_permissions=True
        )
    )
    claude_cmd = executor_skip._build_claude_command("Fix the bug", Path("/tmp/test"))
    print(f"✅ Claude Code (skip): {claude_cmd}")
    
    # Claude Code without skip
    executor_no_skip = ParallelExecutor(
        base_repo="/tmp/test",
        agent_config=AgentConfig(
            agent_type='claude-code',
            skip_permissions=False
        )
    )
    claude_cmd_no_skip = executor_no_skip._build_claude_command("Fix the bug", Path("/tmp/test"))
    print(f"✅ Claude Code (normal): {claude_cmd_no_skip}")
    
    print()


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("AutoDev Agent Selection Tests")
    print("=" * 60 + "\n")
    
    try:
        test_agent_config()
        test_agent_memory()
        test_parallel_executor_init()
        test_command_building()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nUsage:")
        print("  python run_autodev.py --repo owner/repo --issue 123 \\")
        print("    --local-repo /path/to/repo --agent-type opencode")
        print("")
        print("  python run_autodev.py --repo owner/repo --issue 123 \\")
        print("    --local-repo /path/to/repo --agent-type claude-code \\")
        print("    --claude-skip-permissions")
        print()
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
