"""
Configuration management for RO Design MCP Server.

This module handles loading and merging configuration from:
1. Default YAML files in config/
2. Environment variables
3. Runtime overrides
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Handles configuration loading and management."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize the configuration loader.
        
        Args:
            config_dir: Directory containing config files. 
                       Defaults to config/ in project root.
        """
        if config_dir is None:
            # Find project root (where server.py is)
            current_file = Path(__file__)
            project_root = current_file.parent.parent
            config_dir = project_root / "config"
        
        self.config_dir = Path(config_dir)
        self._config: Dict[str, Any] = {}
        self._loaded = False
    
    def load(self, config_files: Optional[list] = None) -> Dict[str, Any]:
        """
        Load configuration from YAML files.
        
        Args:
            config_files: List of config files to load. 
                         If None, loads all .yaml files in config_dir.
        
        Returns:
            Merged configuration dictionary.
        """
        if config_files is None:
            # Load all YAML files in config directory
            config_files = list(self.config_dir.glob("*.yaml"))
        else:
            # Convert to Path objects
            config_files = [self.config_dir / f if isinstance(f, str) else f 
                           for f in config_files]
        
        # Load each file and merge
        for config_file in config_files:
            if config_file.exists():
                logger.debug(f"Loading config from {config_file}")
                with open(config_file, 'r') as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self._config = self._deep_merge(self._config, file_config)
            else:
                logger.warning(f"Config file not found: {config_file}")
        
        # Apply environment variable overrides
        self._apply_env_overrides()
        
        self._loaded = True
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., "membrane_properties.brackish.A_w")
            default: Default value if key not found
        
        Returns:
            Configuration value or default.
        """
        if not self._loaded:
            self.load()
        
        # Navigate nested dictionary using dot notation
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value using dot notation.
        
        Args:
            key: Configuration key
            value: Value to set
        """
        if not self._loaded:
            self.load()
        
        keys = key.split('.')
        config = self._config
        
        # Navigate to parent dictionary
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
    
    def _deep_merge(self, dict1: Dict, dict2: Dict) -> Dict:
        """
        Deep merge two dictionaries.
        
        Args:
            dict1: Base dictionary
            dict2: Dictionary to merge into dict1
        
        Returns:
            Merged dictionary.
        """
        result = dict1.copy()
        
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides to configuration."""
        # Environment variables should be prefixed with RO_DESIGN_
        prefix = "RO_DESIGN_"
        
        for env_key, env_value in os.environ.items():
            if env_key.startswith(prefix):
                # Convert RO_DESIGN_MEMBRANE_PROPERTIES_BRACKISH_A_W to
                # membrane_properties.brackish.A_w
                config_key = env_key[len(prefix):].lower().replace('_', '.')
                
                # Try to convert to appropriate type
                try:
                    # Check boolean first (before numeric checks)
                    if env_value.lower() in ('true', 'false'):
                        value = env_value.lower() == 'true'
                    # Try float
                    elif '.' in env_value or 'e' in env_value.lower():
                        value = float(env_value)
                    # Then int
                    elif env_value.isdigit() or (env_value.startswith('-') and env_value[1:].isdigit()):
                        value = int(env_value)
                    # Otherwise string
                    else:
                        value = env_value
                except ValueError:
                    value = env_value
                
                logger.debug(f"Overriding {config_key} with {value} from environment")
                
                # Apply the override directly without using set() to avoid recursion
                keys = config_key.split('.')
                config = self._config
                
                # Navigate to parent dictionary
                for k in keys[:-1]:
                    if k not in config:
                        config[k] = {}
                    config = config[k]
                
                # Set the value
                config[keys[-1]] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """Return the full configuration as a dictionary."""
        if not self._loaded:
            self.load()
        return self._config.copy()


# Global configuration instance
_config_loader = ConfigLoader()


def load_config(config_files: Optional[list] = None) -> Dict[str, Any]:
    """
    Load configuration (convenience function).
    
    Args:
        config_files: Optional list of config files to load
    
    Returns:
        Configuration dictionary.
    """
    return _config_loader.load(config_files)


def get_config(key: str, default: Any = None) -> Any:
    """
    Get a configuration value (convenience function).
    
    Args:
        key: Configuration key using dot notation
        default: Default value if not found
    
    Returns:
        Configuration value.
    """
    return _config_loader.get(key, default)


def set_config(key: str, value: Any) -> None:
    """
    Set a configuration value (convenience function).
    
    Args:
        key: Configuration key using dot notation
        value: Value to set
    """
    _config_loader.set(key, value)