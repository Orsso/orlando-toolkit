from __future__ import annotations

"""DOCX → DITA conversion implementation.

Core conversion logic that transforms Word documents into DITA topics
and ditamaps with proper Orlando-specific metadata and structure.
"""

from datetime import datetime
import logging
import os
import uuid
import re
from typing import Any, Dict

from docx import Document  # type: ignore
from docx.text.paragraph import Paragraph  # type: ignore
from docx.table import Table  # type: ignore

from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.utils import generate_dita_id
from orlando_toolkit.core.parser import iter_block_items, extract_images_to_context, build_style_heading_map
from orlando_toolkit.core.generators import create_dita_table

# Helper functions migrated from legacy converter
from .helpers import (
    STYLE_MAP,
    add_orlando_topicmeta,
    create_dita_concept,
    process_paragraph_content_and_images,
    apply_paragraph_formatting,
    get_heading_level,
)

logger = logging.getLogger(__name__)

__all__ = ["convert_docx_to_dita"]

# Global style map (user can override via metadata)
STYLE_MAP  # re-exported from helpers


def convert_docx_to_dita(file_path: str, metadata: Dict[str, Any]) -> DitaContext:  # noqa: C901 (complex)
    """Convert a DOCX file into an in-memory DitaContext.

    Processes Word document structure, formatting, images, and metadata
    to generate Orlando-compliant DITA topics and ditamap.
    """
    logger.info("Starting DOCX→DITA conversion (core.converter)…: %s", file_path)

    context = DitaContext(metadata=dict(metadata))

    try:
        logger.info("Loading DOCX file…")
        doc = Document(file_path)
        all_images_map_rid = extract_images_to_context(doc, context)

        logger.info("Extracting images…")

        map_root = ET.Element("map")
        map_root.set("{http://www.w3.org/XML/1998/namespace}lang", "en-US")
        context.ditamap_root = map_root

        map_title = ET.SubElement(map_root, "title")
        map_title.text = metadata.get("manual_title", "Document Title")

        add_orlando_topicmeta(map_root, context.metadata)

        heading_counters = [0] * 9
        parent_elements: Dict[int, ET.Element] = {0: map_root}

        current_concept = None
        old_file_name = ""
        current_conbody = None
        current_list = None
        current_sl = None

        style_heading_map = build_style_heading_map(doc)
        style_heading_map.update(STYLE_MAP)

        # Optional user override mapping provided via metadata
        if isinstance(metadata.get("style_heading_map"), dict):
            style_heading_map.update(metadata["style_heading_map"])  # type: ignore[arg-type]

        # Generic heading-name detection (e.g., "HEADING 5 GM"). Enabled by
        # default but can be disabled with metadata["generic_heading_match"] = False.
        if metadata.get("generic_heading_match", True):
            heading_rx = re.compile(r"\b(?:heading|titre)[ _]?(\\d)\\b", re.IGNORECASE)
            for sty in doc.styles:  # type: ignore[attr-defined]
                try:
                    name = sty.name  # type: ignore[attr-defined]
                except Exception:
                    continue
                m = heading_rx.search(name or "")
                if m and name not in style_heading_map:
                    try:
                        lvl = int(m.group(1))
                        style_heading_map[name] = lvl
                    except ValueError:
                        pass

        logger.info("Building topics…")
        for block in iter_block_items(doc):
            if isinstance(block, Table):
                if current_conbody is None:
                    continue
                current_list = None
                current_sl = None
                p_for_table = ET.SubElement(current_conbody, "p", id=generate_dita_id())
                dita_table = create_dita_table(block, all_images_map_rid)
                p_for_table.append(dita_table)

            elif isinstance(block, Paragraph):
                heading_level = get_heading_level(block, style_heading_map)
                is_heading = heading_level is not None
                is_list_item = (not is_heading) and (
                    block._p.pPr is not None and block._p.pPr.numPr is not None
                )

                text = block.text.strip()
                is_image_para = any(run.element.xpath(".//@r:embed") for run in block.runs) and not text

                if is_heading and text:
                    current_list = None
                    current_sl = None
                    level = heading_level  # type: ignore[assignment]

                    if current_concept is not None:
                        context.topics[old_file_name] = current_concept

                    # Ensure dynamic accommodation of uncommon heading levels
                    if level > len(heading_counters):
                        heading_counters.extend([0] * (level - len(heading_counters)))
                    heading_counters[level - 1] += 1  # type: ignore[index]
                    for i in range(level, len(heading_counters)):
                        heading_counters[i] = 0
                    toc_index = ".".join(str(c) for c in heading_counters[:level] if c > 0)

                    parent_level = level - 1
                    parent_element = parent_elements.get(parent_level, map_root)

                    file_name = f"topic_{uuid.uuid4().hex[:10]}.dita"
                    topic_id = file_name.replace(".dita", "")

                    current_concept, current_conbody = create_dita_concept(
                        text,
                        topic_id,
                        context.metadata.get("revision_date", datetime.now().strftime("%Y-%m-%d")),
                    )

                    topicref = ET.SubElement(
                        parent_element,
                        "topicref",
                        {"href": f"topics/{file_name}", "locktitle": "yes"},
                    )
                    topicref.set("data-level", str(level))
                    topicmeta_ref = ET.SubElement(topicref, "topicmeta")
                    navtitle_ref = ET.SubElement(topicmeta_ref, "navtitle")
                    navtitle_ref.text = text
                    critdates_ref = ET.SubElement(topicmeta_ref, "critdates")
                    ET.SubElement(critdates_ref, "created", date=context.metadata.get("revision_date"))
                    ET.SubElement(critdates_ref, "revised", modified=context.metadata.get("revision_date"))
                    ET.SubElement(topicmeta_ref, "othermeta", name="tocIndex", content=toc_index)
                    ET.SubElement(topicmeta_ref, "othermeta", name="foldout", content="false")
                    ET.SubElement(topicmeta_ref, "othermeta", name="tdm", content="false")
                    parent_elements[level] = topicref  # type: ignore[assignment]

                    # Preserve original paragraph style for fine-grain filtering
                    if block.style and block.style.name:
                        topicref.set("data-style", block.style.name)

                    for k in [l for l in parent_elements if l > level]:
                        del parent_elements[k]

                    old_file_name = file_name

                elif current_conbody is not None:
                    if is_image_para:
                        current_list = None
                        if current_sl is None:
                            current_sl = ET.SubElement(current_conbody, "sl", id=generate_dita_id())
                        sli = ET.SubElement(current_sl, "sli", id=generate_dita_id())
                        for run in block.runs:
                            r_ids = run.element.xpath(".//@r:embed")
                            if r_ids and r_ids[0] in all_images_map_rid:
                                img_filename = os.path.basename(all_images_map_rid[r_ids[0]])
                                ET.SubElement(
                                    sli,
                                    "image",
                                    href=f"../media/{img_filename}",
                                    id=generate_dita_id(),
                                )
                                break
                    elif is_list_item:
                        current_sl = None
                        list_style = "ul"
                        if current_list is None or current_list.tag != list_style:
                            current_list = ET.SubElement(current_conbody, list_style, id=generate_dita_id())
                        li = ET.SubElement(current_list, "li", id=generate_dita_id())
                        p_in_li = ET.SubElement(li, "p", id=generate_dita_id())
                        process_paragraph_content_and_images(
                            p_in_li, block, all_images_map_rid, None
                        )
                    else:
                        current_list = None
                        current_sl = None
                        if not text:
                            continue
                        p_el = ET.SubElement(current_conbody, "p", id=generate_dita_id())
                        apply_paragraph_formatting(p_el, block)  # align, roundedbox
                        process_paragraph_content_and_images(
                            p_el, block, all_images_map_rid, current_conbody
                        )

        if current_concept is not None:
            context.topics[old_file_name] = current_concept

    except Exception as exc:
        logger.error("Conversion failed: %s", exc, exc_info=True)
        raise

    logger.info("Conversion finished.")
    return context 