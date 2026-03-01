"""Tests for AgentConfig."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.agent_config import AgentConfig, get_agent_config, AGENT_CHOICES, DEFAULT_AGENT


class TestAgentConfig:
    """Test AgentConfig class."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = AgentConfig(agent_type=DEFAULT_AGENT)
        assert config.agent_type == 'opencode'
        assert config.model == 'MiniMax-M2.5'
        assert config.timeout == 300
        assert config.skip_permissions is False
        assert config.max_retries == 3
    
    def test_claude_code_config(self):
        """Test Claude Code configuration."""
        config = AgentConfig(
            agent_type='claude-code',
            skip_permissions=True,
            timeout=600
        )
        assert config.agent_type == 'claude-code'
        assert config.skip_permissions is True
        assert config.timeout == 600
    
    def test_invalid_agent_type(self):
        """Test invalid agent type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AgentConfig(agent_type='invalid')
        assert 'must be one of' in str(exc_info.value)
    
    def test_from_dict(self):
        """Test creating config from dict."""
        data = {
            'agent_type': 'claude-code',
            'model': 'Claude-3',
            'skip_permissions': True,
            'timeout': 500,
            'max_retries': 5
        }
        config = AgentConfig.from_dict(data)
        assert config.agent_type == 'claude-code'
        assert config.model == 'Claude-3'
        assert config.skip_permissions is True
        assert config.timeout == 500
        assert config.max_retries == 5
    
    def test_from_dict_defaults(self):
        """Test from_dict uses defaults for missing keys."""
        config = AgentConfig.from_dict({})
        assert config.agent_type == DEFAULT_AGENT
        assert config.timeout == 300


class TestGetAgentConfig:
    """Test get_agent_config function."""
    
    def test_none_config(self):
        """Test with None config."""
        config = get_agent_config(None)
        assert config.agent_type == DEFAULT_AGENT
    
    def test_with_agents_config(self):
        """Test with agents config."""
        config = get_agent_config({
            'agents': {
                'agent_type': 'claude-code',
                'timeout': 600
            }
        })
        assert config.agent_type == 'claude-code'
        assert config.timeout == 600
