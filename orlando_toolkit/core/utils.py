from __future__ import annotations

"""Simple reusable helper functions.

These helpers are side-effect-free and contain no GUI or disk I/O; they can be
used across all layers of the toolkit.
"""

from typing import Any, Optional, Dict
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

def convert_color_to_outputclass(
    color_value: Optional[str], color_rules: Dict[str, Any]
) -> Optional[str]:
    """Map Word colour representation to Orlando `outputclass` (red/green).

    The logic is unchanged from the legacy implementation, supporting:
    • exact hex matches (case-insensitive)
    • a limited set of Word theme colours
    • heuristic detection based on RGB dominance.
    """
    if not color_value:
        return None

    color_mappings = color_rules.get("color_mappings", {})
    theme_map = color_rules.get("theme_map", {})

    color_lower = color_value.lower()
    if color_lower in color_mappings:
        return color_mappings[color_lower]

    if color_value.startswith("theme-"):
        theme_name = color_value[6:]
        return theme_map.get(theme_name)

    # Background colour tokens coming from shading (already prefixed)
    if color_value.startswith("background-"):
        return color_mappings.get(color_value)

    # ------------------------------------------------------------------
    # HSV-based tolerance fallback (optional)
    # ------------------------------------------------------------------
    tolerance_cfg = color_rules.get("tolerance", {})
    if color_lower.startswith("#") and len(color_lower) == 7 and tolerance_cfg:
        try:
            r = int(color_lower[1:3], 16) / 255.0
            g = int(color_lower[3:5], 16) / 255.0
            b = int(color_lower[5:7], 16) / 255.0

            import colorsys

            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            h_deg = h * 360
            s_pct = s * 100
            v_pct = v * 100

            for out_class, spec in tolerance_cfg.items():
                # Extract ranges
                hue_range = spec.get("hue")
                hue2_range = spec.get("hue2")  # optional secondary segment (wrap-around)
                sat_min = spec.get("sat_min", 0)
                val_min = spec.get("val_min", 0)

                def _in_range(hrange: list[int] | tuple[int, int] | None) -> bool:
                    if not hrange:
                        return False
                    start, end = hrange
                    return start <= h_deg <= end

                if (
                    (_in_range(hue_range) or _in_range(hue2_range))
                    and s_pct >= sat_min
                    and v_pct >= val_min
                ):
                    return out_class
        except Exception:
            pass

    return None 