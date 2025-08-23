from __future__ import annotations

from typing import Callable, Optional


class RightPanelCoordinator:
    """Coordinate right-side panel visibility (preview | filter | none).

    This orchestrates grid/show logic for the preview and heading filter panels,
    delegates sash management to a PanedLayoutCoordinator, and calls a
    FilterCoordinator to populate the panel when needed.

    Parameters
    ----------
    set_toggle_states : Callable[[bool, bool], None]
        Callback to update visual state of the two toggle buttons
        (preview_active, filter_active).
    update_legend : Callable[[], None]
        Callback to refresh the `StyleLegend` widget after changes.
    create_filter_panel : Callable[[], object]
        Factory returning a HeadingFilterPanel instance.
    paned_layout : object
        PanedLayoutCoordinator instance.
    preview_panel : object
        PreviewPanel instance to show/hide.
    preview_container : object
        Parent container where the filter panel should be created.
    filter_coordinator : object
        FilterCoordinator instance.
    tree : object
        Structure tree widget (used for clearing filter highlights).
    """

    def __init__(
        self,
        *,
        set_toggle_states: Callable[[bool, bool], None],
        update_legend: Callable[[], None],
        create_filter_panel: Callable[[], object],
        paned_layout: object,
        preview_panel: object,
        preview_container: object,
        filter_coordinator: object,
        tree: object,
    ) -> None:
        self._set_toggles = set_toggle_states
        self._update_legend = update_legend
        self._create_filter_panel = create_filter_panel
        self._paned_layout = paned_layout
        self._preview_panel = preview_panel
        self._container = preview_container
        self._filter_coord = filter_coordinator
        self._tree = tree
        self._filter_panel: Optional[object] = None
        self._kind: str = "preview"

    # ------------------------------------------------------------------
    def set_active(self, kind: str) -> None:
        """Switch active right panel between 'preview', 'filter', or 'none'."""
        if kind == "none":
            self._hide_all()
            self._set_toggles(False, False)
            self._kind = "none"
            return

        if kind == "preview":
            # Hide filter, show preview and restore preview sash
            self._ensure_pane_present()
            try:
                if self._filter_panel is not None:
                    self._filter_panel.grid_remove()
            except Exception:
                pass
            try:
                self._preview_panel.grid()
            except Exception:
                pass
            try:
                if hasattr(self._tree, 'clear_filter_highlight_refs'):
                    self._tree.clear_filter_highlight_refs()  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                self._paned_layout.set_kind("preview")
            except Exception:
                pass
            self._set_toggles(True, False)
            self._kind = "preview"
            try:
                self._update_legend()
            except Exception:
                pass
            return

        # kind == 'filter'
        self._ensure_pane_present()
        # Ensure filter panel exists
        if self._filter_panel is None:
            try:
                self._filter_panel = self._create_filter_panel()
                # Allow FilterCoordinator to know the panel
                try:
                    if hasattr(self._filter_coord, 'set_panel'):
                        self._filter_coord.set_panel(self._filter_panel)  # type: ignore[attr-defined]
                except Exception:
                    pass
            except Exception:
                self._filter_panel = None
        # Show filter, hide preview
        try:
            if self._filter_panel is not None:
                self._filter_panel.grid(row=0, column=0, sticky="nsew")
        except Exception:
            pass
        try:
            self._preview_panel.grid_remove()
        except Exception:
            pass
        try:
            self._paned_layout.set_kind("filter")
        except Exception:
            pass
        # Populate panel data and update legend
        try:
            self._filter_coord.populate()
        except Exception:
            pass
        try:
            self._update_legend()
        except Exception:
            pass
        self._set_toggles(False, True)
        self._kind = "filter"

    # ------------------------------------------------------------------
    def kind(self) -> str:
        return self._kind

    def get_filter_panel(self) -> Optional[object]:
        return self._filter_panel

    def select_style(self, style: str) -> None:
        if not isinstance(style, str) or not style:
            return
        # Ensure filter panel is visible
        self.set_active("filter")
        try:
            panel = self._filter_panel
            if panel is not None and hasattr(panel, 'select_style'):
                panel.select_style(style)  # type: ignore[attr-defined]
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _hide_all(self) -> None:
        try:
            if self._filter_panel is not None:
                try:
                    if hasattr(self._filter_panel, 'clear_selection'):
                        self._filter_panel.clear_selection()
                except Exception:
                    pass
                try:
                    self._filter_panel.grid_remove()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._preview_panel.grid_remove()
        except Exception:
            pass
        try:
            self._paned_layout.set_kind("none")
        except Exception:
            pass
        try:
            if hasattr(self._tree, 'clear_filter_highlight_refs'):
                self._tree.clear_filter_highlight_refs()  # type: ignore[attr-defined]
        except Exception:
            pass

    def _ensure_pane_present(self) -> None:
        try:
            self._paned_layout.set_kind(self._kind or "preview")
        except Exception:
            pass


