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
    "merge_topics_by_titles",
    "merge_topics_by_levels",
    "merge_topics_by_styles",
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

    def _recurse(node: ET.Element, level: int, ancestor_topic_el: ET.Element | None):
        """Depth-first walk that merges nodes beyond *depth_limit*.

        Parameters
        ----------
        node
            Current <topicref>/<topichead> container we are iterating over.
        level
            1-based depth inside the ditamap (root = 1).
        ancestor_topic_el
            The closest ancestor *topic* element (a node that **can** hold
            ``conbody`` content). It stays the same while traversing through
            section-only levels that do **not** reference a topic file.
        """

        for tref in list(node):
            if tref.tag not in ("topicref", "topichead"):
                continue

            t_level = int(tref.get("data-level", level))

            # Resolve the <topic> element that this topicref points to (if any)
            href = tref.get("href")
            topic_el: ET.Element | None = None
            if href:
                fname = href.split("/")[-1]
                topic_el = ctx.topics.get(fname)

            # The next ancestor‐candidate is either this topic_el (when it is
            # a real topic) or the current ancestor_topic_el if this tref is a
            # section-only container.
            next_ancestor = topic_el if topic_el is not None else ancestor_topic_el

            # When maximum depth is exceeded we attempt to merge the content
            # into the *nearest* ancestor topic that can receive body
            # children.  If such an ancestor does not exist we leave the node
            # untouched so that its content is still rendered later.
            if t_level > depth_limit:
                if ancestor_topic_el is not None and topic_el is not None:
                    # -- Merge -------------------------------------------------
                    title_el = topic_el.find("title")
                    if title_el is not None and title_el.text:
                        clean_title = " ".join(title_el.text.split())
                        head_p = ET.Element("p", id=generate_dita_id())
                        head_p.text = clean_title

                        parent_body = ancestor_topic_el.find("conbody")
                        if parent_body is None:
                            parent_body = ET.SubElement(ancestor_topic_el, "conbody")
                        parent_body.append(head_p)

                    _copy_content(topic_el, ancestor_topic_el)

                    # Recurse so that grandchildren are merged as well (still
                    # targeting the same *ancestor_topic_el*)
                    _recurse(tref, t_level + 1, ancestor_topic_el)

                    # Remove the now-merged topicref and mark topic for purge
                    node.remove(tref)
                    removed_topics.add(fname)
                else:
                    # Either no ancestor topic yet or topic_el is None.
                    # If ancestor_topic_el is a *section* (has no href) but topic_el exists,
                    # we need to create an own-content module under that section.
                    if ancestor_topic_el is None and topic_el is not None:
                        # Find nearest section <topicref> (node) to attach module
                        section_container = node if node.tag in ("topicref", "topichead") else None
                        if section_container is not None:
                            target_mod = _ensure_content_module(ctx, section_container)
                            # Copy title paragraph + body
                            title_el = topic_el.find("title")
                            if title_el is not None and title_el.text:
                                clean_title = " ".join(title_el.text.split())
                                head_p = ET.Element("p", id=generate_dita_id())
                                head_p.text = clean_title
                                tb = target_mod.find("conbody") or ET.SubElement(target_mod, "conbody")
                                tb.append(head_p)

                            _copy_content(topic_el, target_mod)

                            # Recurse deeper merging into the *target_mod*
                            _recurse(tref, t_level + 1, target_mod)

                            # Remove source tref and purge
                            node.remove(tref)
                            removed_topics.add(fname)
                            continue

                    # Default: traverse deeper without removing
                    _recurse(tref, t_level + 1, next_ancestor)
            else:
                # Depth within limit – keep traversing deeper.
                _recurse(tref, t_level + 1, next_ancestor)

    _recurse(root, 1, None)

    # Purge merged topics from the map
    for fname in removed_topics:
        ctx.topics.pop(fname, None)

    # Final cleanup: make sure section-only <topicref> elements do not retain body
    for tref in root.xpath('.//topicref[not(@href)]'):
        for body in tref.findall('conbody'):
            tref.remove(body)

    # Mark depth merged so we avoid double processing
    ctx.metadata["merged_depth"] = depth_limit


def _clean_title(raw: str | None) -> str:
    """Normalize *raw* heading text for reliable comparisons."""
    if not raw:
        return ""
    return " ".join(raw.split()).lower()


def merge_topics_by_titles(ctx: "DitaContext", exclude_titles: set[str]) -> None:
    """Merge any topics whose *title* is in *exclude_titles* into their parent.

    The comparison is case-insensitive and whitespace-insensitive.  Behaviour
    is similar to :func:`merge_topics_below_depth` but operates on an explicit
    list of forbidden titles, independent of depth.
    """

    if not exclude_titles or ctx.ditamap_root is None:
        return

    # Pre-normalize for O(1) look-ups
    targets = {_clean_title(t) for t in exclude_titles}

    removed: Set[str] = set()

    def _walk(parent_ref, ancestor_topic_el):
        for tref in list(parent_ref):
            if tref.tag not in ("topicref", "topichead"):
                continue

            href = tref.get("href")
            topic_el = None
            fname = None
            if href:
                fname = href.split("/")[-1]
                topic_el = ctx.topics.get(fname)

            # Title to test comes from navtitle (preferred) or topic title
            title_txt = ""
            navtitle_el = tref.find("topicmeta/navtitle")
            if navtitle_el is not None and navtitle_el.text:
                title_txt = navtitle_el.text
            elif topic_el is not None:
                t_el = topic_el.find("title")
                title_txt = t_el.text if t_el is not None else ""

            if _clean_title(title_txt) in targets and ancestor_topic_el is not None and topic_el is not None:
                # 1) Preserve heading paragraph
                head_p = ET.Element("p", id=generate_dita_id())
                head_p.text = title_txt.strip()

                parent_body = ancestor_topic_el.find("conbody")
                if parent_body is None:
                    parent_body = ET.SubElement(ancestor_topic_el, "conbody")
                parent_body.append(head_p)

                # 2) Merge body content
                _copy_content(topic_el, ancestor_topic_el)

                # 3) Recurse into descendants so grand-children also merge
                _walk(tref, ancestor_topic_el)

                # 4) Remove topicref & mark topic for purge
                parent_ref.remove(tref)
                if fname:
                    removed.add(fname)
            else:
                # Continue traversal; update ancestor when we have a real topic
                next_ancestor = topic_el if topic_el is not None else ancestor_topic_el
                _walk(tref, next_ancestor)

    _walk(ctx.ditamap_root, None)

    for fname in removed:
        ctx.topics.pop(fname, None)

    # Mark to avoid duplicate processing
    ctx.metadata["merged_exclude"] = True


def merge_topics_by_levels(ctx: "DitaContext", exclude_levels: set[int]) -> None:
    """Merge all topics whose *data-level* attribute is in *exclude_levels*.

    This allows users to turn specific heading styles (e.g., all "Heading 2")
    into mere sections, merging their content into the nearest ancestor topic.
    """

    if not exclude_levels or ctx.ditamap_root is None:
        return

    removed: Set[str] = set()

    def _walk(node: ET.Element, level: int, ancestor_topic_el: ET.Element | None):
        for tref in list(node):
            if tref.tag not in ("topicref", "topichead"):
                continue

            t_level = int(tref.get("data-level", level))

            href = tref.get("href")
            topic_el = None
            fname = None
            if href:
                fname = href.split("/")[-1]
                topic_el = ctx.topics.get(fname)

            next_ancestor = topic_el if topic_el is not None else ancestor_topic_el

            if t_level in exclude_levels and ancestor_topic_el is not None:
                # If the node has its own topic content, merge it first
                if topic_el is not None:
                    # Preserve heading title as paragraph
                    title_el = topic_el.find("title")
                    if title_el is not None and title_el.text:
                        head_p = ET.Element("p", id=generate_dita_id())
                        head_p.text = " ".join(title_el.text.split())
                        parent_body = ancestor_topic_el.find("conbody")
                        if parent_body is None:
                            parent_body = ET.SubElement(ancestor_topic_el, "conbody")
                        parent_body.append(head_p)

                    _copy_content(topic_el, ancestor_topic_el)

                # Recurse into children so grandchildren are kept/merged
                _walk(tref, t_level + 1, ancestor_topic_el)

                # Remove the excluded node itself
                node.remove(tref)

                if fname:
                    removed.add(fname)
            else:
                _walk(tref, t_level + 1, next_ancestor)

    _walk(ctx.ditamap_root, 1, None)

    for fname in removed:
        ctx.topics.pop(fname, None)

    ctx.metadata["merged_exclude_levels"] = True


def merge_topics_by_styles(ctx: "DitaContext", exclude_map: dict[int, set[str]]) -> None:
    """Merge topics whose (level, style) matches *exclude_map*.

    *exclude_map* maps heading level (int) to a set of style names to be
    removed/merged into the parent. Style comparison is case-sensitive to
    match Word names.
    """

    if not exclude_map or ctx.ditamap_root is None:
        return

    removed: Set[str] = set()

    def _walk(node: ET.Element, level: int, ancestor_topic_el: ET.Element | None):
        for tref in list(node):
            if tref.tag not in ("topicref", "topichead"):
                continue

            t_level = int(tref.get("data-level", level))
            style_name = tref.get("data-style", "")

            href = tref.get("href")
            topic_el = None
            fname = None
            if href:
                fname = href.split("/")[-1]
                topic_el = ctx.topics.get(fname)

            next_ancestor = topic_el if topic_el is not None else ancestor_topic_el

            if t_level in exclude_map and style_name in exclude_map[t_level] and ancestor_topic_el is not None:
                # Preserve heading title paragraph then merge body content
                if topic_el is not None:
                    title_el = topic_el.find("title")
                    if title_el is not None and title_el.text:
                        head_p = ET.Element("p", id=generate_dita_id())
                        head_p.text = " ".join(title_el.text.split())
                        parent_body = ancestor_topic_el.find("conbody")
                        if parent_body is None:
                            parent_body = ET.SubElement(ancestor_topic_el, "conbody")
                        parent_body.append(head_p)

                    _copy_content(topic_el, ancestor_topic_el)

                # Recurse into children
                _walk(tref, t_level + 1, ancestor_topic_el)

                node.remove(tref)
                if fname:
                    removed.add(fname)
            else:
                _walk(tref, t_level + 1, next_ancestor)

    _walk(ctx.ditamap_root, 1, None)

    for fname in removed:
        ctx.topics.pop(fname, None)

    ctx.metadata["merged_exclude_styles"] = True


# ---------------------------------------------------------------------------
# Helper utilities (internal)
# ---------------------------------------------------------------------------


def _new_topic_with_title(title_text: str) -> ET.Element:
    """Create a bare <concept> topic element with *title_text*."""
    topic_el = ET.Element("concept", id=generate_dita_id())
    title_el = ET.SubElement(topic_el, "title")
    title_el.text = title_text
    # Body will be added later when content is copied
    return topic_el


def _ensure_content_module(ctx: "DitaContext", section_tref: ET.Element) -> ET.Element:
    """Ensure there is a child *module* topic under *section_tref* and return its <concept> element.

    If the first child already references a topic (module) we reuse it, otherwise we
    create a new topic file, register it in ctx.topics and insert a new <topicref>.
    """
    # Try to reuse the first existing module child if present
    for child in section_tref:
        href = child.get("href")
        if href:
            fname = href.split("/")[-1]
            existing_topic = ctx.topics.get(fname)
            if existing_topic is not None:
                return existing_topic

    # No module child – create a fresh one
    # Derive filename similar to converter naming scheme: topic_<id>.dita
    new_id = generate_dita_id()
    fname = f"topic_{new_id}.dita"

    # Build topic element
    section_title_el = section_tref.find("topicmeta/navtitle")
    title_txt = section_title_el.text if section_title_el is not None and section_title_el.text else "Untitled"
    topic_el = _new_topic_with_title(title_txt)

    # Register in topics map
    ctx.topics[fname] = topic_el

    # Create child topicref
    child_ref = ET.Element("topicref", href=f"topics/{fname}")
    child_ref.set("data-level", str(int(section_tref.get("data-level", 1)) + 1))
    # Keep navtitle in sync
    nav = ET.SubElement(child_ref, "topicmeta")
    navtitle = ET.SubElement(nav, "navtitle")
    navtitle.text = title_txt

    # Insert as first child to preserve order
    section_tref.insert(0, child_ref)

    return topic_el 