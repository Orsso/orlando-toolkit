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
            # Core conversion/generation internals can be verbose; route via root handlers only
            'orlando_toolkit.core.generators': {
                'level': 'INFO',
                'propagate': True,
            },
            'orlando_toolkit.core.converter': {
                'level': 'INFO',
                'propagate': True,
            },
            'orlando_toolkit.core.parser': {
                'level': 'INFO',
                'propagate': True,
            },
            'orlando_toolkit.core.services': {
                # Services emit concise INFO audit entries and DEBUG diagnostics
                'level': 'INFO',
                'propagate': True,
            },
            'orlando_toolkit.core.merge': {
                # Capture merge summaries at INFO for post-mortem debugging
                'level': 'INFO',
                'propagate': True,
            },
            'orlando_toolkit.ui.controllers': {
                # Controllers remain mostly quiet; escalate only if explicitly enabled
                'level': 'WARNING',
                'propagate': True,
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