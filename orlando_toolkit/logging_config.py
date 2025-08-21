from __future__ import annotations

"""Central logging configuration for Orlando Toolkit.

Import and call :func:`setup_logging` at application start-up.
"""

import logging
import os
import logging.config
from orlando_toolkit.config import ConfigManager

__all__ = ["setup_logging"]

def setup_logging() -> None:
    """Configure logging for the application using configuration from YAML files."""
    log_dir = os.environ.get("ORLANDO_LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    # Try to get logging config from ConfigManager
    try:
        config_manager = ConfigManager()
        logging_config = config_manager.get_logging_config()
        
        if logging_config and isinstance(logging_config, dict) and logging_config.get("version"):
            # Update the filename dynamically
            if "handlers" in logging_config and "file" in logging_config["handlers"]:
                logging_config["handlers"]["file"]["filename"] = log_file
            
            logging.config.dictConfig(logging_config)
            logging.info("===== Logging initialised from config files =====")
        else:
            # No valid config found, use minimal fallback
            _setup_minimal_logging(log_file)
    except Exception as exc:
        # Error loading config, fall back to minimal logging
        print(f"Error loading logging config: {exc}")
        _setup_minimal_logging(log_file)


def _setup_minimal_logging(log_file: str) -> None:
    """Set up minimal console-only logging when config is unavailable."""
    minimal_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'simple': {
                'format': '%(levelname)s - %(message)s',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'simple',
                'level': 'INFO',
            },
        },
        'root': {
            'level': 'INFO',
            'handlers': ['console'],
        },
    }
    
    logging.config.dictConfig(minimal_config)
    logging.error("===== Logging initialised with minimal fallback (config error) =====") 