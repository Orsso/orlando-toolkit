from typing import List, Dict, Literal, Optional, Callable, Any, Set

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.services.structure_editing_service import (
    StructureEditingService,
    OperationResult,
)
from orlando_toolkit.core.services.undo_service import UndoService
from orlando_toolkit.core.services.preview_service import PreviewService, PreviewResult
from orlando_toolkit.core.services import heading_analysis_service as _heading_analysis


class StructureController:
    """Controller for coordinating structure editing UI actions with services.

    This controller maintains transient UI-related state and delegates operations
    to the appropriate services. It contains no UI toolkit code and does not
    perform I/O or logging.

    Parameters
    ----------
    context : DitaContext
        The active DITA context the UI is working with.
    editing_service : StructureEditingService
        Service that performs structural editing operations.
    undo_service : UndoService
        Service that manages undo/redo snapshots and restoration.
    preview_service : PreviewService
        Service that compiles previews and renders HTML previews.

    Notes
    -----
    - This controller is conservative and non-raising for routine validation
      failures; most methods return booleans or result objects indicating success.
    - No Tkinter or UI framework code should appear in this module.
    """

    def __init__(
        self,
        context: DitaContext,
        editing_service: StructureEditingService,
        undo_service: UndoService,
        preview_service: PreviewService,
    ) -> None:
        # Dependencies
        self.context: DitaContext = context
        self.editing_service: StructureEditingService = editing_service
        self.undo_service: UndoService = undo_service
        self.preview_service: PreviewService = preview_service

        # Transient UI-related state
        self.max_depth: int = 999
        self.search_term: str = ""
        self.search_results: List[str] = []  # e.g., list of topic_ref ids
        self.search_index: int = -1  # current index into search_results for navigation
        self.selected_items: List[str] = []
        self.heading_filter_exclusions: Dict[str, bool] = {}  # style -> excluded
        self.style_visibility: Dict[str, bool] = {}  # style -> visible (show marker)

    # ---------------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------------

    def _recorded_edit(self, mutate: Callable[[], Any]) -> Any:
        """Execute a mutating operation with pre/post undo snapshots.

        - Pushes a snapshot before mutation; failure is non-fatal.
        - Executes the provided callable.
        - On success (OperationResult.success True or boolean True), pushes a post snapshot.
        - Returns the original result.

        This preserves business logic in services and keeps snapshot policy DRY.
        """
        pre_snapshot_failed = False
        try:
            self.undo_service.push_snapshot(self.context)
        except Exception:
            pre_snapshot_failed = True

        result = None
        try:
            result = mutate()
        except Exception:
            return result

        # Determine success flag conservatively
        success = False
        if isinstance(result, bool):
            success = result
        else:
            success = bool(getattr(result, "success", False))

        if success:
            try:
                self.undo_service.push_snapshot(self.context)
            except Exception:
                # Non-fatal – the operation already succeeded; redo may be limited
                pass

        # Optionally augment message if pre-snapshot failed
        if pre_snapshot_failed and hasattr(result, "success") and getattr(result, "success"):
            msg = getattr(result, "message", "") or ""
            warning = " Warning: Undo snapshot failed - undo may not be available for this operation."
            try:
                result.message = f"{msg}{warning}".strip()
            except Exception:
                pass
        return result

    def handle_depth_change(self, new_depth: int) -> bool:
        """Handle a change in the maximum depth to display.

        Clamps the value to be at least 1, stores it, and returns True if
        the value actually changed.

        Parameters
        ----------
        new_depth : int
            The requested new maximum depth.

        Returns
        -------
        bool
            True if the stored depth changed, False otherwise.
        """
        # Guard: new_depth must be an int
        if not isinstance(new_depth, int):
            return False

        # Clamp to minimum of 1
        clamped = max(1, new_depth)

        # If no effective change, preserve previous behavior
        if clamped == self.max_depth:
            return False

        # Only proceed when the clamped value differs from current max_depth.
        # Push an undo snapshot (non-fatal on failure).
        pre_failed = False
        try:
            self.undo_service.push_snapshot(self.context)
        except Exception:
            pre_failed = True
            if hasattr(self, "logger"):
                self.logger.warning("Failed to push undo snapshot for depth change", exc_info=True)

        # Build a minimal style exclusions map for the merge API:
        # Convert controller's heading_filter_exclusions (Dict[str, bool], True means excluded)
        # into the expected Dict[int, Set[str]] where key 1 is used for "all levels" for now.
        if hasattr(self, "heading_filter_exclusions") and isinstance(self.heading_filter_exclusions, dict):
            names = sorted([name for name, flag in self.heading_filter_exclusions.items() if flag])
        else:
            names = []
        # Deliberately simple mapping pending per-level filters.
        style_exclusions_map = None if not names else {1: set(names)}

        # Delegate to the structure editing service to apply the depth limit/merge.
        try:
            result = self.editing_service.apply_depth_limit(self.context, clamped, style_exclusions_map)
        except Exception:
            return False

        # Require an explicit success signal
        if not getattr(result, "success", False):
            return False

        # On success, update controller state and report True
        self.max_depth = clamped
        # Persist chosen depth so packaging/export uses the same value
        try:
            if hasattr(self, "context") and hasattr(self.context, "metadata"):
                self.context.metadata["topic_depth"] = clamped
        except Exception:
            # Best-effort only; keep UI responsive even if metadata is not writable
            pass
        # Push post-mutation snapshot to enable redo
        try:
            self.undo_service.push_snapshot(self.context)
        except Exception:
            # Non-fatal: operation already applied
            pass

        return True

    def handle_move_operation(
        self, direction: Literal["up", "down", "promote", "demote"]
    ) -> OperationResult:
        """Handle a move operation on the first selected item.

        If there is no selection, an unsuccessful OperationResult is returned.
        Otherwise, this pushes an undo snapshot, delegates to the editing service
        for the move, and relies on UndoService snapshot semantics to manage
        redo clearing.

        Parameters
        ----------
        direction : Literal["up", "down", "promote", "demote"]
            The move direction to apply to the first selected item.

        Returns
        -------
        OperationResult
            The result of the move operation from the editing service. If the
            undo snapshot fails to be created, the operation will still proceed
            but the result will include a warning about the undo capability loss.

        Notes
        -----
        - Multi-select handling is intentionally left for future extension.
        - Routine validation failures should not raise; instead an unsuccessful
          OperationResult is returned.
        - Snapshot failures are caught and reported in the result message to
          inform users of potential undo capability loss.
        """
        first_ref: Optional[str] = self.selected_items[0] if self.selected_items else None
        if not first_ref:
            # Construct a conservative unsuccessful result without raising.
            return OperationResult(success=False, message="No selection")

        try:
            return self._recorded_edit(
                lambda: self.editing_service.move_topic(self.context, first_ref, direction)
            )
        except Exception:
            # Non-raising for routine errors: return an unsuccessful result.
            return OperationResult(success=False, message="Move operation failed")

    def handle_rename(self, topic_ref: str, new_title: str) -> OperationResult:
        """Rename a topic via the editing service wrapped with undo snapshots."""
        if not isinstance(topic_ref, str) or not topic_ref:
            return OperationResult(success=False, message="No topic selected to rename")
        if not isinstance(new_title, str) or not new_title.strip():
            return OperationResult(success=False, message="Empty title is not allowed")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.rename_topic(self.context, topic_ref, new_title)
            )
        except Exception:
            return OperationResult(success=False, message="Rename operation failed")

    def handle_delete(self, topic_refs: List[str]) -> OperationResult:
        """Delete topics via the editing service wrapped with undo snapshots."""
        refs = [r for r in (topic_refs or []) if isinstance(r, str) and r]
        if not refs:
            return OperationResult(success=False, message="No topics selected to delete")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.delete_topics(self.context, refs)
            )
        except Exception:
            return OperationResult(success=False, message="Delete operation failed")

    def handle_merge(self, topic_refs: List[str]) -> OperationResult:
        """Merge topics via the editing service with undo snapshots.

        Policy: first ref is target, remaining are sources. Requires >= 2 refs.
        Falls back to a two-arg merge signature if service expects it.
        """
        refs = [r for r in (topic_refs or []) if isinstance(r, str) and r]
        if len(refs) < 2:
            return OperationResult(success=False, message="Select at least two topics to merge")
        target_id = refs[0]
        source_ids = refs[1:]

        def _call_merge():
            try:
                # Preferred signature: (context, source_ids, target_id)
                return self.editing_service.merge_topics(self.context, source_ids, target_id)
            except TypeError:
                # Fallback legacy signature: (context, refs)
                return self.editing_service.merge_topics(self.context, refs)  # type: ignore[arg-type]

        try:
            return self._recorded_edit(_call_merge)
        except Exception:
            return OperationResult(success=False, message="Merge operation failed")

    def handle_apply_filters(self, style_excl_map: Optional[Dict[int, Set[str]]] = None) -> OperationResult:
        """Apply heading-style filters through the depth-limit service with snapshots."""
        try:
            return self._recorded_edit(
                lambda: self.editing_service.apply_depth_limit(self.context, self.max_depth, style_excl_map)
            )
        except Exception:
            return OperationResult(success=False, message="Failed to apply filters")

    # ---------------------------------------------------------------------
    # Heading analysis wrappers (UI queries)
    # ---------------------------------------------------------------------

    def get_heading_counts(self) -> Dict[str, int]:
        """Return counts of headings per style using the original (pre-merge) structure.

        The filter panel needs to display styles that may currently be excluded
        or beyond the visible depth. We temporarily restore the original map to
        compute comprehensive counts, then restore the filtered structure.
        """
        try:
            original_root = None
            if hasattr(self.context, 'restore_from_original'):
                original_root = getattr(self.context, 'ditamap_root', None)
                self.context.restore_from_original()
            result = _heading_analysis.build_headings_cache(self.context)
            if original_root is not None and hasattr(self.context, 'ditamap_root'):
                self.context.ditamap_root = original_root
            return result
        except Exception:
            return {}

    def get_heading_occurrences(self) -> Dict[str, List[Dict[str, str]]]:
        """Return mapping style -> occurrences using the original (pre-merge) structure.

        Ensures styles beyond the current depth/exclusions are still available
        in the filter panel with their occurrences.
        """
        try:
            original_root = None
            if hasattr(self.context, 'restore_from_original'):
                original_root = getattr(self.context, 'ditamap_root', None)
                self.context.restore_from_original()
            result = _heading_analysis.build_heading_occurrences(self.context)
            if original_root is not None and hasattr(self.context, 'ditamap_root'):
                self.context.ditamap_root = original_root
            return result
        except Exception:
            return {}

    def get_heading_occurrences_current(self) -> Dict[str, List[Dict[str, str]]]:
        """Return style -> occurrences for the current (post-merge) structure.

        Used for UI highlighting so that selections align with what the tree shows now.
        """
        try:
            return _heading_analysis.build_heading_occurrences(self.context)
        except Exception:
            return {}

    def get_style_levels(self) -> Dict[str, Optional[int]]:
        """Return mapping style -> level using the original (pre-merge) structure.

        This provides a stable grouping for styles even when the current view
        has filtered them out.
        """
        try:
            original_root = None
            if hasattr(self.context, 'restore_from_original'):
                original_root = getattr(self.context, 'ditamap_root', None)
                self.context.restore_from_original()
            result = _heading_analysis.build_style_levels(self.context)
            if original_root is not None and hasattr(self.context, 'ditamap_root'):
                self.context.ditamap_root = original_root
            return result
        except Exception:
            return {}

    def estimate_unmergable(self, style_excl_map: Dict[int, Set[str]]) -> int:
        """Estimate number of items that cannot be merged for given style-level exclusions."""
        try:
            return _heading_analysis.count_unmergable_for_styles(self.context, style_excl_map)
        except Exception:
            return 0

    def build_style_exclusion_map_from_flags(self, exclusions: Dict[str, bool]) -> Dict[int, Set[str]]:
        """Convert style->excluded flags to per-level style set map.

        For styles with unknown level, default to level 1 to preserve prior behavior.
        """
        levels_map = self.get_style_levels()
        style_excl_map: Dict[int, Set[str]] = {}
        try:
            for style, excluded in (exclusions or {}).items():
                if not excluded:
                    continue
                level_val = levels_map.get(style)
                level = int(level_val) if isinstance(level_val, int) else 1
                style_excl_map.setdefault(level, set()).add(style)
        except Exception:
            pass
        return style_excl_map

    def handle_search(self, term: str) -> List[str]:
        """Handle a search request and store transient search state.

        Attempts to compute conservative search results using the available
        context if possible. If underlying data is unavailable or access fails,
        returns an empty list while persisting state.

        Parameters
        ----------
        term : str
            The search term to apply.

        Returns
        -------
        List[str]
            A list of matched topic_ref identifiers. Empty list on failure or no match.

        Notes
        -----
        - Method should not raise for data access issues; returns [] in such cases.
        - Results are intentionally conservative given limited knowledge of the context.
        """
        self.search_term = term or ""
        self.search_results = []
        self.search_index = -1

        if not self.search_term:
            return self.search_results

        # Prefer searching the structured ditamap when available so that we
        # return hrefs that the tree widget understands and can highlight.
        try:
            root = getattr(self.context, "ditamap_root", None)
        except Exception:
            root = None

        term_lower = self.search_term.lower()

        if root is not None:
            try:
                def iter_heading_children(node: object):
                    try:
                        if hasattr(node, "iterchildren"):
                            for child in node.iterchildren():
                                try:
                                    tag = str(getattr(child, "tag", "") or "")
                                except Exception:
                                    tag = ""
                                if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                                    yield child
                            return
                    except Exception:
                        pass
                    try:
                        if hasattr(node, "getchildren"):
                            for child in node.getchildren():  # type: ignore[attr-defined]
                                try:
                                    tag = str(getattr(child, "tag", "") or "")
                                except Exception:
                                    tag = ""
                                if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                                    yield child
                            return
                    except Exception:
                        pass
                    try:
                        if hasattr(node, "findall"):
                            for child in list(node.findall("./topicref")) + list(node.findall("./topichead")):
                                yield child
                    except Exception:
                        return

                def extract_title(node: object) -> str:
                    # Prefer topicmeta/navtitle, then <title>, else @navtitle
                    try:
                        if hasattr(node, "find"):
                            nav = node.find("topicmeta/navtitle")
                            if nav is not None:
                                txt = getattr(nav, "text", None)
                                if isinstance(txt, str) and txt.strip():
                                    return txt.strip()
                            tnode = node.find("title")
                            if tnode is not None:
                                ttxt = getattr(tnode, "text", None)
                                if isinstance(ttxt, str) and ttxt.strip():
                                    return ttxt.strip()
                    except Exception:
                        pass
                    try:
                        if hasattr(node, "get"):
                            alt = node.get("navtitle")
                            if isinstance(alt, str) and alt.strip():
                                return alt.strip()
                    except Exception:
                        pass
                    return ""

                def extract_href(node: object) -> str:
                    try:
                        if hasattr(node, "get"):
                            href = node.get("href")
                            if isinstance(href, str) and href.strip():
                                return href.strip()
                    except Exception:
                        pass
                    return ""

                matches: List[str] = []
                stack = [root]
                visited = 0
                max_nodes = 200000

                while stack and visited < max_nodes:
                    node = stack.pop()
                    visited += 1
                    try:
                        tag = str(getattr(node, "tag", "") or "")
                    except Exception:
                        tag = ""

                    is_heading = tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}
                    if is_heading:
                        title = extract_title(node)
                        href = extract_href(node)
                        # Match on title text, full href, file basename
                        basename = href.split("/")[-1] if href else ""
                        def _contains(s: str) -> bool:
                            return bool(s) and term_lower in s.lower()
                        if _contains(title) or _contains(href) or _contains(basename):
                            if href:
                                matches.append(href)

                    try:
                        # Push children in reverse order so the DFS visit preserves
                        # the original left-to-right visual order when popping.
                        children = []
                        for child in iter_heading_children(node):
                            children.append(child)
                        for child in reversed(children):
                            stack.append(child)
                    except Exception:
                        pass

                # Deduplicate while preserving order
                seen: Dict[str, bool] = {}
                uniq: List[str] = []
                for h in matches:
                    if h not in seen:
                        seen[h] = True
                        uniq.append(h)
                self.search_results = uniq
                self.search_index = 0 if self.search_results else -1
                return self.search_results
            except Exception:
                # Fall through to attribute-based best-effort search
                pass

        # Best-effort fallback: probe common attributes and filter by substring
        try:
            candidates: List[str] = []
            possible_attrs = [
                "topics",
                "topic_refs",
                "all_topics",
                "all_topic_refs",
                "nodes",
                "items",
            ]
            for attr in possible_attrs:
                if hasattr(self.context, attr):
                    value = getattr(self.context, attr)
                    if isinstance(value, dict):
                        candidates.extend(list(value.keys()))
                    elif isinstance(value, list):
                        for entry in value:
                            if isinstance(entry, str):
                                candidates.append(entry)
                            else:
                                for id_attr in ["id", "ref", "topic_ref", "uid"]:
                                    if hasattr(entry, id_attr):
                                        ref_val = getattr(entry, id_attr)
                                        if isinstance(ref_val, str):
                                            candidates.append(ref_val)
                                            break

            # Deduplicate
            seen2: Dict[str, bool] = {}
            unique_candidates: List[str] = []
            for c in candidates:
                if c not in seen2:
                    seen2[c] = True
                    unique_candidates.append(c)

            self.search_results = [c for c in unique_candidates if term_lower in c.lower()]
            self.search_index = 0 if self.search_results else -1
        except Exception:
            self.search_results = []
            self.search_index = -1

        return self.search_results

    def handle_filter_toggle(self, style: str, enabled: bool) -> Dict[str, bool]:
        """Toggle a heading style filter.

        Updates the internal mapping of style exclusions. When enabled=False,
        the style is considered excluded (i.e., not shown).

        Parameters
        ----------
        style : str
            The heading style key (e.g., 'Heading1', 'Heading2').
        enabled : bool
            Whether the style should be enabled (shown). If False, it is excluded.

        Returns
        -------
        Dict[str, bool]
            The current mapping of style to excluded flag.
        """
        if not isinstance(style, str) or not style:
            # Do nothing if invalid style label; keep conservative behavior
            return self.heading_filter_exclusions

        excluded = not enabled
        self.heading_filter_exclusions[style] = excluded
        return self.heading_filter_exclusions

    def handle_style_visibility_toggle(self, style: str, visible: bool) -> Dict[str, bool]:
        """Toggle visibility of a style marker.

        Updates the internal mapping of style visibility for tree markers.

        Parameters
        ----------
        style : str
            Style name (e.g., 'Heading1', 'Heading2').
        visible : bool
            True to show the marker, False to hide it.

        Returns
        -------
        Dict[str, bool]
            Current mapping style -> visible.
        """
        if not isinstance(style, str) or not style:
            return self.style_visibility
            
        self.style_visibility[style] = bool(visible)
        return self.style_visibility
        
    def get_style_visibility(self) -> Dict[str, bool]:
        """Return the current visibility for all styles."""
        return dict(self.style_visibility)
        
    def get_style_colors(self) -> Dict[str, str]:
        """Generate and return the colors assigned to styles.

        Uses the same logic as `StyleLegend` to preserve consistency.
        """
        try:
            # Local import to avoid circular dependencies
            from orlando_toolkit.ui.widgets.style_legend import STYLE_COLORS
        except ImportError:
            # Fallback if import fails - synchronized final palette
            STYLE_COLORS = [
                "#E53E3E", "#38A169", "#FF6B35", "#805AD5", "#D4AF37", "#228B22",
                "#FF8C00", "#B22222", "#9400D3", "#32CD32", "#8B0000", "#FF4500",
                "#2E8B57", "#B8860B", "#8B4513", "#CD853F", "#8FBC8F", "#A0522D",
                "#2F4F4F", "#8B008B", "#556B2F", "#800000", "#483D8B"
            ]
            
        colors = {}
        try:
            # Use the collision-free color manager
            from orlando_toolkit.ui.widgets.style_legend import _color_manager
            for style in self.style_visibility.keys():
                colors[style] = _color_manager.get_color_for_style(style)
        except ImportError:
            # Fallback to legacy method if import fails
            for style in self.style_visibility.keys():
                color_index = hash(style) % len(STYLE_COLORS)
                colors[style] = STYLE_COLORS[color_index]
        
        return colors

    def select_items(self, item_refs: List[str]) -> None:
        """Set the current selection to the provided list of item references.

        Ensures selection is stored as a list of unique references in order of first appearance.

        Parameters
        ----------
        item_refs : List[str]
            The list of item reference identifiers to select.

        Returns
        -------
        None
        """
        if not isinstance(item_refs, list):
            self.selected_items = []
            return

        seen: Dict[str, bool] = {}
        unique_refs: List[str] = []
        for ref in item_refs:
            if isinstance(ref, str) and ref and ref not in seen:
                seen[ref] = True
                unique_refs.append(ref)
        self.selected_items = unique_refs

    def get_selection(self) -> List[str]:
        """Get the current selection.

        Returns
        -------
        List[str]
            The list of selected item reference identifiers.
        """
        return list(self.selected_items)

    def can_undo(self) -> bool:
        """Check if an undo operation is available.

        Returns
        -------
        bool
            True if undo is available, False otherwise.
        """
        try:
            return self.undo_service.can_undo()
        except Exception:
            return False

    def can_redo(self) -> bool:
        """Check if a redo operation is available.

        Returns
        -------
        bool
            True if redo is available, False otherwise.
        """
        try:
            return self.undo_service.can_redo()
        except Exception:
            return False

    def undo(self) -> bool:
        """Perform an undo operation by restoring the previous snapshot into the context.

        Returns
        -------
        bool
            True if the undo succeeded, False otherwise.
        """
        try:
            return self.undo_service.undo(self.context)
        except Exception:
            return False

    def redo(self) -> bool:
        """Perform a redo operation by restoring the next snapshot into the context.

        Returns
        -------
        bool
            True if the redo succeeded, False otherwise.
        """
        try:
            return self.undo_service.redo(self.context)
        except Exception:
            return False

    def compile_preview(self, topic_ref: str) -> PreviewResult:
        """Compile a preview for the provided or selected topic reference.

        If topic_ref is falsy, attempts to use the first selected item. Returns
        a conservative unsuccessful PreviewResult if neither is available.

        Parameters
        ----------
        topic_ref : str
            The topic reference identifier to compile. If empty, uses selection.

        Returns
        -------
        PreviewResult
            The result from the preview service compilation.
        """
        ref = topic_ref or (self.selected_items[0] if self.selected_items else "")
        if not isinstance(ref, str) or not ref:
            # Construct a conservative unsuccessful preview result.
            return PreviewResult(success=False, message="No topic reference provided")

        try:
            # Prefer the canonical method if present, otherwise fall back to legacy name.
            if hasattr(self.preview_service, "compile_topic_preview"):
                return self.preview_service.compile_topic_preview(self.context, ref)  # type: ignore[attr-defined]
            else:
                return self.preview_service.compile_preview(self.context, ref)  # type: ignore[attr-defined]
        except Exception:
            # Construct a minimal unsuccessful PreviewResult; include required fields.
            return PreviewResult(success=False, content="", message="Preview compilation failed")

    def render_html_preview(self, topic_ref: str) -> PreviewResult:
        """Render an HTML preview for the provided or selected topic reference.

        If topic_ref is falsy, attempts to use the first selected item. Returns
        a conservative unsuccessful PreviewResult if neither is available.

        Parameters
        ----------
        topic_ref : str
            The topic reference identifier to render. If empty, uses selection.

        Returns
        -------
        PreviewResult
            The result from the preview service HTML rendering.
        """
        ref = topic_ref or (self.selected_items[0] if self.selected_items else "")
        if not isinstance(ref, str) or not ref:
            return PreviewResult(success=False, message="No topic reference provided")

        try:
            return self.preview_service.render_html_preview(self.context, ref)
        except Exception:
            return PreviewResult(success=False, message="HTML rendering failed")