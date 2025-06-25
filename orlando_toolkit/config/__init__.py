"""Configuration files (YAML/TOML) and helpers will live here.

Later phases will introduce `ConfigManager` that reads default files from
this folder and merges with user overrides.
"""

from .manager import ConfigManager

__all__ = [
    "ConfigManager",
] 