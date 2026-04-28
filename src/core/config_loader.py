"""Configuration Loader - Handles YAML config files"""
import yaml
import os
from typing import Dict, Any

class ConfigLoader:
    def __init__(self, config_path: str = "config/system_config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load YAML config file"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        return config
    
    def get(self, key: str, default=None) -> Any:
        """Get config value by dot notation. E.g., 'power_system.base_power_mva'"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value
    
    def get_all(self) -> Dict[str, Any]:
        """Get entire config"""
        return self.config
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire section of config"""
        return self.config.get(section, {})

# Global config instance
_config = None

def get_config(config_path: str = "config/system_config.yaml") -> ConfigLoader:
    """Get or create global config instance"""
    global _config
    if _config is None:
        _config = ConfigLoader(config_path)
    return _config
