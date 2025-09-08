from __future__ import annotations

from typing import Callable, Dict, List, Optional


class FilterCoordinator:
    """Coordinate heading filter panel with controller and tree.

    Parameters
    ----------
    controller_getter : Callable[[], object]
        Zero-arg callable returning controller.
    panel : object
        HeadingFilterPanel-like with set_data, update_status, update_style_colors, clear_selection.
    tree : object
        Structure tree with set_style_visibility, update_style_colors, clear_filter_highlight_refs.
    """

    def __init__(
        self,
        *,
        controller_getter: Callable[[], object],
        panel: object,
        tree: object,
    ) -> None:
        self._get_controller = controller_getter
        self._panel = panel
        self._tree = tree

    def set_panel(self, panel: object) -> None:
        """Allow late injection of the filter panel instance."""
        self._panel = panel

    def populate(self) -> None:
        ctrl = self._get_controller()
        panel = self._panel
        try:
            if ctrl is None or panel is None:
                return
            headings_cache = ctrl.get_heading_counts()
            occurrences_map = ctrl.get_heading_occurrences()
            style_levels = ctrl.get_style_levels()
            current = dict(getattr(ctrl, "filter_exclusions", {}) or {})
            panel.set_data(headings_cache, occurrences_map, style_levels, current)
            # Initialize style colors/visibility
            style_colors = ctrl.get_style_colors()
            style_visibility = ctrl.get_style_visibility()
            self._tree.update_style_colors(style_colors)
            self._tree.set_style_visibility(style_visibility)
            try:
                if hasattr(panel, 'update_style_colors'):
                    panel.update_style_colors(style_colors)
            except Exception:
                pass
        except Exception:
            pass

    def apply(self, exclusions: Dict[str, bool]) -> Optional[object]:
        ctrl = self._get_controller()
        if ctrl is None:
            return None
        try:
            ctrl.filter_exclusions = dict(exclusions or {})
            style_excl_map = ctrl.build_style_exclusion_map_from_flags(exclusions)
            return ctrl.handle_apply_filters(style_excl_map or None)
        except Exception:
            return None

    def toggle_style_visibility(self, style: str, visible: bool) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            ctrl.handle_style_visibility_toggle(style, visible)
            style_visibility = ctrl.get_style_visibility()
            style_colors = ctrl.get_style_colors()
            self._tree.set_style_visibility(style_visibility)
            self._tree.update_style_colors(style_colors)
            try:
                if hasattr(self._panel, 'update_style_colors'):
                    self._panel.update_style_colors(style_colors)
            except Exception:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    def apply_with_ui(
        self,
        exclusions: Dict[str, bool],
        *,
        run_in_thread: Callable[[Callable[[], object], Optional[Callable[[object], None]]], None],
        set_busy: Callable[[bool], None],
        refresh_tree: Callable[[], None],
        get_current_selection: Callable[[], list],
        predict_target: Callable[[object], Optional[object]],
    ) -> None:
        ctrl = self._get_controller()
        panel = self._panel
        tree = self._tree
        if ctrl is None:
            return
        try:
            ctrl.filter_exclusions = dict(exclusions or {})
            style_excl_map = ctrl.build_style_exclusion_map_from_flags(exclusions)
        except Exception:
            style_excl_map = None

        # Pre-calc selection and predicted target
        original_nodes: list = []
        original_ref: str = ""
        predicted_node: Optional[object] = None
        try:
            sel = list(get_current_selection() or [])
            # Prefer XML nodes
            if sel and hasattr(sel[0], 'tag'):
                original_nodes = sel
                try:
                    predicted_node = predict_target(sel[0])
                except Exception:
                    predicted_node = None
            else:
                # Legacy refs fallback
                if sel:
                    original_ref = sel[0]
        except Exception:
            pass

        # Inform user about potential unmergable items
        try:
            unmergable = ctrl.estimate_unmergable(style_excl_map)
            if unmergable > 0 and panel is not None:
                plural = "s" if unmergable > 1 else ""
                panel.update_status(f"Unable to filter: {unmergable} topic{plural} doesn't have parent to merge")  # type: ignore[attr-defined]
        except Exception:
            pass

        def _work():
            try:
                return ctrl.handle_apply_filters(style_excl_map or None)  # type: ignore[attr-defined]
            except Exception:
                return None

        def _done(res):
            try:
                if not (getattr(res, "success", False)):
                    try:
                        if panel is not None:
                            panel.update_status("Failed to apply heading filter")  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    return
                # Refresh tree and restore/center selection
                refresh_tree()
                try:
                    if original_nodes and hasattr(tree, 'update_selection_by_xml_nodes'):
                        tree.update_selection_by_xml_nodes(original_nodes)  # type: ignore[attr-defined]
                        try:
                            tree.focus_item_centered(original_nodes[0])  # type: ignore[attr-defined]
                        except Exception:
                            pass
                    elif original_ref:
                        try:
                            if hasattr(tree, 'focus_item_centered_by_ref'):
                                tree.focus_item_centered_by_ref(original_ref)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if panel is not None:
                        panel.update_status("Filters applied")  # type: ignore[attr-defined]
                except Exception:
                    pass
            finally:
                try:
                    set_busy(False)
                except Exception:
                    pass

        try:
            set_busy(True)
        except Exception:
            pass
        run_in_thread(_work, _done)


