# -*- coding: utf-8 -*-
"""Application version detection utilities.

Provides a single public function, ``get_app_version()``, which attempts to
determine the current application version using several strategies in order of
stability. This keeps UI code simple and avoids duplication across modules.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

_CACHED_VERSION: Optional[str] = None


def get_app_version() -> str:
    """Return the application version string (e.g., ``v1.2.3``).

    Production: read version.txt written by the packaging script.
    Development fallback: return "vdev" if file is missing.
    """
    global _CACHED_VERSION
    if _CACHED_VERSION:
        return _CACHED_VERSION

    # version.txt near the app root (packaged builds place it alongside the package root)
    try:
        here = Path(__file__).resolve()
        version_file = here.parent.parent / "version.txt"
        if version_file.exists():
            text = version_file.read_text(encoding="ascii", errors="ignore").strip()
            if text:
                _CACHED_VERSION = text if text.startswith("v") else f"v{text}"
                return _CACHED_VERSION
    except Exception:
        pass

    _CACHED_VERSION = "vdev"
    return _CACHED_VERSION




