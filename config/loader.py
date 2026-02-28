"""Configuration loader for AutoDev."""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from utils.validators import ConfigValidator


class Config:
    """AutoDev configuration manager."""
    
    DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config"
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.validator = ConfigValidator()
    
    def load(self, repo_name: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from file."""
        # Load default config
        default_path = self.DEFAULT_CONFIG_DIR / "default.yaml"
        if default_path.exists():
            with open(default_path, "r") as f:
                self.config = yaml.safe_load(f) or {}
        
        # Load repo-specific config if provided
        if repo_name:
            repo_config_path = self.DEFAULT_CONFIG_DIR / "repos" / f"{repo_name}.yaml"
            if repo_config_path.exists():
                with open(repo_config_path, "r") as f:
                    repo_config = yaml.safe_load(f) or {}
                    self._merge_config(repo_config)
        
        # Load custom config if provided
        if self.config_path:
            custom_path = Path(self.config_path)
            if custom_path.exists():
                with open(custom_path, "r") as f:
                    custom_config = yaml.safe_load(f) or {}
                    self._merge_config(custom_config)
        
        # Override with environment variables
        self._load_env_overrides()
        
        # Validate (only if repo info is provided)
        if self.config.get("repo", {}).get("owner") and self.config.get("repo", {}).get("name"):
            errors = self.validator.validate_config(self.config)
            if errors:
                raise ValueError(f"Config validation failed: {errors}")
        
        return self.config
    
    def _merge_config(self, new_config: Dict[str, Any]):
        """Deep merge new config into existing."""
        def merge(base: dict, overlay: dict):
            for key, value in overlay.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    merge(base[key], value)
                else:
                    base[key] = value
        
        merge(self.config, new_config)
    
    def _load_env_overrides(self):
        """Load configuration overrides from environment variables."""
        env_mappings = {
            "AUTODEV_GITHUB_TOKEN": ("github", "token"),
            "AUTODEV_GITHUB_OWNER": ("repo", "owner"),
            "AUTODEV_GITHUB_REPO": ("repo", "name"),
            "AUTODEV_MAX_PARALLEL": ("agents", "max_parallel"),
            "AUTODEV_TIMEOUT": ("agents", "timeout_per_subtask"),
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                # Convert to int if needed
                if env_var.startswith("AUTODEV_MAX") or env_var.startswith("AUTODEV_TIMEOUT"):
                    try:
                        value = int(value)
                    except ValueError:
                        continue
                
                # Navigate to the nested key
                current = self.config
                for key in config_path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[config_path[-1]] = value
    
    def get(self, *keys, default=None) -> Any:
        """Get a config value by nested keys."""
        current = self.config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    def set(self, value: Any, *keys):
        """Set a config value by nested keys."""
        current = self.config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value


def load_config(config_path: Optional[str] = None, repo_name: Optional[str] = None) -> Dict[str, Any]:
    """Convenience function to load configuration."""
    config = Config(config_path)
    return config.load(repo_name)
