from __future__ import annotations

"""Service layer for structural edits on the in-memory DITA map.

This module provides a UI-agnostic, testable service that encapsulates the
business logic previously embedded in UI code for manipulating the DITA
structure (reordering, promoting/demoting, renaming, deleting topics).

Scope and guarantees:
- Operates purely in-memory on DitaContext, no file I/O nor UI imports.
- Conservative behavior with boundary checks; invalid operations return
  OperationResult(success=False, ...) with clear messaging, never raise.
- Keeps API stable and isolates uncertain internals into helpers with TODO notes.

This service focuses on topicref/topichead manipulation inside context.ditamap_root
and synchronizes with context.topics when necessary.

Examples
--------
Basic usage:

    service = StructureEditingService()
    result = service.move_topic(ctx, "topics/topic_123.dita", "up")
    if not result.success:
        print(result.message)

"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Literal

from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core import utils, merge


__all__ = ["OperationResult", "StructureEditingService"]


@dataclass(frozen=True)
class OperationResult:
    """Result of a structural editing operation.

    Attributes
    ----------
    success
        Whether the operation completed successfully.
    message
        Human-readable summary suitable for logs or UI display.
    details
        Optional structured details for diagnostics or caller logic.
    """
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class StructureEditingService:
    """Encapsulates structural edit operations on a DITA map.

    The service performs safe, conservative edits to the DITA map within
    a DitaContext. It manipulates topicref/topichead elements in
    context.ditamap_root and updates context.topics where applicable.

    Design principles:
    - No UI dependencies (no Tkinter), no disk I/O.
    - No exceptions for expected invalid actions; return OperationResult.
    - Non-destructive helpers are used to locate nodes and parents.
    - Where deeper internals are uncertain, the logic is isolated and documented
      for future refinement while preserving the public API.

    Notes
    -----
    Topic references are represented by elements with tag "topicref" (content-bearing)
    or "topichead" (structural). Renaming and deletion operate primarily on "topicref"
    with an href attribute pointing to topics/{filename}. Promote/demote and up/down
    are implemented in terms of reordering and reparenting of topicref/topichead nodes.
    """

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def move_topic(
        self,
        context,
        topic_id: str,
        direction: Literal["up", "down", "promote", "demote"],
    ) -> OperationResult:
        """Move a topic within the DITA map by topic_id.

        Canonical API: accepts topic_id only (href or filename). Topic refs/elements are not accepted.

        - Returns OperationResult with success flag and non-raising boundary handling.
        """
        # Do not hard-require a real ditamap here; tests may monkeypatch adapters.
        # Always attempt to resolve via the adapter first.
        node = self._find_topic_ref(context, topic_id)
        if node is None:
            return OperationResult(False, f"Topic not found for id '{topic_id}'.", {"topic_id": topic_id})

        if direction == "up":
            ok = self._move_up(context, node)
            return OperationResult(ok, ("Moved topic up." if ok else "Cannot move up (at boundary)."), {"topic_id": topic_id})
        if direction == "down":
            ok = self._move_down(context, node)
            return OperationResult(ok, ("Moved topic down." if ok else "Cannot move down (at boundary)."), {"topic_id": topic_id})
        if direction == "promote":
            ok = self._promote(context, node)
            return OperationResult(ok, ("Promoted topic." if ok else "Cannot promote (at root or invalid)."), {"topic_id": topic_id})
        if direction == "demote":
            ok = self._demote(context, node)
            return OperationResult(ok, ("Demoted topic." if ok else "Cannot demote (no previous sibling)."), {"topic_id": topic_id})

        return OperationResult(False, f"Unsupported move direction '{direction}'.", {"allowed": ["up", "down", "promote", "demote"]})

    def merge_topics(self, context, source_ids: List[str], target_id: str) -> OperationResult:
        """Manually merge selected topics into the first selected target.

        - Only topicref nodes with href are considered (sections are ignored).
        - Each source topic's title is inserted as a formatted paragraph in the target
          (same style used by unified merge), followed by its body content.
        - Source topicrefs are removed from the map and their topic files are purged.
        """
        try:
            if getattr(context, "ditamap_root", None) is None:
                return OperationResult(False, "No ditamap available in context.", {"reason": "missing_ditamap"})

            # Resolve target
            target_node = self._find_topic_ref(context, target_id)
            if target_node is None or not target_node.get("href"):
                return OperationResult(False, "Target topic not found or not content-bearing.", {"target": target_id})
            target_fname = target_node.get("href").split("/")[-1]
            target_topic = context.topics.get(target_fname)
            if target_topic is None:
                return OperationResult(False, "Target topic content not found.", {"target": target_fname})

            merged_count = 0
            removed_files: List[str] = []

            # Import helpers locally to avoid tight coupling
            try:
                from orlando_toolkit.core.merge import _add_title_paragraph as _mt_add_title, _copy_content as _mt_copy
            except Exception:
                def _mt_add_title(_dest, _t):
                    return
                def _mt_copy(_s, _d):
                    return

            # Merge each source in given order
            for sid in list(source_ids):
                src_node = self._find_topic_ref(context, sid)
                if src_node is None:
                    continue
                href = src_node.get("href")
                if not href:
                    # Skip sections
                    continue
                src_fname = href.split("/")[-1]
                src_topic = context.topics.get(src_fname)
                if src_topic is None:
                    continue

                # Title then content
                title_text = ""
                try:
                    t_el = src_topic.find("title")
                    if t_el is not None and t_el.text:
                        title_text = t_el.text
                except Exception:
                    title_text = ""
                _mt_add_title(target_topic, title_text)
                _mt_copy(src_topic, target_topic)

                # Remove topicref from the map
                parent = src_node.getparent()
                if parent is not None:
                    try:
                        parent.remove(src_node)
                        merged_count += 1
                        removed_files.append(src_fname)
                    except Exception:
                        pass

            # Purge unreferenced topics
            for fn in removed_files:
                context.topics.pop(fn, None)

            # Ensure future depth-limit operations take this state as the new baseline
            self._invalidate_original_structure(context)

            return OperationResult(True, "Merged topics into target.", {"target": target_fname, "merged_count": merged_count})
        except Exception as e:
            return OperationResult(False, "Manual merge failed.", {"error": str(e)})

    def rename_topic(self, context, topic_id: str, new_title: str) -> OperationResult:
        """Rename a topic by topic_id (href or filename). Canonical API uses topic_id only; topic refs/elements are not accepted."""
        if getattr(context, "ditamap_root", None) is None:
            return OperationResult(False, "No ditamap available in context.", {"reason": "missing_ditamap"})

        node = self._find_topic_ref(context, topic_id)
        if node is None:
            return OperationResult(False, f"Topic not found for id '{topic_id}'.", {"topic_id": topic_id})

        ok = self._rename(context, node, new_title)
        if ok:
            filename = self._normalize_filename(topic_id)
            # Persist rename across future depth-limit changes
            self._invalidate_original_structure(context)
            return OperationResult(True, f"Renamed topic '{filename}'.", {"topic_id": topic_id, "new_title": " ".join((new_title or "").split())})
        return OperationResult(False, "Rename failed.", {"topic_id": topic_id})

    def delete_topics(self, context, topic_ids: List[str]) -> OperationResult:
        """Delete topics by topic_ids (hrefs or filenames). Canonical API uses topic_ids only; topic refs/elements are not accepted."""
        if getattr(context, "ditamap_root", None) is None:
            return OperationResult(False, "No ditamap available in context.", {"reason": "missing_ditamap"})

        requested = list(topic_ids)
        deleted_count = self._delete_by_ids(context, topic_ids)

        # Persist deletion baseline for future depth-limit operations
        self._invalidate_original_structure(context)
        details = {"requested": requested, "deleted": deleted_count, "skipped": max(0, len(requested) - deleted_count)}
        return OperationResult(deleted_count > 0, ("Deleted topics." if deleted_count > 0 else "No topics deleted."), details)

    def apply_depth_limit(self, context, depth_limit: int, style_exclusions: dict[int, set[str]] | None = None) -> OperationResult:
        """Apply a depth limit merge to the current context with reversible behavior.

        This method:
        - Saves original structure on first use to enable depth limit reversibility
        - Always works from original structure to avoid compound transformations
        - Never raises; returns OperationResult with details
        """
        try:
            # 1) Validate context has a ditamap_root
            if getattr(context, "ditamap_root", None) is None:
                return OperationResult(False, "No ditamap available in context.", {"reason": "missing_ditamap"})

            # 2) Check current configuration before any changes
            prev_depth = getattr(context, "metadata", {}).get("merged_depth")
            prev_styles_flag = getattr(context, "metadata", {}).get("merged_exclude_styles", False)
            current_styles_flag = bool(style_exclusions)
            
            # 3) Save original structure if not already saved AND before any modifications
            # This must happen BEFORE any restore or merge operations
            if hasattr(context, 'save_original_structure'):
                context.save_original_structure()
            
            # 4) Early exit if exactly the same configuration
            if prev_depth == depth_limit and prev_styles_flag == current_styles_flag:
                return OperationResult(True, "Depth limit already applied", {"depth_limit": depth_limit, "merged": False})

            # 5) Restore from original before applying new depth limit
            # This ensures we always start from clean state
            if hasattr(context, 'restore_from_original'):
                context.restore_from_original()

            # 6) Apply merge on clean original structure
            from orlando_toolkit.core.merge import merge_topics_unified  # local import by design
            merge_topics_unified(context, depth_limit, style_exclusions)
            
            return OperationResult(True, "Applied depth limit", {"depth_limit": depth_limit, "merged": True})
        except Exception as e:
            # Never raise; encapsulate error
            return OperationResult(False, "Failed to apply depth limit", {"error": str(e)})

    # -------------------------------------------------------------------------
    # Internal helpers (non-destructive, isolated)
    # -------------------------------------------------------------------------

    # Adapter helpers (for monkeypatching in tests)
    def _find_topic_ref(self, context, topic_id):
        """Resolve topic_id (href or filename) to the topicref element, or None."""
        root = getattr(context, "ditamap_root", None)
        if root is None:
            return None
        if isinstance(topic_id, str) and "/" in topic_id:
            return self._find_topicref_by_href(root, topic_id)
        filename = self._normalize_filename(topic_id)
        return self._find_topicref_by_filename(root, filename)

    def _move_up(self, context, node) -> bool:
        """Adapter mapping to internal move up."""
        parent = node.getparent()
        if parent is None:
            return False
        res = self._move_sibling(context, parent, node, delta=-1)
        return bool(res.success)

    def _move_down(self, context, node) -> bool:
        """Adapter mapping to internal move down."""
        parent = node.getparent()
        if parent is None:
            return False
        res = self._move_sibling(context, parent, node, delta=1)
        return bool(res.success)

    def _promote(self, context, node) -> bool:  # adapter name required; delegates to existing internal
        res = super(type(self), self)._promote(context, node) if False else self.__class__.__dict__['_promote'](self, context, node)  # type: ignore
        # The above indirection keeps name intact while returning bool for adapter
        return bool(res.success)

    def _demote(self, context, node) -> bool:  # adapter name required; delegates to existing internal
        res = super(type(self), self)._demote(context, node) if False else self.__class__.__dict__['_demote'](self, context, node)  # type: ignore
        return bool(res.success)

    def _rename(self, context, node, new_title) -> bool:
        """Adapter encapsulating rename logic; updates topic title and navtitle."""
        cleaned = " ".join((new_title or "").split())
        if not cleaned:
            return False

        # Update topic XML title if content-bearing (has href -> filename -> context.topics)
        href = node.get("href")
        if href:
            fname = href.split("/")[-1]
            topic_el = context.topics.get(fname)
            if topic_el is not None:
                title_el = topic_el.find("title")
                if title_el is None:
                    title_el = ET.SubElement(topic_el, "title")
                title_el.text = cleaned

        # Update topicref's navtitle
        self._ensure_navtitle(node, cleaned)
        return True

    def _delete_by_ids(self, context, ids: List[str]) -> int:
        """Adapter performing deletion by ids, purging unreferenced topics afterwards."""
        if getattr(context, "ditamap_root", None) is None:
            return 0

        count = 0
        for tid in ids:
            node = self._find_topic_ref(context, tid)
            if node is None:
                continue
            href = node.get("href")
            if not href:
                # skip structural nodes
                continue
            parent = node.getparent()
            if parent is None:
                continue
            parent.remove(node)
            count += 1

        # purge topics after batch delete
        self._purge_unreferenced_topics(context)
        return count

    @staticmethod
    def _normalize_filename(topic_ref: str) -> str:
        """Return bare filename from an href or filename string."""
        # Accept "topics/foo.dita" or "foo.dita"
        if "/" in topic_ref:
            return topic_ref.split("/")[-1]
        return topic_ref

    @staticmethod
    def _find_topicref_by_filename(root: ET.Element, filename: str) -> Optional[ET.Element]:
        """Locate a topicref element pointing to topics/{filename}.

        Returns the first matching element or None if not found.
        """
        # Prefer exact href matches
        expr = f".//topicref[@href='topics/{filename}']"
        found = root.find(expr)
        if found is not None:
            return found

        # Fallback: any topicref whose href ends with the filename
        # This is more permissive and robust if paths varied.
        for tref in root.xpath(".//topicref[@href]"):
            href = tref.get("href", "")
            if href.endswith(filename):
                return tref
        return None

    @staticmethod
    def _find_topicref_by_href(root: ET.Element, href: str) -> Optional[ET.Element]:
        """Locate a topicref element by exact @href match."""
        try:
            expr = f".//topicref[@href='{href}']"
            return root.find(expr)
        except Exception:
            return None

    @staticmethod
    def _ensure_navtitle(tref: ET.Element, text: str) -> None:
        """Ensure topicmeta/navtitle exists and update its text."""
        topicmeta = tref.find("topicmeta")
        if topicmeta is None:
            topicmeta = ET.SubElement(tref, "topicmeta")
        navtitle = topicmeta.find("navtitle")
        if navtitle is None:
            navtitle = ET.SubElement(topicmeta, "navtitle")
        navtitle.text = text

    def _move_sibling(self, context: DitaContext, parent: ET.Element, tref: ET.Element, *, delta: int) -> OperationResult:
        """Move a topicref up/down among its siblings by one position."""
        # Consider only siblings that are structural/content nodes to preserve order relative to metadata
        siblings = [el for el in list(parent) if el.tag in ("topicref", "topichead")]
        try:
            idx_in_filtered = siblings.index(tref)
        except ValueError:
            # If tref not in filtered list (unlikely), fall back to raw indexing
            children = list(parent)
            if tref not in children:
                return OperationResult(False, "Internal error: node not found among parent's children.", {})
            current_index = children.index(tref)
            target_index = current_index + (-1 if delta < 0 else 1)
            if target_index < 0 or target_index >= len(children):
                return OperationResult(False, "Cannot move: already at boundary.", {"current_index": current_index})
            parent.remove(tref)
            parent.insert(target_index, tref)
            return OperationResult(True, "Moved topic.", {"from_index": current_index, "to_index": target_index})

        current_index = list(parent).index(tref)
        new_filtered_index = idx_in_filtered + (-1 if delta < 0 else 1)
        if new_filtered_index < 0 or new_filtered_index >= len(siblings):
            # Boundary; no change
            return OperationResult(False, "Cannot move: already at boundary.", {"filtered_index": idx_in_filtered})

        # Compute actual insertion index among all children by finding the target sibling
        target_sibling = siblings[new_filtered_index]
        target_index = list(parent).index(target_sibling)

        # When moving down and inserting before the target that follows after removing, adjust
        parent.remove(tref)
        insert_at = target_index
        if delta > 0:
            # Recompute index if needed after removal
            # If target_index was after tref, removing tref decreases indices by 1.
            # To keep relative order as "move after", we increment insertion by 1 when moving down.
            after_index = list(parent).index(target_sibling)
            insert_at = after_index + 1

        parent.insert(insert_at, tref)
        return OperationResult(True, "Moved topic.", {"from_index": current_index, "to_index": insert_at})

    def _promote(self, context: DitaContext, tref: ET.Element) -> OperationResult:
        """Promote a topicref one level up (outdent), placing it after its former parent."""
        parent = tref.getparent()
        if parent is None:
            return OperationResult(False, "Cannot promote: node has no parent.", {})

        grandparent = parent.getparent()
        if grandparent is None:
            return OperationResult(False, "Cannot promote: node is at root level.", {})

        # Find position of parent within grandparent among structural nodes
        gp_children = list(grandparent)
        if parent not in gp_children:
            return OperationResult(False, "Internal error: parent not found under grandparent.", {})
        parent_index = gp_children.index(parent)

        # Remove from current parent and insert after parent in grandparent
        parent.remove(tref)

        insert_at = parent_index + 1
        grandparent.insert(insert_at, tref)

        # Optionally update data-level to reflect new depth if present
        self._update_level_attributes_after_reparent(tref, parent, grandparent, direction="promote")

        return OperationResult(True, "Promoted topic one level up.", {"insert_index": insert_at})

    def _demote(self, context: DitaContext, tref: ET.Element) -> OperationResult:
        """Demote a topicref one level down (indent), making it the last child of the nearest previous sibling."""
        parent = tref.getparent()
        if parent is None:
            return OperationResult(False, "Cannot demote: node has no parent.", {})

        # Find previous sibling that is a structural/content node
        siblings = [el for el in list(parent) if el.tag in ("topicref", "topichead")]
        if tref not in siblings:
            return OperationResult(False, "Internal error: node not found among siblings.", {})
        idx = siblings.index(tref)
        if idx == 0:
            return OperationResult(False, "Cannot demote: no preceding sibling to become the new parent.", {})

        new_parent = siblings[idx - 1]

        # Only topicref or topichead can accept children; both are fine structurally
        # Insert as last child
        parent.remove(tref)
        new_parent.append(tref)

        # Optionally update data-level to reflect new depth if present
        self._update_level_attributes_after_reparent(tref, parent, new_parent, direction="demote")

        return OperationResult(True, "Demoted topic under previous sibling.", {})

    @staticmethod
    def _update_level_attributes_after_reparent(tref: ET.Element, old_parent: ET.Element, new_parent: ET.Element, *, direction: str) -> None:
        """Best-effort update of data-level attributes after reparenting.

        The codebase uses a 'data-level' attribute in several places to record
        logical depth. This helper performs a conservative adjustment:

        - promote: decrease tref's data-level by 1 if present
        - demote: increase tref's data-level by 1 if present

        It does not recursively update descendants; deeper synchronization may be
        addressed in future iterations if required by callers.

        TODO: Consider recalculating all levels with a traversal for strict
        consistency, or using utils.calculate_section_numbers if appropriate.
        """
        try:
            level_attr = tref.get("data-level")
            if level_attr is None:
                return
            level = int(level_attr)
            if direction == "promote":
                level = max(1, level - 1)
            elif direction == "demote":
                level = level + 1
            tref.set("data-level", str(level))
        except Exception:
            # Fail silently; level annotations are best-effort
            pass

    @staticmethod
    def _purge_unreferenced_topics(context: DitaContext) -> None:
        """Remove topics from context.topics that are no longer referenced in the map.

        Safe no-op if ditamap_root is missing or no hrefs found.
        """
        if context.ditamap_root is None:
            return
        hrefs = {
            (tref.get("href") or "").split("/")[-1]
            for tref in context.ditamap_root.xpath(".//topicref[@href]")
        }
        # Keep only referenced topics
        context.topics = {fn: el for fn, el in context.topics.items() if fn in hrefs}

    # ----------------------- Section operations -----------------------

    def convert_section_to_topic(self, context: DitaContext, index_path: List[int]) -> OperationResult:
        """Convert a section (topichead) located by index_path into a topic that hosts its subtree.

        All descendant topics' titles and content are merged into the created/reused
        content module topic to match unified merge formatting.
        """
        if getattr(context, "ditamap_root", None) is None:
            return OperationResult(False, "No ditamap available in context.")
        try:
            section = self._locate_node_by_index_path(context, index_path)
            if section is None or getattr(section, "tag", None) != "topichead":
                return OperationResult(False, "Section not found.", {"index_path": list(index_path)})

            # Find or create a content module child
            content_child = None
            for child in list(section):
                if getattr(child, "tag", None) == "topicref" and child.get("href"):
                    content_child = child
                    break
            if content_child is None:
                try:
                    merge._ensure_content_module(context, section)  # type: ignore[attr-defined]
                except Exception:
                    pass
                for child in list(section):
                    if getattr(child, "tag", None) == "topicref" and child.get("href"):
                        content_child = child
                        break
            if content_child is None:
                return OperationResult(False, "Failed to create content module for section.")

            # Resolve target topic element for merging
            target_topic_el = None
            try:
                href = content_child.get("href") or ""
                fname = href.split("/")[-1] if href else ""
                target_topic_el = context.topics.get(fname)
            except Exception:
                target_topic_el = None

            # Import merge helpers
            try:
                from orlando_toolkit.core.merge import _add_title_paragraph as _mt_add_title, _copy_content as _mt_copy
            except Exception:
                def _mt_add_title(_dest, _t):
                    return
                def _mt_copy(_s, _d):
                    return

            # Merge all descendants' content into target_topic_el, removing child refs
            removed_files: List[str] = []

            def _merge_descendants(node: ET.Element) -> None:
                for sub in list(node):
                    tag = getattr(sub, "tag", None)
                    if tag not in ("topicref", "topichead"):
                        continue
                    # Do not process the content module itself
                    try:
                        if sub is content_child:
                            continue
                    except Exception:
                        pass
                    if tag == "topicref" and sub.get("href"):
                        # Merge this topic's title and content, then recurse its children
                        try:
                            s_href = sub.get("href") or ""
                            s_fname = s_href.split("/")[-1]
                            s_topic = context.topics.get(s_fname)
                        except Exception:
                            s_topic = None
                            s_fname = ""
                        if target_topic_el is not None and s_topic is not None:
                            # Title paragraph then body content
                            try:
                                t_el = s_topic.find("title")
                                t_txt = t_el.text if t_el is not None and t_el.text else ""
                            except Exception:
                                t_txt = ""
                            _mt_add_title(target_topic_el, t_txt)
                            _mt_copy(s_topic, target_topic_el)
                        # Recurse deeper under same target
                        _merge_descendants(sub)
                        # Remove this child from original section after processing
                        try:
                            if sub.getparent() is node:
                                node.remove(sub)
                            if s_fname:
                                removed_files.append(s_fname)
                        except Exception:
                            pass
                    else:
                        # topichead: recurse; all its descendants will merge
                        _merge_descendants(sub)
                        try:
                            if sub.getparent() is node:
                                node.remove(sub)
                        except Exception:
                            pass

            # Perform merging from the section (excluding the content_child itself)
            _merge_descendants(section)

            # Transfer navtitle and attributes; normalize level/style
            section_navtitle = section.find("topicmeta/navtitle")
            if section_navtitle is not None and section_navtitle.text:
                tm = content_child.find("topicmeta")
                if tm is None:
                    tm = ET.SubElement(content_child, "topicmeta")
                nt = tm.find("navtitle")
                if nt is None:
                    nt = ET.SubElement(tm, "navtitle")
                nt.text = section_navtitle.text

            for attr, value in section.attrib.items():
                content_child.set(attr, value)
            try:
                lvl_attr = section.get("data-level")
                if lvl_attr is not None:
                    new_level = int(lvl_attr)
                else:
                    new_level = 1
                    cur = section.getparent()
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
            parent = section.getparent()
            if parent is not None:
                idx = list(parent).index(section)
                parent.remove(section)
                parent.insert(idx, content_child)

            # Purge removed topics
            for fn in removed_files:
                context.topics.pop(fn, None)

            # Ensure future depth-limit operations use this as baseline
            self._invalidate_original_structure(context)

            return OperationResult(True, "Section converted to topic.", {"index_path": list(index_path)})
        except Exception as e:
            return OperationResult(False, "Failed to convert section.", {"error": str(e)})

    def rename_section(self, context: DitaContext, index_path: List[int], new_title: str) -> OperationResult:
        """Rename the navtitle of a section (topichead) located by index_path."""
        if getattr(context, "ditamap_root", None) is None:
            return OperationResult(False, "No ditamap available in context.")
        cleaned = " ".join((new_title or "").split())
        if not cleaned:
            return OperationResult(False, "Empty title is not allowed")
        try:
            node = self._locate_node_by_index_path(context, index_path)
            if node is None or getattr(node, "tag", None) != "topichead":
                return OperationResult(False, "Section not found.", {"index_path": list(index_path)})
            topicmeta = node.find("topicmeta")
            if topicmeta is None:
                topicmeta = ET.SubElement(node, "topicmeta")
            navtitle = topicmeta.find("navtitle")
            if navtitle is None:
                navtitle = ET.SubElement(topicmeta, "navtitle")
            navtitle.text = cleaned
            # Persist rename across depth-limit changes
            self._invalidate_original_structure(context)
            return OperationResult(True, "Section renamed.", {"index_path": list(index_path), "new_title": cleaned})
        except Exception as e:
            return OperationResult(False, "Failed to rename section.", {"error": str(e)})

    @staticmethod
    def _locate_node_by_index_path(context: DitaContext, index_path: List[int]) -> Optional[ET.Element]:
        try:
            root = getattr(context, "ditamap_root", None)
            if root is None:
                return None
            node = root
            for idx in index_path:
                structural_children = [el for el in list(node) if getattr(el, "tag", None) in ("topicref", "topichead")]
                if idx < 0 or idx >= len(structural_children):
                    return None
                node = structural_children[idx]
            return node
        except Exception:
            return None

    def delete_section(self, context: DitaContext, index_path: List[int]) -> OperationResult:
        """Delete a section (topichead) and its subtree; then purge unreferenced topics."""
        if getattr(context, "ditamap_root", None) is None:
            return OperationResult(False, "No ditamap available in context.")
        try:
            node = self._locate_node_by_index_path(context, index_path)
            if node is None or getattr(node, "tag", None) != "topichead":
                return OperationResult(False, "Section not found.", {"index_path": list(index_path)})
            parent = node.getparent()
            if parent is None:
                return OperationResult(False, "Cannot delete root section.")

            # Collect topic files referenced under this subtree for potential purge
            try:
                removed_refs = [
                    (tref.get("href") or "").split("/")[-1]
                    for tref in node.xpath(".//topicref[@href]")
                ]
            except Exception:
                removed_refs = []

            parent.remove(node)
            # Purge topics that are no longer referenced anywhere
            self._purge_unreferenced_topics(context)
            # Persist deletion baseline
            self._invalidate_original_structure(context)
            return OperationResult(True, "Section deleted.", {"index_path": list(index_path), "purged_candidates": removed_refs})
        except Exception as e:
            return OperationResult(False, "Failed to delete section.", {"error": str(e)})

    @staticmethod
    def _invalidate_original_structure(context: DitaContext) -> None:
        """Drop saved original structure and merge flags so future depth merges start from current state."""
        try:
            context.metadata.pop("original_structure", None)
            context.metadata.pop("merged_depth", None)
            context.metadata.pop("merged_exclude_styles", None)
        except Exception:
            pass