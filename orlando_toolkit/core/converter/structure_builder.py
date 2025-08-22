from __future__ import annotations

"""Document structure analysis for two-pass DITA conversion.

This module builds a hierarchical representation of the document structure,
allowing for deferred section vs module decisions based on complete context.
"""

from typing import List
import logging
import re
from docx import Document  # type: ignore
from docx.text.paragraph import Paragraph  # type: ignore
from docx.table import Table  # type: ignore

from orlando_toolkit.core.models import HeadingNode
from orlando_toolkit.core.parser import iter_block_items
from orlando_toolkit.core.converter.helpers import get_heading_level

import uuid
import os
from datetime import datetime
from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.utils import generate_dita_id, clean_heading_text
from orlando_toolkit.core.generators import create_dita_table
from orlando_toolkit.core.converter.helpers import (
    create_dita_concept,
    process_paragraph_content_and_images,
    apply_paragraph_formatting
)
_TOC_PATTERN = re.compile(r"\b(toc|table\s+of\s+contents|sommaire|table\s+des\s+mati[eè]res)\b", re.IGNORECASE)

def _is_toc_paragraph(p: Paragraph) -> bool:
    """Return True when paragraph is part of a Table of Contents.

    Heuristics:
    - Style name contains TOC keywords (e.g., "TOC 1", custom styles)
    - Paragraph text contains common TOC titles (English/French)
    """
    try:
        style_name = getattr(p.style, 'name', None) if p.style else None
    except Exception:
        style_name = None
    try:
        text_val = (p.text or "").strip()
    except Exception:
        text_val = ""

    if isinstance(style_name, str) and style_name and _TOC_PATTERN.search(style_name):
        return True
    if text_val and _TOC_PATTERN.search(text_val):
        return True
    return False



def _paragraph_has_effective_content(p: Paragraph) -> bool:
    """Return True if paragraph carries meaningful content.

    Criteria:
    - Non-whitespace text OR
    - List item OR
    - Embedded image
    """
    try:
        if (p.text or "").strip():
            return True
        # List item (numbering)
        if getattr(p._p, "pPr", None) is not None and getattr(p._p.pPr, "numPr", None) is not None:
            return True
        # Images (any embedded rel id)
        for run in getattr(p, "runs", []) or []:
            r_ids = run.element.xpath(".//@r:embed")
            if r_ids:
                return True
        # SDT-contained text (checkbox or other content that may not appear in p.text)
        try:
            for child in p._p.iter():  # type: ignore[attr-defined]
                tag = getattr(child, "tag", None)
                if isinstance(tag, str) and tag.endswith("}t"):
                    if (getattr(child, "text", None) or "").strip():
                        return True
        except Exception:
            pass
    except Exception:
        # Be conservative: assume not effective when inspection fails
        return False
    return False


def _table_has_effective_content(t: Table) -> bool:
    """Return True if the table has at least one non-empty cell or image."""
    try:
        for row in t.rows:
            for cell in row.cells:
                # Quick text check
                if (cell.text or "").strip():
                    return True
                # Check images/text within cell paragraphs
                for p in getattr(cell, "paragraphs", []) or []:
                    if _paragraph_has_effective_content(p):
                        return True
    except Exception:
        return False
    return False


def _has_effective_content(blocks: List) -> bool:
    """Return True if any block in *blocks* carries meaningful content."""
    for block in blocks or []:
        if isinstance(block, Table):
            if _table_has_effective_content(block):
                return True
        elif isinstance(block, Paragraph):
            if _paragraph_has_effective_content(block):
                return True
        else:
            # Unknown block types: be conservative and ignore for gating
            continue
    return False


def build_document_structure(doc: Document, style_heading_map: dict, all_images_map_rid: dict) -> List[HeadingNode]:
    """Build hierarchical document structure from Word document.
    
    First pass of two-pass conversion: analyze complete document structure
    without making immediate section vs module decisions.
    
    Parameters
    ----------
    doc
        Word document to analyze
    style_heading_map
        Mapping of style names to heading levels
    all_images_map_rid
        Image relationship ID mapping for content processing
        
    Returns
    -------
    List[HeadingNode]
        Root-level heading nodes with complete hierarchy
    """
    root_nodes: List[HeadingNode] = []
    heading_stack: List[HeadingNode] = []  # Track parent chain for hierarchy
    
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            heading_level = get_heading_level(block, style_heading_map)
            
            if heading_level is not None:
                # Skip Table of Contents headings entirely
                try:
                    if _is_toc_paragraph(block):
                        continue
                except Exception:
                    pass
                # Create new heading node
                text = clean_heading_text(block.text.strip())
                if not text:
                    continue  # Skip empty headings
                
                style_name = getattr(block.style, 'name', None) if block.style else None
                node = HeadingNode(
                    text=text,
                    level=heading_level,
                    style_name=style_name
                )
                
                # Find correct parent in hierarchy
                # Remove nodes from stack that are at same or deeper level
                while heading_stack and heading_stack[-1].level >= heading_level:
                    heading_stack.pop()
                
                # Add to hierarchy
                if heading_stack:
                    # Has parent - add as child
                    parent = heading_stack[-1]
                    parent.add_child(node)
                else:
                    # No parent - add as root node
                    root_nodes.append(node)
                
                # Add to stack for potential children
                heading_stack.append(node)
            else:
                # Content block - add to current heading if exists
                if heading_stack:
                    current_heading = heading_stack[-1]
                    # Ignore TOC lines to avoid polluting content modules
                    try:
                        if _is_toc_paragraph(block):
                            pass
                        else:
                            current_heading.add_content_block(block)
                    except Exception:
                        current_heading.add_content_block(block)
                # Content before first heading is ignored.
                
        elif isinstance(block, Table):
            # Table block - add to current heading if exists
            if heading_stack:
                current_heading = heading_stack[-1]
                current_heading.add_content_block(block)
    
    return root_nodes


def determine_node_roles(nodes: List[HeadingNode]) -> None:
    """Determine section vs module roles for all nodes in hierarchy.
    
    Decision logic:
    - Has children → Section
    - No children → Module
    - Section with content → Create implicit module child for content
    
    Parameters
    ----------
    nodes
        List of heading nodes to process (modified in-place)
    """
    for node in nodes:
        if node.has_children():
            node.role = "section"
            # If section has content, it will be handled during DITA generation
            # by creating an implicit module child
        else:
            node.role = "module"
        
        # Recursively process children
        determine_node_roles(node.children)


def generate_dita_from_structure(
    nodes: List[HeadingNode], 
    context: DitaContext, 
    metadata: dict,
    all_images_map_rid: dict,
    parent_element: ET.Element,
    heading_counters: list,
) -> None:
    """Generate DITA topics and map structure from hierarchical document structure.
    
    Second pass of two-pass conversion: create DITA topics with correct
    section vs module roles based on analyzed structure.
    
    Parameters
    ----------
    nodes
        List of heading nodes to process
    context
        DITA context to populate with topics
    metadata
        Document metadata
    all_images_map_rid
        Image relationship ID mapping
    parent_element
        Parent element in ditamap for topicref creation
    heading_counters
        Heading counters for TOC indexing
    (no parent-elements mapping needed)
    """
    for node in nodes:
        level = node.level
        
        # Update heading counters
        if level > len(heading_counters):
            heading_counters.extend([0] * (level - len(heading_counters)))
        heading_counters[level - 1] += 1
        for i in range(level, len(heading_counters)):
            heading_counters[i] = 0
        toc_index = ".".join(str(c) for c in heading_counters[:level] if c > 0)
        
        # Generate unique file name and topic ID
        file_name = f"topic_{uuid.uuid4().hex[:10]}.dita"
        topic_id = file_name.replace(".dita", "")
        
        if node.role == "section":
            # Create section as pure structural topichead (no topic file)
            topichead = ET.SubElement(
                parent_element,
                "topichead",
                {"locktitle": "yes"},
            )
            topichead.set("data-level", str(level))
            
            # Add topicmeta for section
            topicmeta_ref = ET.SubElement(topichead, "topicmeta")
            navtitle_ref = ET.SubElement(topicmeta_ref, "navtitle")
            navtitle_ref.text = node.text
            critdates_ref = ET.SubElement(topicmeta_ref, "critdates")
            _rev_date = metadata.get("revision_date") or datetime.now().strftime("%Y-%m-%d")
            ET.SubElement(critdates_ref, "created", date=_rev_date)
            ET.SubElement(critdates_ref, "revised", modified=_rev_date)
            ET.SubElement(topicmeta_ref, "othermeta", name="tocIndex", content=toc_index)
            ET.SubElement(topicmeta_ref, "othermeta", name="foldout", content="false")
            ET.SubElement(topicmeta_ref, "othermeta", name="tdm", content="false")
            
            # Preserve style information
            if node.style_name:
                topichead.set("data-style", node.style_name)
            
            # If section has content, create a content module child for it (single-pass)
            module_file = f"topic_{uuid.uuid4().hex[:10]}.dita"
            module_id = module_file.replace(".dita", "")
            module_concept, module_conbody = create_dita_concept(
                node.text,
                module_id,
                metadata.get("revision_date", datetime.now().strftime("%Y-%m-%d")),
            )
            added_any = _add_content_to_topic(
                module_conbody,
                node.content_blocks,
                all_images_map_rid,
                table_context={"toc_index": toc_index, "title": node.text},
            )
            if added_any:
                module_topicref = ET.SubElement(
                    topichead,
                    "topicref",
                    {"href": f"topics/{module_file}", "locktitle": "yes"},
                )
                try:
                    module_topicref.set("data-level", str(level + 1))
                    module_topicref.set("data-style", f"Heading {level + 1}")
                except Exception:
                    pass
                tm = ET.SubElement(module_topicref, "topicmeta")
                nt = ET.SubElement(tm, "navtitle")
                nt.text = node.text
                context.topics[module_file] = module_concept
            
            # Process children recursively
            generate_dita_from_structure(
                node.children, context, metadata, all_images_map_rid,
                topichead, heading_counters
            )
            
        else:  # node.role == "module"
            # Create module topic with content
            module_concept, module_conbody = create_dita_concept(
                node.text,
                topic_id,
                metadata.get("revision_date", datetime.now().strftime("%Y-%m-%d")),
            )
            
            # Add content to module
            _add_content_to_topic(
                module_conbody,
                node.content_blocks,
                all_images_map_rid,
                table_context={"toc_index": toc_index, "title": node.text},
            )
            
            # Create topicref in ditamap
            topicref = ET.SubElement(
                parent_element,
                "topicref",
                {"href": f"topics/{file_name}", "locktitle": "yes"},
            )
            topicref.set("data-level", str(level))
            
            # Add topicmeta
            topicmeta_ref = ET.SubElement(topicref, "topicmeta")
            navtitle_ref = ET.SubElement(topicmeta_ref, "navtitle")
            navtitle_ref.text = node.text
            critdates_ref = ET.SubElement(topicmeta_ref, "critdates")
            _rev_date2 = metadata.get("revision_date") or datetime.now().strftime("%Y-%m-%d")
            ET.SubElement(critdates_ref, "created", date=_rev_date2)
            ET.SubElement(critdates_ref, "revised", modified=_rev_date2)
            ET.SubElement(topicmeta_ref, "othermeta", name="tocIndex", content=toc_index)
            ET.SubElement(topicmeta_ref, "othermeta", name="foldout", content="false")
            ET.SubElement(topicmeta_ref, "othermeta", name="tdm", content="false")
            
            # Preserve style information
            if node.style_name:
                topicref.set("data-style", node.style_name)
            
            # Store in context
            context.topics[file_name] = module_concept
            # Process children recursively (modules can have children too)
            generate_dita_from_structure(
                node.children, context, metadata, all_images_map_rid,
                topicref, heading_counters
            )


def _add_content_to_topic(
    conbody: ET.Element,
    content_blocks: List,
    all_images_map_rid: dict,
    *,
    table_context: dict | None = None,
) -> bool:
    """Add content blocks to a topic's conbody element.
    
    Parameters
    ----------
    conbody
        The conbody element to add content to
    content_blocks
        List of content blocks (paragraphs, tables, etc.)
    all_images_map_rid
        Image relationship ID mapping
    """
    current_list = None
    current_sl = None
    _table_counter = 0
    _tb_logger = logging.getLogger("orlando_toolkit.core.generators.dita_builder")
    
    added_any = False
    for block in content_blocks:
        if isinstance(block, Table):
            current_list = None
            current_sl = None
            _table_counter += 1
            if _tb_logger.isEnabledFor(logging.DEBUG):
                try:
                    ctx_idx = table_context.get("toc_index") if isinstance(table_context, dict) else None
                    ctx_title = table_context.get("title") if isinstance(table_context, dict) else None
                except Exception:
                    ctx_idx = None
                    ctx_title = None
                loc_label = f"[{ctx_idx}] {ctx_title}" if ctx_idx and ctx_title else "[unknown]"
                try:
                    declared_cols = len(getattr(block, "columns", []))
                    declared_rows = len(getattr(block, "rows", []))
                except Exception:
                    declared_cols = 0
                    declared_rows = 0
                _tb_logger.debug(
                    "Converting table #%d at %s (rows=%s, cols=%s)",
                    _table_counter,
                    loc_label,
                    declared_rows,
                    declared_cols,
                )
            
            p_for_table = ET.SubElement(conbody, "p", id=generate_dita_id())
            dita_table = create_dita_table(block, all_images_map_rid)
            p_for_table.append(dita_table)
            added_any = True
            
        elif isinstance(block, Paragraph):
            # Check if it's a list item
            is_list_item = (
                block._p.pPr is not None and block._p.pPr.numPr is not None
            )
            
            text = block.text.strip()
            is_image_para = any(run.element.xpath(".//@r:embed") for run in block.runs) and not text
            
            if is_image_para:
                current_list = None
                if current_sl is None:
                    current_sl = ET.SubElement(conbody, "sl", id=generate_dita_id())
                sli = ET.SubElement(current_sl, "sli", id=generate_dita_id())
                for run in block.runs:
                    r_ids = run.element.xpath(".//@r:embed")
                    if r_ids and r_ids[0] in all_images_map_rid:
                        img_filename = os.path.basename(all_images_map_rid[r_ids[0]])
                        ET.SubElement(sli, "image", href=f"../media/{img_filename}", id=generate_dita_id())
                        break
                added_any = True
            elif is_list_item:
                current_sl = None
                list_style = "ul"
                if current_list is None or current_list.tag != list_style:
                    current_list = ET.SubElement(conbody, list_style, id=generate_dita_id())
                li = ET.SubElement(current_list, "li", id=generate_dita_id())
                p_in_li = ET.SubElement(li, "p", id=generate_dita_id())
                process_paragraph_content_and_images(p_in_li, block, all_images_map_rid, None)
                added_any = True
            else:
                current_list = None
                current_sl = None
                if not text:
                    continue
                p_el = ET.SubElement(conbody, "p", id=generate_dita_id())
                apply_paragraph_formatting(p_el, block)
                process_paragraph_content_and_images(p_el, block, all_images_map_rid, conbody) 
                added_any = True
    return added_any