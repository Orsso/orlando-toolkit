from __future__ import annotations

"""Simple reusable helper functions.

These helpers are side-effect-free and contain no GUI or disk I/O; they can be
used across all layers of the toolkit.
"""

from typing import Any, Optional, Dict
import logging
import re
import uuid
from lxml import etree as ET
import xml.dom.minidom as _minidom

if False:  # TYPE_CHECKING pragma
    from orlando_toolkit.core.models import DitaContext

__all__ = [
    "slugify",
    "clean_heading_text",
    "generate_dita_id",
    "save_xml_file",
    "save_minified_xml_file",
    "calculate_section_numbers",
    "get_section_number_for_topicref",
    "find_topicref_for_image",
]

logger = logging.getLogger(__name__)

def slugify(text: str) -> str:
    """Return a file-system-safe slug version of *text*.

    Removes non-alphanumeric chars, converts whitespace/dashes to underscores,
    and lower-cases the result. Provides consistent filename generation.
    """
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", text)


def clean_heading_text(text: str) -> str:
    """Remove hardcoded section numbering from heading text.

    Removes common numbering patterns that would conflict with Orlando's
    automatic numbering system. Preserves the original casing and formatting
    of the cleaned title.

    Args:
        text: Raw heading text that may contain section numbers

    Returns:
        Cleaned heading text with numbering patterns removed

    Examples:
        >>> clean_heading_text("1.2.3 My Title")
        "My Title"
        >>> clean_heading_text("1.2.3. My Title")
        "My Title"
        >>> clean_heading_text("1) My Title")
        "My Title"
        >>> clean_heading_text("a) My Title")
        "My Title"
        >>> clean_heading_text("I. My Title")
        "My Title"
        >>> clean_heading_text("My Title")  # No numbering
        "My Title"
    """
    if not text or not isinstance(text, str):
        return text

    # Pattern to match common section numbering at the beginning of titles:
    # - 1.2.3 Title (decimal with dots)
    # - 1.2.3. Title (decimal with dots and final period)
    # - 1) Title (decimal with parenthesis)
    # - a) Title (lowercase letter with parenthesis)
    # - A) Title (uppercase letter with parenthesis)
    # - I. Title (Roman numeral with period)
    # - i. Title (lowercase Roman numeral with period)
    # - 1- Title (decimal with dash)
    # Also handles leading whitespace
    numbering_pattern = re.compile(
        r"^\s*(?:"
        r"\d+(?:\.\d+)*\.?\s+"    # 1.2.3 or 1.2.3.
        r"|\d+[)\-]\s+"           # 1) or 1-
        r"|[a-zA-Z][)\-]\s+"      # a) or A) or a- or A-
        r"|[ivxlcdmIVXLCDM]+\.\s+" # Roman numerals with period
        r")"
    )

    cleaned = numbering_pattern.sub("", text).strip()
    return cleaned if cleaned else text  # Fallback to original if everything was removed


def generate_dita_id() -> str:
    """Generate a globally unique ID suitable for DITA elements."""
    return f"id-{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# XML convenience wrappers
# ---------------------------------------------------------------------------

# We keep exact behaviour of legacy functions to guarantee no regression.


def save_xml_file(element: ET.Element, path: str, doctype_str: str, *, pretty: bool = True) -> None:
    """Write *element* to *path* with XML declaration and supplied doctype.

    Parameters
    ----------
    element
        Root ``lxml`` element to serialise.
    path
        Destination file path (will be opened in binary mode).
    doctype_str
        Full doctype string, including leading whitespace; e.g.::

            '\n<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
    pretty
        When *True* (default) lxml pretty-prints the output for readability.
    """

    xml_bytes = ET.tostring(
        element,
        pretty_print=pretty,
        xml_declaration=True,
        encoding="UTF-8",
        doctype=doctype_str,
    )
    try:
        with open(path, "wb") as fh:
            fh.write(xml_bytes)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("I/O: wrote XML pretty path=%s bytes=%d", path, len(xml_bytes))
    except Exception:
        # Caller context handles user feedback; file handler captures traceback
        logger.error("I/O FAIL: write XML path=%s", path, exc_info=True)
        raise


def save_minified_xml_file(element: ET.Element, path: str, doctype_str: str) -> None:
    """Save *element* on a single line (minified) to *path*.

    This reproduces the logic previously embedded in the converter.
    """

    xml_bytes = ET.tostring(element, encoding="UTF-8")
    dom = _minidom.parseString(xml_bytes)
    minified_content = dom.documentElement.toxml() if dom.documentElement else ""

    full = f'<?xml version="1.0" encoding="UTF-8"?>{doctype_str}{minified_content}'
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(full)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("I/O: wrote XML minified path=%s chars=%d", path, len(full))
    except Exception:
        logger.error("I/O FAIL: write XML (minified) path=%s", path, exc_info=True)
        raise


 

# ---------------------------------------------------------------------------
# Section numbering utilities
# ---------------------------------------------------------------------------

def calculate_section_numbers(ditamap_root: ET.Element) -> Dict[ET.Element, str]:
    """Calculate hierarchical section numbers for all topicref/topichead elements.
    
    Parameters
    ----------
    ditamap_root
        Root element of the ditamap
        
    Returns
    -------
    Dict[ET.Element, str]
        Mapping from topicref/topichead elements to their section numbers (e.g., "1.2.1")
    """
    section_map = {}
    
    def _walk_elements(parent_element: ET.Element, counters: list[int]):
        """Recursively walk the element tree and assign section numbers."""
        current_level = len(counters)
        child_counter = 0
        
        for element in parent_element:
            if element.tag in ("topicref", "topichead"):
                child_counter += 1
                
                # Extend counters if needed for this level
                level_counters = counters.copy() + [child_counter]
                
                # Generate section number string
                section_number = ".".join(str(c) for c in level_counters)
                section_map[element] = section_number
                
                # Recursively process children
                _walk_elements(element, level_counters)
    
    # Start with empty counters for root level
    _walk_elements(ditamap_root, [])
    return section_map


def get_section_number_for_topicref(topicref: ET.Element, ditamap_root: ET.Element) -> str:
    """Get the section number for a specific topicref element.
    
    Parameters
    ----------
    topicref
        The topicref element to get the section number for
    ditamap_root
        Root element of the ditamap
        
    Returns
    -------
    str
        Section number (e.g., "1.2.1") or "0" if not found
    """
    section_map = calculate_section_numbers(ditamap_root)
    return section_map.get(topicref, "0")


def find_topicref_for_image(image_filename: str, context: "DitaContext") -> Optional[ET.Element]:
    """Find the topicref element that contains a specific image.
    
    Parameters
    ----------
    image_filename
        The filename of the image to search for
    context
        The DITA context containing topics and ditamap
        
    Returns
    -------
    Optional[ET.Element]
        The topicref element containing the image, or None if not found
    """
    if getattr(context, "ditamap_root", None) is None:
        return None
    
    # Search through all topics to find which one contains the image
    for topic_filename, topic_element in context.topics.items():
        # Look for image references in the topic
        image_elements = topic_element.xpath(f".//image[@href='../media/{image_filename}']")
        if image_elements:
            # Find the corresponding topicref in the ditamap
            for topicref in context.ditamap_root.xpath(".//topicref"):
                href = topicref.get("href", "")
                if href.endswith(topic_filename):
                    return topicref
    
    return None 