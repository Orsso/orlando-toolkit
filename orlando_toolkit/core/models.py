from __future__ import annotations

"""Shared data structures used across the Orlando Toolkit core.

This module is intentionally free of UI / I/O code so that the contained
objects can be reused in any context (unit-tests, CLI, GUI, etc.).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from lxml import etree as ET

__all__ = ["DitaContext"]


@dataclass
class DitaContext:
    """In-memory representation of a converted manual.

    Attributes
    ----------
    ditamap_root
        Root element of the in-memory ditamap (lxml Element).
    topics
        Mapping of topic file names to their root XML Element.
    images
        Mapping of image file names to the raw bytes (as extracted from DOCX).
    metadata
        Arbitrary key/value pairs captured from GUI or config (title, code…).
    """

    ditamap_root: Optional[ET.Element] = None
    topics: Dict[str, ET.Element] = field(default_factory=dict)
    images: Dict[str, bytes] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict) 