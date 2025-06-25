from __future__ import annotations

"""Bundled DITA DTDs shipped with Orlando Toolkit.

This package contains the full DITA DTD hierarchy that used to live in
``src/dtd_package``.  It is now part of the installable package so the
application works regardless of the current working directory.
"""

import os
from importlib import resources
from pathlib import Path

__all__ = ["get_dtd_root", "dtd_package_path"]

# Absolute path to this directory (kept for backward compatibility)
dtd_package_path: str = os.path.dirname(os.path.abspath(__file__))


def get_dtd_root() -> Path:  # pragma: no cover
    """Return a pathlib Path to the root of the bundled DTD directory."""
    return Path(resources.files(__package__).joinpath("")) 