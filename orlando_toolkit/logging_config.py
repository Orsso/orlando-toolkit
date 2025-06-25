from __future__ import annotations

"""Central logging configuration for Orlando Toolkit.

Import and call :func:`setup_logging` at application start-up.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
import logging.config
from typing import Any, Dict

__all__ = ["setup_logging"]

# Attempt to apply YAML configuration at import time
_DICT_CONFIG_APPLIED = False
try:
    from orlando_toolkit.config.manager import ConfigManager
    _cfg: Dict[str, Any] = ConfigManager().get_logging_config()
    if _cfg:
        logging.config.dictConfig(_cfg)
        logging.getLogger(__name__).debug("Logging configured via ConfigManager YAML")
        _DICT_CONFIG_APPLIED = True
except Exception:
    # Fail silently and fall back to builtin setup
    pass

def setup_logging() -> None:
    """Configure root logger with rotating file and console handlers.

    If a dictConfig was already applied during import, this function becomes a
    no-op so callers can invoke it unconditionally.
    """
    if _DICT_CONFIG_APPLIED:
        return

    log_dir = os.getenv("ORLANDO_LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "app.log")

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logging.info("===== Logging initialised =====") 