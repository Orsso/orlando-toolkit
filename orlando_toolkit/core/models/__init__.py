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

    def has_effective_content(self) -> bool:
        """Return True if content blocks contain meaningful content.

        Converter-level helpers use a stricter gating than mere presence of blocks.
        This method remains lightweight and is used only where the full
        converter helpers are not available. Primary gating lives in the
        converter module to avoid cross-layer imports.
        """
        return any(self.content_blocks)
    
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

    def save_original_structure(self) -> None:
        """Save the original structure before any depth merging operations.
        
        This enables reversible depth limit changes by preserving the unmodified state.
        Should be called once when first applying any depth limit.
        
        IMPORTANT: Only saves if structure is truly original (no prior depth merges).
        This prevents saving already-modified states.
        """
        # Only save if no original structure AND no previous depth merges
        if ("original_structure" not in self.metadata and 
            "merged_depth" not in self.metadata):
            from copy import deepcopy
            # Create completely independent copies to avoid corruption
            self.metadata["original_structure"] = {
                "ditamap_root": deepcopy(self.ditamap_root) if self.ditamap_root is not None else None,
                "topics": deepcopy(self.topics),
                "metadata_snapshot": {k: v for k, v in self.metadata.items() 
                                    if k not in ["original_structure", "merged_depth", "merged_exclude_styles"]},
            }

    def restore_from_original(self) -> None:
        """Restore context to its original pre-merge state.
        
        Resets ditamap_root and topics to their state before any depth merging.
        Clears merge-related metadata flags.
        """
        original = self.metadata.get("original_structure")
        if original:
            from copy import deepcopy
            self.ditamap_root = deepcopy(original["ditamap_root"]) if original["ditamap_root"] is not None else None
            self.topics = deepcopy(original["topics"])
            # Clear merge flags but preserve original metadata
            self.metadata.update(original["metadata_snapshot"])
            self.metadata.pop("merged_depth", None)
            self.metadata.pop("merged_exclude_styles", None)
