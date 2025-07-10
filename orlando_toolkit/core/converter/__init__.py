from __future__ import annotations

"""DOCX to DITA conversion logic.

This package contains the core conversion pipeline that transforms Word documents
into Orlando-compliant DITA topics and ditamaps. The conversion follows a
two-pass approach:

1. Structure Analysis: Build hierarchical document representation
2. Role Determination: Decide section vs module based on content
3. DITA Generation: Create topics with correct Orlando semantics

Key modules:
- docx_to_dita: Main conversion entry point
- structure_builder: Two-pass conversion implementation
- helpers: Shared utilities for formatting and content processing
"""

from typing import Any, Dict
import os
import uuid
import logging

from orlando_toolkit.core.models import DitaContext

# Core conversion implementation
from .docx_to_dita import convert_docx_to_dita
from .structure_builder import (
    build_document_structure,
    determine_node_roles,
    generate_dita_from_structure
)

__all__ = [
    "convert_docx_to_dita",
    "build_document_structure",
    "determine_node_roles",
    "generate_dita_from_structure",
    "save_dita_package",
    "update_image_references_and_names",
    "update_topic_references_and_names",
    "prune_empty_topics",
]

logger = logging.getLogger(__name__)


def save_dita_package(context: DitaContext, output_dir: str) -> None:
    """Write the DITA package folder structure to *output_dir*.

    Behaviour reproduced from legacy implementation.  Uses helpers from
    core.utils for XML output.
    """
    from pathlib import Path

    from orlando_toolkit.core.utils import save_xml_file, save_minified_xml_file, slugify

    output_dir = str(output_dir)
    data_dir = os.path.join(output_dir, "DATA")
    topics_dir = os.path.join(data_dir, "topics")
    media_dir = os.path.join(data_dir, "media")

    # Directory for assets – we deliberately *do not* embed the DTD files
    # anymore, but we keep the variable in case relative paths are still used
    # in DOCTYPE system identifiers.
    os.makedirs(topics_dir, exist_ok=True)
    os.makedirs(media_dir, exist_ok=True)

    # Ensure manual_code
    if not context.metadata.get("manual_code"):
        context.metadata["manual_code"] = slugify(context.metadata.get("manual_title", "default"))

    manual_code = context.metadata.get("manual_code")
    ditamap_path = os.path.join(data_dir, f"{manual_code}.ditamap")
    # The system identifier is reduced to a simple filename so that Orlando's
    # own catalog (or any resolver in the target environment) can map the
    # PUBLIC ID without relying on the embedded dtd folder.
    doctype_str = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'
    save_xml_file(context.ditamap_root, ditamap_path, doctype_str)

    # Save topics (minified)
    # The system identifier is reduced to a simple filename so that Orlando's
    # own catalog (or any resolver in the target environment) can map the
    # PUBLIC ID without relying on the embedded dtd folder.
    doctype_concept = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
    for filename, topic_el in context.topics.items():
        save_minified_xml_file(topic_el, os.path.join(topics_dir, filename), doctype_concept)

    # Save images
    for filename, blob in context.images.items():
        Path(os.path.join(media_dir, filename)).write_bytes(blob)

    logger.info("DITA package saved to %s", output_dir)


def update_image_references_and_names(context: DitaContext) -> DitaContext:
    """Rename image files and update hrefs inside all topic XML trees."""
    logger.info("Updating image names and references (core.converter)...")

    manual_code = context.metadata.get("manual_code", "MANUAL")
    prefix = context.metadata.get("prefix", "IMG")

    # Create per-section image naming
    from orlando_toolkit.core.utils import find_topicref_for_image, get_section_number_for_topicref
    
    # Group images by section
    section_images = {}
    for image_filename in list(context.images.keys()):
        topicref = find_topicref_for_image(image_filename, context)
        if topicref is not None and context.ditamap_root is not None:
            section_number = get_section_number_for_topicref(topicref, context.ditamap_root)
        else:
            section_number = "0"
        
        if section_number not in section_images:
            section_images[section_number] = []
        section_images[section_number].append(image_filename)
    
    # Generate new filenames with per-section numbering
    rename_map: dict[str, str] = {}
    for section_number, images_in_section in section_images.items():
        for i, image_filename in enumerate(images_in_section):
            extension = os.path.splitext(image_filename)[1]
            
            # Base filename parts
            base_name = f"{prefix}-{manual_code}-{section_number}"
            
            # Add image number only if there are multiple images in this section
            if len(images_in_section) > 1:
                img_num = i + 1
                new_filename = f"{base_name}-{img_num}{extension}"
            else:
                new_filename = f"{base_name}{extension}"
            
            rename_map[image_filename] = new_filename

    # Update href references in topic XML
    for topic_el in context.topics.values():
        for img_el in topic_el.iter("image"):
            href = img_el.get("href")
            if href:
                basename = os.path.basename(href)
                if basename in rename_map:
                    img_el.set("href", f"../media/{rename_map[basename]}")

    # Rebuild images dictionary with new names
    new_images: dict[str, bytes] = {}
    for old_name, data in context.images.items():
        new_images[rename_map.get(old_name, old_name)] = data

    context.images = new_images
    return context


def update_topic_references_and_names(context: DitaContext) -> DitaContext:
    """Generate stable filenames for topics and update ditamap hrefs."""
    logger.info("Updating topic filenames and references (core.converter)...")

    if not context.ditamap_root:
        return context

    new_topics: dict[str, Any] = {}

    for old_filename, topic_el in list(context.topics.items()):
        new_filename = f"topic_{uuid.uuid4().hex[:12]}.dita"
        topic_el.set("id", new_filename[:-5])

        topicref = context.ditamap_root.find(
            f".//topicref[@href='topics/{old_filename}']"
        )
        if topicref is not None:
            topicref.set("href", f"topics/{new_filename}")

        new_topics[new_filename] = topic_el

    context.topics = new_topics
    return context


def prune_empty_topics(context: "DitaContext") -> "DitaContext":
    """Remove topicrefs pointing to empty content modules.

    With the new architecture, sections are created as topichead elements,
    but content modules might still end up empty in edge cases. This function
    removes such empty modules and their topicrefs.

    Note: This is now mainly a safety net since sections are properly handled
    during initial creation as topichead elements.
    """

    if context.ditamap_root is None:
        return context

    empty_filenames: list[str] = []

    # Detect empty content modules
    for fname, topic_el in context.topics.items():
        conbody = topic_el.find("conbody")
        if conbody is None:
            empty_filenames.append(fname)
            continue

        has_children = len(list(conbody)) > 0
        has_text = (conbody.text or "").strip() != ""

        if not has_children and not has_text:
            empty_filenames.append(fname)

    if not empty_filenames:
        return context

    # Remove empty content modules
    for fname in empty_filenames:
        # Find corresponding topicref
        tref = context.ditamap_root.find(f".//topicref[@href='topics/{fname}']")
        if tref is not None:
            # Remove the entire topicref (content module should not exist if empty)
            parent = tref.getparent()
            if parent is not None:
                parent.remove(tref)
        # Remove topic
        context.topics.pop(fname, None)

    return context 