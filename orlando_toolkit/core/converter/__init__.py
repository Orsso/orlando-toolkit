from __future__ import annotations

"""DOCX to DITA conversion logic.

This sub-package provides the core conversion functionality, exposing
stable interfaces for higher-level services while maintaining compatibility
with existing workflows.
"""

from typing import Any, Dict
import os
import uuid
import logging

from orlando_toolkit.core.models import DitaContext

# Core conversion implementation
from .docx_to_dita import convert_docx_to_dita

__all__ = [
    "convert_docx_to_dita",
    "save_dita_package",
    "update_image_references_and_names",
    "update_topic_references_and_names",
]

logger = logging.getLogger(__name__)


# convert_docx_to_dita now provided by .docx_to_dita


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
    dtd_dir = os.path.join(data_dir, "dtd")

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
    logger.info("Updating image names and references (core.converter)…")

    manual_code = context.metadata.get("manual_code", "MANUAL")
    prefix = context.metadata.get("prefix", "IMG")

    rename_map: dict[str, str] = {}
    for i, original_filename in enumerate(list(context.images.keys())):
        section_num = "0"  # placeholder until real section logic is added
        img_num = i + 1
        extension = os.path.splitext(original_filename)[1]
        new_filename = f"{prefix}-{manual_code}-{section_num}-{img_num}{extension}"
        rename_map[original_filename] = new_filename

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
    logger.info("Updating topic filenames and references (core.converter)…")

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