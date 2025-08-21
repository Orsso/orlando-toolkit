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
from orlando_toolkit.config import ConfigManager

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

    # Get image naming configuration
    image_naming_config = {}
    try:
        image_naming_config = ConfigManager().get_image_naming() or {}
    except Exception as exc:
        logger.error("Failed to read image naming config: %s", exc)

    required_keys = {"prefix", "pattern", "index_start", "index_zero_pad"}
    if not required_keys.issubset(image_naming_config.keys()):
        logger.warning("Image naming config missing keys %s; skipping image renaming", 
                       sorted(list(required_keys - set(image_naming_config.keys()))))
        return context

    manual_code = context.metadata.get("manual_code", "manual")
    prefix = image_naming_config.get("prefix")
    pattern = image_naming_config.get("pattern")
    index_start = image_naming_config.get("index_start")
    index_zero_pad = image_naming_config.get("index_zero_pad")

    # Validate basic types to avoid raising
    try:
        index_start = int(index_start)
        index_zero_pad = int(index_zero_pad)
    except Exception:
        logger.warning("Image naming config has invalid integer fields; skipping image renaming")
        return context

    # Create per-section image naming
    from orlando_toolkit.core.utils import find_topicref_for_image, get_section_number_for_topicref

    # Group images by section
    section_images: Dict[str, list[str]] = {}
    for image_filename in list(context.images.keys()):
        topicref = find_topicref_for_image(image_filename, context)
        if topicref is not None and context.ditamap_root is not None:
            section_number = get_section_number_for_topicref(topicref, context.ditamap_root)
        else:
            section_number = "0"

        section_images.setdefault(section_number, []).append(image_filename)

    # Generate new filenames with per-section numbering using configurable pattern
    rename_map: dict[str, str] = {}
    for section_number, images_in_section in section_images.items():
        for i, image_filename in enumerate(images_in_section):
            extension = os.path.splitext(image_filename)[1]

            # Prepare tokens for pattern substitution
            tokens = {
                "prefix": prefix,
                "manual_code": manual_code,
                "section": section_number,
                "ext": extension,
                "-index": "",
            }

            # Add index only if there are multiple images in this section
            if len(images_in_section) > 1:
                img_num = i + index_start
                index_str = str(img_num).zfill(index_zero_pad) if index_zero_pad > 0 else str(img_num)
                tokens["-index"] = f"-{index_str}"

            try:
                new_filename = pattern.format(**tokens)
            except Exception as exc:
                logger.error("Image naming pattern error: %s; skipping image renaming", exc)
                return context

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
    """Generate human-readable, stable filenames for topics and update hrefs.

    Strategy:
    - Base name on section number + slugified title/navtitle: "topic_<num>_<slug>.dita".
    - Ensure uniqueness by suffixing "-2", "-3", ... when needed.
    - Update both the ditamap @href and the topics dict keys.
    """
    logger.info("Updating topic filenames and references (core.converter)...")

    if context.ditamap_root is None:
        return context

    try:
        from orlando_toolkit.core.utils import calculate_section_numbers, slugify
    except Exception:
        # Fallback to UUID naming if helpers unavailable
        new_topics: dict[str, Any] = {}
        for old_filename, topic_el in list(context.topics.items()):
            new_filename = f"topic_{uuid.uuid4().hex[:12]}.dita"
            topic_el.set("id", new_filename[:-5])
            tref = context.ditamap_root.find(f".//topicref[@href='topics/{old_filename}']")
            if tref is not None:
                tref.set("href", f"topics/{new_filename}")
            new_topics[new_filename] = topic_el
        context.topics = new_topics
        return context

    # Build section numbers for all structural nodes once
    section_number_map = calculate_section_numbers(context.ditamap_root)

    # First pass: discover referenced topics and propose deterministic names
    rename_map: dict[str, str] = {}
    used_names: set[str] = set()
    import hashlib  # local import to avoid increasing module import time
    MAX_FILENAME_LEN = 120  # conservative cap for Windows path constraints

    def _pick_title_for(topic_el, tref_el) -> str:
        # Prefer topic <title>, fallback to navtitle
        try:
            t = topic_el.find("title") if topic_el is not None else None
            if t is not None and getattr(t, "text", None):
                return str(t.text)
        except Exception:
            pass
        try:
            nav = tref_el.find("topicmeta/navtitle") if tref_el is not None else None
            if nav is not None and getattr(nav, "text", None):
                return str(nav.text)
        except Exception:
            pass
        return "topic"

    for tref in list(context.ditamap_root.xpath(".//topicref[@href]")):
        href = tref.get("href") or ""
        old_filename = href.split("/")[-1]
        topic_el = context.topics.get(old_filename)
        if topic_el is None:
            continue

        # Section number (e.g., 3.2.1) → filename-safe variant
        number = section_number_map.get(tref, "0")
        safe_number = number.replace(".", "-") if isinstance(number, str) else "0"
        title = _pick_title_for(topic_el, tref)
        base_slug = slugify(title) or "topic"
        prefix = f"topic_{safe_number}_"
        ext = ".dita"
        allowed = MAX_FILENAME_LEN - len(prefix) - len(ext)
        if allowed < 8:
            allowed = 8  # ensure minimal space for slug
        if len(base_slug) > allowed:
            # Truncate and add deterministic suffix for stability
            h = hashlib.md5((title or "").encode("utf-8")).hexdigest()[:8]
            allowed2 = max(1, allowed - 9)  # account for '-' + 8-char hash
            trimmed = base_slug[:allowed2]
            candidate = f"{prefix}{trimmed}-{h}{ext}"
        else:
            candidate = f"{prefix}{base_slug}{ext}"

        unique_name = candidate
        suffix = 2
        while unique_name in used_names:
            base_no_ext = unique_name[:-len(ext)]
            unique_name = f"{base_no_ext}-{suffix}{ext}"
            suffix += 1

        used_names.add(unique_name)
        rename_map[old_filename] = unique_name

    if not rename_map:
        return context

    # Second pass: apply renames in topics dict and update map hrefs
    new_topics: dict[str, Any] = {}
    for old_filename, topic_el in list(context.topics.items()):
        new_filename = rename_map.get(old_filename)
        if not new_filename:
            # Keep as-is if unreferenced or not mapped
            new_topics[old_filename] = topic_el
            continue
        try:
            topic_el.set("id", new_filename[:-5])
        except Exception:
            pass
        new_topics[new_filename] = topic_el

    # Update hrefs in the map
    for tref in list(context.ditamap_root.xpath(".//topicref[@href]")):
        href = tref.get("href") or ""
        old_filename = href.split("/")[-1]
        new_filename = rename_map.get(old_filename)
        if new_filename:
            tref.set("href", f"topics/{new_filename}")

    context.topics = new_topics
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Renamed %d topics", len(rename_map))
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