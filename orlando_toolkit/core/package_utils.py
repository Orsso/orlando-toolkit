"""Package utilities for DITA archive creation and finalization.

These utilities handle the final stages of DITA package preparation:
- Saving DITA packages to disk
- Renaming topics and images with consistent patterns  
- Converting empty topics to structural elements
- Updating references throughout the package

This module contains format-agnostic utilities that were previously part of
the DOCX-specific converter module but are needed for all plugin conversions.
"""

from __future__ import annotations

import os
import uuid
import logging
from pathlib import Path
from typing import Dict, Any

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.utils import save_xml_file, save_minified_xml_file, slugify
from orlando_toolkit.config import ConfigManager
from lxml import etree as ET
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

__all__ = [
    "save_dita_package",
    "update_image_references_and_names", 
    "update_topic_references_and_names",
    "prune_empty_topics",
]


# Removed manual_reference normalization; not used in standardized archive output


def _ensure_map_metadata(context: DitaContext) -> None:
    """Ensure map-level title, manual_reference and manualCode exist for all archives.

    - Title: from context.metadata["manual_title"] or default "VIDEO-LIBRARY"
    - manual_reference: normalized from title (UPPER, hyphen-separated)
    - manualCode: slugified(title).upper()
    - critdates: created/revised dates present
    """
    root = getattr(context, "ditamap_root", None)
    if root is None:
        return

    # Resolve title and short name; ensure metadata has values for downstream consumers
    # Fallback to unique title when missing to avoid SaaS import rejection
    from datetime import datetime
    title_text = (context.metadata.get("manual_title") or context.metadata.get("title") or "")
    if not str(title_text).strip():
        title_text = f"MANUAL_{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    short_name = None
    try:
        raw_short = context.metadata.get("manual_code")
        short_name = (raw_short if raw_short else slugify(title_text)).upper()
        context.metadata["manual_code"] = short_name
    except Exception:
        short_name = (slugify(title_text) or "manual").upper()
    try:
        context.metadata["manual_title"] = title_text
    except Exception:
        pass

    # Ensure xml:lang
    try:
        if not root.get("xml:lang"):
            root.set("xml:lang", "en-US")
    except Exception:
        pass

    # Ensure <title>
    try:
        title_el = root.find("title")
        if title_el is None:
            title_el = ET.Element("title")
            # Insert as first child for predictable ordering
            try:
                root.insert(0, title_el)
            except Exception:
                root.append(title_el)
        else:
            # Move existing title to the top if needed
            try:
                if list(root).index(title_el) != 0:
                    root.remove(title_el)
                    root.insert(0, title_el)
            except Exception:
                pass
        if not (getattr(title_el, "text", None) and str(title_el.text).strip()):
            title_el.text = title_text
    except Exception:
        pass

    # Ensure <topicmeta>
    try:
        metas = root.findall("topicmeta")
        topicmeta = metas[0] if metas else None
        # Remove duplicate topicmeta nodes to keep a single standardized container
        if len(metas) > 1:
            for m in metas[1:]:
                try:
                    root.remove(m)
                except Exception:
                    pass
        if topicmeta is None:
            topicmeta = ET.Element("topicmeta")
            # Insert right after title for predictable ordering
            try:
                idx = 1 if len(root) >= 1 else 0
                root.insert(idx, topicmeta)
            except Exception:
                root.append(topicmeta)
        else:
            # Ensure it is positioned after title
            try:
                desired_idx = 1
                cur_idx = list(root).index(topicmeta)
                if cur_idx != desired_idx:
                    root.remove(topicmeta)
                    root.insert(min(desired_idx, len(root)), topicmeta)
            except Exception:
                pass
    except Exception:
        topicmeta = None

    # Ensure othermeta entries and ordering inside topicmeta
    if topicmeta is not None:
        try:
            # 1) critdates as first child
            crit = topicmeta.find("critdates")
            if crit is None:
                crit = ET.Element("critdates")
            # Ensure created/revised
            created = crit.find("created")
            if created is None:
                created = ET.SubElement(crit, "created")
            if not created.get("date"):
                created.set("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            revised = crit.find("revised")
            if revised is None:
                revised = ET.SubElement(crit, "revised")
            if not revised.get("modified"):
                revised.set("modified", context.metadata.get("revision_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            # Reposition critdates to index 0
            try:
                if crit.getparent() is not None:
                    topicmeta.remove(crit)
            except Exception:
                pass
            topicmeta.insert(0, crit)

            # 2) manualCode after critdates
            manual_code_el = None
            for om in topicmeta.findall("othermeta"):
                if om.get("name") == "manualCode":
                    manual_code_el = om
                    break
            if manual_code_el is None:
                manual_code_el = ET.Element("othermeta")
                manual_code_el.set("name", "manualCode")
            manual_code_el.set("content", short_name or "MANUAL")
            # Reposition manualCode to index 1
            try:
                if manual_code_el.getparent() is not None:
                    topicmeta.remove(manual_code_el)
            except Exception:
                pass
            topicmeta.insert(min(1, len(topicmeta)), manual_code_el)

            # 3) Optional compatibility fields after manualCode
            def _ensure_othermeta(name: str, content: str) -> ET.Element:
                el = None
                for om in topicmeta.findall("othermeta"):
                    if om.get("name") == name:
                        el = om
                        break
                if el is None:
                    el = ET.Element("othermeta")
                    el.set("name", name)
                if not el.get("content"):
                    el.set("content", content)
                return el

            rev_number = _ensure_othermeta("revNumber", "0.0")
            is_rev_null = _ensure_othermeta("isRevNumberNull", "true")
            # Reposition after manualCode (indexes 2 and 3)
            for idx, el in enumerate([rev_number, is_rev_null], start=2):
                try:
                    if el.getparent() is not None:
                        topicmeta.remove(el)
                except Exception:
                    pass
                topicmeta.insert(min(idx, len(topicmeta)), el)
        except Exception:
            pass

        # Ensure critdates
        try:
            crit = topicmeta.find("critdates")
            if crit is None:
                crit = ET.SubElement(topicmeta, "critdates")
            # created@date
            created = crit.find("created")
            if created is None:
                created = ET.SubElement(crit, "created")
            if not created.get("date"):
                created.set("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            # revised@modified
            revised = crit.find("revised")
            if revised is None:
                revised = ET.SubElement(crit, "revised")
            if not revised.get("modified"):
                revised.set("modified", context.metadata.get("revision_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        except Exception:
            pass

def save_dita_package(context: DitaContext, output_dir: str) -> None:
    """Write the DITA package folder structure to *output_dir*.

    Creates the standard DITA package structure:
    - DATA/topics/ - Contains all DITA topic files
    - DATA/media/ - Contains all referenced images
    - DATA/{manual_code}.ditamap - Main ditamap file

    Args:
        context: DitaContext containing the DITA content to save
        output_dir: Directory path where the package should be written
    """
    output_dir = str(output_dir)
    data_dir = os.path.join(output_dir, "DATA")
    topics_dir = os.path.join(data_dir, "topics")
    media_dir = os.path.join(data_dir, "media")

    # Create directory structure
    os.makedirs(topics_dir, exist_ok=True)
    os.makedirs(media_dir, exist_ok=True)

    # Ensure map-level metadata (title, manual_reference, manualCode) across all plugins
    try:
        _ensure_map_metadata(context)
    except Exception:
        pass

    # Ensure manual_code exists
    if not context.metadata.get("manual_code"):
        context.metadata["manual_code"] = slugify(context.metadata.get("manual_title", "default"))

    manual_code = context.metadata.get("manual_code")
    ditamap_path = os.path.join(data_dir, f"{manual_code}.ditamap")
    
    # Save ditamap with SaaS-compatible DOCTYPE path (matches reference)
    doctype_str = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "./dtd/technicalContent/dtd/map.dtd">'
    save_xml_file(context.ditamap_root, ditamap_path, doctype_str)

    # Save topics with proper DOCTYPE
    doctype_concept = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
    for filename, topic_el in context.topics.items():
        save_minified_xml_file(topic_el, os.path.join(topics_dir, filename), doctype_concept)

    # Save images
    for filename, blob in context.images.items():
        Path(os.path.join(media_dir, filename)).write_bytes(blob)

    # Save videos (ensure video media are included in the package)
    try:
        for filename, blob in getattr(context, 'videos', {}).items():
            Path(os.path.join(media_dir, filename)).write_bytes(blob)
    except Exception as exc:
        logger.error("Failed to write video media: %s", exc)

    logger.info("DITA package saved to %s", output_dir)


def update_image_references_and_names(context: DitaContext) -> DitaContext:
    """Rename image files and update hrefs inside all topic XML trees.
    
    Uses the image naming configuration to generate consistent filenames
    based on section numbers and configured patterns.

    Args:
        context: DitaContext to update
        
    Returns:
        Updated DitaContext with renamed images and updated references
    """
    logger.info("Updating image names and references...")

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

    # Validate basic types
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

    # Generate new filenames with per-section numbering
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
    - Base name on section number + slugified title/navtitle: "topic_<num>_<slug>.dita"
    - Ensure uniqueness by suffixing "-2", "-3", ... when needed
    - Update both the ditamap @href and the topics dict keys

    Args:
        context: DitaContext to update
        
    Returns:
        Updated DitaContext with renamed topics and updated references
    """
    logger.info("Updating topic filenames and references...")

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


def prune_empty_topics(context: DitaContext) -> DitaContext:
    """Remove topicrefs pointing to empty content modules.

    With the plugin architecture, sections are created as topichead elements,
    but content modules might still end up empty in edge cases. This function
    removes such empty modules and their topicrefs.

    Args:
        context: DitaContext to update
        
    Returns:
        Updated DitaContext with empty topics removed
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