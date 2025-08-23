from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set


class TreeRefreshCoordinator:
    """Populate and refresh the structure tree from controller state.

    Responsibilities:
    - Preserve and restore expansion state
    - Respect heading style exclusions
    - Repopulate tree from controller context/max_depth
    - Re-apply selection and enable/disable toolbar heuristically
    - Optionally untoggle excluded styles in an attached filter panel
    """

    def __init__(
        self,
        *,
        controller_getter: Callable[[], object],
        tree: object,
        toolbar: object,
        get_filter_panel: Callable[[], Optional[object]] | None = None,
    ) -> None:
        self._get_controller = controller_getter
        self._tree = tree
        self._toolbar = toolbar
        self._get_filter_panel = get_filter_panel or (lambda: None)

    def refresh(self) -> None:
        ctrl = self._get_controller()
        tree = self._tree
        if ctrl is None or not hasattr(ctrl, "context") or getattr(ctrl, "context", None) is None:
            try:
                tree.clear()
                self._toolbar.enable_buttons(False)
            except Exception:
                pass
            return

        # Capture expansion state
        try:
            expanded_refs: Set[str] = set(tree.get_expanded_items())
        except Exception:
            expanded_refs = set()
        try:
            expanded_sections: List[List[int]] = (
                tree.get_expanded_section_index_paths()  # type: ignore[attr-defined]
                if hasattr(tree, "get_expanded_section_index_paths")
                else []
            )
        except Exception:
            expanded_sections = []

        # Apply exclusions on the tree before population
        try:
            exclusions = dict(getattr(ctrl, "heading_filter_exclusions", {}) or {})
            if hasattr(tree, "set_style_exclusions"):
                tree.set_style_exclusions(exclusions)  # type: ignore[attr-defined]
        except Exception:
            pass

        # Populate
        try:
            tree.populate_tree(ctrl.context, max_depth=getattr(ctrl, "max_depth", 999))
        except Exception:
            try:
                tree.clear()
            except Exception:
                pass
            return

        # Untoggle excluded styles in filter panel if needed
        try:
            panel = self._get_filter_panel() if callable(self._get_filter_panel) else None
            if panel is not None:
                exclusions = dict(getattr(ctrl, "heading_filter_exclusions", {}) or {})
                excluded_styles = [k for k, v in exclusions.items() if v]
                try:
                    current_visibility = panel.get_visible_styles()  # type: ignore[attr-defined]
                except Exception:
                    current_visibility = {}
                for style in excluded_styles:
                    try:
                        if current_visibility.get(style, False):
                            panel.toggle_style_visibility(style, False)  # type: ignore[attr-defined]
                    except Exception:
                        continue
        except Exception:
            pass

        # Restore expansion state directly 
        try:
            if expanded_sections and hasattr(tree, "restore_expanded_sections"):
                tree.restore_expanded_sections(expanded_sections)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            if expanded_refs:
                tree.restore_expanded_items(expanded_refs)
        except Exception:
            pass

        # Re-apply selection and enable toolbar
        try:
            selection = list(getattr(ctrl, "get_selection", lambda: [])())
            try:
                tree.update_selection(selection)
            except Exception:
                pass
            try:
                self._toolbar.enable_buttons(bool(selection))
            except Exception:
                pass
        except Exception:
            try:
                self._toolbar.enable_buttons(False)
            except Exception:
                pass


