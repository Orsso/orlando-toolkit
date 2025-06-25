from __future__ import annotations

"""Utility functions for analysing Word styles to infer heading hierarchy.

This module keeps all raw-XML poking isolated, so the rest of the codebase
can stay on the higher-level python-docx API.
"""

from docx.document import Document  # type: ignore
from docx.enum.style import WD_STYLE_TYPE  # type: ignore
from typing import Dict

# Namespaces used in WordprocessingML
_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

# Numbering formats that clearly denote ordered headings (bullets are excluded)
_HEADING_NUMFMTS = {
    "decimal",
    "decimalZero",
    "upperRoman",
    "lowerRoman",
    "upperLetter",
    "lowerLetter",
    "roman",  # Some generators use this legacy value
    "alpha",  # Legacy
}


def _is_ordered_numfmt(numfmt: str | None) -> bool:
    """Return True if *numfmt* is a format typically used for ordered headings."""
    return bool(numfmt and numfmt in _HEADING_NUMFMTS)


def build_style_heading_map(doc: Document) -> Dict[str, int]:
    """Return a mapping {style_name: heading_level} inferred from the DOCX styles.

    Strategy:
    1. If a style has an explicit <w:outlineLvl val="n"/>, map to level n+1.
    2. Else, if the style references a numbering definition whose format is
       ordered (decimal/roman/alpha) and not bullet, map to level ilvl+1.
    The function never raises; on failure it returns an empty dict.
    """
    style_map: Dict[str, int] = {}

    try:
        numbering_root = doc.part.numbering_part._element  # lxml element
    except Exception:
        numbering_root = None

    for style in doc.styles:
        try:
            if style.type != WD_STYLE_TYPE.PARAGRAPH:
                continue
            style_el = style._element  # lxml element
            name = style.name

            # 1) Outline level ---------------------------------------------
            outline_vals = style_el.xpath("./w:pPr/w:outlineLvl/@w:val", namespaces=_NS)
            if outline_vals:
                try:
                    lvl = int(outline_vals[0]) + 1
                    style_map[name] = lvl
                    continue
                except ValueError:
                    pass  # fall through to numbering detection

            # 2) Numbering-based heading detection -------------------------
            numId_vals = style_el.xpath("./w:pPr/w:numPr/w:numId/@w:val", namespaces=_NS)
            if not numId_vals or numbering_root is None:
                continue
            numId = numId_vals[0]
            ilvl_vals = style_el.xpath("./w:pPr/w:numPr/w:ilvl/@w:val", namespaces=_NS)
            ilvl = ilvl_vals[0] if ilvl_vals else "0"

            # Resolve abstractNumId for this numId
            abs_ids = numbering_root.xpath(
                f'.//w:num[@w:numId="{numId}"]/w:abstractNumId/@w:val', namespaces=_NS
            )
            if not abs_ids:
                continue
            abs_id = abs_ids[0]
            numfmts = numbering_root.xpath(
                f'.//w:abstractNum[@w:abstractNumId="{abs_id}"]/w:lvl[@w:ilvl="{ilvl}"]/w:numFmt/@w:val',
                namespaces=_NS,
            )
            if not numfmts:
                continue
            numfmt = numfmts[0]
            if _is_ordered_numfmt(numfmt):
                try:
                    style_map[name] = int(ilvl) + 1
                except ValueError:
                    style_map[name] = 1
        except Exception:
            # Never crash conversion due to style map errors
            continue

    return style_map 