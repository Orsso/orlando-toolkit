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

    # Apply environment-driven debug overrides (module-specific), standard and maintainable
    _apply_debug_overrides()


def _setup_minimal_logging(log_file: str) -> None:
    """Set up minimal console-only logging when config is unavailable."""
    minimal_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'simple': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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
        # Provide a module logger entry so we can flip it via env even in minimal mode
        'loggers': {
            'orlando_toolkit.core.services.structure_editing_service': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            }
        }
    }
    
    logging.config.dictConfig(minimal_config)
    logging.error("===== Logging initialised with minimal fallback (config error) =====") 


def _apply_debug_overrides() -> None:
    """Apply environment-driven module-specific debug overrides.

    Supports:
    - ORLANDO_DEBUG_MOVEMENT=true  -> DEBUG for movement service
    - ORLANDO_DEBUG_MODULES=comma,separated,logger,names -> DEBUG for listed loggers
    """
    try:
        debug_movement = os.environ.get('ORLANDO_DEBUG_MOVEMENT', '').strip().lower() in {'1', 'true', 'yes', 'on'}
        extra_modules = os.environ.get('ORLANDO_DEBUG_MODULES', '').strip()
        targets = []
        if debug_movement:
            targets.append('orlando_toolkit.core.services.structure_editing_service')
            targets.append('orlando_toolkit.ui.widgets.structure_tree_widget')  # Also debug neighbor resolution
        if extra_modules:
            targets.extend([m.strip() for m in extra_modules.split(',') if m.strip()])
        if not targets:
            return
        for name in targets:
            logger = logging.getLogger(name)
            logger.setLevel(logging.DEBUG)
            # Ensure at least one handler emits DEBUG for this logger
            has_debug_handler = False
            for h in logger.handlers:
                try:
                    if (getattr(h, 'level', logging.NOTSET) == logging.NOTSET) or (h.level <= logging.DEBUG):
                        has_debug_handler = True
                        break
                except Exception:
                    continue
            if not has_debug_handler:
                h = logging.StreamHandler()
                h.setLevel(logging.DEBUG)
                fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                h.setFormatter(fmt)
                logger.addHandler(h)
            logger.info("Debug override active for logger '%s'", name)
    except Exception as exc:
        # Don't crash the app because of logging
        print(f"Warning: failed to apply debug overrides: {exc}")
