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
import logging
from typing import Any, Dict, List, Optional, Literal

from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext


__all__ = ["OperationResult", "StructureEditingService"]

logger = logging.getLogger(__name__)


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
    
    Plugin Integration:
    - Constructor supports dependency injection for plugin-aware composition
    - Service can be instantiated with or without plugin dependencies
    - Maintains backward compatibility with existing non-plugin usage
    """
    
    def __init__(self, app_context: Optional[Any] = None) -> None:
        """Initialize structure editing service.
        
        Args:
            app_context: Optional application context for plugin integration
        """
        self._app_context = app_context
        self._logger = logging.getLogger(f"{__name__}.StructureEditingService")

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
        logger.info("Edit: move_topic direction=%s topic=%s", direction, topic_id)
        node = self._find_topic_ref(context, topic_id)
        if node is None:
            logger.warning("Edit FAIL: move_topic topic_not_found topic=%s", topic_id)
            return OperationResult(False, f"Topic not found for id '{topic_id}'.", {"topic_id": topic_id})

        if direction == "up":
            ok = self._move_up(context, node)
            if ok:
                # Persist this structural change as the new baseline for future depth-limit merges
                self._invalidate_original_structure(context)
            res = OperationResult(ok, ("Moved topic up." if ok else "Cannot move up (at boundary)."), {"topic_id": topic_id})
            if res.success:
                logger.info("Edit OK: move_topic direction=up topic=%s", topic_id)
            else:
                logger.info("Edit noop: move_topic direction=up boundary topic=%s", topic_id)
            return res
        if direction == "down":
            ok = self._move_down(context, node)
            if ok:
                # Persist this structural change as the new baseline for future depth-limit merges
                self._invalidate_original_structure(context)
            res = OperationResult(ok, ("Moved topic down." if ok else "Cannot move down (at boundary)."), {"topic_id": topic_id})
            if res.success:
                logger.info("Edit OK: move_topic direction=down topic=%s", topic_id)
            else:
                logger.info("Edit noop: move_topic direction=down boundary topic=%s", topic_id)
            return res
        return OperationResult(False, f"Unsupported move direction '{direction}'.", {"allowed": ["up", "down"]})

    def move_consecutive_topics(
        self,
        context,
        topic_refs: List[str],
        direction: Literal["up", "down"]
    ) -> OperationResult:
        """Move multiple consecutive topics as a group while preserving their relative order.
        
        This method validates that the topics are consecutive siblings, then moves them
        by applying the existing single-topic intelligent movement logic to each topic
        in the correct order to maintain group cohesion.
        
        Parameters
        ----------
        context : DitaContext
            The DITA context containing the document structure.
        topic_refs : List[str]
            List of topic references (hrefs) that should be moved together.
            These must be consecutive sibling topics.
        direction : Literal["up", "down"]
            Direction to move the group of topics.
            
        Returns
        -------
        OperationResult
            Result indicating success/failure with appropriate message.
        """
        logger.info("Edit: move_consecutive_topics direction=%s count=%d", direction, len(topic_refs or []))
        
        # Validate input
        if not topic_refs or len(topic_refs) < 2:
            return OperationResult(
                False, 
                "At least two topics must be selected for group movement.",
                {"topic_count": len(topic_refs or [])}
            )
        
        # Resolve all topic nodes
        nodes = []
        for ref in topic_refs:
            node = self._find_topic_ref(context, ref)
            if node is None:
                logger.warning("Edit FAIL: move_consecutive_topics topic_not_found topic=%s", ref)
                return OperationResult(
                    False, 
                    f"Topic not found: {ref}",
                    {"missing_topic": ref}
                )
            nodes.append(node)
        
        # Validate that all nodes are consecutive siblings
        if not self._are_nodes_consecutive_siblings(nodes):
            return OperationResult(
                False,
                "Selected topics must be consecutive siblings (no gaps, same parent).",
                {"topic_refs": topic_refs}
            )
        
        # Use existing single-topic intelligent movement logic
        # The key insight: move topics individually in the correct order to maintain group cohesion
        if direction == "up":
            # For UP movement, move topics from first to last
            # This maintains their relative order and group positioning
            topics_to_move = nodes
        else:  # direction == "down"
            # For DOWN movement, move topics from last to first
            # This preserves relative positions as each topic moves to its new location
            topics_to_move = list(reversed(nodes))
        
        success_count = 0
        for node in topics_to_move:
            if direction == "up":
                success = self._move_up_intelligent(context, node)
            else:
                success = self._move_down_intelligent(context, node)
            
            if success:
                success_count += 1
            else:
                # If any topic can't move, stop the operation
                # This prevents partial moves that could break document structure
                break
        
        if success_count == len(nodes):
            # All topics moved successfully
            self._invalidate_original_structure(context)
            result = OperationResult(
                True,
                f"Moved {len(nodes)} topics {direction} as a group.",
                {"topic_count": len(nodes), "direction": direction}
            )
            logger.info("Edit OK: move_consecutive_topics direction=%s count=%d", direction, len(nodes))
            return result
        elif success_count > 0:
            # Partial success - some topics moved
            self._invalidate_original_structure(context)
            result = OperationResult(
                True,
                f"Moved {success_count} of {len(nodes)} topics {direction}. Some topics reached boundary.",
                {"topic_count": success_count, "total_count": len(nodes), "direction": direction}
            )
            logger.info("Edit PARTIAL: move_consecutive_topics direction=%s moved=%d total=%d", direction, success_count, len(nodes))
            return result
        else:
            # No topics could be moved
            logger.info("Edit noop: move_consecutive_topics direction=%s boundary count=%d", direction, len(nodes))
            return OperationResult(
                False,
                f"Cannot move {direction} (at boundary).",
                {"direction": direction, "topic_count": len(nodes)}
            )

    def merge_topics(self, context, source_ids: List[str], target_id: str) -> OperationResult:
        """Manually merge selected topics into the first selected target.

        - Only topicref nodes with href are considered (sections are ignored).
        - Each source topic's title is inserted as a formatted paragraph in the target
          (same style used by unified merge), followed by its body content.
        - Source topicrefs are removed from the map and their topic files are purged.
        """
        try:
            logger.info("Edit: merge_topics target=%s sources=%d", target_id, len(source_ids or []))
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

            # Import shared helper to DRY merge behavior
            try:
                from orlando_toolkit.core.merge import merge_topicref_into as _merge_tref
            except Exception:
                _merge_tref = None

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

                # Merge via helper for consistent behavior
                if _merge_tref is not None:
                    removed_name = _merge_tref(context, target_topic, src_node)
                else:
                    removed_name = None
                # Fallback if helper unavailable
                if removed_name is None:
                    parent = src_node.getparent()
                    if parent is not None:
                        try:
                            parent.remove(src_node)
                        except Exception:
                            pass
                    removed_name = src_fname
                merged_count += 1
                if removed_name:
                    removed_files.append(removed_name)

            # Purge unreferenced topics
            for fn in removed_files:
                context.topics.pop(fn, None)

            # Ensure future depth-limit operations take this state as the new baseline
            self._invalidate_original_structure(context)

            result = OperationResult(True, "Merged topics into target.", {"target": target_fname, "merged_count": merged_count})
            logger.info("Edit OK: merge_topics target=%s merged=%d", target_fname, merged_count)
            return result
        except Exception as e:
            logger.error("Edit FAIL: merge_topics error=%s", e, exc_info=True)
            return OperationResult(False, "Manual merge failed.", {"error": str(e)})

    def rename_topic(self, context, topic_id: str, new_title: str) -> OperationResult:
        """Rename a topic by topic_id (href or filename). Canonical API uses topic_id only; topic refs/elements are not accepted."""
        logger.info("Edit: rename_topic topic=%s", topic_id)
        if getattr(context, "ditamap_root", None) is None:
            return OperationResult(False, "No ditamap available in context.", {"reason": "missing_ditamap"})

        node = self._find_topic_ref(context, topic_id)
        if node is None:
            logger.warning("Edit FAIL: rename_topic topic_not_found topic=%s", topic_id)
            return OperationResult(False, f"Topic not found for id '{topic_id}'.", {"topic_id": topic_id})

        ok = self._rename(context, node, new_title)
        if ok:
            filename = self._normalize_filename(topic_id)
            # Persist rename across future depth-limit changes
            self._invalidate_original_structure(context)
            result = OperationResult(True, f"Renamed topic '{filename}'.", {"topic_id": topic_id, "new_title": " ".join((new_title or "").split())})
            logger.info("Edit OK: rename_topic topic=%s", filename)
            return result
        logger.warning("Edit FAIL: rename_topic topic=%s", topic_id)
        return OperationResult(False, "Rename failed.", {"topic_id": topic_id})

    def delete_topics(self, context, topic_ids: List[str]) -> OperationResult:
        """Delete topics by topic_ids (hrefs or filenames). Canonical API uses topic_ids only; topic refs/elements are not accepted."""
        logger.info("Edit: delete_topics count=%d", len(topic_ids or []))
        if getattr(context, "ditamap_root", None) is None:
            return OperationResult(False, "No ditamap available in context.", {"reason": "missing_ditamap"})

        requested = list(topic_ids)
        deleted_count = self._delete_by_ids(context, topic_ids)

        # Persist deletion baseline for future depth-limit operations
        self._invalidate_original_structure(context)
        details = {"requested": requested, "deleted": deleted_count, "skipped": max(0, len(requested) - deleted_count)}
        result = OperationResult(deleted_count > 0, ("Deleted topics." if deleted_count > 0 else "No topics deleted."), details)
        if result.success:
            logger.info("Edit OK: delete_topics deleted=%d skipped=%d", details.get("deleted", 0), details.get("skipped", 0))
        else:
            logger.info("Edit noop: delete_topics deleted=0")
        return result

    def apply_depth_limit(self, context, depth_limit: int, style_exclusions: dict[int, set[str]] | None = None) -> OperationResult:
        """Apply a depth limit merge to the current context with reversible behavior.

        This method:
        - Saves original structure on first use to enable depth limit reversibility
        - Always works from original structure to avoid compound transformations
        - Never raises; returns OperationResult with details
        """
        try:
            logger.info("Edit: apply_depth_limit depth=%d styles=%s", depth_limit, bool(style_exclusions))
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
            
            result = OperationResult(True, "Applied depth limit", {"depth_limit": depth_limit, "merged": True})
            # Merge summary for diagnostics
            try:
                root = getattr(context, "ditamap_root", None)
                refs = int(root.xpath('count(.//topicref[@href])')) if root is not None else 0
                topics = len(getattr(context, "topics", {}) or {})
                logger.info("Merge summary: topicrefs=%d topics=%d", refs, topics)
            except Exception:
                pass
            logger.info("Edit OK: apply_depth_limit depth=%d", depth_limit)
            return result
        except Exception as e:
            # Never raise; encapsulate error
            logger.error("Edit FAIL: apply_depth_limit depth=%d error=%s", depth_limit, e, exc_info=True)
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
            logger.info("Edit: move_topics_to_target count=%d dest=%s", len(topic_ids or []), str(target_index_path))
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
            result = OperationResult(True, "Moved topics to destination.", {"count": len(moved)})
            logger.info("Edit OK: move_topics_to_target moved=%d", len(moved))
            return result
        except Exception as e:
            logger.error("Edit FAIL: move_topics_to_target error=%s", e, exc_info=True)
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
            logger.info("Edit: move_section_to_target dest=%s", str(target_index_path))
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
            result = OperationResult(True, "Moved section to destination.", {"index_path": list(section_index_path)})
            logger.info("Edit OK: move_section_to_target index_path=%s", str(section_index_path))
            return result
        except Exception as e:
            logger.error("Edit FAIL: move_section_to_target error=%s", e, exc_info=True)
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
            logger.info("Edit: move_sections_to_target count=%d dest=%s", len(section_index_paths or []), str(target_index_path))
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
            result = OperationResult(True, "Moved sections to destination.", {"count": moved})
            logger.info("Edit OK: move_sections_to_target moved=%d", moved)
            return result
        except Exception as e:
            logger.error("Edit FAIL: move_sections_to_target error=%s", e, exc_info=True)
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
            
            # Case 1: Moving within same parent
            if current_parent is target_parent:
                # If the previous item is a section, enter it as last child
                if getattr(target_node, "tag", None) == "topichead":
                    self._reparent_node(node, current_parent, target_node, 10**9)
                    target_level = self._calculate_target_level(node, target_node)
                    self._apply_level_adaptation(node, target_level)
                    return True
                # Otherwise perform simple sibling movement
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

    def _are_nodes_consecutive_siblings(self, nodes: List) -> bool:
        """Check if nodes are consecutive siblings with no gaps.
        
        Parameters
        ----------
        nodes : List
            List of XML nodes to check for consecutiveness.
            
        Returns
        -------
        bool
            True if all nodes are consecutive siblings, False otherwise.
        """
        try:
            if len(nodes) < 2:
                return False
            
            # All nodes must have the same parent
            parent = nodes[0].getparent()
            if parent is None:
                return False
            
            for node in nodes[1:]:
                if node.getparent() != parent:
                    return False
            
            # Get all siblings and find positions
            siblings = [child for child in parent if child.tag in ("topicref", "topichead")]
            indices = []
            
            for node in nodes:
                try:
                    idx = siblings.index(node)
                    indices.append(idx)
                except ValueError:
                    return False
            
            # Sort indices and check for consecutiveness
            indices.sort()
            for i in range(1, len(indices)):
                if indices[i] != indices[i-1] + 1:
                    return False
            
            return True
        except Exception:
            return False
    
    # REMOVED: Complex group movement helper methods that violated DRY principles.
    # The simplified move_consecutive_topics method now reuses existing single-topic
    # intelligent movement logic (_move_up_intelligent, _move_down_intelligent) which
    # already handles all the complex cases including level adaptation, section boundary
    # crossing, and boundary checking. This follows YAGNI and DRY principles.


    # ----------------------- Section operations -----------------------

    def insert_section_after_index_path(self, context: DitaContext, index_path: List[int], title: str) -> OperationResult:
        """Insert a new section (topichead) directly below the structural node at index_path.

        The new section is created as a sibling under the same parent. It sets
        topicmeta/navtitle to the provided title and applies level/style
        attributes consistent with other structural operations.
        """
        logger.info("Edit: insert_section_after_index_path index_path=%s", str(index_path))
        root = getattr(context, "ditamap_root", None)
        if root is None:
            return OperationResult(False, "No ditamap available in context.")
        cleaned = " ".join((title or "").split())
        if not cleaned:
            return OperationResult(False, "Empty title is not allowed")
        try:
            # Locate the reference node and its parent using structural indexing
            ref_node = self._locate_node_by_index_path(context, index_path)
            if ref_node is None or getattr(ref_node, "tag", None) not in ("topicref", "topichead"):
                return OperationResult(False, "Reference node not found for insertion.", {"index_path": list(index_path or [])})

            parent = ref_node.getparent() or root

            # Compute insertion raw index in parent's children to place after the ref structural sibling
            # Build structural and raw children lists once
            raw_children = list(parent)
            structural_children = [el for el in raw_children if getattr(el, "tag", None) in ("topicref", "topichead")]
            try:
                sidx_after = structural_children.index(ref_node) + 1
            except ValueError:
                # Fallback: append at end of structural list
                sidx_after = len(structural_children)

            if sidx_after >= len(structural_children):
                # Insert after last structural child -> before first non-structural that follows, or append
                if structural_children:
                    last_struct = structural_children[-1]
                    insert_at = raw_children.index(last_struct) + 1
                else:
                    insert_at = len(raw_children)
            else:
                # Insert before the next structural child in raw list
                next_struct = structural_children[sidx_after]
                insert_at = raw_children.index(next_struct)

            # Create the new section node
            new_section = ET.Element("topichead")
            # Ensure navtitle
            topicmeta = ET.SubElement(new_section, "topicmeta")
            navtitle = ET.SubElement(topicmeta, "navtitle")
            navtitle.text = cleaned

            # Insert into parent at computed raw index
            try:
                parent.insert(insert_at, new_section)
            except Exception:
                parent.append(new_section)

            # Apply level/style for the new section
            target_level = self._calculate_target_level(new_section, parent)
            self._apply_level_adaptation(new_section, target_level)

            # Persist baseline so future merges start from current structure
            self._invalidate_original_structure(context)

            # New structural path is the same parent path with last index + 1
            new_path = list(index_path or [])
            if new_path:
                new_path[-1] = new_path[-1] + 1
            else:
                # If inserted at root before any selection (edge), compute index from tree
                try:
                    structural_children = [el for el in list(parent) if getattr(el, "tag", None) in ("topicref", "topichead")]
                    new_path = [structural_children.index(new_section)]
                except Exception:
                    new_path = []

            result = OperationResult(True, "Section inserted.", {"new_index_path": new_path, "new_level": int(target_level) if isinstance(target_level, int) else target_level})
            logger.info("Edit OK: insert_section_after_index_path at new_path=%s", str(new_path))
            return result
        except Exception as e:
            logger.error("Edit FAIL: insert_section_after_index_path error=%s", e, exc_info=True)
            return OperationResult(False, "Failed to insert section.", {"error": str(e)})

    def insert_section_as_first_child(self, context: DitaContext, index_path: List[int], title: str) -> OperationResult:
        """Insert a new section (topichead) as the first structural child of the section at index_path.

        Returns unsuccessful OperationResult when index_path does not locate a section (topichead).
        """
        logger.info("Edit: insert_section_as_first_child index_path=%s", str(index_path))
        root = getattr(context, "ditamap_root", None)
        if root is None:
            return OperationResult(False, "No ditamap available in context.")
        cleaned = " ".join((title or "").split())
        if not cleaned:
            return OperationResult(False, "Empty title is not allowed")
        try:
            # Locate the section node by index_path
            parent_section = self._locate_node_by_index_path(context, index_path)
            if parent_section is None or getattr(parent_section, "tag", None) != "topichead":
                return OperationResult(False, "Target section not found for insertion.", {"index_path": list(index_path or [])})

            # Determine raw insertion index corresponding to 'first structural child'
            raw_children = list(parent_section)
            structural_children = [el for el in raw_children if getattr(el, "tag", None) in ("topicref", "topichead")]
            if structural_children:
                first_struct = structural_children[0]
                insert_at = raw_children.index(first_struct)
            else:
                insert_at = len(raw_children)

            # Create new section node with navtitle
            new_section = ET.Element("topichead")
            topicmeta = ET.SubElement(new_section, "topicmeta")
            navtitle = ET.SubElement(topicmeta, "navtitle")
            navtitle.text = cleaned

            # Insert at computed position
            try:
                parent_section.insert(insert_at, new_section)
            except Exception:
                parent_section.append(new_section)

            # Apply level/style for the new section (child of section)
            target_level = self._calculate_target_level(new_section, parent_section)
            self._apply_level_adaptation(new_section, target_level)

            # Persist baseline so future merges start from current structure
            self._invalidate_original_structure(context)

            # Compute new structural path: same as parent path with child index 0
            try:
                structural_children_after = [el for el in list(parent_section) if getattr(el, "tag", None) in ("topicref", "topichead")]
                new_index = structural_children_after.index(new_section) if new_section in structural_children_after else 0
            except Exception:
                new_index = 0
            new_path = list(index_path or []) + [new_index]

            result = OperationResult(True, "Section inserted as first child.", {"new_index_path": new_path, "new_level": int(target_level) if isinstance(target_level, int) else target_level})
            logger.info("Edit OK: insert_section_as_first_child at new_path=%s", str(new_path))
            return result
        except Exception as e:
            logger.error("Edit FAIL: insert_section_as_first_child error=%s", e, exc_info=True)
            return OperationResult(False, "Failed to insert section as first child.", {"error": str(e)})

    def convert_section_to_topic(self, context: DitaContext, index_path: List[int]) -> OperationResult:
        """Convert a section (topichead) located by index_path into a topic that hosts its subtree.

        All descendant topics' titles and content are merged into the created/reused
        content module topic to match unified merge formatting.
        """
        logger.info("Edit: convert_section_to_topic index_path=%s", str(index_path))
        if getattr(context, "ditamap_root", None) is None:
            return OperationResult(False, "No ditamap available in context.")
        try:
            section = self._locate_node_by_index_path(context, index_path)
            if section is None or getattr(section, "tag", None) != "topichead":
                return OperationResult(False, "Section not found.", {"index_path": list(index_path)})

            # Delegate to shared merge helper for uniform behavior
            try:
                from orlando_toolkit.core.merge import convert_section_to_local_topic
            except Exception:
                return OperationResult(False, "Merge helper unavailable.")

            target_topic_el, removed_files = convert_section_to_local_topic(context, section)
            if target_topic_el is None:
                return OperationResult(False, "Failed to create content module for section.")

            # Purge removed topics
            for fn in removed_files or []:
                try:
                    context.topics.pop(fn, None)
                except Exception:
                    pass

            # Persist baseline after structural change
            self._invalidate_original_structure(context)
            result = OperationResult(True, "Section converted to topic.", {"index_path": list(index_path)})
            logger.info("Edit OK: convert_section_to_topic index_path=%s", str(index_path))
            return result
        except Exception as e:
            logger.error("Edit FAIL: convert_section_to_topic error=%s", e, exc_info=True)
            return OperationResult(False, "Failed to convert section.", {"error": str(e)})

    def rename_section(self, context: DitaContext, index_path: List[int], new_title: str) -> OperationResult:
        """Rename the navtitle of a section (topichead) located by index_path."""
        logger.info("Edit: rename_section index_path=%s", str(index_path))
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
            result = OperationResult(True, "Section renamed.", {"index_path": list(index_path), "new_title": cleaned})
            logger.info("Edit OK: rename_section index_path=%s", str(index_path))
            return result
        except Exception as e:
            logger.error("Edit FAIL: rename_section error=%s", e, exc_info=True)
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
        logger.info("Edit: delete_section index_path=%s", str(index_path))
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
            result = OperationResult(True, "Section deleted.", {"index_path": list(index_path), "purged_candidates": removed_refs})
            logger.info("Edit OK: delete_section index_path=%s purged=%d", str(index_path), len(removed_refs or []))
            return result
        except Exception as e:
            logger.error("Edit FAIL: delete_section error=%s", e, exc_info=True)
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