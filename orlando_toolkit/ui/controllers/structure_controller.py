from typing import List, Dict, Literal, Optional

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.services.structure_editing_service import (
    StructureEditingService,
    OperationResult,
)
from orlando_toolkit.core.services.undo_service import UndoService
from orlando_toolkit.core.services.preview_service import PreviewService, PreviewResult


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
        try:
            self.undo_service.push_snapshot(self.context)
        except Exception:
            # If a logger exists, warn; otherwise continue silently.
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

        # Push snapshot prior to mutation to enable undo, per spec.
        snapshot_failed = False
        try:
            self.undo_service.push_snapshot(self.context)
        except Exception:
            # Be conservative: if snapshot fails, still attempt the move but
            # track the failure to include in the result message.
            snapshot_failed = True

        try:
            result = self.editing_service.move_topic(self.context, first_ref, direction)
            
            # If snapshot failed, modify the result message to inform the user
            if snapshot_failed and result.success:
                warning_msg = "Warning: Undo snapshot failed - undo may not be available for this operation."
                if result.message:
                    result.message = f"{result.message} {warning_msg}"
                else:
                    result.message = warning_msg
                    
            return result
        except Exception:
            # Non-raising for routine errors: return an unsuccessful result.
            return OperationResult(success=False, message="Move operation failed")

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