# -*- coding: utf-8 -*-
"""StructureTab presentation layer.

This refactor transforms StructureTab into a thin UI composition class that
wires widgets to the StructureController and delegates all business logic to
services via the controller. It strictly avoids direct XML manipulation, undo/redo
stack management in the UI, and any file or console I/O.

Layout:
- Vertical layout:
  - Toolbar (top)
  - Search widget (below)
  - Tree widget (main area)

Responsibilities:
- Dependency injection of services or construction from a provided DitaContext.
- Wiring widget callbacks to controller methods.
- Keeping selection and simple button enablement heuristic in sync.
- Providing keyboard shortcuts that delegate to controller.
- Tree refresh helper that repopulates from controller state.

Notes:
- This presentation class is intentionally conservative. If behavior or attributes
  are unknown, we prefer a no-op and leave TODOs rather than embedding business logic.
- The class name and public entry points remain compatible for external callers.

"""

from __future__ import annotations

from typing import Optional, List
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

# Required imports per specification
from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
from orlando_toolkit.core.services.undo_service import UndoService
from orlando_toolkit.core.services.preview_service import PreviewService
from orlando_toolkit.ui.controllers.structure_controller import StructureController
from orlando_toolkit.ui.widgets.structure_tree import StructureTreeWidget
from orlando_toolkit.ui.widgets.search_widget import SearchWidget
from orlando_toolkit.ui.widgets.toolbar_widget import ToolbarWidget
from orlando_toolkit.ui.dialogs.heading_filter_dialog import HeadingFilterDialog
from orlando_toolkit.ui.dialogs.context_menu import ContextMenuHandler


__all__ = ["StructureTab"]


class StructureTab(ttk.Frame):
    """Presentation-focused structure tab.

    This class composes toolbar, search, and tree widgets, and wires them to a
    StructureController. All operations and business logic are delegated to the
    controller and its services.

    Parameters
    ----------
    parent : tk.Widget
        Parent container widget.
    context : Optional[DitaContext], optional
        A DitaContext instance for this tab. If provided, the tab constructs
        default services and controller as specified, by default None.
    controller : Optional[StructureController], optional
        An externally constructed controller instance. If provided, it takes
        precedence over `context` construction path, by default None.

    Other Parameters
    ----------------
    editing_service : Optional[StructureEditingService]
        Optional injected editing service. Used only when `controller` is not provided.
    undo_service : Optional[UndoService]
        Optional injected undo service. Used only when `controller` is not provided.
    preview_service : Optional[PreviewService]
        Optional injected preview service. Used only when `controller` is not provided.

    Notes
    -----
    - If a DitaContext is passed (and no controller), the following are set up:
        editing_service = StructureEditingService()
        undo_service = UndoService(max_history=50)
        preview_service = PreviewService()
        controller = StructureController(context, editing_service, undo_service, preview_service)
      The resulting controller is stored on self._controller.
    - If neither `controller` nor `context` is provided, the tab will be initialized
      without a controller; most actions will be no-ops until `attach_controller` is called.
    """

    def __init__(
        self,
        parent: "tk.Widget",
        *,
        context: Optional[DitaContext] = None,
        controller: Optional[StructureController] = None,
        editing_service: Optional[StructureEditingService] = None,
        undo_service: Optional[UndoService] = None,
        preview_service: Optional[PreviewService] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)

        # Controller setup (dependency injection)
        if controller is not None:
            self._controller: Optional[StructureController] = controller
        elif context is not None:
            editing_service = editing_service or StructureEditingService()
            undo_service = undo_service or UndoService(max_history=50)
            preview_service = preview_service or PreviewService()
            self._controller = StructureController(
                context, editing_service, undo_service, preview_service
            )
        else:
            self._controller = None  # Will need attach_controller before use.

        # UI Composition
        # Root vertical layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Toolbar
        self._toolbar = ToolbarWidget(self, on_move=self._on_toolbar_move_clicked)
        self._toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        # Search widget row (contains search and heading filter button)
        search_row = ttk.Frame(self)
        search_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        search_row.columnconfigure(0, weight=1)

        self._search = SearchWidget(
            search_row,
            on_term_changed=self._on_search_term_changed,
            on_navigate=self._on_search_navigate,
        )
        self._search.grid(row=0, column=0, sticky="ew")

        self._heading_filter_btn = ttk.Button(
            search_row, text="Heading filters…", command=self._on_heading_filters_clicked
        )
        self._heading_filter_btn.grid(row=0, column=1, padx=(8, 0))

        # Depth control (Label + Spinbox) placed alongside existing toolbar/search widgets
        try:
            # Default depth is 3, controller will be synced later
            self._depth_var = tk.IntVar(value=3)

            # Small container to align neatly in the same row
            depth_container = ttk.Frame(search_row)
            depth_container.grid(row=0, column=2, padx=(12, 0), sticky="e")

            depth_label = ttk.Label(depth_container, text="Depth")
            depth_label.grid(row=0, column=0, sticky="w")

            self._depth_spin = ttk.Spinbox(
                depth_container,
                from_=1,
                to=999,
                textvariable=self._depth_var,
                width=4,
                command=self._on_depth_changed,
                wrap=False,
            )
            self._depth_spin.grid(row=0, column=1, padx=(6, 0))

            # Bind Return (Enter) and focus-out to commit manual edits
            try:
                self._depth_spin.bind("<Return>", lambda e: self._on_depth_changed())
                self._depth_spin.bind("<FocusOut>", lambda e: self._on_depth_changed())
            except Exception:
                pass
        except Exception:
            # Non-fatal if depth control cannot be created
            pass

        # Add expand/collapse buttons next to Depth
        try:
            self._expand_all_btn = ttk.Button(
                depth_container, text="⊞", width=3, command=self._on_expand_all
            )
            self._expand_all_btn.grid(row=0, column=2, padx=(8, 2))
            # Add tooltip-style hint via balloon help simulation
            try:
                # Store tooltip text in button for potential future tooltip system
                self._expand_all_btn.tooltip_text = "Expand all items"
            except Exception:
                pass
            
            self._collapse_all_btn = ttk.Button(
                depth_container, text="⊟", width=3, command=self._on_collapse_all
            )
            self._collapse_all_btn.grid(row=0, column=3, padx=(2, 8))
            try:
                self._collapse_all_btn.tooltip_text = "Collapse all items"
            except Exception:
                pass
        except Exception:
            self._expand_all_btn = None  # type: ignore[assignment]
            self._collapse_all_btn = None  # type: ignore[assignment]

        # Add show/hide preview toggle button next to expand/collapse buttons
        try:
            self._preview_visible = True
            self._preview_toggle_btn = ttk.Button(
                depth_container, text="Hide Preview", command=self._on_toggle_preview
            )
            self._preview_toggle_btn.grid(row=0, column=4, padx=(8, 0))
        except Exception:
            self._preview_toggle_btn = None  # type: ignore[assignment]

        # Main area: PanedWindow with tree (left) and preview panel (right)
        self._paned = ttk.PanedWindow(self, orient="horizontal")
        self._paned.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

        left = ttk.Frame(self._paned)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        right = ttk.Frame(self._paned)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        # Make preview panel about ~15% narrower than before by adjusting weights
        # Old: left=3, right=2 (40% preview). New: left=4, right=2 (~33% preview)
        self._paned.add(left, weight=4)
        self._paned.add(right, weight=2)
        # Prevent zero-width panes by setting a reasonable minimum size for the preview pane
        try:
            self._paned.paneconfigure(right, minsize=150)
        except Exception:
            pass

        # Keep handles to panes so we can properly hide/show the preview pane
        self._left_pane = left  # type: ignore[assignment]
        self._right_pane = right  # type: ignore[assignment]
        # Store sash position as a fraction of total width for robust restoration
        self._last_sash_ratio = 0.67  # type: ignore[assignment]

        # Tree widget on the left
        self._tree = StructureTreeWidget(
            left,
            on_selection_changed=self._on_tree_selection_changed,
            on_item_activated=self._on_tree_item_activated,
            on_context_menu=self._on_tree_context_menu,
        )
        self._tree.grid(row=0, column=0, sticky="nsew")

        # Preview panel on the right
        from orlando_toolkit.ui.widgets.preview_panel import PreviewPanel  # local import to avoid cycles

        self._preview_panel = PreviewPanel(
            right,
            on_mode_changed=self._on_preview_mode_changed,
        )
        self._preview_panel.grid(row=0, column=0, sticky="nsew")

        # Context menu handler wired to StructureTab callbacks
        self._ctx_menu = ContextMenuHandler(
            self,
            on_open=self._ctx_open,
            on_merge=self._ctx_merge,
            on_rename=self._ctx_rename,
            on_delete=self._ctx_delete,
        )

        # Keyboard shortcuts (non-invasive)
        self.bind("<Control-z>", self._on_shortcut_undo)
        self.bind("<Control-y>", self._on_shortcut_redo)
        self.bind("<Alt-Up>",   lambda e: self._on_shortcut_move("up"))
        self.bind("<Alt-Down>", lambda e: self._on_shortcut_move("down"))
        self.bind("<Alt-Left>", lambda e: self._on_shortcut_move("promote"))
        self.bind("<Alt-Right>",lambda e: self._on_shortcut_move("demote"))
        # Ensure this widget can receive keyboard focus
        self.focus_set()
        # Initial population
        self._refresh_tree()
        # Set initial sash position (~67% left / 33% right)
        try:
            self.after(0, self._set_initial_sash_position)
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Public API shims to preserve external expectations (conservative, presentation-only)
    # ---------------------------------------------------------------------------------

    def load_context(self, context: DitaContext) -> None:
        """Accept a new context by reconstructing controller dependencies.

        Parameters
        ----------
        context : DitaContext
            New context to use for this tab. Constructs default services and a
            new StructureController as specified, stores it as self._controller,
            then refreshes the tree.
        """
        editing_service = StructureEditingService()
        undo_service = UndoService(max_history=50)
        preview_service = PreviewService()
        self._controller = StructureController(context, editing_service, undo_service, preview_service)
        self._sync_depth_control()
        self._refresh_tree()

    def attach_controller(self, controller: StructureController) -> None:
        """Attach an externally created controller and refresh the UI."""
        self._controller = controller
        self._sync_depth_control()
        self._refresh_tree()
    
    def _sync_depth_control(self) -> None:
        """Apply the default depth (3) to the controller and sync the display."""
        if not hasattr(self, "_depth_var") or self._controller is None:
            return
        try:
            # Apply default depth of 3 to controller
            if hasattr(self._controller, "handle_depth_change"):
                self._controller.handle_depth_change(3)
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------------

    def _refresh_tree(self) -> None:
        """Repopulate the tree from controller state and re-apply selection.

        Behavior:
        - If no controller/context is available, clears the tree and disables toolbar.
        - Otherwise repopulates the tree with controller.context and controller.max_depth.
        - Re-applies selection from controller.get_selection() where possible.
        - Preserves expansion state of tree items during refresh.
        - Enables toolbar based on non-empty selection heuristic.
        """
        ctrl = self._controller
        if ctrl is None or not hasattr(ctrl, "context") or ctrl.context is None:
            try:
                self._tree.clear()
                self._toolbar.enable_buttons(False)
            except Exception:
                pass
            return

        # Preserve expansion state before refresh
        expanded_refs = set()
        try:
            expanded_refs = self._tree.get_expanded_items()
        except Exception:
            pass

        try:
            # Apply current heading exclusions from controller before population
            try:
                exclusions = dict(getattr(ctrl, "heading_filter_exclusions", {}) or {})
                if hasattr(self._tree, "set_style_exclusions"):
                    self._tree.set_style_exclusions(exclusions)  # type: ignore[attr-defined]
            except Exception:
                pass

            self._tree.populate_tree(ctrl.context, max_depth=getattr(ctrl, "max_depth", 999))
            
            # Restore expansion state after population, or expand all if no previous state
            try:
                if expanded_refs:
                    self._tree.restore_expanded_items(expanded_refs)
                else:
                    # No previous expansion state, keep the default expansion from populate_tree
                    pass
            except Exception:
                pass
        except Exception:
            # Presentation layer should remain robust; on failure just clear and continue.
            try:
                self._tree.clear()
            except Exception:
                pass

        # Re-apply selection
        try:
            current_selection = ctrl.get_selection()
            self._tree.update_selection(current_selection)
        except Exception:
            pass

        # Enable toolbar if selection non-empty
        try:
            enabled = len(ctrl.get_selection()) > 0
            self._toolbar.enable_buttons(enabled)
        except Exception:
            self._toolbar.enable_buttons(False)

    def _set_initial_sash_position(self) -> None:
        """Position the paned window sash so the preview takes ~33% width."""
        try:
            paned = getattr(self, "_paned", None)
            if paned is None:
                return
            width = paned.winfo_width()
            # If geometry not ready yet, retry shortly
            if width <= 1:
                self.after(50, self._set_initial_sash_position)
                return
            pos = int(width * 0.67)
            try:
                paned.sashpos(0, pos)
                try:
                    self._last_sash_ratio = max(0.05, min(0.95, pos / max(1, width)))  # type: ignore[assignment]
                except Exception:
                    pass
            except Exception:
                # Some Tk variants may not support sashpos right away; retry once
                self.after(50, self._set_initial_sash_position)
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Tree expansion control callbacks
    # ---------------------------------------------------------------------------------

    def _on_expand_all(self) -> None:
        """Handle expand all button click."""
        try:
            self._tree.expand_all()
        except Exception:
            pass

    def _on_collapse_all(self) -> None:
        """Handle collapse all button click."""
        try:
            self._tree.collapse_all()
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Depth control callback
    # ---------------------------------------------------------------------------------

    def _on_depth_changed(self) -> None:
        """Handle user changes to the 'Depth' spinbox.

        Reads the value, clamps it to [1, 999], updates the spinbox if normalized,
        delegates to controller.handle_depth_change, and repopulates tree while preserving expansion.
        """
        # Ensure var exists and controller is present
        if not hasattr(self, "_depth_var"):
            return
        ctrl = self._controller
        if ctrl is None:
            return

        try:
            # Read and clamp
            val = int(self._depth_var.get())
        except Exception:
            val = getattr(ctrl, "max_depth", 999)

        # Clamp to sensible bounds
        if val < 1:
            val = 1
        elif val > 999:
            val = 999

        # Normalize UI value if needed
        try:
            if int(self._depth_var.get()) != val:
                self._depth_var.set(val)
        except Exception:
            try:
                self._depth_var.set(val)
            except Exception:
                pass

        # Delegate to controller and refresh tree
        try:
            changed = False
            if hasattr(ctrl, "handle_depth_change"):
                changed = bool(ctrl.handle_depth_change(val))
            if changed:
                self._refresh_tree()
                # Keep preview in sync when depth affects rendering
                try:
                    self._update_side_preview()
                except Exception:
                    pass
        except Exception:
            # Keep UI stable; ignore errors
            pass

    # ---------------------------------------------------------------------------------
    # Toolbar callbacks
    # ---------------------------------------------------------------------------------

    def _on_toolbar_move_clicked(self, direction: str) -> None:
        """Handle move operations from the toolbar and refresh tree."""
        ctrl = self._controller
        if ctrl is None:
            return
        try:
            result = ctrl.handle_move_operation(direction)  # returns OperationResult
            if getattr(result, "success", False):
                # After successful move, refresh tree and keep selection
                self._refresh_tree()
            else:
                # No popup/I-O; presentation only. Keep UI stable.
                pass
        except Exception:
            # Swallow to protect Tk mainloop
            pass

    # ---------------------------------------------------------------------------------
    # Search callbacks
    # ---------------------------------------------------------------------------------

    def _on_search_term_changed(self, term: str) -> None:
        """Handle search term changes by delegating to the controller and selecting first match."""
        ctrl = self._controller
        if ctrl is None:
            return
        try:
            results = ctrl.handle_search(term) or []
            # Apply yellow highlight to all matches without changing selection
            try:
                if results:
                    self._tree.set_highlight_refs(list(results))  # type: ignore[attr-defined]
                else:
                    self._tree.clear_highlight_refs()  # type: ignore[attr-defined]
            except Exception:
                pass
            # Focus and preview first match when available (no selection change)
            if results:
                try:
                    self._tree.focus_item_by_ref(results[0])  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    self._render_preview_for_ref(results[0], self._preview_panel)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_search_navigate(self, direction: "str") -> None:
        """Navigate among stored search results and update selection."""
        ctrl = self._controller
        if ctrl is None:
            return
        try:
            results: List[str] = list(getattr(ctrl, "search_results", []) or [])
            if not results:
                return
            # Cycle using controller's search_index
            idx = getattr(ctrl, "search_index", -1)
            if direction == "prev":
                # Move up if possible; clamp at 0
                idx = max(0, idx - 1)
            else:
                # Move down if possible; clamp at last
                idx = min(len(results) - 1, idx + 1)
            try:
                ctrl.search_index = idx  # type: ignore[attr-defined]
            except Exception:
                pass
            # Keep all matches highlighted; select the current item to show default selection highlight
            try:
                ctrl.select_items([results[idx]])
            except Exception:
                pass
            self._refresh_tree()
            try:
                self._tree.set_highlight_refs(list(results))  # type: ignore[attr-defined]
            except Exception:
                pass
            # Trigger preview update for the focused match across sections/levels
            try:
                self._render_preview_for_ref(results[idx], self._preview_panel)
            except Exception:
                pass
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Tree callbacks
    # ---------------------------------------------------------------------------------

    def _render_preview_for_ref(self, topic_ref: str, panel: object) -> None:
        """Common helper for rendering preview content in a panel.
        
        Handles mode detection, loading state management, rendering, and error handling.
        
        Parameters
        ----------
        topic_ref : str
            The topic reference to render preview for.
        panel : object
            The preview panel to render content into.
        """
        ctrl = self._controller
        if ctrl is None:
            return

        # Determine current mode and render accordingly
        try:
            mode = panel.get_mode()
        except Exception:
            mode = "html"

        # Set loading/title
        try:
            panel.set_title(f"Preview — {topic_ref or 'Untitled'}")
            panel.set_loading(True)
        except Exception:
            pass

        try:
            if mode == "xml":
                res = ctrl.compile_preview(topic_ref)
            else:
                res = ctrl.render_html_preview(topic_ref)
        except Exception as ex:
            try:
                panel.show_error(f"Preview failed: {ex}")
            finally:
                try:
                    panel.set_loading(False)
                except Exception:
                    pass
            return

        try:
            if getattr(res, "success", False) and isinstance(getattr(res, "content", None), str):
                content = getattr(res, "content")
                # Ensure XML appears as preformatted when in XML mode
                if mode == "xml":
                    try:
                        from html import escape as _escape
                        content = f"<pre style=\"white-space:pre-wrap;\">{_escape(content)}</pre>"
                    except Exception:
                        pass
                panel.set_content(content)
            else:
                msg = getattr(res, "message", None) or "Unable to render preview"
                panel.show_error(str(msg))
        finally:
            try:
                panel.set_loading(False)
            except Exception:
                pass

    def _on_tree_selection_changed(self, refs: List[str]) -> None:
        """Update controller selection and toolbar enablement on selection change."""
        ctrl = self._controller
        if ctrl is None:
            return
        try:
            ctrl.select_items(refs or [])
            # Simple heuristic: enable toolbar when selection non-empty
            self._toolbar.enable_buttons(bool(refs))
        except Exception:
            self._toolbar.enable_buttons(False)

        # Debounce preview update
        try:
            if not hasattr(self, "_pending_preview_job"):
                self._pending_preview_job = None  # type: ignore[attr-defined]
            if getattr(self, "_pending_preview_job", None):
                try:
                    self.after_cancel(self._pending_preview_job)  # type: ignore[attr-defined]
                except Exception:
                    pass
            self._pending_preview_job = self.after(250, self._update_side_preview)  # type: ignore[attr-defined]
        except Exception:
            # Do not break selection behavior if after scheduling fails
            pass

    def _on_tree_item_activated(self, item_refs: Optional[object]) -> None:
        """Handle activation (double-click/Enter) on a tree item to update side preview panel.

        Accepts either a single ref (str) or list of refs; normalizes to one topic_ref.
        Routes preview rendering to the right-hand PreviewPanel according to current mode.
        """
        ctrl = self._controller
        if ctrl is None:
            return

        # Normalize incoming refs: can be str or list[str]
        topic_ref: str = ""
        try:
            if isinstance(item_refs, str):
                topic_ref = item_refs
            elif isinstance(item_refs, (list, tuple)) and item_refs:
                topic_ref = str(item_refs[0])
            else:
                topic_ref = ""
        except Exception:
            topic_ref = ""

        panel = getattr(self, "_preview_panel", None)
        if panel is None:
            return

        # Delegate to helper method
        self._render_preview_for_ref(topic_ref, panel)

    def _on_tree_context_menu(self, event: "tk.Event", refs: List[str]) -> None:
        """Ensure latest selection and show context menu."""
        try:
            current_refs = refs or self._tree.get_selected_items()
            self._ctx_menu.show_context_menu(event, current_refs)
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Context menu command handlers (wired per step 4/4)
    # ---------------------------------------------------------------------------------

    def _ctx_open(self, refs: List[str]) -> None:
        """Context menu 'Open' action -> route to side preview panel update."""
        if not refs:
            return
        try:
            self._on_tree_item_activated(refs[0])
        except Exception:
            pass

    def _ctx_rename(self, refs: List[str]) -> None:
        if len(refs) != 1:
            return
        try:
            from tkinter import simpledialog
            new_title = simpledialog.askstring("Rename topic", "New title:", parent=self)
            if not new_title:
                return
            res = self._controller.editing_service.rename_topic(self._controller.context, refs[0], new_title)  # type: ignore[attr-defined]
            if not getattr(res, "success", False):
                # Keep UI non-blocking; panel-based errors are handled elsewhere.
                return
            self._refresh_tree()
        except Exception:
            pass

    def _ctx_delete(self, refs: List[str]) -> None:
        if not refs:
            return
        try:
            res = self._controller.editing_service.delete_topics(self._controller.context, refs)  # type: ignore[attr-defined]
            if not getattr(res, "success", False):
                # Keep UI non-blocking; errors are handled elsewhere.
                return
            # Clear selection via controller and refresh
            try:
                self._controller.select_items([])  # type: ignore[attr-defined]
            except Exception:
                pass
            self._refresh_tree()
        except Exception:
            pass

    def _ctx_merge(self, refs: List[str]) -> None:
        if len(refs) < 2:
            return
        try:
            res = self._controller.editing_service.merge_topics(self._controller.context, refs)  # type: ignore[attr-defined]
            if not getattr(res, "success", False):
                # Keep UI non-blocking; errors are handled elsewhere.
                return
            self._refresh_tree()
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Heading filter
    # ---------------------------------------------------------------------------------

    def _on_heading_filters_clicked(self) -> None:
        """Open HeadingFilterDialog and update controller.heading_filter_exclusions."""
        ctrl = self._controller
        if ctrl is None:
            return

        try:
            # Build counts and occurrences by traversing the ditamap root
            headings_cache = self._build_headings_cache_for_dialog(ctrl.context)
            occurrences_map = self._build_heading_occurrences(ctrl.context)

            dialog = HeadingFilterDialog(self)
            current = dict(getattr(ctrl, "heading_filter_exclusions", {}) or {})
            # Extend call to pass occurrences for details panel
            updated = dialog.show_dialog(headings_cache, current, occurrences=occurrences_map)

            # Update controller state: style -> excluded
            ctrl.heading_filter_exclusions = dict(updated or {})
            # Refresh the tree to reflect filter changes (controller.max_depth unchanged)
            self._refresh_tree()
        except Exception:
            pass

    def _build_headings_cache_for_dialog(self, context: Optional[DitaContext]) -> dict:
        """Construct headings cache for HeadingFilterDialog by traversing context.ditamap_root.

        Rules:
        - Count occurrences of styles by traversing topicref/topichead nodes.
        - Style resolution priority:
          1) node.get("data-style")
          2) if missing, derive "Heading {data-level}" when @data-level exists
          3) fallback to "Heading"
        """
        counts: dict[str, int] = {}

        if context is None:
            return counts

        root = getattr(context, "ditamap_root", None)
        if root is None:
            return counts

        # Helper to resolve style according to rules
        def resolve_style(node: object) -> str:
            style = None
            try:
                if hasattr(node, "get"):
                    style = node.get("data-style")
            except Exception:
                style = None
            if not style:
                level = None
                try:
                    if hasattr(node, "get"):
                        level = node.get("data-level")
                except Exception:
                    level = None
                if level:
                    style = f"Heading {level}"
            if not style:
                style = "Heading"
            return style

        # Helper to iterate children that are topicref/topichead
        def iter_children(node: object):
            # Prefer iterchildren if available
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
            # Fallback to getchildren
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
            # Fallback to findall scoped children
            try:
                if hasattr(node, "findall"):
                    for child in list(node.findall("./topicref")) + list(node.findall("./topichead")):
                        yield child
            except Exception:
                pass

        # Stack-based traversal to avoid recursion limits
        stack = [root]
        visited = 0
        max_nodes = 200000  # safety cap
        while stack and visited < max_nodes:
            node = stack.pop()
            visited += 1
            # Only count topicref/topichead nodes (skip the map root itself unless it matches)
            try:
                tag = str(getattr(node, "tag", "") or "")
            except Exception:
                tag = ""
            if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                style = resolve_style(node)
                counts[style] = counts.get(style, 0) + 1
            # Push children
            try:
                for child in iter_children(node):
                    stack.append(child)
            except Exception:
                continue

        return counts

    def _build_heading_occurrences(self, context: Optional[DitaContext]) -> dict[str, list[dict[str, str]]]:
        """Construct mapping: style -> list of occurrences with 'title' and 'href'.

        Traverses context.ditamap_root and for each topicref/topichead node:
        - Derive style using same rules as counts:
          * data-style
          * else "Heading {data-level}" when data-level present
          * else "Heading"
        - Derive title with priority:
          * topicmeta/navtitle text
          * else title text
          * else @href
          * else "Untitled"
        - href is @href if present (topichead may be missing it).
        """
        occurrences: dict[str, list[dict[str, str]]] = {}
        if context is None:
            return occurrences
        root = getattr(context, "ditamap_root", None)
        if root is None:
            return occurrences

        def resolve_style(node: object) -> str:
            style = None
            try:
                if hasattr(node, "get"):
                    style = node.get("data-style")
            except Exception:
                style = None
            if not style:
                level = None
                try:
                    if hasattr(node, "get"):
                        level = node.get("data-level")
                except Exception:
                    level = None
                if level:
                    style = f"Heading {level}"
            if not style:
                style = "Heading"
            return style

        def get_text_or_none(node: object) -> Optional[str]:
            try:
                text = getattr(node, "text", None)
                if text is not None:
                    return str(text).strip() or None
            except Exception:
                pass
            return None

        def find_first(node: object, path: str):
            try:
                if hasattr(node, "find"):
                    return node.find(path)
            except Exception:
                return None
            return None

        def extract_title_and_href(node: object) -> tuple[str, Optional[str]]:
            # Try topicmeta/navtitle
            navtitle = None
            try:
                topicmeta = find_first(node, "./topicmeta")
                if topicmeta is not None:
                    nav = find_first(topicmeta, "./navtitle")
                    if nav is not None:
                        navtitle = get_text_or_none(nav)
            except Exception:
                navtitle = None

            title_text = None
            if not navtitle:
                try:
                    tnode = find_first(node, "./title")
                    if tnode is not None:
                        title_text = get_text_or_none(tnode)
                except Exception:
                    title_text = None

            href_val = None
            try:
                if hasattr(node, "get"):
                    href_val = node.get("href")
            except Exception:
                href_val = None

            title_final = navtitle or title_text or (href_val if href_val else "Untitled")
            return str(title_final), (str(href_val) if href_val else None)

        def iter_children(node: object):
            # Prefer iterchildren
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
            # Fallback getchildren
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
            # Fallback findall
            try:
                if hasattr(node, "findall"):
                    for child in list(node.findall("./topicref")) + list(node.findall("./topichead")):
                        yield child
            except Exception:
                pass

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
            if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                style = resolve_style(node)
                title, href = extract_title_and_href(node)
                item = {"title": title}
                if href:
                    item["href"] = href
                occurrences.setdefault(style, []).append(item)
            try:
                for child in iter_children(node):
                    stack.append(child)
            except Exception:
                continue

        return occurrences

    # ---------------------------------------------------------------------------------
    # Keyboard shortcuts
    # ---------------------------------------------------------------------------------

    def _on_shortcut_undo(self, _event: Optional[tk.Event]) -> str:
        ctrl = self._controller
        if ctrl is None:
            return "break"
        try:
            if ctrl.undo():
                self._refresh_tree()
        except Exception:
            pass
        return "break"

    # ---------------------------------------------------------------------------------
    # Preview helper
    # ---------------------------------------------------------------------------------


    def _on_shortcut_redo(self, _event: Optional[tk.Event]) -> str:
        ctrl = self._controller
        if ctrl is None:
            return "break"
        try:
            if ctrl.redo():
                self._refresh_tree()
        except Exception:
            pass
        return "break"

    # -------------------------------------------------------------------------
    # Preview panel wiring
    # -------------------------------------------------------------------------

    def _on_toggle_preview(self) -> None:
        """Show/hide the right-hand preview pane."""
        try:
            self._preview_visible = not getattr(self, "_preview_visible", True)
            if self._preview_toggle_btn is not None:
                self._preview_toggle_btn.configure(text=("Show Preview" if not self._preview_visible else "Hide Preview"))
            # Properly hide/show the preview by removing/adding the right pane
            paned = getattr(self, "_paned", None)
            right = getattr(self, "_right_pane", None)
            if paned is None or right is None:
                return
            if self._preview_visible:
                try:
                    panes = paned.panes()
                    if str(right) not in panes:
                        # Ensure the left pane exists; add it first if needed
                        try:
                            if str(self._left_pane) not in panes:
                                paned.add(self._left_pane, weight=4)
                                panes = paned.panes()
                        except Exception:
                            pass
                        # Append the right pane so it sits to the right of the left pane
                        paned.add(right, weight=2)
                        try:
                            paned.paneconfigure(right, minsize=150)
                        except Exception:
                            pass
                        # Restore sash position after idle to ensure layout is realized
                        try:
                            self.after_idle(self._restore_sash_position)
                        except Exception:
                            try:
                                self.after(0, self._restore_sash_position)
                            except Exception:
                                pass
                except Exception:
                    pass
            else:
                try:
                    try:
                        # Capture current sash position as fraction before hiding
                        # Flush layout then capture ratio
                        paned.update_idletasks()
                        width = paned.winfo_width()
                        if width and width > 0:
                            pos_px = int(paned.sashpos(0))
                            ratio = max(0.05, min(0.95, float(pos_px) / float(width)))
                            self._last_sash_ratio = ratio  # type: ignore[assignment]
                        else:
                            # Keep previous ratio; do not overwrite with None
                            pass
                    except Exception:
                        self._last_sash_ratio = None  # type: ignore[assignment]
                    panes = paned.panes()
                    if str(right) in panes:
                        paned.forget(right)
                except Exception:
                    pass
        except Exception:
            pass

    def _restore_sash_position(self) -> None:
        """Restore sash to last known position or default fraction when showing preview."""
        try:
            paned = getattr(self, "_paned", None)
            if paned is None:
                return
            paned.update_idletasks()
            width = paned.winfo_width()
            if width <= 1:
                self.after(50, self._restore_sash_position)
                return
            ratio = getattr(self, "_last_sash_ratio", None)
            if not isinstance(ratio, float) or ratio <= 0.05 or ratio >= 0.95:
                ratio = 0.67
            pos = int(width * ratio)
            try:
                paned.sashpos(0, pos)
            except Exception:
                # Retry once more in case layout isn't ready
                self.after(50, lambda: self._safe_set_sash(pos))
        except Exception:
            pass

    def _safe_set_sash(self, pos: int) -> None:
        try:
            paned = getattr(self, "_paned", None)
            if paned is None:
                return
            paned.sashpos(0, pos)
        except Exception:
            pass

    def _get_first_selected_ref(self) -> str:
        try:
            ctrl = self._controller
            if ctrl is None:
                return ""
            sel = ctrl.get_selection()
            return sel[0] if sel else ""
        except Exception:
            return ""

    def _update_side_preview(self) -> None:
        """Render side preview for current selection based on panel mode."""
        panel = getattr(self, "_preview_panel", None)
        ctrl = self._controller
        if panel is None or ctrl is None:
            return
        topic_ref = self._get_first_selected_ref()
        if not topic_ref:
            panel.clear()
            return

        # Delegate to helper method
        self._render_preview_for_ref(topic_ref, panel)

    def _on_preview_mode_changed(self, mode: str) -> None:
        """Re-render preview when mode toggle changes."""
        try:
            self._update_side_preview()
        except Exception:
            pass

    def _on_preview_refresh_clicked(self) -> None:
        """Re-run preview for the current selection."""
        try:
            self._update_side_preview()
        except Exception:
            pass

    def _on_shortcut_move(self, direction: str) -> str:
        ctrl = self._controller
        if ctrl is None:
            return "break"
        try:
            result = ctrl.handle_move_operation(direction)  # OperationResult
            if getattr(result, "success", False):
                self._refresh_tree()
        except Exception:
            pass
        return "break"