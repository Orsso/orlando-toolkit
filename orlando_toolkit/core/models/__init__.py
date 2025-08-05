from __future__ import annotations

"""Shared data structures used across the Orlando Toolkit core.

This package exposes dataclasses and value objects used by services and other
core layers. It is intentionally free of UI / I/O code so that the contained
objects can be reused in any context (unit-tests, CLI, GUI, etc.).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List

from lxml import etree as ET

__all__ = ["DitaContext", "HeadingNode"]


@dataclass
class HeadingNode:
    """Represents a heading in the document hierarchy with associated content.
    
    Used during two-pass conversion to build document structure before
    making section vs module decisions.
    """
    text: str
    level: int
    style_name: Optional[str] = None
    content_blocks: List[Any] = field(default_factory=list)  # Tables, Paragraphs, etc.
    children: List['HeadingNode'] = field(default_factory=list)
    parent: Optional['HeadingNode'] = None
    role: Optional[str] = None  # "section" | "module" | None
    
    def has_children(self) -> bool:
        """Return True if this heading has sub-headings."""
        return len(self.children) > 0
    
    def has_content(self) -> bool:
        """Return True if this heading has associated content blocks."""
        return len(self.content_blocks) > 0
    
    def add_child(self, child: 'HeadingNode') -> None:
        """Add a child heading and set its parent reference."""
        child.parent = self
        self.children.append(child)
    
    def add_content_block(self, block: Any) -> None:
        """Add a content block (Table, Paragraph, etc.) to this heading."""
        self.content_blocks.append(block)


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
