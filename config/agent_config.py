"""Agent configuration for AutoDev."""
from typing import Optional
from dataclasses import dataclass

# Agent type choices
AGENT_CHOICES = ['opencode', 'claude-code']
DEFAULT_AGENT = 'claude-code'


@dataclass
class AgentConfig:
    """Configuration for coding agents."""
    agent_type: str  # 'opencode' or 'claude-code'
    model: str = "MiniMax-M2.5-highspeed"
    skip_permissions: bool = False  # Only for claude-code
    timeout: int = 300  # seconds
    max_retries: int = 3
    
    def __post_init__(self):
        if self.agent_type not in AGENT_CHOICES:
            raise ValueError(f"agent_type must be one of {AGENT_CHOICES}")
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AgentConfig':
        """Create from dictionary."""
        return cls(
            agent_type=data.get('agent_type', DEFAULT_AGENT),
            model=data.get('model', 'MiniMax-M2.5'),
            skip_permissions=data.get('skip_permissions', False),
            timeout=data.get('timeout', 300),
            max_retries=data.get('max_retries', 3)
        )


def get_agent_config(config: Optional[dict] = None) -> AgentConfig:
    """Get agent configuration from config dict."""
    if config is None:
        return AgentConfig(agent_type=DEFAULT_AGENT)
    
    agents_config = config.get('agents', {})
    return AgentConfig.from_dict(agents_config)
