from __future__ import annotations

"""Configuration loading and access helpers (Phase 4).

This module centralises all declarative rules (style map, colour map, naming
patterns, etc.).  It loads YAML files packaged with *orlando_toolkit* and
optionally merges them with user overrides located in Local AppData.

On Windows: ``%LOCALAPPDATA%\\OrlandoToolkit\\config\\*.yml``
On Unix: ``~/.orlando_toolkit/*.yml``

The class is intentionally lightweight; missing PyYAML falls back to embedded
Python dictionaries so existing behaviour is never broken.
"""

import importlib.resources as pkg_resources
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

__all__ = ["ConfigManager"]


def _get_user_config_dir() -> Path:
    """Get the user configuration directory in Local AppData."""
    if os.name == 'nt':  # Windows
        local_appdata = os.environ.get('LOCALAPPDATA')
        if local_appdata:
            return Path(local_appdata) / "OrlandoToolkit" / "config"
        else:
            # Fallback for Windows
            return Path.home() / "AppData" / "Local" / "OrlandoToolkit" / "config"
    else:  # Unix-like systems
        return Path.home() / ".orlando_toolkit"


def _ensure_user_configs_exist(user_config_dir: Path, default_filenames: Dict[str, str]) -> None:
    """Copy default config files to user directory if they don't exist."""
    try:
        # Create user config directory if it doesn't exist
        user_config_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy each default config file if user version doesn't exist
        for key, filename in default_filenames.items():
            user_config_path = user_config_dir / filename
            
            if not user_config_path.exists():
                try:
                    # Read packaged default config
                    with pkg_resources.open_text(__package__, filename) as fh:
                        default_content = fh.read()
                    
                    # Write to user config directory
                    user_config_path.write_text(default_content, encoding='utf-8')
                    logger.info("Created user config: %s", user_config_path)
                    
                except (FileNotFoundError, OSError) as e:
                    logger.warning("Could not copy default config %s: %s", filename, e)
                except Exception as e:
                    logger.error("Error copying config %s: %s", filename, e)
                    
    except Exception as e:
        logger.error("Could not create user config directory %s: %s", user_config_dir, e)


class _Singleton(type):
    _instance: "ConfigManager" | None = None

    def __call__(cls, *args, **kwargs):  # type: ignore[no-self-use]
        if cls._instance is None:
            cls._instance = super().__call__(*args, **kwargs)
        return cls._instance


class ConfigManager(metaclass=_Singleton):
    """Lazy-loads and exposes configuration sections as dictionaries."""

    _DEFAULT_FILENAMES = {
        "style_map": "default_style_map.yml",
        "color_rules": "default_color_rules.yml",
        "image_naming": "image_naming.yml",
        "logging": "logging.yml",
        "style_detection": "style_detection.yml",
    }

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._ensure_loaded()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def get_style_map(self) -> Dict[str, Any]:
        return self._data.get("style_map", {})

    def get_color_rules(self) -> Dict[str, Any]:
        return self._data.get("color_rules", {})

    def get_image_naming(self) -> Dict[str, Any]:
        return self._data.get("image_naming", {})

    def get_logging_config(self) -> Dict[str, Any]:
        return self._data.get("logging", {})

    def get_style_detection(self) -> Dict[str, Any]:
        return self._data.get("style_detection", {})

    # ------------------------------------------------------------------
    # Internal loading logic
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._data:
            return  # already loaded

        try:
            import yaml  # type: ignore
        except ModuleNotFoundError:
            logger.warning("PyYAML not installed – falling back to built-in defaults")
            self._data = self._builtin_defaults()
            return

        startup_summary = []
        
        # Get user config directory and ensure configs exist
        user_config_dir = _get_user_config_dir()
        _ensure_user_configs_exist(user_config_dir, self._DEFAULT_FILENAMES)
        
        for key, filename in self._DEFAULT_FILENAMES.items():
            merged_cfg: Dict[str, Any] = {}
            status = "missing"

            # 1. load packaged default
            try:
                with pkg_resources.open_text(__package__, filename) as fh:
                    packaged_data = yaml.safe_load(fh) or {}
                    merged_cfg.update(packaged_data)
                    status = "loaded"
            except (FileNotFoundError, OSError):
                logger.error("Missing packaged config for %s (%s)", key, filename)
                status = "missing"
            except Exception as exc:
                logger.error("Invalid packaged config for %s (%s): %s", key, filename, exc)
                status = "invalid"

            # 2. load user overrides from Local AppData
            user_path = user_config_dir / filename
            if user_path.exists():
                try:
                    user_data = yaml.safe_load(user_path.read_text()) or {}
                    merged_cfg.update(user_data)
                    if status == "loaded":
                        status = "loaded+overrides"
                except Exception as exc:
                    logger.error("Could not parse user config %s: %s", user_path, exc)

            self._data[key] = merged_cfg
            startup_summary.append(f"{key}: {status}")

        # Log startup summary
        logger.info("Config startup: %s", " | ".join(startup_summary))

    @staticmethod
    def _builtin_defaults() -> Dict[str, Dict[str, Any]]:
        """Return neutral empty mappings (no business rules embedded)."""
        return {
            "style_map": {},
            "color_rules": {},
            "image_naming": {},
            "logging": {},
            "style_detection": {},
        } 