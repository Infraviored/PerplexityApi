"""
Configuration management for Perplexity.ai automation
"""
import json
import os
import logging


class Config:
    """Configuration manager for Perplexity.ai Automation"""
    
    def __init__(self, config_path=None):
        """
        Initialize configuration
        
        Args:
            config_path (str, optional): Path to config.json file
        """
        if config_path is None:
            # Default to config.json in project root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, 'config.json')
        
        self.config_path = config_path
        self._config = {}
        self.load()
    
    def load(self):
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    self._config = json.load(f)
            else:
                # Use defaults
                self._config = self._get_defaults()
                logging.warning(f"Config file not found at {self.config_path}, using defaults")
        except Exception as e:
            logging.error(f"Error loading configuration: {e}")
            self._config = self._get_defaults()
    
    def _get_defaults(self):
        """Get default configuration"""
        return {
            "browser": {
                "perplexity_url": "https://www.perplexity.ai/?login-source=signupButton&login-new=false",
                "user_data_dir": "~/.perplexity-browser-profile",
                "headless": False,
                "browser_load_wait_seconds": 5,
                "chrome_driver_path": None,
                "login_detect_timeout_seconds": 45
            },
            "perplexity": {
                "default_model": "Claude Sonnet 4.5",
                "default_reasoning": True,
                "question_input_timeout": 10,
                "response_wait_timeout": 300,
                "element_wait_timeout": 30
            }
        }
    
    def get(self, section, key=None):
        """
        Get configuration value
        
        Args:
            section (str): Configuration section
            key (str, optional): Configuration key within section
        
        Returns:
            Configuration value, or None if not found
        """
        if section not in self._config:
            return None
        
        if key is None:
            return self._config[section]
        
        return self._config[section].get(key)


def load_config(config_path=None):
    """Load and return a Config instance"""
    return Config(config_path)

