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
from orlando_toolkit.core import merge


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
        direction: Literal["up", "down"],
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
            if ok:
                # Persist this structural change as the new baseline for future depth-limit merges
                self._invalidate_original_structure(context)
            return OperationResult(ok, ("Moved topic up." if ok else "Cannot move up (at boundary)."), {"topic_id": topic_id})
        if direction == "down":
            ok = self._move_down(context, node)
            if ok:
                # Persist this structural change as the new baseline for future depth-limit merges
                self._invalidate_original_structure(context)
            return OperationResult(ok, ("Moved topic down." if ok else "Cannot move down (at boundary)."), {"topic_id": topic_id})
        return OperationResult(False, f"Unsupported move direction '{direction}'.", {"allowed": ["up", "down"]})

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
    # New: direct move operations to a destination
    # -------------------------------------------------------------------------

    def move_topics_to_target(
        self,
        context: DitaContext,
        topic_ids: List[str],
        target_index_path: Optional[List[int]]
    ) -> OperationResult:
        """Move one or more topics (topicref with @href) to a destination section or root.

        - The destination is the map root when target_index_path is None.
        - Topics are appended at the end of the destination in the order provided.
        - Section nodes (topichead) are ignored in this API.
        - Levels/styles are adapted similarly to intelligent move behavior.
        """
        try:
            root = getattr(context, "ditamap_root", None)
            if root is None:
                return OperationResult(False, "No ditamap available in context.")

            # Resolve destination parent element
            if target_index_path is None:
                dest_parent = root
            else:
                dest_parent = self._locate_node_by_index_path(context, target_index_path)
                if dest_parent is None or getattr(dest_parent, "tag", None) not in ("topichead", "topicref", "map"):
                    return OperationResult(False, "Destination not found.", {"target_index_path": list(target_index_path)})

            # Resolve candidate nodes (topics only)
            candidate_nodes = []
            id_by_node = {}
            for tid in list(topic_ids or []):
                node = self._find_topic_ref(context, tid)
                if node is None:
                    continue
                # Only content-bearing topics
                href = node.get("href")
                if not href:
                    continue
                candidate_nodes.append(node)
                id_by_node[node] = tid

            if not candidate_nodes:
                return OperationResult(False, "No topics to move.")

            # Keep only roots among selected nodes (preserve relative structure)
            roots: List[Any] = []
            for n in candidate_nodes:
                is_descendant = False
                for other in candidate_nodes:
                    if other is n:
                        continue
                    if self._is_ancestor(other, n):
                        is_descendant = True
                        break
                if not is_descendant:
                    roots.append(n)

            # Prevent moving into a descendant of any root
            for r in roots:
                if self._is_ancestor(r, dest_parent):
                    return OperationResult(False, "Cannot move into a descendant of a selected topic.")

            # Preserve original document order when appending
            order_index = {}
            try:
                linear = self._build_linear_view(root)
                for i, (node, _p, _idx) in enumerate(linear):
                    order_index[node] = i
            except Exception:
                # Fallback: keep current order
                pass
            try:
                roots.sort(key=lambda n: order_index.get(n, 10**9))
            except Exception:
                pass

            moved: List[str] = []
            for node in roots:
                old_parent = node.getparent()
                if old_parent is None:
                    continue
                self._reparent_node(node, old_parent, dest_parent, 10**9)
                target_level = self._calculate_target_level(node, dest_parent)
                self._apply_level_adaptation(node, target_level)
                moved.append(id_by_node.get(node, ""))

            if not moved:
                return OperationResult(False, "No topics moved.")

            # Persist as new baseline
            self._invalidate_original_structure(context)
            return OperationResult(True, "Moved topics to destination.", {"count": len(moved)})
        except Exception as e:
            return OperationResult(False, "Failed to move topics to destination.", {"error": str(e)})

    def move_section_to_target(
        self,
        context: DitaContext,
        section_index_path: List[int],
        target_index_path: Optional[List[int]]
    ) -> OperationResult:
        """Move a section (topichead) identified by index_path to a destination section or root.

        - Appends the section at the end of the destination.
        - Prevents moving a section into its own descendant subtree.
        - Adapts level/style for the moved section root.
        """
        try:
            root = getattr(context, "ditamap_root", None)
            if root is None:
                return OperationResult(False, "No ditamap available in context.")

            section = self._locate_node_by_index_path(context, section_index_path)
            if section is None or getattr(section, "tag", None) != "topichead":
                return OperationResult(False, "Section not found.", {"index_path": list(section_index_path or [])})

            # Resolve destination
            if target_index_path is None:
                dest_parent = root
            else:
                dest_parent = self._locate_node_by_index_path(context, target_index_path)
                if dest_parent is None or getattr(dest_parent, "tag", None) not in ("topichead", "topicref", "map"):
                    return OperationResult(False, "Destination not found.", {"target_index_path": list(target_index_path)})

            # Prevent moving into own descendant subtree
            if self._is_ancestor(section, dest_parent):
                return OperationResult(False, "Cannot move a section into its own descendant.")

            old_parent = section.getparent()
            if old_parent is None:
                return OperationResult(False, "Cannot move root section.")

            self._reparent_node(section, old_parent, dest_parent, 10**9)

            # Adapt level/style for section root
            target_level = self._calculate_target_level(section, dest_parent)
            self._apply_level_adaptation(section, target_level)

            self._invalidate_original_structure(context)
            return OperationResult(True, "Moved section to destination.", {"index_path": list(section_index_path)})
        except Exception as e:
            return OperationResult(False, "Failed to move section to destination.", {"error": str(e)})

    def move_sections_to_target(
        self,
        context: DitaContext,
        section_index_paths: List[List[int]],
        target_index_path: Optional[List[int]]
    ) -> OperationResult:
        """Move multiple sections to a destination (append in order), preserving relative structure.

        - Keeps only roots among selected sections (no descendant of another selected section).
        - Appends in document order.
        - Prevents moving into a descendant of any selected root.
        """
        try:
            root = getattr(context, "ditamap_root", None)
            if root is None:
                return OperationResult(False, "No ditamap available in context.")

            # Resolve destination
            if target_index_path is None:
                dest_parent = root
            else:
                dest_parent = self._locate_node_by_index_path(context, target_index_path)
                if dest_parent is None or getattr(dest_parent, "tag", None) not in ("topichead", "topicref", "map"):
                    return OperationResult(False, "Destination not found.", {"target_index_path": list(target_index_path)})

            # Resolve nodes and filter to topichead
            nodes = []
            for ip in list(section_index_paths or []):
                node = self._locate_node_by_index_path(context, list(ip))
                if node is not None and getattr(node, "tag", None) == "topichead":
                    nodes.append(node)
            if not nodes:
                return OperationResult(False, "No sections to move.")

            # Keep only roots (exclude nodes that are descendants of another selected node)
            roots = []
            for n in nodes:
                if not any(self._is_ancestor(other, n) for other in nodes if other is not n):
                    roots.append(n)
            if not roots:
                return OperationResult(False, "No sections to move.")

            # Prevent moving into a descendant of any root
            for r in roots:
                if self._is_ancestor(r, dest_parent):
                    return OperationResult(False, "Cannot move into a descendant of a selected section.")

            # Sort roots by document order
            order_index = {}
            try:
                linear = self._build_linear_view(root)
                for i, (node, _p, _idx) in enumerate(linear):
                    order_index[node] = i
                roots.sort(key=lambda n: order_index.get(n, 10**9))
            except Exception:
                pass

            moved = 0
            for node in roots:
                old_parent = node.getparent()
                if old_parent is None:
                    continue
                self._reparent_node(node, old_parent, dest_parent, 10**9)
                target_level = self._calculate_target_level(node, dest_parent)
                self._apply_level_adaptation(node, target_level)
                moved += 1

            if moved <= 0:
                return OperationResult(False, "No sections moved.")

            self._invalidate_original_structure(context)
            return OperationResult(True, "Moved sections to destination.", {"count": moved})
        except Exception as e:
            return OperationResult(False, "Failed to move sections to destination.", {"error": str(e)})

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
        """Move topic up in the visual list with intelligent level adaptation."""
        return self._move_up_intelligent(context, node)

    def _move_down(self, context, node) -> bool:
        """Move topic down in the visual list with intelligent level adaptation."""
        return self._move_down_intelligent(context, node)

    def _move_up_intelligent(self, context, node) -> bool:
        """Move node up with intelligent section boundary crossing and level adaptation."""
        try:
            # Get the root for building linear view
            root = getattr(context, "ditamap_root", None)
            if root is None:
                return False
            
            # Build linear view of all structural nodes
            linear_view = self._build_linear_view(root)
            if not linear_view:
                return False
            
            # Find current node in linear view
            current_index = self._find_node_in_linear_view(linear_view, node)
            if current_index <= 0:  # Already at top or not found
                return False
            
            # Get target position (one position up in visual order)
            target_index = current_index - 1
            target_node, target_parent, target_index_in_parent = linear_view[target_index]
            
            # Get current node info
            current_node, current_parent, current_index_in_parent = linear_view[current_index]
            
            # Case 1: Moving within same parent (simple sibling movement)
            if current_parent is target_parent:
                # Use existing sibling movement logic
                res = self._move_sibling(context, current_parent, node, delta=-1)
                return bool(res.success)
            
            # Case 2: Moving to different parent (section boundary crossing)
            # Special case: previous item is our parent (exiting a section). Place node
            # directly above the section it exits by inserting BEFORE the parent at the
            # grandparent level.
            if target_node is current_parent:
                grandparent = current_parent.getparent()
                if grandparent is None:
                    return False
                try:
                    parent_index_in_gp = list(grandparent).index(current_parent)
                except ValueError:
                    return False
                self._reparent_node(node, current_parent, grandparent, parent_index_in_gp)
                target_level = self._calculate_target_level(node, grandparent)
                self._apply_level_adaptation(node, target_level)
                return True

            # Try to enter the nearest enclosing section that is a direct child of current_parent
            # Example: moving from between Section 2 and Section 3 into Section 2 should append
            # as the last direct child of Section 2, not inside a nested subsection.
            enter_parent = None
            probe = target_node
            try:
                while probe is not None and probe.getparent() is not None and probe.getparent() is not current_parent:
                    probe = probe.getparent()
                # If probe is a section under current_parent, enter it
                if getattr(probe, "tag", None) == "topichead" and probe.getparent() is current_parent:
                    enter_parent = probe
            except Exception:
                enter_parent = None

            if enter_parent is not None:
                # Append to the end of the section (last direct child)
                self._reparent_node(node, current_parent, enter_parent, 10**9)
                target_level = self._calculate_target_level(node, enter_parent)
                self._apply_level_adaptation(node, target_level)
                return True

            # General case: move to the same level as target_node, placing right after it
            insert_index = target_index_in_parent + 1
            self._reparent_node(node, current_parent, target_parent, insert_index)
            target_level = self._calculate_target_level(node, target_parent)
            self._apply_level_adaptation(node, target_level)
            
            return True
            
        except Exception:
            return False

    def _move_down_intelligent(self, context, node) -> bool:
        """Move node down with intelligent section boundary crossing and level adaptation."""
        try:
            # Get the root for building linear view
            root = getattr(context, "ditamap_root", None)
            if root is None:
                return False
            
            # Build linear view of all structural nodes
            linear_view = self._build_linear_view(root)
            if not linear_view:
                return False
            
            # Find current node in linear view
            current_index = self._find_node_in_linear_view(linear_view, node)
            if current_index < 0 or current_index >= len(linear_view) - 1:  # Already at bottom or not found
                return False
            
            # Get target position (one position down in visual order)
            target_index = current_index + 1
            target_node, target_parent, target_index_in_parent = linear_view[target_index]
            
            # Get current node info
            current_node, current_parent, current_index_in_parent = linear_view[current_index]
            
            # If moving down from inside a section and the next item is the next section
            # at the same grandparent level, first exit current section and land after it
            # (symmetric to the UP behavior), instead of entering the next section directly.
            if getattr(target_node, "tag", None) == "topichead":
                try:
                    # Find the nearest ancestor of current_parent that is a direct child of target_parent
                    ancestor = current_parent
                    while (
                        ancestor is not None
                        and getattr(ancestor, "getparent", None) is not None
                        and ancestor.getparent() is not None
                        and ancestor.getparent() is not target_parent
                    ):
                        ancestor = ancestor.getparent()

                    if (
                        ancestor is not None
                        and getattr(ancestor, "getparent", None) is not None
                        and ancestor.getparent() is target_parent
                        and getattr(ancestor, "tag", None) in ("topicref", "topichead")
                    ):
                        # Insert right after this ancestor at target_parent level
                        try:
                            ancestor_index = list(target_parent).index(ancestor)
                        except ValueError:
                            ancestor_index = None
                        if ancestor_index is not None:
                            self._reparent_node(node, current_parent, target_parent, ancestor_index + 1)
                            target_level = self._calculate_target_level(node, target_parent)
                            self._apply_level_adaptation(node, target_level)
                            return True
                except Exception:
                    pass
                # Default: enter the section - become first child of target_node
                new_parent = target_node
                insert_index = 0
                self._reparent_node(node, current_parent, new_parent, insert_index)
                target_level = self._calculate_target_level(node, new_parent)
                self._apply_level_adaptation(node, target_level)
                return True
            
            # Case 1: Moving within same parent (simple sibling movement)
            elif current_parent is target_parent:
                # Use existing sibling movement logic
                res = self._move_sibling(context, current_parent, node, delta=1)
                return bool(res.success)
            
            # Case 2: Moving to different parent (section boundary crossing)
            else:
                # Move to same level as target_node using reference-based insert
                new_parent = target_parent
                place_before = False
                # If moving to a shallower level (target_parent is an ancestor of current_parent),
                # place BEFORE the target so numbering advances to the next top-level (e.g., 5.5.2 -> 5.6)
                try:
                    probe = current_parent
                    while probe is not None:
                        if probe is new_parent:
                            place_before = True
                            break
                        probe = probe.getparent() if hasattr(probe, "getparent") else None
                except Exception:
                    pass

                # Perform relative insertion using the real index of target_node
                try:
                    if current_parent is not None:
                        current_parent.remove(node)
                    raw_children = list(new_parent)
                    ref_idx = raw_children.index(target_node)
                    insert_at = ref_idx if place_before else ref_idx + 1
                    if insert_at >= len(raw_children):
                        new_parent.append(node)
                    else:
                        new_parent.insert(insert_at, node)
                except Exception:
                    # Fallback to simple reparent by index
                    self._reparent_node(node, current_parent, new_parent, target_index_in_parent + (0 if place_before else 1))

                # Adapt level for new position
                target_level = self._calculate_target_level(node, new_parent)
                self._apply_level_adaptation(node, target_level)
                return True
            
        except Exception:
            return False

    def _build_linear_view(self, root):
        """Build a flattened linear view of all structural nodes in document order.
        
        Returns a list of (node, parent, index_in_parent) tuples representing
        the order nodes appear visually in the tree widget.
        """
        linear_view = []
        
        def traverse(parent_element, depth=0):
            if parent_element is None:
                return
                
            # Get structural children (topicref/topichead) only
            children = [el for el in list(parent_element) if el.tag in ("topicref", "topichead")]
            
            for index, child in enumerate(children):
                # Add current node to linear view
                linear_view.append((child, parent_element, index))
                
                # Recursively traverse children
                traverse(child, depth + 1)
        
        # Start traversal from root
        traverse(root)
        return linear_view

    def _find_node_in_linear_view(self, linear_view, target_node):
        """Find the index of target_node in the linear view."""
        for i, (node, parent, index) in enumerate(linear_view):
            if node is target_node:
                return i
        return -1

    def _calculate_target_level(self, node, new_parent):
        """Calculate appropriate level for node when placed under new_parent."""
        try:
            # If new_parent is the root (map), check siblings to determine level
            if new_parent.tag == "map":
                # Look at siblings at root level to determine appropriate level
                siblings = [el for el in list(new_parent) if el.tag in ("topicref", "topichead") and el is not node]
                if siblings:
                    # Get level from first sibling
                    for sibling in siblings:
                        level_attr = sibling.get("data-level")
                        if level_attr:
                            return int(level_attr)
                # Default to level 1 if no siblings with levels found
                return 1
            
            # Get new_parent's level and add 1
            parent_level_attr = new_parent.get("data-level")
            if parent_level_attr:
                parent_level = int(parent_level_attr)
                return parent_level + 1
            
            # Fallback: calculate by counting hierarchy depth
            depth = 1
            current = new_parent
            while current is not None and current.tag != "map":
                if current.tag in ("topicref", "topichead"):
                    depth += 1
                current = current.getparent()
            return depth
        except (ValueError, TypeError):
            return 1

    def _apply_level_adaptation(self, node, target_level):
        """Apply the target level to the node's attributes."""
        try:
            node.set("data-level", str(target_level))
            # Update data-style if it's a generic heading style
            current_style = node.get("data-style", "")
            if not current_style or current_style.startswith("Heading "):
                node.set("data-style", f"Heading {target_level}")
        except Exception:
            pass

    def _reparent_node(self, node, old_parent, new_parent, new_index):
        """Move node from old_parent to new_parent at the specified index."""
        try:
            # Remove from old parent
            if old_parent is not None:
                old_parent.remove(node)
            
            # Insert into new parent at specified index
            new_parent_children = list(new_parent)
            if new_index >= len(new_parent_children):
                new_parent.append(node)
            else:
                new_parent.insert(new_index, node)
                    
        except Exception:
            # If reparenting fails, ensure node stays in tree
            if node.getparent() is None and old_parent is not None:
                old_parent.append(node)


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

    # Removed legacy promote/demote helpers (unused). Up/Down implement reparenting and level adaptation.

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

    # ----------------------- Small helpers -----------------------

    @staticmethod
    def _is_ancestor(ancestor: ET.Element, node: ET.Element) -> bool:
        """Return True if ancestor is an ancestor of node (or the same node)."""
        try:
            cur = node
            while cur is not None:
                if cur is ancestor:
                    return True
                cur = cur.getparent() if hasattr(cur, "getparent") else None
        except Exception:
            return False
        return False