from __future__ import annotations

"""Configuration loading and access helpers (Phase 4).

This module centralises all declarative rules (style map, colour map, naming
patterns, etc.).  It loads YAML files packaged with *orlando_toolkit* and
optionally merges them with user overrides located in
``~/.orlando_toolkit/*.yml``.

The class is intentionally lightweight; missing PyYAML falls back to embedded
Python dictionaries so existing behaviour is never broken.
"""

import importlib.resources as pkg_resources
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

__all__ = ["ConfigManager"]


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

        for key, filename in self._DEFAULT_FILENAMES.items():
            merged_cfg: Dict[str, Any] = {}

            # 1. load packaged default
            try:
                with pkg_resources.open_text(__package__, filename) as fh:
                    merged_cfg.update(yaml.safe_load(fh) or {})
            except (FileNotFoundError, OSError):
                logger.debug("No packaged config for %s", key)

            # 2. load user overrides (~/.orlando_toolkit)
            user_path = Path.home() / ".orlando_toolkit" / filename
            if user_path.exists():
                try:
                    merged_cfg.update(yaml.safe_load(user_path.read_text()) or {})
                except Exception as exc:
                    logger.error("Could not parse user config %s: %s", user_path, exc)

            self._data[key] = merged_cfg

        # Ensure fallbacks for missing sections
        defaults = self._builtin_defaults()
        for k, v in defaults.items():
            self._data.setdefault(k, v)

    @staticmethod
    def _builtin_defaults() -> Dict[str, Dict[str, Any]]:
        """Return hard-coded defaults to guarantee behaviour parity."""
        return {
            "style_map": {},
            "color_rules": {},
            "image_naming": {},
            "logging": {},
        } 