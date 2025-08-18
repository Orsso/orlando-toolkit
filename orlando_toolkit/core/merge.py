from __future__ import annotations

"""Topic merge helper – joins content from descendants deeper than a depth limit.

This module is UI-agnostic and manipulates only the in-memory DitaContext.
It must not perform any file I/O so that it can be reused by CLI, GUI and tests.
"""

from copy import deepcopy
from typing import Set, Optional, Tuple
from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext  # noqa: F401
from orlando_toolkit.core.utils import generate_dita_id

__all__ = [
    "merge_topics_by_titles", 
    "merge_topics_unified",
    "convert_section_to_local_topic",
    "merge_topicref_into",
]


# BLOCK_LEVEL_TAGS removed - we now copy ALL content to preserve completeness


def _copy_content(src_topic: ET.Element, dest_topic: ET.Element) -> None:
    """Copy all content children from src_topic conbody into dest_topic conbody.
    
    Preserves complete content hierarchy and de-duplicates @id values.
    """

    dest_body = dest_topic.find("conbody")
    if dest_body is None:
        dest_body = ET.SubElement(dest_topic, "conbody")

    src_body = src_topic.find("conbody")
    if src_body is None:
        return

    for child in list(src_body):
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
                # Use shared helper for consistent behavior
                try:
                    removed_name = merge_topicref_into(ctx, ancestor_topic_el, tref)
                except Exception:
                    removed_name = None
                # Recurse into descendants so grand-children also merge
                _walk(tref, ancestor_topic_el)
                # Remove topicref & mark topic for purge (if helper didn't already)
                try:
                    if tref.getparent() is parent_ref:
                        parent_ref.remove(tref)
                except Exception:
                    pass
                if removed_name:
                    removed.add(removed_name)
                elif fname:
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
    # Ensure visible emphasis without relying on external CSS by uppercasing and
    # wrapping in bold+underline inline elements.
    try:
        bold = ET.SubElement(head_p, "b")
        underline = ET.SubElement(bold, "u")
        underline.text = clean_title.upper()
    except Exception:
        # Fallback to plain text if inline elements cannot be created
        head_p.text = clean_title.upper()
    # Mark paragraph for downstream styling (preview + consumers)
    head_p.set("outputclass", "merged-title")
    # Keep a class for downstream consumers (preview/styling)

    parent_body = target_el.find("conbody")
    if parent_body is None:
        parent_body = ET.SubElement(target_el, "conbody")
    # De-duplicate: if the closest previous merged-title has the same text, skip
    try:
        # Compute new visible text using the canonical cleaned title
        new_text = clean_title.upper()
        for el in reversed(list(parent_body)):
            if getattr(el, 'tag', None) != 'p':
                continue
            oc = el.get("outputclass") or ""
            if "merged-title" not in oc:
                # Stop only when we encounter a merged-title; other paragraphs are fine to skip
                continue
            # Extract previous visible text (handles nested b/u)
            prev_text = (el.text or "")
            if not prev_text:
                try:
                    txt_nodes = el.xpath(".//text()")
                    prev_text = "".join(t for t in txt_nodes if isinstance(t, str))
                except Exception:
                    prev_text = ""
            if prev_text.strip().upper() == new_text:
                return
            # Different merged-title encountered → do not dedup further
            break
    except Exception:
        pass
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
    # Structural metadata to ensure consistent merge/filter behavior
    try:
        next_level = int(section_tref.get("data-level", 1)) + 1
    except Exception:
        next_level = 2
    child_ref.set("data-level", str(next_level))
    # Standardize style so style-based filters operate predictably
    child_ref.set("data-style", f"Heading {next_level}")
    # Mark origin was previously recorded via a non-standard attribute; avoid invalid DITA attrs
    # Keep navtitle in sync
    nav = ET.SubElement(child_ref, "topicmeta")
    navtitle = ET.SubElement(nav, "navtitle")
    navtitle.text = title_txt

    # Insert after topicmeta to preserve DTD order (topicmeta must be first if present)
    try:
        tm_index = None
        for idx, ch in enumerate(list(section_tref)):
            if getattr(ch, "tag", None) == "topicmeta":
                tm_index = idx
                break
        if tm_index is None:
            section_tref.insert(0, child_ref)
        else:
            section_tref.insert(tm_index + 1, child_ref)
    except Exception:
        # Fallback to append
        section_tref.append(child_ref)

    return topic_el 


def merge_topicref_into(ctx: "DitaContext", target_topic_el: ET.Element, src_tref: ET.Element) -> str | None:
    """Merge a single topicref into an existing target topic.

    Adds a title paragraph (merged-title), copies the entire conbody, and removes the
    src_tref from the map. Returns the filename of the merged topic for later purge.
    Returns None if the source has no resolvable topic.
    """
    try:
        href = src_tref.get("href") or ""
        if not href:
            return None
        fname = href.split("/")[-1]
        src_topic = ctx.topics.get(fname)
        if src_topic is None:
            return None
        # Title paragraph then body content
        title_text = _extract_title_text(src_topic, is_topichead=False)
        _add_title_paragraph(target_topic_el, title_text)
        _copy_content(src_topic, target_topic_el)
        # Remove topicref from the map
        parent = src_tref.getparent()
        if parent is not None:
            try:
                parent.remove(src_tref)
            except Exception:
                pass
        return fname
    except Exception:
        return None

def convert_section_to_local_topic(ctx: "DitaContext", section_tref: ET.Element) -> tuple[ET.Element | None, list[str]]:
    """Convert a section (topichead) into a content-bearing topic under itself.

    - Ensures a content module topic exists as first child topicref
    - Merges ALL descendant topicrefs' titles + content into that module
    - Removes processed descendants and replaces the section with the module topicref
    - Returns (target_topic_el, removed_filenames)
    """
    if ctx is None or section_tref is None or getattr(section_tref, "tag", None) != "topichead":
        return (None, [])

    # Ensure content module child exists
    content_child = None
    for child in list(section_tref):
        if getattr(child, "tag", None) == "topicref" and child.get("href"):
            content_child = child
            break
    if content_child is None:
        try:
            _ensure_content_module(ctx, section_tref)
        except Exception:
            pass
        for child in list(section_tref):
            if getattr(child, "tag", None) == "topicref" and child.get("href"):
                content_child = child
                break
    if content_child is None:
        return (None, [])

    # Resolve target topic element
    target_topic_el = None
    try:
        href = content_child.get("href") or ""
        fname = href.split("/")[-1] if href else ""
        target_topic_el = ctx.topics.get(fname)
    except Exception:
        target_topic_el = None

    removed_files: list[str] = []

    def _merge_descendants(node: ET.Element) -> None:
        for sub in list(node):
            tag = getattr(sub, "tag", None)
            if tag not in ("topicref", "topichead"):
                continue
            # Skip the module itself
            if sub is content_child:
                continue
            if tag == "topicref" and sub.get("href"):
                try:
                    s_href = sub.get("href") or ""
                    s_fname = s_href.split("/")[-1]
                    s_topic = ctx.topics.get(s_fname)
                except Exception:
                    s_topic = None
                    s_fname = ""
                if target_topic_el is not None and s_topic is not None:
                    t_el = s_topic.find("title")
                    t_txt = t_el.text if t_el is not None and t_el.text else ""
                    _add_title_paragraph(target_topic_el, t_txt)
                    _copy_content(s_topic, target_topic_el)
                _merge_descendants(sub)
                try:
                    if sub.getparent() is node:
                        node.remove(sub)
                    if s_fname:
                        removed_files.append(s_fname)
                except Exception:
                    pass
            else:
                _merge_descendants(sub)
                try:
                    if sub.getparent() is node:
                        node.remove(sub)
                except Exception:
                    pass

    _merge_descendants(section_tref)

    # Transfer navtitle and attributes; normalize level/style
    section_navtitle = section_tref.find("topicmeta/navtitle")
    if section_navtitle is not None and section_navtitle.text:
        tm = content_child.find("topicmeta")
        if tm is None:
            tm = ET.SubElement(content_child, "topicmeta")
        nt = tm.find("navtitle")
        if nt is None:
            nt = ET.SubElement(tm, "navtitle")
        nt.text = section_navtitle.text

    for attr, value in section_tref.attrib.items():
        content_child.set(attr, value)
    try:
        lvl_attr = section_tref.get("data-level")
        if lvl_attr is not None:
            new_level = int(lvl_attr)
        else:
            new_level = 1
            cur = section_tref.getparent()
            while cur is not None:
                try:
                    if getattr(cur, "tag", None) in ("topicref", "topichead"):
                        new_level += 1
                except Exception:
                    pass
                cur = cur.getparent()
    except Exception:
        new_level = 1
    try:
        content_child.set("data-level", str(new_level))
        if not content_child.get("data-style"):
            content_child.set("data-style", f"Heading {new_level}")
    except Exception:
        pass

    # Replace section with content child
    parent = section_tref.getparent()
    if parent is not None:
        try:
            idx = list(parent).index(section_tref)
            parent.remove(section_tref)
            parent.insert(idx, content_child)
        except Exception:
            try:
                parent.remove(section_tref)
                parent.append(content_child)
            except Exception:
                pass

    return (target_topic_el, removed_files)

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

    def _find_prev_content_target(current_tref: ET.Element) -> Tuple[Optional[ET.Element], Optional[ET.Element]]:
        """Find the closest previous sibling that points to a content topic.

        Returns a tuple (prev_topicref, prev_topic_element). If none is found, returns (None, None).
        """
        try:
            parent = current_tref.getparent()
            if parent is None:
                return (None, None)
            siblings = list(parent)
            try:
                idx = siblings.index(current_tref)
            except ValueError:
                return (None, None)
            for i in range(idx - 1, -1, -1):
                sib = siblings[i]
                if getattr(sib, "tag", None) != "topicref":
                    continue
                href = sib.get("href")
                if not href:
                    continue
                fname = href.split("/")[-1]
                prev_topic = ctx.topics.get(fname)
                if prev_topic is not None:
                    return (sib, prev_topic)
            return (None, None)
        except Exception:
            return (None, None)
    
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
                # If this is a section: convert it to a local content topic like manual merge does
                if tref.tag == "topichead":
                    parent = tref.getparent()
                    try:
                        insert_pos = list(parent).index(tref) if parent is not None else None
                    except Exception:
                        insert_pos = None

                    topic_el, removed = convert_section_to_local_topic(ctx, tref)
                    for fn in removed:
                        removed_topics.add(fn)

                    # After conversion, try to immediately process the inserted topicref
                    new_ref = None
                    try:
                        if parent is not None and insert_pos is not None:
                            children_after = list(parent)
                            if 0 <= insert_pos < len(children_after):
                                candidate = children_after[insert_pos]
                                if getattr(candidate, "tag", None) == "topicref":
                                    new_ref = candidate
                    except Exception:
                        new_ref = None

                    if new_ref is not None and _should_merge(new_ref):
                        # Resolve its topic element
                        nhref = new_ref.get("href") or ""
                        nfname = nhref.split("/")[-1] if nhref else ""
                        ntopic = ctx.topics.get(nfname)

                        if ancestor_topic_el is not None and ntopic is not None:
                            # Merge into current ancestor
                            removed_name = merge_topicref_into(ctx, ancestor_topic_el, new_ref)
                            _recurse(new_ref, t_level + 1, ancestor_topic_el, ancestor_tref)
                            if removed_name:
                                removed_topics.add(removed_name)
                            else:
                                try:
                                    node.remove(new_ref)
                                except Exception:
                                    pass
                                if nfname:
                                    removed_topics.add(nfname)
                            continue

                        # No ancestor target: try previous sibling with content, else parent module
                        prev_tref, prev_topic = _find_prev_content_target(new_ref)
                        target_topic = prev_topic if prev_topic is not None else _find_parent_module(ctx, new_ref)
                        target_tref = prev_tref if prev_topic is not None else (new_ref if target_topic is not None else None)

                        if target_topic is not None and ntopic is not None:
                            removed_name = merge_topicref_into(ctx, target_topic, new_ref)
                            _recurse(new_ref, t_level + 1, target_topic, target_tref)
                            if removed_name:
                                removed_topics.add(removed_name)
                            else:
                                try:
                                    node.remove(new_ref)
                                except Exception:
                                    pass
                                if nfname:
                                    removed_topics.add(nfname)
                            continue

                        # Fallback: just traverse deeper with whatever ancestor we have
                        _recurse(new_ref, t_level + 1, ancestor_topic_el, ancestor_tref)
                        continue

                    # Otherwise, continue processing siblings/children in subsequent iterations
                    continue

                # tref is a content-bearing topicref here
                if ancestor_topic_el is not None and topic_el is not None:
                    # Topic with ancestor: merge via helper and recurse
                    removed_name = merge_topicref_into(ctx, ancestor_topic_el, tref)
                    _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)
                    if removed_name:
                        removed_topics.add(removed_name)
                    else:
                        # Fallback removal if helper couldn't resolve
                        try:
                            node.remove(tref)
                        except Exception:
                            pass
                        if fname:
                            removed_topics.add(fname)
                    continue

                if ancestor_topic_el is None and topic_el is not None:
                    # Topic without ancestor: try same-level previous topic first; else parent module
                    prev_tref, prev_topic = _find_prev_content_target(tref)
                    target_topic = prev_topic if prev_topic is not None else _find_parent_module(ctx, tref)
                    target_tref = prev_tref if prev_topic is not None else (tref if target_topic is not None else None)
                    if target_topic is not None:
                        # Special-case: if target is the same topic (section's auto-module), normalize and keep
                        if target_topic is topic_el:
                            try:
                                section_parent = tref.getparent()
                                if section_parent is not None:
                                    try:
                                        section_level = int(section_parent.get("data-level", t_level - 1))
                                    except Exception:
                                        section_level = max(1, t_level - 1)
                                    tref.set("data-level", str(section_level))
                                    tref.set("data-style", f"Heading {section_level}")
                            except Exception:
                                pass
                            _recurse(tref, t_level + 1, topic_el, tref)
                            continue
                        # General case: merge into target and remove self
                        removed_name = merge_topicref_into(ctx, target_topic, tref)
                        _recurse(tref, t_level + 1, target_topic, target_tref)
                        if removed_name:
                            removed_topics.add(removed_name)
                        else:
                            try:
                                node.remove(tref)
                            except Exception:
                                pass
                            if fname:
                                removed_topics.add(fname)
                        continue
                    # Fallback: traverse deeper without removing
                    _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)
                    continue

                # No content to merge - just traverse deeper
                _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)
                continue
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
    # Note: We no longer promote sections at the depth boundary into topics here.
    # Keeping sections at the boundary preserves collapsibility and expected UI behavior
    # when users increase the depth afterward.

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
        # Do not overwrite the child's topic <title>; set navtitle on topicref only.
        section_navtitle = section_topichead.find("topicmeta/navtitle")
        if section_navtitle is not None and section_navtitle.text:
            tm = content_child.find("topicmeta")
            if tm is None:
                tm = ET.SubElement(content_child, "topicmeta")
            nt = tm.find("navtitle")
            if nt is None:
                nt = ET.SubElement(tm, "navtitle")
            nt.text = section_navtitle.text
        
        # Copy section attributes to content child and normalize level to match the section;
        # but preserve explicit custom data-style from the child when present.
        for attr, value in section_topichead.attrib.items():
            content_child.set(attr, value)
        # Determine correct level: prefer section's data-level; else compute from tree depth
        try:
            lvl_attr = section_topichead.get("data-level")
            if lvl_attr is not None:
                new_level = int(lvl_attr)
            else:
                # Compute structural level by walking ancestors conservatively
                new_level = 1
                cur = section_topichead.getparent()
                while cur is not None:
                    try:
                        if cur.tag in ("topicref", "topichead"):
                            new_level += 1
                    except Exception:
                        pass
                    cur = cur.getparent()
        except Exception:
            new_level = 1
        try:
            content_child.set("data-level", str(new_level))
            # Preserve child's custom style if it has one; else synthesize from level
            child_style = content_child.get("data-style")
            if not child_style:
                content_child.set("data-style", f"Heading {new_level}")
        except Exception:
            pass
        
        # Replace section with content module in the parent
        parent = section_topichead.getparent()
        if parent is not None:
            parent_index = list(parent).index(section_topichead)
            parent.remove(section_topichead)
            parent.insert(parent_index, content_child) 


def _promote_sections_at_depth_limit(ctx: "DitaContext", depth_limit: int) -> None:
    """Ensure sections at the depth limit become content-bearing topics.

    For any topichead with data-level == depth_limit, replace it with its content
    module (creating one if needed) and transfer metadata. This guarantees that at
    the boundary, a navigable topic exists rather than a structural topichead.
    """
    if ctx.ditamap_root is None:
        return

    # Collect candidates first to avoid modifying while iterating
    try:
        candidates = []
        for th in ctx.ditamap_root.findall(".//topichead"):
            try:
                lvl = int(th.get("data-level", 1))
            except Exception:
                lvl = 1
            if lvl == depth_limit:
                candidates.append(th)
    except Exception:
        candidates = []

    for section_topichead in candidates:
        # Find or create content module child
        content_child = None
        for child in section_topichead:
            if child.tag == "topicref" and child.get("href"):
                content_child = child
                break
        if content_child is None:
            # Create new content module for this section
            content_topic = _ensure_content_module(ctx, section_topichead)
            # Find the newly inserted child (first child by _ensure_content_module)
            for child in section_topichead:
                if child.tag == "topicref" and child.get("href"):
                    content_child = child
                    break
        if content_child is None:
            continue

        # Transfer section metadata: do not overwrite child topic <title>; set navtitle on topicref
        section_navtitle = section_topichead.find("topicmeta/navtitle")
        if section_navtitle is not None and section_navtitle.text:
            tm = content_child.find("topicmeta")
            if tm is None:
                tm = ET.SubElement(content_child, "topicmeta")
            nt = tm.find("navtitle")
            if nt is None:
                nt = ET.SubElement(tm, "navtitle")
            nt.text = section_navtitle.text

        for attr, value in section_topichead.attrib.items():
            content_child.set(attr, value)
        # Normalize level to match the section; preserve explicit custom style if present
        try:
            lvl_attr = section_topichead.get("data-level")
            if lvl_attr is not None:
                new_level = int(lvl_attr)
            else:
                # Compute structural level by walking ancestors conservatively
                new_level = 1
                cur = section_topichead.getparent()
                while cur is not None:
                    try:
                        if cur.tag in ("topicref", "topichead"):
                            new_level += 1
                    except Exception:
                        pass
                    cur = cur.getparent()
        except Exception:
            new_level = 1
        try:
            content_child.set("data-level", str(new_level))
            child_style = content_child.get("data-style")
            if not child_style:
                content_child.set("data-style", f"Heading {new_level}")
        except Exception:
            pass

        # Replace in parent
        parent = section_topichead.getparent()
        if parent is not None:
            parent_index = list(parent).index(section_topichead)
            parent.remove(section_topichead)
            parent.insert(parent_index, content_child)