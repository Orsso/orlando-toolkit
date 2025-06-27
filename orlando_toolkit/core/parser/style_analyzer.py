from __future__ import annotations

"""Utility functions for analysing Word styles to infer heading hierarchy.

Migrated from ``src/style_analyzer.py`` during Phase-8.  The public helper
:func:`build_style_heading_map` is used by the DOCX→DITA converter to decide
which Word styles should be treated as headings.
"""

from typing import Dict
import re

from docx.document import Document  # type: ignore
from docx.enum.style import WD_STYLE_TYPE  # type: ignore

# Namespaces used in WordprocessingML
_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

# Generic heading-style name regex (optional safeguard)
_GENERIC_RX = re.compile(r"\b(?:heading|titre)[ _]?(\d)\b", re.IGNORECASE)

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
    """Return True if *numfmt* is a numbering format typically used for ordered headings."""
    return bool(numfmt and numfmt in _HEADING_NUMFMTS)


def build_style_heading_map(doc: Document) -> Dict[str, int]:  # noqa: D401
    """Return a mapping ``{style_name: heading_level}`` inferred from the DOCX styles.

    Strategy
    ========
    1. If a style has an explicit ``<w:outlineLvl val="n"/>``, map to level ``n+1``.
    2. Otherwise, if the style references a numbering definition whose format is
       *ordered* (decimal/roman/alpha) and not bullet, map to level ``ilvl+1``.

    The function never raises; on failure it returns an empty dict so that the
    caller can fall back to defaults.
    """
    style_map: Dict[str, int] = {}

    try:
        numbering_root = doc.part.numbering_part._element  # type: ignore[attr-defined]
    except Exception:
        numbering_root = None

    # Build quick lookup of style name → element for inheritance walk-up
    _style_el_map = {}
    for _s in doc.styles:  # type: ignore[attr-defined]
        try:
            _style_el_map[_s.name] = _s._element  # type: ignore[attr-defined]
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Main pass over styles
    # ------------------------------------------------------------------
    for style in doc.styles:  # type: ignore[attr-defined]
        try:
            if style.type != WD_STYLE_TYPE.PARAGRAPH:  # type: ignore[attr-defined]
                continue
            style_el = style._element  # lxml element
            name = style.name  # type: ignore[attr-defined]

            # 1) Outline level -------------------------------------------------
            outline_vals = _xp(style_el, "./w:pPr/w:outlineLvl/@w:val")
            if outline_vals:
                try:
                    lvl = int(outline_vals[0]) + 1
                    style_map[name] = lvl
                    continue
                except ValueError:
                    pass  # fall through to numbering detection

            # 2) Inheritance walk-up ----------------------------------------
            def _inherit_lvl(st_el):
                seen = set()
                while st_el is not None:
                    # Prevent infinite loops
                    sid = id(st_el)
                    if sid in seen:
                        break
                    seen.add(sid)

                    outline_vals = _xp(st_el, "./w:pPr/w:outlineLvl/@w:val")
                    if outline_vals:
                        try:
                            return int(outline_vals[0]) + 1
                        except ValueError:
                            break

                    based_vals = _xp(st_el, "./w:basedOn/@w:val")
                    if not based_vals:
                        break
                    parent_name = based_vals[0]
                    st_el = _style_el_map.get(parent_name)
                return None

            inherited_lvl = _inherit_lvl(style_el)
            if inherited_lvl:
                style_map[name] = inherited_lvl
                continue

            # 3) Name-based heuristic (generic regex)
            m = _GENERIC_RX.search(name or "")
            if m:
                try:
                    style_map[name] = int(m.group(1))
                    continue
                except ValueError:
                    pass

            # 4) Numbering-based heading detection ---------------------------
            numId_vals = _xp(style_el, "./w:pPr/w:numPr/w:numId/@w:val")
            if not numId_vals or numbering_root is None:
                continue
            numId = numId_vals[0]
            ilvl_vals = _xp(style_el, "./w:pPr/w:numPr/w:ilvl/@w:val")
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

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _xp(el, path: str):  # noqa: D401
    """Namespace-agnostic XPath helper.

    python-docx proxies sometimes raise ``TypeError`` when the *namespaces*
    keyword is supplied.  This helper first tries the project-wide ``_NS``
    mapping and falls back to the element's own ``nsmap`` to stay compatible
    with all library versions.
    """

    try:
        return el.xpath(path, namespaces=_NS)
    except TypeError:
        try:
            return el.xpath(path, namespaces=getattr(el, "nsmap", None))
        except Exception:
            # Last-chance: run without namespaces (works with local-name())
            return el.xpath(path) 