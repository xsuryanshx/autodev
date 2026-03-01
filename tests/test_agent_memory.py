"""Tests for AgentMemory (shared context for parallel agents)."""
import pytest
import sys
import json
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent_memory import AgentMemory


class TestAgentMemory:
    """Test AgentMemory class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp)
    
    @pytest.fixture
    def memory(self, temp_dir):
        """Create AgentMemory instance."""
        return AgentMemory(session_id="test-session", memory_dir=temp_dir)
    
    def test_init(self, memory):
        """Test memory initialization."""
        assert memory.session_id == "test-session"
        assert "session_id" in memory._context
        assert "agents" in memory._context
        assert "shared_data" in memory._context
        assert "messages" in memory._context
        assert "progress" in memory._context
    
    def test_register_agent(self, memory):
        """Test registering an agent."""
        memory.register_agent("agent_1", "claude-code", "/tmp/worktree1")
        
        agents = memory.get_all_agents()
        assert "agent_1" in agents
        assert agents["agent_1"]["type"] == "claude-code"
        assert agents["agent_1"]["worktree"] == "/tmp/worktree1"
        assert agents["agent_1"]["status"] == "running"
    
    def test_update_agent_status(self, memory):
        """Test updating agent status."""
        memory.register_agent("agent_1", "opencode", "/tmp/worktree1")
        memory.update_agent_status("agent_1", "completed", "Finished work")
        
        status = memory.get_agent_status("agent_1")
        assert status["status"] == "completed"
        assert status["last_message"] == "Finished work"
    
    def test_set_shared_data(self, memory):
        """Test setting shared data."""
        memory.set_shared_data("repo", "owner/repo")
        memory.set_shared_data("issue_number", 42)
        
        assert memory.get_shared_data("repo") == "owner/repo"
        assert memory.get_shared_data("issue_number") == 42
    
    def test_get_shared_data_default(self, memory):
        """Test getting non-existent shared data returns default."""
        result = memory.get_shared_data("nonexistent", default="default_value")
        assert result == "default_value"
    
    def test_post_message(self, memory):
        """Test posting messages between agents."""
        memory.post_message("agent_1", "agent_2", "Done with task A")
        messages = memory.get_messages()
        assert len(messages) == 1
    
    def test_update_progress(self, memory):
        """Test updating task progress."""
        memory.update_progress("agent_1", "task_1", "started", {"file": "main.py"})
        memory.update_progress("agent_1", "task_1", "completed", {"files_changed": 5})
        
        progress = memory.get_progress()
        key = "agent_1:task_1"
        assert key in progress
        assert progress[key]["status"] == "completed"
        assert progress[key]["details"]["files_changed"] == 5
    
    def test_get_summary(self, memory):
        """Test getting memory summary."""
        memory.register_agent("agent_1", "claude-code", "/tmp/w1")
        memory.register_agent("agent_2", "opencode", "/tmp/w2")
        memory.set_shared_data("key", "value")
        memory.post_message("agent_1", "all", "Hello")
        
        summary = memory.get_summary()
        assert summary["session_id"] == "test-session"
        assert summary["agent_count"] == 2
        assert summary["messages_count"] == 1
        assert summary["shared_keys"] == ["key"]
    
    def test_persistence(self, memory, temp_dir):
        """Test memory persists to disk."""
        memory.register_agent("agent_1", "claude-code", "/tmp/w1")
        memory.set_shared_data("test", "value")
        
        # Check file exists
        memory_file = Path(temp_dir) / "test-session.json"
        assert memory_file.exists()
        
        # Verify content
        with open(memory_file) as f:
            data = json.load(f)
            assert "agent_1" in data["agents"]
            assert data["shared_data"]["test"]["value"] == "value"
