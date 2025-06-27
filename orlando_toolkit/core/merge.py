from __future__ import annotations

"""Topic merge helper – joins content from descendants deeper than a depth limit.

This module is UI-agnostic and manipulates only the in-memory DitaContext.
It must not perform any file I/O so that it can be reused by CLI, GUI and tests.
"""

from copy import deepcopy
from typing import Set
from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext  # noqa: F401
from orlando_toolkit.core.utils import generate_dita_id

__all__ = [
    "merge_topics_below_depth",
]


BLOCK_LEVEL_TAGS: Set[str] = {
    "p",
    "ul",
    "ol",
    "sl",
    "table",
    "section",
    "fig",
    "image",
    "codeblock",
}


def _copy_content(src_topic: ET.Element, dest_topic: ET.Element) -> None:
    """Append block-level children from *src_topic* into *dest_topic*."""

    dest_body = dest_topic.find("conbody")
    if dest_body is None:
        dest_body = ET.SubElement(dest_topic, "conbody")

    src_body = src_topic.find("conbody")
    if src_body is None:
        return

    for child in list(src_body):
        if child.tag in BLOCK_LEVEL_TAGS:
            # Shallow copy so we don't affect original
            new_child = deepcopy(child)
            # Ensure unique @id attributes to avoid duplicates
            id_map = {}
            if "id" in new_child.attrib:
                old = new_child.get("id")
                new = generate_dita_id()
                new_child.set("id", new)
                id_map[old] = new

            # Also dedup nested IDs and collect mapping
            for el in new_child.xpath('.//*[@id]'):
                old = el.get("id")
                new = generate_dita_id()
                el.set("id", new)
                id_map[old] = new

            # Update internal references within the copied subtree
            for el in new_child.xpath('.//*[@href|@conref]'):
                for attr in ("href", "conref"):
                    val = el.get(attr)
                    if val and val.startswith("#"):
                        ref = val[1:]
                        if ref in id_map:
                            el.set(attr, f"#{id_map[ref]}")
            dest_body.append(new_child)


def merge_topics_below_depth(ctx: "DitaContext", depth_limit: int) -> None:  # noqa: D401
    """Merge descendants deeper than *depth_limit* into their nearest ancestor.

    The function modifies *ctx* in-place:
        • Updates ctx.ditamap_root (removes pruned <topicref>s)
        • Strips merged entries from ctx.topics
        • Sets ctx.metadata["merged_depth"] = depth_limit
    """

    root = ctx.ditamap_root
    if root is None:
        return

    removed_topics: Set[str] = set()

    def _recurse(node: ET.Element, level: int, parent_topic_el: ET.Element | None):
        for tref in list(node):
            if tref.tag not in ("topicref", "topichead"):
                continue
            t_level = int(tref.get("data-level", level))
            href = tref.get("href")
            topic_el = None
            if href:
                fname = href.split("/")[-1]
                topic_el = ctx.topics.get(fname)
            if t_level > depth_limit:
                # First, merge this node (and its descendants) into the surviving ancestor
                if parent_topic_el is not None and topic_el is not None:
                    # Preserve child title as a heading paragraph before content
                    if topic_el is not None:
                        title_el = topic_el.find("title")
                        if title_el is not None and title_el.text:
                            clean_title = " ".join(title_el.text.split())
                            head_p = ET.Element("p", id=generate_dita_id())
                            head_p.text = clean_title
                            # insert heading before other merged blocks
                            parent_body = parent_topic_el.find("conbody")
                            if parent_body is None:
                                parent_body = ET.SubElement(parent_topic_el, "conbody")
                            parent_body.append(head_p)

                        _copy_content(topic_el, parent_topic_el)

                    # Recurse into its children so grandchildren are also merged
                    _recurse(tref, t_level + 1, parent_topic_el)

                node.remove(tref)
                if href:
                    removed_topics.add(fname)
            else:
                # Recurse further
                _recurse(tref, t_level + 1, topic_el)

    _recurse(root, 1, None)

    # Purge merged topics from the map
    for fname in removed_topics:
        ctx.topics.pop(fname, None)

    # Mark depth merged so we avoid double processing
    ctx.metadata["merged_depth"] = depth_limit 