from __future__ import annotations

"""Helper utilities for DOCX to DITA conversion.

Small, side-effect-free functions used by the core conversion logic
for XML element creation, formatting, and content processing.
"""

from datetime import datetime
import os
import re
from typing import Dict, Any, Optional, Tuple

from lxml import etree as ET  # type: ignore
from docx.text.paragraph import Paragraph  # type: ignore
from docx.enum.text import WD_ALIGN_PARAGRAPH  # type: ignore
from docx.oxml.ns import qn  # type: ignore

from orlando_toolkit.core.utils import (
    slugify,
    generate_dita_id,
    convert_color_to_outputclass,
)

__all__ = [
    "STYLE_MAP",
    "create_dita_concept",
    "add_orlando_topicmeta",
    "process_paragraph_content_and_images",
    "apply_paragraph_formatting",
    "get_heading_level",
]

# ---------------------------------------------------------------------------
# User-customisable style mapping (kept for backward compatibility)
# ---------------------------------------------------------------------------

STYLE_MAP: Dict[str, Any] = {}

# ---------------------------------------------------------------------------
# DITA element builders
# ---------------------------------------------------------------------------

def create_dita_concept(title: str, topic_id: str, revision_date: str):
    """Return ``(<concept>, <conbody>)`` elements for a new DITA concept."""
    concept_root = ET.Element("concept", id=topic_id)
    title_elem = ET.SubElement(concept_root, "title")
    title_elem.text = title

    conbody = ET.SubElement(concept_root, "conbody")
    return concept_root, conbody


def add_orlando_topicmeta(map_root: ET.Element, metadata: Dict[str, Any]) -> None:
    """Insert the Orlando-specific ``<topicmeta>`` block into *map_root*."""
    topicmeta = ET.Element("topicmeta")
    critdates = ET.SubElement(topicmeta, "critdates")
    rev_date = metadata.get("revision_date", datetime.now().strftime("%Y-%m-%d"))
    ET.SubElement(critdates, "created", date=rev_date)
    ET.SubElement(critdates, "revised", modified=rev_date)

    manual_code = metadata.get("manual_code") or slugify(metadata.get("manual_title", "default_code"))
    manual_ref = (
        metadata.get("manual_reference") or slugify(metadata.get("manual_title", "default_ref")).upper()
    )

    ET.SubElement(topicmeta, "othermeta", name="manualCode", content=manual_code)
    ET.SubElement(topicmeta, "othermeta", name="manual_reference", content=manual_ref)
    ET.SubElement(topicmeta, "othermeta", name="revNumber", content=metadata.get("revision_number", "1.0"))
    ET.SubElement(topicmeta, "othermeta", name="isRevNumberNull", content="false")

    title_element = map_root.find("title")
    insert_index = list(map_root).index(title_element) + 1 if title_element is not None else 0
    map_root.insert(insert_index, topicmeta)

# ---------------------------------------------------------------------------
# Paragraph processing helpers
# ---------------------------------------------------------------------------

def _process_paragraph_runs(p_element: ET.Element, paragraph: Paragraph, image_map: dict, *, exclude_images: bool = False) -> None:  # noqa: D401,E501
    """Rebuild the runs of a Word paragraph into DITA inline markup."""
    last_element: Optional[ET.Element] = None

    # python-docx ≥0.9.8 exposes iter_inner_content()
    try:
        content_items = list(paragraph.iter_inner_content())  # type: ignore[attr-defined]
    except AttributeError:
        content_items = paragraph.runs  # type: ignore[attr-defined]

    current_group: list[str] = []
    current_formatting: Optional[Tuple[Tuple[str, ...], Optional[str]]] = None

    def finish_current_group() -> None:
        nonlocal current_group, current_formatting, last_element
        if not current_group:
            return
        consolidated_text = "".join(current_group)
        formatting_tuple: Tuple[str, ...] = current_formatting[0] if current_formatting else tuple()
        run_color: Optional[str] = current_formatting[1] if current_formatting else None

        if formatting_tuple or run_color:
            target_element: Optional[ET.Element] = None
            innermost_element: Optional[ET.Element] = None

            # Base <ph> for colour
            if run_color:
                target_element = ET.Element("ph", id=generate_dita_id())
                target_element.set("class", "- topic/ph ")
                color_class = convert_color_to_outputclass(run_color)
                if color_class:
                    target_element.set("outputclass", color_class)
                innermost_element = target_element

            def _nest(tag: str) -> ET.Element:
                nonlocal target_element, innermost_element
                el = ET.Element(tag, id=generate_dita_id())
                el.set("class", f"+ topic/ph hi-d/{tag} ")
                if innermost_element is not None:
                    innermost_element.append(el)
                else:
                    target_element = el
                innermost_element = el
                return el

            if "bold" in formatting_tuple:
                _nest("b")
            if "italic" in formatting_tuple:
                _nest("i")
            if "underline" in formatting_tuple:
                _nest("u")

            if innermost_element is not None:
                innermost_element.text = consolidated_text
                p_element.append(target_element)  # type: ignore[arg-type]
                last_element = target_element
        else:
            if last_element is not None:
                last_element.tail = (last_element.tail or "") + consolidated_text
            else:
                p_element.text = (p_element.text or "") + consolidated_text  # type: ignore[assignment]

        current_group = []
        current_formatting = None

    for item in content_items:
        # Hyperlink handling
        if hasattr(item, "address"):
            finish_current_group()
            href_el = ET.Element("xref", id=generate_dita_id())
            href_el.set("class", "- topic/xref ")
            href_el.set("format", "html")
            href_el.set("scope", "external")
            href_el.set("href", item.url or item.address)  # type: ignore[attr-defined]
            href_el.text = item.text  # type: ignore[attr-defined]
            p_element.append(href_el)
            last_element = href_el
            continue

        run = item  # regular run -------------------------------------------
        run_text = run.text or ""
        run_format = []
        if run.bold:
            run_format.append("bold")
        if run.italic:
            run_format.append("italic")
        if run.underline:
            run_format.append("underline")

        # colour extraction (simplified)
        run_color: Optional[str] = None
        try:
            font_color = run.font.color  # type: ignore[attr-defined]
            if font_color and font_color.rgb:
                run_color = f"#{str(font_color.rgb).lower()}"
        except Exception:
            pass

        fmt_tuple: Tuple[Tuple[str, ...], Optional[str]] = (tuple(run_format), run_color)
        if current_formatting == fmt_tuple:
            current_group.append(run_text)
        else:
            finish_current_group()
            current_group = [run_text]
            current_formatting = fmt_tuple

        # image handling ------------------------------------------------------
        if not exclude_images:
            r_ids = run.element.xpath(".//@r:embed")
            if r_ids and r_ids[0] in image_map:
                img_filename = os.path.basename(image_map[r_ids[0]])
                ET.SubElement(p_element, "image", href=f"../media/{img_filename}", id=generate_dita_id())

    finish_current_group()


def process_paragraph_content_and_images(
    p_element: ET.Element,
    paragraph: Paragraph,
    image_map: dict,
    conbody: Optional[ET.Element],
) -> None:
    """Split images into separate centred paragraphs when *conbody* is provided."""

    if conbody is None:
        _process_paragraph_runs(p_element, paragraph, image_map, exclude_images=False)
        return

    images: list[str] = []
    for run in paragraph.runs:
        r_ids = run.element.xpath(".//@r:embed")
        if r_ids and r_ids[0] in image_map:
            images.append(os.path.basename(image_map[r_ids[0]]))

    _process_paragraph_runs(p_element, paragraph, image_map, exclude_images=True)

    for img in images:
        img_p = ET.SubElement(conbody, "p", id=generate_dita_id(), outputclass="align-center")
        ET.SubElement(img_p, "image", href=f"../media/{img}", id=generate_dita_id())


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def apply_paragraph_formatting(p_element: ET.Element, paragraph: Paragraph) -> None:
    """Set ``outputclass`` on *p_element* to reflect paragraph alignment/shading."""
    classes: list[str] = []
    if paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER:  # type: ignore[attr-defined]
        classes.append("align-center")
    elif paragraph.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:  # type: ignore[attr-defined]
        classes.append("align-justify")

    p_pr = paragraph._p.pPr  # type: ignore[attr-defined]
    if p_pr is not None:
        shd = p_pr.find(qn("w:shd"))
        if shd is not None and shd.attrib.get(qn("w:fill")) == "F2F2F2":
            classes.append("roundedbox")

    if classes:
        p_element.set("outputclass", " ".join(classes))

# ---------------------------------------------------------------------------
# Heading detection
# ---------------------------------------------------------------------------

def get_heading_level(paragraph: Paragraph, style_map: Optional[dict] = None) -> Optional[int]:
    """Return heading level for *paragraph*, or ``None`` if it is not a heading."""
    try:
        # 1) Explicit user mapping
        if paragraph.style and paragraph.style.name:  # type: ignore[attr-defined]
            style_name = paragraph.style.name
            if style_map and style_name in style_map:
                return int(style_map[style_name])
            if style_name.startswith("Heading ") and style_name.split(" ")[-1].isdigit():
                return int(style_name.split(" ")[-1])

        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        outline_vals = paragraph._p.xpath("./w:pPr/w:outlineLvl/@w:val", namespaces=ns)
        if outline_vals:
            return int(outline_vals[0]) + 1

        if paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None:
            numPr = paragraph._p.pPr.numPr
            ilvl = getattr(numPr.ilvl, "val", None)
            if ilvl is not None:
                try:
                    return int(ilvl) + 1
                except ValueError:
                    pass
    except Exception:
        pass

    return None 