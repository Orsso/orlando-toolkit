from __future__ import annotations

"""Central logging configuration for Orlando Toolkit.

Import and call :func:`setup_logging` at application start-up.
"""

import logging
import os
import logging.config

__all__ = ["setup_logging"]

def setup_logging() -> None:
    """Configure logging for the application using a dictionary configuration."""
    log_dir = os.environ.get("ORLANDO_LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    LOGGING_CONFIG = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'default',
                'level': 'INFO',
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'default',
                'filename': log_file,
                'maxBytes': 1024 * 1024 * 5,  # 5 MB
                'backupCount': 2,
                'level': 'DEBUG',
            },
        },
        'loggers': {
            'orlando_toolkit.core.generators': {
                'level': 'DEBUG',
                'handlers': ['file'],
                'propagate': False,
            },
            'PIL': {
                'level': 'INFO',
                'handlers': ['file'],
                'propagate': False,
            },
        },
        'root': {
            'level': 'INFO',
            'handlers': ['console', 'file'],
        },
    }

    logging.config.dictConfig(LOGGING_CONFIG)
    logging.info("===== Logging initialised (dictConfig) =====") 