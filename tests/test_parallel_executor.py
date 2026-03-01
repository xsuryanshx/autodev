"""Tests for ParallelExecutor."""
import pytest
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parallel_executor import ParallelExecutor, AgentResult
from config.agent_config import AgentConfig


class TestParallelExecutorInit:
    """Test ParallelExecutor initialization."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp, ignore_errors=True)
    
    def test_default_init(self, temp_dir):
        """Test default initialization."""
        executor = ParallelExecutor(base_repo=temp_dir)
        
        assert executor.max_agents == 4
        assert executor.base_repo == Path(temp_dir)
    
    def test_init_with_custom_agents(self, temp_dir):
        """Test initialization with custom agent count."""
        executor = ParallelExecutor(base_repo=temp_dir, max_agents=8)
        assert executor.max_agents == 8
    
    def test_init_with_agent_config(self, temp_dir):
        """Test initialization with agent config."""
        config = AgentConfig(agent_type='claude-code', skip_permissions=True)
        executor = ParallelExecutor(base_repo=temp_dir, agent_config=config)
        
        assert executor.agent_config.agent_type == 'claude-code'
        assert executor.agent_config.skip_permissions is True


class TestAgentResult:
    """Test AgentResult dataclass."""
    
    def test_agent_result_creation(self):
        """Test creating AgentResult."""
        result = AgentResult(
            agent_id="agent_1",
            task_id="task_1",
            status="running",
            output="Started"
        )
        
        assert result.agent_id == "agent_1"
        assert result.task_id == "task_1"
        assert result.status == "running"
        assert result.output == "Started"
        assert result.error is None
    
    def test_agent_result_with_error(self):
        """Test AgentResult with error."""
        result = AgentResult(
            agent_id="agent_1",
            task_id="task_1",
            status="failed",
            output="",
            error="Something went wrong",
            exit_code=1
        )
        
        assert result.status == "failed"
        assert result.error == "Something went wrong"
        assert result.exit_code == 1


class TestCommandBuilding:
    """Test command building methods."""
    
    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with OpenCode config."""
        config = AgentConfig(agent_type='opencode')
        return ParallelExecutor(base_repo=str(tmp_path), agent_config=config)
    
    @pytest.fixture
    def claude_executor(self, tmp_path):
        """Create executor with Claude Code config."""
        config = AgentConfig(agent_type='claude-code', skip_permissions=False)
        return ParallelExecutor(base_repo=str(tmp_path), agent_config=config)
    
    @pytest.fixture
    def claude_skip_executor(self, tmp_path):
        """Create executor with Claude Code skip permissions."""
        config = AgentConfig(agent_type='claude-code', skip_permissions=True)
        return ParallelExecutor(base_repo=str(tmp_path), agent_config=config)
    
    def test_build_opencode_command(self, executor):
        """Test building OpenCode command."""
        cmd = executor._build_opencode_command("Fix the bug")
        
        assert cmd[0] == "opencode"
        assert cmd[1] == "run"
        assert cmd[2] == "--print-logs"
        assert cmd[3] == "Fix the bug"
    
    def test_build_claude_command_normal(self, claude_executor):
        """Test building Claude Code command without skip."""
        cmd = claude_executor._build_claude_command("Fix the bug", Path("/tmp/test"))
        
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "Fix the bug" in cmd
        assert "--dangerously-skip-permissions" not in cmd
    
    def test_build_claude_command_skip(self, claude_skip_executor):
        """Test building Claude Code command with skip."""
        cmd = claude_skip_executor._build_claude_command("Fix the bug", Path("/tmp/test"))
        
        assert cmd[0] == "claude"
        assert "--dangerously-skip-permissions" in cmd
        assert "-p" in cmd
