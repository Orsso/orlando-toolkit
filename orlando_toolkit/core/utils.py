from __future__ import annotations

"""Simple reusable helper functions.

These helpers are side-effect-free and contain no GUI or disk I/O; they can be
used across all layers of the toolkit.
"""

from typing import Any, Optional
import re
import uuid
from lxml import etree as ET
import xml.dom.minidom as _minidom

__all__ = [
    "slugify",
    "generate_dita_id",
    "save_xml_file",
    "save_minified_xml_file",
    "convert_color_to_outputclass",
]


def slugify(text: str) -> str:
    """Return a file-system-safe slug version of *text*.

    Removes non-alphanumeric chars, converts whitespace/dashes to underscores,
    and lower-cases the result. Mirrors previous implementation from
    ``docx_to_dita_converter`` for backward compatibility.
    """
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", text)


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
        When *True* (default) lxml pretty-prints the output; matches previous
        behaviour in :pyfile:`src/docx_to_dita_converter.py`.
    """

    xml_bytes = ET.tostring(
        element,
        pretty_print=pretty,
        xml_declaration=True,
        encoding="UTF-8",
        doctype=doctype_str,
    )
    with open(path, "wb") as fh:
        fh.write(xml_bytes)


def save_minified_xml_file(element: ET.Element, path: str, doctype_str: str) -> None:
    """Save *element* on a single line (minified) to *path*.

    This reproduces the logic previously embedded in the converter.
    """

    xml_bytes = ET.tostring(element, encoding="UTF-8")
    dom = _minidom.parseString(xml_bytes)
    minified_content = dom.documentElement.toxml() if dom.documentElement else ""

    full = f'<?xml version="1.0" encoding="UTF-8"?>{doctype_str}{minified_content}'
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(full)


# ---------------------------------------------------------------------------
# Colour mapping utilities (extracted from original converter)  [p3c]
# ---------------------------------------------------------------------------

def convert_color_to_outputclass(color_value: Optional[str]) -> Optional[str]:
    """Map Word colour representation to Orlando `outputclass` (red/green).

    The logic is unchanged from the legacy implementation, supporting:
    • exact hex matches (case-insensitive)
    • a limited set of Word theme colours
    • heuristic detection based on RGB dominance.
    """
    if not color_value:
        return None

    color_mappings = {
        # Reds ------------------------------------------------------------
        "#ff0000": "color-red",
        "#dc143c": "color-red",
        "#b22222": "color-red",
        "#8b0000": "color-red",
        "#ff4500": "color-red",
        "#cd5c5c": "color-red",
        "#c0504d": "color-red",
        "#da0000": "color-red",
        "#ff1d1d": "color-red",
        "#a60000": "color-red",
        "#cc0000": "color-red",
        "#800000": "color-red",
        "#e74c3c": "color-red",
        "#ee0000": "color-red",
        # Greens ----------------------------------------------------------
        "#008000": "color-green",
        "#00ff00": "color-green",
        "#32cd32": "color-green",
        "#228b22": "color-green",
        "#006400": "color-green",
        "#adff2f": "color-green",
        "#9acd32": "color-green",
        "#00b050": "color-green",
        "#00a300": "color-green",
        "#1d7d1d": "color-green",
        "#2e8b57": "color-green",
        "#27ae60": "color-green",
        # Blues -----------------------------------------------------------
        "#0000ff": "color-blue",
        "#1e90ff": "color-blue",
        "#4169e1": "color-blue",
        "#4682b4": "color-blue",
        "#5b9bd5": "color-blue",  
        "#2e75b6": "color-blue-dark",
        # Ambers ----------------------------------------------------------
        "#ffbf00": "color-amber",
        "#ffc000": "color-amber",
        # Cyans -----------------------------------------------------------
        "#00ffff": "color-cyan",
        "#00b0f0": "color-cyan",
        # Yellows ---------------------------------------------------------
        "#ffff00": "color-yellow",
        "#fff200": "color-yellow",
        # Background reds -------------------------------------------------
        "background-light-red": "background-color-light-red",
        "background-dark-blue": "background-color-dark-blue",
        # Background green -----------------------------------------------
        "background-color-green": "background-color-green",
        "#c6efce": "background-color-green",
    }

    color_lower = color_value.lower()
    if color_lower in color_mappings:
        return color_mappings[color_lower]

    if color_value.startswith("theme-"):
        theme_name = color_value[6:]
        theme_map = {
            "accent_1": "color-red",
            "accent_6": "color-green",
            "accent_5": "color-blue",  
            "accent_2": "color-amber",
            "accent_3": "color-cyan",
            "accent_4": "color-yellow",
        }
        return theme_map.get(theme_name)

    # Background colour tokens coming from shading (already prefixed)
    if color_value.startswith("background-"):
        return color_mappings.get(color_value)

    if color_lower.startswith("#") and len(color_lower) == 7:
        try:
            r = int(color_lower[1:3], 16)
            g = int(color_lower[3:5], 16)
            b = int(color_lower[5:7], 16)
            if r > g and r > b and r > 100 and (r > g + 20 or g < 150):
                return "color-red"
            if g > r and g > b and g > 100 and (g > r + 20 or r < 150):
                return "color-green"
        except ValueError:
            pass

    return None 