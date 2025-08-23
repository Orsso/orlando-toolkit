from __future__ import annotations

from typing import Callable, List, Optional


class SearchCoordinator:
    """Coordinate search interactions between UI tree, controller, and preview."""

    def __init__(
        self,
        *,
        controller_getter: Callable[[], object],
        tree: object,
        preview: object,
        update_legend: Callable[[], None],
    ) -> None:
        self._get_controller = controller_getter
        self._tree = tree
        self._preview = preview
        self._update_legend = update_legend

    # ------------------------------------------------------------------
    def term_changed(self, term: str) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            results: List[str] = list(ctrl.handle_search(term) or [])
        except Exception:
            results = []

        # Highlight all matches without altering selection
        try:
            if results:
                self._tree.set_highlight_refs(list(results))  # type: ignore[attr-defined]
            else:
                self._tree.clear_highlight_refs()  # type: ignore[attr-defined]
        except Exception:
            pass

        # Focus and preview first match
        if results:
            try:
                self._tree.focus_item_centered_by_ref(results[0])  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                if self._preview is not None and hasattr(self._preview, 'render_for_ref'):
                    self._preview.render_for_ref(results[0])  # type: ignore[attr-defined]
            except Exception:
                pass

        # Update legend
        try:
            self._update_legend()
        except Exception:
            pass

    # ------------------------------------------------------------------
    def navigate(self, direction: str) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            results: List[str] = list(getattr(ctrl, "search_results", []) or [])
        except Exception:
            results = []
        if not results:
            return
        try:
            idx = getattr(ctrl, "search_index", -1)
        except Exception:
            idx = -1
        idx = max(0, idx - 1) if direction == "prev" else min(len(results) - 1, idx + 1)
        try:
            ctrl.search_index = idx  # type: ignore[attr-defined]
        except Exception:
            pass
        # Select current match, update tree/preview
        try:
            ctrl.select_items([results[idx]])
        except Exception:
            pass
        try:
            self._tree.update_selection([results[idx]])  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self._tree.focus_item_centered_by_ref(results[idx])  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            if self._preview is not None and hasattr(self._preview, 'render_for_ref'):
                self._preview.render_for_ref(results[idx])  # type: ignore[attr-defined]
        except Exception:
            pass


