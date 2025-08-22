from __future__ import annotations

"""DOCX → DITA conversion implementation.

Core conversion logic that transforms Word documents into DITA topics
and ditamaps with proper Orlando-specific metadata and structure.
"""

from datetime import datetime
import time
import os
import uuid
import logging
import re
from typing import Any, Dict

from docx import Document  # type: ignore

from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.parser import extract_images_to_context, build_style_heading_map, iter_block_items
from orlando_toolkit.core.parser.style_analyzer import _analyze_structural_patterns, _detect_generic_heading_level
from orlando_toolkit.config import ConfigManager

# Helper functions migrated from legacy converter
from .helpers import (
    STYLE_MAP,
    add_orlando_topicmeta,
)

logger = logging.getLogger(__name__)

__all__ = ["convert_docx_to_dita"]


def convert_docx_to_dita(file_path: str, metadata: Dict[str, Any]) -> DitaContext:  # noqa: C901 (complex)
    """Convert a DOCX file into an in-memory DitaContext.

    Processes Word document structure, formatting, images, and metadata
    to generate Orlando-compliant DITA topics and ditamap.
    """
    logger.info("Starting DOCX->DITA conversion (core.converter)...: %s", file_path)

    context = DitaContext(metadata=dict(metadata))

    try:
        logger.info("Loading DOCX file...")
        doc = Document(file_path)
        all_images_map_rid = extract_images_to_context(doc, context)

        logger.info("Extracting images...")

        map_root = ET.Element("map")
        map_root.set("{http://www.w3.org/XML/1998/namespace}lang", "en-US")
        context.ditamap_root = map_root

        map_title = ET.SubElement(map_root, "title")
        map_title.text = metadata.get("manual_title", "Document Title")

        add_orlando_topicmeta(map_root, context.metadata)

        # Get style detection configuration (file-based only)
        config_manager = ConfigManager()
        style_detection_config = config_manager.get_style_detection() or {}

        # Unified structural inference flag (backward-compatible):
        # Priority order for enabling: metadata.enable_structural_style_inference →
        # metadata.use_structural_analysis → metadata.use_enhanced_style_detection →
        # config.enable_structural_style_inference → config.use_structural_analysis → config.use_enhanced_style_detection → default False
        enable_structural = metadata.get("enable_structural_style_inference")
        if enable_structural is None:
            usa_md = metadata.get("use_structural_analysis")
            enh_md = metadata.get("use_enhanced_style_detection")
            if usa_md is not None:
                enable_structural = bool(usa_md)
            elif enh_md is not None:
                enable_structural = bool(enh_md)
        if enable_structural is None:
            es_cfg = style_detection_config.get("enable_structural_style_inference")
            if es_cfg is not None:
                enable_structural = bool(es_cfg)
            else:
                usa_cfg = style_detection_config.get("use_structural_analysis")
                enh_cfg = style_detection_config.get("use_enhanced_style_detection")
                if usa_cfg is not None:
                    enable_structural = bool(usa_cfg)
                elif enh_cfg is not None:
                    enable_structural = bool(enh_cfg)
        if enable_structural is None:
            enable_structural = False

        # Structural inference parameter (only used if structural is enabled)
        mfp = metadata.get("min_following_paragraphs")
        if mfp is None:
            mfp = style_detection_config.get("min_following_paragraphs", 3)
        try:
            mfp_int = int(mfp)
        except Exception:
            mfp_int = 3

        # Build base style map and optionally augment with structural inference
        base_t0 = time.perf_counter()
        base_map = build_style_heading_map(doc)
        base_ms = int((time.perf_counter() - base_t0) * 1000)
        style_heading_map = dict(base_map)
        structural_added = 0
        structural_ms = 0

        if enable_structural:
            st_t0 = time.perf_counter()
            try:
                structural_styles = _analyze_structural_patterns(doc, mfp_int)
            except Exception as e:
                logger.warning(f"Structural analysis failed: {e}")
                structural_styles = {}
            # Add-only merge: do not override base detection
            before = len(style_heading_map)
            for style_name, level in (structural_styles or {}).items():
                if style_name not in style_heading_map:
                    style_heading_map[style_name] = level
            structural_added = len(style_heading_map) - before
            structural_ms = int((time.perf_counter() - st_t0) * 1000)
        else:
            pass

        # Apply legacy and user overrides with clear priority order
        logger.debug(f"Base style map: {len(base_map)} styles")

        # Legacy STYLE_MAP: fill missing only (lower priority than base/structural)
        legacy_added = 0
        for k, v in STYLE_MAP.items():
            if k not in style_heading_map:
                style_heading_map[k] = v
                legacy_added += 1

        # Generic heading-name detection (e.g., "HEADING 5 GM"). From config, metadata can override.
        generic_match_enabled = metadata.get(
            "generic_heading_match",
            bool(style_detection_config.get("generic_heading_match", False)),
        )
        generic_added = 0
        generic_ms = 0
        if generic_match_enabled:
            gen_t0 = time.perf_counter()
            for sty in getattr(doc, "styles", []) or []:  # type: ignore[attr-defined]
                try:
                    name = getattr(sty, "name", None)  # type: ignore[attr-defined]
                    if not name or name in style_heading_map:
                        continue
                    level = _detect_generic_heading_level(name)
                    if level:
                        style_heading_map[name] = level
                        generic_added += 1
                except Exception:
                    continue
            generic_ms = int((time.perf_counter() - gen_t0) * 1000)

        # User override mapping (highest priority): allow overrides and additions
        if isinstance(metadata.get("style_heading_map"), dict):
            user_overrides = metadata["style_heading_map"]  # type: ignore[arg-type]
            added_or_overridden = 0
            for k, v in user_overrides.items():
                try:
                    prev = style_heading_map.get(k)
                    if prev != v:
                        added_or_overridden += 1
                    style_heading_map[k] = v
                except Exception:
                    continue
            logger.debug(f"Applied {added_or_overridden} user style overrides/additions")

        # Final style detection summary
        logger.info(
            "Style detection: base=%s structural_added=%s legacy_fill=%s generic_added=%s total=%s | base_ms=%sms structural_ms=%sms generic_ms=%sms",
            len(base_map), structural_added, legacy_added, generic_added, len(style_heading_map), base_ms, structural_ms, generic_ms,
        )
        logger.debug(f"Final style heading map: {len(style_heading_map)} styles detected")
        if logger.isEnabledFor(logging.DEBUG):
            for style_name, level in sorted(style_heading_map.items(), key=lambda x: (x[1], x[0])):
                logger.debug(f"  Level {level}: '{style_name}'")

        # Prepare topic generation (two-pass). Actual building starts after structure analysis below.
        logger.debug("Preparing topic generation (two-pass)...")

        # ======================================================================
        # TWO-PASS APPROACH: Build structure first, then generate DITA
        # ======================================================================
        from orlando_toolkit.core.converter.structure_builder import (
            build_document_structure,
            determine_node_roles,
            generate_dita_from_structure,
            _add_content_to_topic,
        )

        # Pass 1: Build complete document structure
        logger.info("Analyzing document structure...")
        root_nodes = build_document_structure(doc, style_heading_map, all_images_map_rid)

        # Pass 2: Determine section vs module roles
        logger.info("Determining section/module roles...")
        determine_node_roles(root_nodes)

        # Pass 3: Generate DITA topics and map structure
        logger.info("Building topics...")
        heading_counters = [0] * 9
        parent_elements: Dict[int, ET.Element] = {0: map_root}

        generate_dita_from_structure(
            root_nodes,
            context,
            context.metadata,
            all_images_map_rid,
            map_root,
            heading_counters,
        )

        # ------------------------------------------------------------------
        # Fallback: no topics detected → create a single topic hosting all
        # content, titled after the DOCX filename (without extension).
        # ------------------------------------------------------------------
        if not context.topics:
            fallback_title = os.path.splitext(os.path.basename(file_path))[0] or "Document"
            file_name = f"topic_{uuid.uuid4().hex[:10]}.dita"
            topic_id = file_name.replace(".dita", "")

            concept_root, conbody = (
                # reuse existing builder to keep formatting/images consistent
                __import__(
                    "orlando_toolkit.core.converter.helpers", fromlist=["create_dita_concept"]
                ).create_dita_concept(
                    fallback_title,
                    topic_id,
                    context.metadata.get("revision_date", datetime.now().strftime("%Y-%m-%d")),
                )
            )

            # Feed all block items; underlying helper filters empties and
            # handles paragraphs, lists, images, and tables uniformly.
            all_blocks = [blk for blk in iter_block_items(doc)]
            _add_content_to_topic(conbody, all_blocks, all_images_map_rid)

            # Reference in ditamap
            topicref = ET.SubElement(
                map_root,
                "topicref",
                {"href": f"topics/{file_name}", "locktitle": "yes"},
            )
            topicref.set("data-level", "1")

            topicmeta_ref = ET.SubElement(topicref, "topicmeta")
            navtitle_ref = ET.SubElement(topicmeta_ref, "navtitle")
            navtitle_ref.text = fallback_title
            critdates_ref = ET.SubElement(topicmeta_ref, "critdates")
            _rev_date_fb = context.metadata.get("revision_date") or datetime.now().strftime("%Y-%m-%d")
            ET.SubElement(critdates_ref, "created", date=_rev_date_fb)
            ET.SubElement(critdates_ref, "revised", modified=_rev_date_fb)
            ET.SubElement(topicmeta_ref, "othermeta", name="tocIndex", content="1")
            ET.SubElement(topicmeta_ref, "othermeta", name="foldout", content="false")
            ET.SubElement(topicmeta_ref, "othermeta", name="tdm", content="false")

            context.topics[file_name] = concept_root

    except Exception as exc:
        logger.error("Conversion failed: %s", exc, exc_info=True)
        raise

    logger.info("Conversion finished.")
    return context 