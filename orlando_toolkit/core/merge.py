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
    "merge_topics_by_titles", 
    "merge_topics_unified",
]


# BLOCK_LEVEL_TAGS removed - we now copy ALL content to preserve completeness


def _copy_content(src_topic: ET.Element, dest_topic: ET.Element) -> None:
    """Copy all content children from src_topic conbody into dest_topic conbody.
    
    Preserves complete content hierarchy to avoid data loss during merge operations.
    """

    dest_body = dest_topic.find("conbody")
    if dest_body is None:
        dest_body = ET.SubElement(dest_topic, "conbody")

    src_body = src_topic.find("conbody")
    if src_body is None:
        return

    for child in list(src_body):
        # Copy ALL children, not just those in BLOCK_LEVEL_TAGS
        # This ensures no content is lost during merge operations
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



def _clean_title(raw: str | None) -> str:
    """Normalize *raw* heading text for reliable comparisons."""
    if not raw:
        return ""
    return " ".join(raw.split()).lower()


def merge_topics_by_titles(ctx: "DitaContext", exclude_titles: set[str]) -> None:
    """Merge any topics whose *title* is in *exclude_titles* into their parent.

    The comparison is case-insensitive and whitespace-insensitive. This operates on an explicit
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





# ---------------------------------------------------------------------------
# Helper utilities (internal) - DRY refactoring
# ---------------------------------------------------------------------------

def _add_title_paragraph(target_el: ET.Element, title_text: str) -> None:
    """Add a title as paragraph to target element's conbody.
    
    DRY helper to avoid repetition of conbody creation and paragraph addition.
    """
    if not title_text:
        return
    
    clean_title = " ".join(title_text.split())
    head_p = ET.Element("p", id=generate_dita_id())
    head_p.text = clean_title

    parent_body = target_el.find("conbody")
    if parent_body is None:
        parent_body = ET.SubElement(target_el, "conbody")
    parent_body.append(head_p)

def _extract_title_text(element: ET.Element, is_topichead: bool = False) -> str:
    """Extract title text from topic or topichead element.
    
    DRY helper to handle both topic/title and topichead/topicmeta/navtitle patterns.
    """
    if is_topichead:
        navtitle_el = element.find("topicmeta/navtitle")
        return navtitle_el.text if navtitle_el is not None and navtitle_el.text else ""
    else:
        title_el = element.find("title")
        return title_el.text if title_el is not None and title_el.text else ""

def _find_parent_module(ctx: "DitaContext", current_node: ET.Element) -> ET.Element | None:
    """Find or create a parent content module by traversing up the hierarchy.
    
    DRY helper to avoid code duplication in ancestor finding logic.
    """
    parent_module = None
    current = current_node.getparent()
    while current is not None and parent_module is None:
        if current.tag == "topichead":
            # Create a content module for this parent topichead
            parent_module = _ensure_content_module(ctx, current)
            break
        elif current.tag == "topicref" and current.get("href"):
            # Found a content-bearing topicref
            parent_fname = current.get("href").split("/")[-1]
            parent_module = ctx.topics.get(parent_fname)
            break
        current = current.getparent()
    return parent_module

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


def merge_topics_unified(ctx: "DitaContext", depth_limit: int, exclude_style_map: dict[int, set[str]] = None) -> None:
    """Unified merge that handles both depth limits and style exclusions in a single pass.
    
    This replaces the problematic sequential approach that caused content loss.
    Merges topics if they exceed depth_limit OR if their (level, style) is in exclude_style_map.
    
    Parameters
    ----------
    ctx : DitaContext
        The context containing topics and ditamap to modify
    depth_limit : int
        Maximum allowed depth (topics deeper than this get merged)
    exclude_style_map : dict[int, set[str]], optional
        Map of level -> set of style names to exclude/merge
    """
    
    if ctx.ditamap_root is None:
        return
        
    exclude_style_map = exclude_style_map or {}
    removed_topics: Set[str] = set()
    
    def _should_merge(tref: ET.Element) -> bool:
        """Determine if a topicref should be merged based on depth OR style."""
        t_level = int(tref.get("data-level", 1))  # Use actual data-level attribute
        style_name = tref.get("data-style", "")
        
        # For topichead (structural sections): only merge if they exceed depth OR have excluded style
        # They need to be converted to content-bearing topics when merged
        if tref.tag == "topichead":
            # Merge topichead if beyond depth limit (needs conversion to topic)
            if t_level > depth_limit:
                return True
            # Merge topichead if style is excluded for this level
            if t_level in exclude_style_map and style_name in exclude_style_map[t_level]:
                return True
            return False
            
        # For topicref (content-bearing): same logic applies
        # Merge if beyond depth limit
        if t_level > depth_limit:
            return True
            
        # Merge if style is excluded for this level
        if t_level in exclude_style_map and style_name in exclude_style_map[t_level]:
            return True
            
        return False
    
    def _recurse(node: ET.Element, level: int, ancestor_topic_el: ET.Element | None, ancestor_tref: ET.Element | None = None):
        """Single-pass traversal that applies both depth and style criteria."""
        
        for tref in list(node):
            if tref.tag not in ("topicref", "topichead"):
                continue

            t_level = int(tref.get("data-level", level))

            # Resolve the topic element that this topicref points to (if any)
            href = tref.get("href")
            topic_el: ET.Element | None = None
            fname = None
            if href:
                fname = href.split("/")[-1]
                topic_el = ctx.topics.get(fname)

            # Check if this topic should be merged (unified decision)
            if _should_merge(tref):
                if tref.tag == "topichead" and ancestor_topic_el is not None:
                    # topichead with ancestor: convert title to paragraph and merge children
                    title_text = _extract_title_text(tref, is_topichead=True)
                    _add_title_paragraph(ancestor_topic_el, title_text)
                    _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)
                    node.remove(tref)
                    continue
                    
                elif ancestor_topic_el is not None and topic_el is not None:
                    # Topic with ancestor: preserve title, copy content, and merge
                    title_text = _extract_title_text(topic_el, is_topichead=False)
                    _add_title_paragraph(ancestor_topic_el, title_text)
                    _copy_content(topic_el, ancestor_topic_el)
                    _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)
                    node.remove(tref)
                    removed_topics.add(fname)
                    
                elif tref.tag == "topichead" and ancestor_topic_el is None:
                    # topichead without ancestor: find/create parent module
                    parent_module = _find_parent_module(ctx, tref)
                    if parent_module is not None:
                        title_text = _extract_title_text(tref, is_topichead=True)
                        _add_title_paragraph(parent_module, title_text)
                        _recurse(tref, t_level + 1, parent_module, tref)
                        node.remove(tref)
                        continue
                    # Fallback: traverse without removing 
                    _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)
                    continue
                
                elif ancestor_topic_el is None and topic_el is not None:
                    # Topic without ancestor: find/create parent module
                    parent_module = _find_parent_module(ctx, tref)
                    if parent_module is not None:
                        title_text = _extract_title_text(topic_el, is_topichead=False)
                        _add_title_paragraph(parent_module, title_text)
                        _copy_content(topic_el, parent_module)
                        _recurse(tref, t_level + 1, parent_module, tref)
                        node.remove(tref)
                        removed_topics.add(fname)
                        continue
                    # Fallback: traverse deeper without removing
                    _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)
                else:
                    # No content to merge - just traverse deeper
                    _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)
            else:
                # Not merging - traverse deeper with updated ancestor
                # Only update ancestor if this is a topicref with content (has href)
                if tref.tag == "topicref" and href and topic_el is not None:
                    # This topicref can hold content, so it becomes the new ancestor
                    next_ancestor_topic = topic_el
                    next_ancestor_tref = tref
                else:
                    # topichead or no topic, keep current ancestor
                    next_ancestor_topic = ancestor_topic_el
                    next_ancestor_tref = ancestor_tref
                    
                _recurse(tref, t_level + 1, next_ancestor_topic, next_ancestor_tref)

    # Start the unified traversal
    _recurse(ctx.ditamap_root, 1, None, None)

    # Clean up merged topics
    for fname in removed_topics:
        ctx.topics.pop(fname, None)

    # Post-merge cleanup: collapse redundant section + content module structures
    _collapse_redundant_sections(ctx)

    # Note: No final cleanup needed since topichead elements don't have conbody

    # Set metadata to indicate both operations completed
    ctx.metadata["merged_depth"] = depth_limit
    if exclude_style_map:
        ctx.metadata["merged_exclude_styles"] = True


def _collapse_redundant_sections(ctx: "DitaContext") -> None:
    """Collapse topichead sections that have only a content module left.
    
    When filtering removes all children except the content module, the section/module
    separation becomes redundant. This function merges them into a single topic.
    """
    if ctx.ditamap_root is None:
        return
    
    def _find_collapsible_sections(node: ET.Element) -> list[ET.Element]:
        """Find topichead sections that only have one content module child."""
        collapsible = []
        
        for topichead in node.findall(".//topichead"):
            # Count actual topicref children (not metadata)
            children = [child for child in topichead if child.tag in ("topicref", "topichead")]
            
            # Section is collapsible if it has exactly one child with content
            if len(children) == 1:
                child = children[0]
                child_href = child.get("href")
                if child_href:
                    # Verify the child topic exists
                    child_fname = child_href.split("/")[-1]
                    if child_fname in ctx.topics:
                        collapsible.append(topichead)
        
        return collapsible
    
    # Find all collapsible sections
    collapsible_sections = _find_collapsible_sections(ctx.ditamap_root)
    
    for section_topichead in collapsible_sections:
        # Get the single content module child
        content_child = None
        for child in section_topichead:
            if child.tag == "topicref" and child.get("href"):
                content_child = child
                break
        
        if content_child is None:
            continue
            
        # Get the content module topic
        content_href = content_child.get("href")
        content_fname = content_href.split("/")[-1]
        content_topic = ctx.topics.get(content_fname)
        
        if content_topic is None:
            continue
        
        # Transfer section metadata to the content module
        section_navtitle = section_topichead.find("topicmeta/navtitle")
        if section_navtitle is not None and section_navtitle.text:
            # Update content topic title to match section
            content_title_el = content_topic.find("title")
            if content_title_el is not None:
                content_title_el.text = section_navtitle.text
        
        # Copy section attributes to content child
        for attr, value in section_topichead.attrib.items():
            content_child.set(attr, value)
        
        # Replace section with content module in the parent
        parent = section_topichead.getparent()
        if parent is not None:
            parent_index = list(parent).index(section_topichead)
            parent.remove(section_topichead)
            parent.insert(parent_index, content_child) 