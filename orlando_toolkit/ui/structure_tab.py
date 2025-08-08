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
from orlando_toolkit.ui.widgets.heading_filter_panel import HeadingFilterPanel
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

        # Toolbar (now below the modified header row)
        self._toolbar = ToolbarWidget(self, on_move=self._on_toolbar_move_clicked)
        self._toolbar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

        # Search row layout (left tools | search | toggles | spacer | depth controls)
        search_row = ttk.Frame(self)
        search_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        # Column 3 is a flexible spacer to push depth controls to the far right
        search_row.columnconfigure(3, weight=1)

        # Left tools: Expand/Collapse all, placed completely to the left of search bar
        left_tools = ttk.Frame(search_row)
        left_tools.grid(row=0, column=0, padx=(0, 8))

        try:
            self._expand_all_btn = ttk.Button(left_tools, text="⊞", width=3, command=self._on_expand_all)
            self._expand_all_btn.grid(row=0, column=0, padx=(0, 4))
            try:
                from orlando_toolkit.ui.custom_widgets import Tooltip
                Tooltip(self._expand_all_btn, "Expand all", delay_ms=1000)
            except Exception:
                pass
        except Exception:
            self._expand_all_btn = None  # type: ignore[assignment]
        try:
            self._collapse_all_btn = ttk.Button(left_tools, text="⊟", width=3, command=self._on_collapse_all)
            self._collapse_all_btn.grid(row=0, column=1)
            try:
                from orlando_toolkit.ui.custom_widgets import Tooltip
                Tooltip(self._collapse_all_btn, "Collapse all", delay_ms=1000)
            except Exception:
                pass
        except Exception:
            self._collapse_all_btn = None  # type: ignore[assignment]

        # Search widget: make it noticeably narrower via explicit entry width
        self._search = SearchWidget(
            search_row,
            on_term_changed=self._on_search_term_changed,
            on_navigate=self._on_search_navigate,
            entry_width=30,
        )
        # Do not stretch the search widget; keep compact
        self._search.grid(row=0, column=1, sticky="w")

        # Spacer column between search and right-aligned controls
        # Column 3 is configured as the expanding spacer above

        # Depth control (Label + Spinbox) placed just right of the spacer (to the right, before toggles)
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

        # Toggle buttons group (Filters | Preview) with pictograms, placed far right
        toggles = ttk.Frame(search_row)
        toggles.grid(row=0, column=4, padx=(12, 0), sticky="e")

        # Track active states for toggle feedback and behavior
        self._preview_active: bool = True
        self._filter_active: bool = False

        # Filters toggle: gear/filter pictogram
        self._filter_toggle_btn = ttk.Button(
            toggles,
            text="≡",  # hamburger (triple bar) icon for heading filters
            command=self._on_filter_toggle_clicked,
            width=3,
        )
        self._filter_toggle_btn.grid(row=0, column=0, padx=(0, 4))
        try:
            self._filter_toggle_btn.tooltip_text = "Heading filters"  # type: ignore[attr-defined]
        except Exception:
            pass

        # Preview toggle: eye pictogram
        self._preview_toggle_btn = ttk.Button(
            toggles,
            text="👁",
            command=self._on_preview_toggle_clicked,
            width=3,
            style="Accent.TButton",  # active by default
        )
        self._preview_toggle_btn.grid(row=0, column=1)

        # Spacer in column 3 already stretches; no extra controls here

        # Main area: PanedWindow with tree (left) and preview panel (right)
        self._paned = ttk.PanedWindow(self, orient="horizontal")
        self._paned.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

        left = ttk.Frame(self._paned)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        right = ttk.Frame(self._paned)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        # Equal weights; we will set the sash explicitly to 50/50 by default
        self._paned.add(left, weight=1)
        self._paned.add(right, weight=1)
        # Prevent zero-width panes by setting a reasonable minimum size for the preview pane
        try:
            self._paned.paneconfigure(right, minsize=150)
        except Exception:
            pass

        # Keep handles to panes so we can properly hide/show the preview pane
        self._left_pane = left  # type: ignore[assignment]
        self._right_pane = right  # type: ignore[assignment]
        # Store sash ratios independently per right panel kind (preview/filter)
        self._sash_ratio_preview: float = 0.5
        self._sash_ratio_filter: float = 0.5
        # Back-compat aggregate ratio used elsewhere
        self._last_sash_ratio = 0.5  # type: ignore[assignment]
        # Track which right-hand panel is active
        self._active_right_kind: str = "preview"
        # Capture user-resized sash ratio on mouse release
        try:
            self._paned.bind("<ButtonRelease-1>", lambda _e: self._capture_sash_ratio())
        except Exception:
            pass

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

        self._preview_container = right  # remember where preview/filter panels live
        self._preview_panel = PreviewPanel(
            right,
            on_mode_changed=self._on_preview_mode_changed,
        )
        self._preview_panel.grid(row=0, column=0, sticky="nsew")
        self._filter_panel: Optional[HeadingFilterPanel] = None

        # Initialize toggle visuals to match default active preview
        try:
            self._set_toggle_states(True, False)
        except Exception:
            pass

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
        # Ensure shortcuts work regardless of focused child by binding at the application level
        try:
            self.bind_all("<Control-z>", self._on_shortcut_undo, add=True)
            self.bind_all("<Control-y>", self._on_shortcut_redo, add=True)
        except Exception:
            pass
        # Ensure this widget can receive keyboard focus
        self.focus_set()
        # Initial population
        self._refresh_tree()
        # Set initial sash position to 50/50
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

    # Expose the controller's context for callers (e.g., export pipeline)
    @property
    def context(self) -> Optional[DitaContext]:
        try:
            return self._controller.context if self._controller is not None else None
        except Exception:
            return None

    @property
    def max_depth(self) -> Optional[int]:
        try:
            return getattr(self._controller, "max_depth", None) if self._controller is not None else None
        except Exception:
            return None
    
    def _sync_depth_control(self) -> None:
        """Apply the default depth (3) to the controller and sync the display."""
        if not hasattr(self, "_depth_var") or self._controller is None:
            return
        try:
            # Read current depth from context metadata when available; fallback to 3
            depth = 3
            try:
                ctx = getattr(self._controller, "context", None)
                if ctx is not None and hasattr(ctx, "metadata"):
                    depth = int(getattr(ctx, "metadata", {}).get("topic_depth", 3))
            except Exception:
                depth = 3

            # Reflect in the UI control
            try:
                self._depth_var.set(depth)
            except Exception:
                pass

            # Apply to controller so the visible tree matches the persisted depth
            if hasattr(self._controller, "handle_depth_change"):
                self._controller.handle_depth_change(depth)
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
        """Position the paned window sash according to active panel ratio (default 50/50)."""
        try:
            paned = getattr(self, "_paned", None)
            if paned is None:
                return
            width = paned.winfo_width()
            # If geometry not ready yet, retry shortly
            if width <= 1:
                self.after(50, self._set_initial_sash_position)
                return
            ratio = self._sash_ratio_preview if getattr(self, "_active_right_kind", "preview") == "preview" else self._sash_ratio_filter
            if not isinstance(ratio, float) or ratio <= 0.05 or ratio >= 0.95:
                ratio = 0.5
            pos = int(width * ratio)
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
            res = self._controller.handle_rename(refs[0], new_title)  # type: ignore[attr-defined]
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
            res = self._controller.handle_delete(refs)  # type: ignore[attr-defined]
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
            res = self._controller.handle_merge(refs)  # type: ignore[attr-defined]
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
        """Show the new panel in place of preview; remove old dialog usage."""
        ctrl = self._controller
        if ctrl is None:
            return

        try:
            # Build counts and occurrences, plus per-style levels for grouping
            headings_cache = self._build_headings_cache(ctrl.context)
            occurrences_map = self._build_heading_occurrences(ctrl.context)
            style_levels = self._build_style_levels(ctrl.context)
            current = dict(getattr(ctrl, "heading_filter_exclusions", {}) or {})

            # Ensure right pane exists and show filter panel
            self._set_active_panel("filter")
            if self._filter_panel is None:
                return
            self._filter_panel.set_data(headings_cache, occurrences_map, style_levels, current)
            # Clear any previous filter highlights
            try:
                self._tree.clear_filter_highlight_refs()  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass

    def _ensure_filter_panel(self) -> None:
        try:
            container = getattr(self, "_preview_container", None)
            if container is None:
                return
            # Make sure right pane is present in the PanedWindow
            paned = getattr(self, "_paned", None)
            right = getattr(self, "_right_pane", None)
            try:
                if paned is not None and right is not None and str(right) not in paned.panes():
                    paned.add(right, weight=2)
                    try:
                        paned.paneconfigure(right, minsize=150)
                    except Exception:
                        pass
            except Exception:
                pass
            # Hide preview panel if present
            if self._preview_panel is not None:
                try:
                    self._preview_panel.grid_remove()
                except Exception:
                    pass
            # Create once
            if self._filter_panel is None:
                self._filter_panel = HeadingFilterPanel(
                    container,
                    on_close=self._on_filter_close,
                    on_apply=self._on_filter_apply,
                    on_select_style=self._on_filter_select_style,
                )
                self._filter_panel.grid(row=0, column=0, sticky="nsew")
            else:
                try:
                    self._filter_panel.grid()
                except Exception:
                    pass
            # Activate filter panel and restore its sash ratio
            try:
                self._active_right_kind = "filter"
                self.after_idle(self._restore_sash_position)
            except Exception:
                pass
        except Exception:
            pass

    def _on_filter_close(self) -> None:
        # Hide filter panel, show preview panel back
        try:
            if self._filter_panel is not None:
                self._filter_panel.grid_remove()
            if self._preview_panel is not None:
                self._preview_panel.grid()
            try:
                self._active_right_kind = "preview"
                self._tree.clear_filter_highlight_refs()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._set_toggle_states(True, False)
        except Exception:
            pass

    def _on_filter_apply(self, exclusions: dict[str, bool]) -> None:
        ctrl = self._controller
        if ctrl is None:
            return
        try:
            # Update controller mapping
            ctrl.heading_filter_exclusions = dict(exclusions or {})

            # Build style exclusion map per levels for merge
            style_excl_map: dict[int, set[str]] = {}
            levels_map = self._build_style_levels(ctrl.context)
            for style, excluded in exclusions.items():
                if not excluded:
                    continue
                # Derive level from computed map; fallback to level 1
                level = int(levels_map.get(style) or 1)
                style_excl_map.setdefault(level, set()).add(style)

            # Validate mergability upfront and inform user if some items cannot be merged
            try:
                unmergable = self._find_unmergable_for_styles(style_excl_map)
                if unmergable > 0 and self._filter_panel is not None:
                    plural = "s" if unmergable > 1 else ""
                    self._filter_panel.update_status(
                        f"Unable to filter: {unmergable} topic{plural} doesn't have parent to merge"
                    )
            except Exception:
                pass

            # Apply via controller to ensure undo snapshots are recorded
            res = self._controller.handle_apply_filters(style_excl_map or None)  # type: ignore[attr-defined]
            if not getattr(res, "success", False):
                # Surface minimal info in panel status
                try:
                    self._filter_panel.update_status("Failed to apply heading filter")  # type: ignore[attr-defined]
                except Exception:
                    pass
                return

            # Refresh tree and keep preview hidden while panel is up
            self._refresh_tree()
            # Optionally, update status
            try:
                self._filter_panel.update_status("Filters applied")  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            try:
                if self._filter_panel is not None:
                    self._filter_panel.update_status("Failed to apply heading filter")
            except Exception:
                pass

    def _on_filter_select_style(self, style: str) -> None:
        # Highlight occurrences of the selected style in the tree (filter-specific highlights)
        try:
            occ = self._build_heading_occurrences(self._controller.context)  # type: ignore[attr-defined]
            style_items = occ.get(style, []) if occ else []
            refs = [it.get("href") for it in style_items if isinstance(it, dict) and it.get("href")]
            # Keep search highlights intact; only add filter tag
            self._tree.set_filter_highlight_refs(refs)  # type: ignore[attr-defined]
        except Exception:
            try:
                self._tree.clear_filter_highlight_refs()  # type: ignore[attr-defined]
            except Exception:
                pass

    def _build_headings_cache(self, context: Optional[DitaContext]) -> dict:
        """Construct headings cache for the filter panel by traversing context.ditamap_root.

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

    def _build_style_levels(self, context: Optional[DitaContext]) -> dict[str, Optional[int]]:
        """Return a mapping style -> level (int) when derivable, else None.

        Rules mirror other helpers: prefer data-style; else derive from data-level; fallback "Heading" -> None.
        """
        result: dict[str, Optional[int]] = {}
        if context is None:
            return result
        root = getattr(context, "ditamap_root", None)
        if root is None:
            return result
        def resolve_style_and_level(node: object) -> tuple[str, Optional[int]]:
            style = None
            level = None
            try:
                if hasattr(node, "get"):
                    style = node.get("data-style")
            except Exception:
                style = None
            try:
                if hasattr(node, "get"):
                    lv = node.get("data-level")
                    level = int(lv) if lv is not None else None
            except Exception:
                level = None
            if not style and isinstance(level, int):
                style = f"Heading {level}"
            if not style:
                style = "Heading"
            return style, level
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
                style, level = resolve_style_and_level(node)
                result.setdefault(style, level)
            try:
                if hasattr(node, "iterchildren"):
                    for child in node.iterchildren():
                        try:
                            ctag = str(getattr(child, "tag", "") or "")
                        except Exception:
                            ctag = ""
                        if ctag.endswith("topicref") or ctag.endswith("topichead") or ctag in {"topicref", "topichead"}:
                            stack.append(child)
                    continue
            except Exception:
                pass
            try:
                if hasattr(node, "getchildren"):
                    for child in node.getchildren():  # type: ignore[attr-defined]
                        try:
                            ctag = str(getattr(child, "tag", "") or "")
                        except Exception:
                            ctag = ""
                        if ctag.endswith("topicref") or ctag.endswith("topichead") or ctag in {"topicref", "topichead"}:
                            stack.append(child)
                    continue
            except Exception:
                pass
            try:
                if hasattr(node, "findall"):
                    for child in list(node.findall("./topicref")) + list(node.findall("./topichead")):
                        stack.append(child)
            except Exception:
                pass
        return result

    def _find_unmergable_for_styles(self, style_excl_map: dict[int, set[str]]) -> int:
        """Return count of nodes matching excluded (level, style) with no merge parent.

        A node is considered unmergable when it has no ancestor topicref or topichead,
        i.e., it is a direct child of the map root.
        """
        ctrl = self._controller
        if ctrl is None or ctrl.context is None:
            return 0
        root = getattr(ctrl.context, "ditamap_root", None)
        if root is None:
            return 0

        def node_style_level(n: object) -> tuple[str, int]:
            level = 1
            style = "Heading"
            try:
                if hasattr(n, "get"):
                    lv = n.get("data-level")
                    if lv is not None:
                        level = int(lv)
            except Exception:
                pass
            try:
                if hasattr(n, "get"):
                    st = n.get("data-style")
                    if st:
                        style = st
                    elif lv is not None:
                        style = f"Heading {level}"
            except Exception:
                pass
            return style, level

        def has_merge_parent(n: object) -> bool:
            try:
                parent = getattr(n, "getparent", lambda: None)()
                while parent is not None:
                    tag = str(getattr(parent, "tag", "") or "")
                    if tag in ("topicref", "topichead") or tag.endswith("topicref") or tag.endswith("topichead"):
                        return True
                    parent = getattr(parent, "getparent", lambda: None)()
            except Exception:
                return False
            return False

        unmergable = 0
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
            if tag in ("topicref", "topichead") or tag.endswith("topicref") or tag.endswith("topichead"):
                style, level = node_style_level(node)
                if level in style_excl_map and style in style_excl_map[level]:
                    if not has_merge_parent(node):
                        unmergable += 1
            try:
                if hasattr(node, "iterchildren"):
                    for child in node.iterchildren():
                        stack.append(child)
                    continue
            except Exception:
                pass
            try:
                if hasattr(node, "getchildren"):
                    for child in node.getchildren():  # type: ignore[attr-defined]
                        stack.append(child)
                    continue
            except Exception:
                pass
            try:
                if hasattr(node, "findall"):
                    for child in list(node.findall("./topicref")) + list(node.findall("./topichead")):
                        stack.append(child)
            except Exception:
                pass
        return unmergable

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

    def _on_show_preview(self) -> None:
        """Ensure the preview panel is visible and the heading filter panel is closed."""
        try:
            # Show right pane in paned window (if somehow removed)
            paned = getattr(self, "_paned", None)
            right = getattr(self, "_right_pane", None)
            if paned is not None and right is not None:
                panes = paned.panes()
                if str(right) not in panes:
                    paned.add(right, weight=2)
                    try:
                        paned.paneconfigure(right, minsize=150)
                    except Exception:
                        pass
                # Restore sash position to the last preview ratio
                try:
                    self._active_right_kind = "preview"
                    self.after_idle(self._restore_sash_position)
                except Exception:
                    pass

            # Hide filter panel if shown, and show preview panel
            if getattr(self, "_filter_panel", None) is not None:
                try:
                    self._filter_panel.grid_remove()
                except Exception:
                    pass
            if getattr(self, "_preview_panel", None) is not None:
                try:
                    self._preview_panel.grid()
                except Exception:
                    pass

            # Refresh current selection preview content
            self._update_side_preview()
            # Visual toggle state handled by _set_active_panel
        except Exception:
            pass

    def _restore_sash_position(self) -> None:
        """Restore sash to last known position for the active right panel, default 50/50."""
        try:
            paned = getattr(self, "_paned", None)
            if paned is None:
                return
            paned.update_idletasks()
            width = paned.winfo_width()
            if width <= 1:
                self.after(50, self._restore_sash_position)
                return
            # Choose ratio based on active panel kind
            ratio = self._sash_ratio_filter if getattr(self, "_active_right_kind", "preview") == "filter" else self._sash_ratio_preview
            if not isinstance(ratio, float) or ratio <= 0.05 or ratio >= 0.95:
                ratio = 0.5
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

    # -------------------------------------------------------------------------
    # Toggle buttons behavior and visuals
    # -------------------------------------------------------------------------

    def _on_filter_toggle_clicked(self) -> None:
        """Toggle the heading filter panel on/off."""
        try:
            if getattr(self, "_active_right_kind", "preview") == "filter":
                self._set_active_panel("none")
            else:
                self._set_active_panel("filter")
                # Populate data after showing/ensuring the panel exists
                try:
                    ctrl = self._controller
                    if ctrl is not None:
                        headings_cache = self._build_headings_cache(ctrl.context)
                        occurrences_map = self._build_heading_occurrences(ctrl.context)
                        style_levels = self._build_style_levels(ctrl.context)
                        current = dict(getattr(ctrl, "heading_filter_exclusions", {}) or {})
                        if self._filter_panel is not None:
                            self._filter_panel.set_data(headings_cache, occurrences_map, style_levels, current)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_preview_toggle_clicked(self) -> None:
        """Toggle the preview panel on/off (hide if already visible)."""
        try:
            if getattr(self, "_active_right_kind", "preview") == "preview":
                self._set_active_panel("none")
            else:
                self._set_active_panel("preview")
        except Exception:
            pass

    def _set_toggle_states(self, preview_active: bool, filter_active: bool) -> None:
        try:
            self._preview_active = bool(preview_active)
            self._filter_active = bool(filter_active)
            self._apply_toggle_visuals()
        except Exception:
            pass

    def _apply_toggle_visuals(self) -> None:
        """Apply blue accent style to the active toggle button; neutral style otherwise."""
        try:
            if hasattr(self, "_filter_toggle_btn") and self._filter_toggle_btn is not None:
                self._filter_toggle_btn.configure(style=("Accent.TButton" if self._filter_active else "TButton"))
            if hasattr(self, "_preview_toggle_btn") and self._preview_toggle_btn is not None:
                self._preview_toggle_btn.configure(style=("Accent.TButton" if self._preview_active else "TButton"))
        except Exception:
            pass

    def _set_active_panel(self, kind: str) -> None:
        """Switch right-side panel between 'preview', 'filter', or 'none'."""
        try:
            paned = getattr(self, "_paned", None)
            right = getattr(self, "_right_pane", None)

            if kind == "none":
                if paned is not None and right is not None:
                    try:
                        if str(right) in paned.panes():
                            paned.forget(right)
                    except Exception:
                        pass
                self._active_right_kind = "none"
                self._set_toggle_states(False, False)
                return

            # Ensure right pane exists
            if paned is not None and right is not None:
                try:
                    if str(right) not in paned.panes():
                        paned.add(right, weight=2)
                        try:
                            paned.paneconfigure(right, minsize=150)
                        except Exception:
                            pass
                except Exception:
                    pass

            if kind == "preview":
                # Show preview, hide filter
                try:
                    if getattr(self, "_filter_panel", None) is not None:
                        self._filter_panel.grid_remove()
                except Exception:
                    pass
                try:
                    if getattr(self, "_preview_panel", None) is not None:
                        self._preview_panel.grid()
                except Exception:
                    pass
                self._active_right_kind = "preview"
                try:
                    self.after_idle(self._restore_sash_position)
                except Exception:
                    pass
                # Update content
                try:
                    self._update_side_preview()
                except Exception:
                    pass
                self._set_toggle_states(True, False)
                return

            if kind == "filter":
                # Ensure filter panel exists and is visible
                container = getattr(self, "_preview_container", None)
                if container is not None:
                    if getattr(self, "_filter_panel", None) is None:
                        try:
                            self._filter_panel = HeadingFilterPanel(
                                container,
                                on_close=self._on_filter_close,
                                on_apply=self._on_filter_apply,
                                on_select_style=self._on_filter_select_style,
                            )
                            self._filter_panel.grid(row=0, column=0, sticky="nsew")
                        except Exception:
                            pass
                    else:
                        try:
                            self._filter_panel.grid()
                        except Exception:
                            pass
                # Hide preview
                try:
                    if getattr(self, "_preview_panel", None) is not None:
                        self._preview_panel.grid_remove()
                except Exception:
                    pass
                self._active_right_kind = "filter"
                try:
                    self.after_idle(self._restore_sash_position)
                except Exception:
                    pass
                self._set_toggle_states(False, True)
                return
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