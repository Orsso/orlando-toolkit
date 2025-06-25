"""Top-level package for the business-logic portion of Orlando Toolkit.

This package hosts the refactored, GUI-agnostic implementation.  Front-ends
(e.g. Tk GUI, CLI) should only depend on the public API exposed here rather
than importing internal modules directly.
"""

from .core.models import DitaContext  # re-export for convenience

__all__: list[str] = [
    "DitaContext",
] 