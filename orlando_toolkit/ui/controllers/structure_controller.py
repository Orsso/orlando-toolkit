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
        if not isinstance(new_depth, int):
            return False
        clamped = max(1, new_depth)
        if clamped != self.max_depth:
            self.max_depth = clamped
            return True
        return False

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

        if not self.search_term:
            return self.search_results

        # Conservative search: try to iterate context topics if available.
        try:
            # Heuristic: DitaContext might expose collections of topics/refs.
            # We'll try broadly-named attributes and filter by simple text match.
            candidates: List[str] = []

            # Common possible attributes we might find on a context model
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
                        # If dict-like {id: obj/title}, collect keys
                        candidates.extend(list(value.keys()))
                    elif isinstance(value, list):
                        # If list of ids/objects, try to normalize to ids/strings
                        for entry in value:
                            if isinstance(entry, str):
                                candidates.append(entry)
                            else:
                                # Attempt to pull an identifier-like attribute
                                for id_attr in ["id", "ref", "topic_ref", "uid"]:
                                    if hasattr(entry, id_attr):
                                        ref_val = getattr(entry, id_attr)
                                        if isinstance(ref_val, str):
                                            candidates.append(ref_val)
                                            break

            # Deduplicate candidates
            seen: Dict[str, bool] = {}
            unique_candidates = []
            for c in candidates:
                if c not in seen:
                    seen[c] = True
                    unique_candidates.append(c)

            # Filter by simple substring match on identifier
            term_lower = self.search_term.lower()
            self.search_results = [c for c in unique_candidates if term_lower in c.lower()]

        except Exception:
            # Remain conservative and non-raising
            self.search_results = []

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
            # Delegate to the canonical service method; an alias exists for stability.
            return self.preview_service.compile_topic_preview(self.context, ref)
        except Exception:
            return PreviewResult(success=False, message="Preview compilation failed")

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