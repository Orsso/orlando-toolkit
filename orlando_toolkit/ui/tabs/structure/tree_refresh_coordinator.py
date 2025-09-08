from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set


class TreeRefreshCoordinator:
    """Populate and refresh the structure tree from controller state.

    Responsibilities:
    - Preserve and restore expansion state
    - Respect plugin-defined filter exclusions
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
        set_busy: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self._get_controller = controller_getter
        self._tree = tree
        self._toolbar = toolbar
        self._get_filter_panel = get_filter_panel or (lambda: None)
        self._set_busy = set_busy or (lambda _b: None)

    def refresh(self) -> None:
        # Wrap in optional busy indicator
        try:
            self._set_busy(True)
        except Exception:
            pass
        ctrl = self._get_controller()
        tree = self._tree
        if ctrl is None or not hasattr(ctrl, "context") or getattr(ctrl, "context", None) is None:
            try:
                tree.clear()
                self._toolbar.enable_buttons(False)
            except Exception:
                pass
            return

        # Capture expansion state (XML-node based) and current scroll position
        try:
            expanded_nodes: List[object] = list(tree.get_expanded_xml_nodes())  # type: ignore[attr-defined]
        except Exception:
            expanded_nodes = []
        # Capture yview to reduce flashing/jumps during full refresh
        try:
            y_first, _y_last = tree._tree.yview()  # type: ignore[attr-defined]
            yview_snapshot = float(y_first)
        except Exception:
            yview_snapshot = None

        # Capture current selection before rebuilding tree
        selected_elements = []
        try:
            selected_elements = tree.capture_current_selection()
        except Exception:
            pass

        # Apply exclusions on the tree before population
        try:
            exclusions = dict(getattr(ctrl, "filter_exclusions", {}) or {})
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
                exclusions = dict(getattr(ctrl, "filter_exclusions", {}) or {})
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

        # Restore expansion state directly (XML-node based)
        try:
            if expanded_nodes and hasattr(tree, "restore_expanded_xml_nodes"):
                tree.restore_expanded_xml_nodes(expanded_nodes)  # type: ignore[attr-defined]
        except Exception:
            pass

        # Restore scroll position to reduce flashing/jumps
        try:
            if yview_snapshot is not None:
                tree._tree.yview_moveto(yview_snapshot)  # type: ignore[attr-defined]
        except Exception:
            pass

        # Re-apply selection and enable toolbar
        try:
            # Restore captured selection
            if selected_elements:
                tree.restore_captured_selection(selected_elements)
            
            # Enable toolbar based on current selection
            current_selection = tree.get_selected_xml_nodes()
            try:
                self._toolbar.enable_buttons(bool(current_selection))
            except Exception:
                pass
        except Exception:
            try:
                self._toolbar.enable_buttons(False)
            except Exception:
                pass
        finally:
            try:
                self._set_busy(False)
            except Exception:
                pass


