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
import threading
import tkinter as tk
from tkinter import ttk
import logging
import xml.etree.ElementTree as ET

# Required imports per specification
from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
from orlando_toolkit.core.services.undo_service import UndoService
from orlando_toolkit.core.services.preview_service import PreviewService

# UI extension support
try:
    from orlando_toolkit.core.context import get_app_context
    from orlando_toolkit.core.plugins.ui_registry import UIRegistry
except ImportError:
    # Graceful degradation if plugin system not available
    def get_app_context():
        return None
    UIRegistry = None  # type: ignore
from orlando_toolkit.ui.controllers.structure_controller import StructureController
from orlando_toolkit.ui.widgets.structure_tree_widget import StructureTreeWidget
from orlando_toolkit.ui.widgets.search_widget import SearchWidget
from orlando_toolkit.ui.widgets.toolbar_widget import ToolbarWidget
from orlando_toolkit.ui.widgets.style_legend import StyleLegend
from orlando_toolkit.ui.dialogs.context_menu import ContextMenuHandler
from orlando_toolkit.ui.tabs.structure.preview_coordinator import PreviewCoordinator
from orlando_toolkit.ui.tabs.structure.context_menu_coordinator import ContextMenuCoordinator
from orlando_toolkit.ui.tabs.structure.paned_layout import PanedLayoutCoordinator
from orlando_toolkit.ui.tabs.structure.right_panel import RightPanelCoordinator
from orlando_toolkit.ui.tabs.structure.filter_coordinator import FilterCoordinator
from orlando_toolkit.ui.tabs.structure.depth_control import DepthControlCoordinator
from orlando_toolkit.ui.tabs.structure.search_coordinator import SearchCoordinator
from orlando_toolkit.ui.tabs.structure.context_actions import ContextActions
from orlando_toolkit.ui.tabs.structure.tree_refresh_coordinator import TreeRefreshCoordinator
from orlando_toolkit.ui.widgets.universal_spinner import UniversalSpinner

logger = logging.getLogger(__name__)


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

        # Create control rows with batched configuration
        search_row = ttk.Frame(self)
        toolbar_row = ttk.Frame(self)
        
        # Configure grid layout in batch
        search_row.columnconfigure(3, weight=1)  # Spacer column
        toolbar_row.columnconfigure(0, weight=0)
        toolbar_row.columnconfigure(1, weight=1)
        
        # Position both rows
        search_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        toolbar_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

        self._toolbar = ToolbarWidget(toolbar_row, on_move=self._on_toolbar_move_clicked)
        self._toolbar.grid(row=0, column=0, sticky="w")

        # Search widget: make it noticeably narrower via explicit entry width
        self._search = SearchWidget(
            search_row,
            on_term_changed=self._on_search_term_changed,
            on_navigate=self._on_search_navigate,
            entry_width=30,
        )
        # Do not stretch the search widget; keep compact
        self._search.grid(row=0, column=0, sticky="w")

        # Spacer column between search and right-aligned controls
        # Column 3 is configured as the expanding spacer above

        # Depth control (Label + Spinbox) placed just right of the spacer
        try:
            # Initialize with 1; will be synced to metadata or computed max later
            self._depth_var = tk.IntVar(value=1)

            # Small container to align neatly in the same row
            depth_container = ttk.Frame(search_row)
            depth_container.grid(row=0, column=2, padx=(12, 0), sticky="w")

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
            # Reduce selection side-effects for better UX
            try:
                self._depth_spin.configure(exportselection=False)
            except Exception:
                pass

            # (Busy overlay is created later inside the left pane to avoid layout shifts)

            # Bind Return/FocusOut to commit edits and clear selection; clear on spin buttons too
            try:
                self._depth_spin.bind("<Return>", lambda e: (self._on_depth_changed(), self._clear_depth_spin_selection()))
                self._depth_spin.bind("<FocusOut>", lambda e: (self._on_depth_changed(), self._clear_depth_spin_selection()))
                self._depth_spin.bind("<<Increment>>", lambda e: self._clear_depth_spin_selection(), add=True)
                self._depth_spin.bind("<<Decrement>>", lambda e: self._clear_depth_spin_selection(), add=True)
            except Exception:
                pass
        except Exception:
            # Non-fatal if depth control cannot be created
            pass
        
        # Depth coordinator - lazy loaded when first needed
        self._depth_coordinator = None  # type: ignore[assignment]

        # Style legend: placed to the right of the toolbar buttons
        self._style_legend = StyleLegend(toolbar_row)
        self._style_legend.grid(row=0, column=1, padx=(12, 0), sticky="w")

        # Toggle buttons group (Filters | Preview) with pictograms, placed far right
        toggles = ttk.Frame(search_row)
        toggles.grid(row=0, column=4, padx=(8, 0), sticky="e")

        # Track active states for toggle feedback and behavior
        self._preview_active: bool = True
        self._filter_active: bool = False

        # Plugin panels toggle: created dynamically by plugins
        self._plugin_panel_btns = {}  # Dict of panel_type -> button
        self._toggles_frame = toggles  # Keep reference to add buttons dynamically
        self._active_plugin_panel = None  # Currently active panel type

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

        # Create and configure panes in batch
        left = ttk.Frame(self._paned)
        right = ttk.Frame(self._paned)
        
        # Batch configure both panes
        for pane in (left, right):
            pane.columnconfigure(0, weight=1)
            pane.rowconfigure(0, weight=1)
        
        # Add panes with 50/50 weights
        self._paned.add(left, weight=1)
        self._paned.add(right, weight=1)
        
        # Set minimum size for right pane
        try:
            self._paned.paneconfigure(right, minsize=150)
        except Exception:
            pass

        # Keep handles to panes so we can properly hide/show the preview pane
        self._left_pane = left  # type: ignore[assignment]
        self._right_pane = right  # type: ignore[assignment]
        # Sash ratios and active kind are managed by PanedLayoutCoordinator/RightPanelCoordinator

        # Paned layout coordinator (sash and visibility helper)
        try:
            self._paned_coordinator = PanedLayoutCoordinator(
                paned=self._paned,
                right_pane=self._right_pane,
                after=self.after,
            )
            self._paned_coordinator.set_kind("preview")
            try:
                self._paned.bind(
                    "<ButtonRelease-1>",
                    lambda _e: self._paned_coordinator.capture_ratio(),
                    add="+",
                )
            except Exception:
                pass
        except Exception:
            self._paned_coordinator = None  # type: ignore[assignment]

        # Tree widget on the left
        self._tree = StructureTreeWidget(
            left,
            on_selection_changed=self._on_tree_selection_changed,
            on_item_activated=self._on_tree_item_activated,
            on_context_menu=self._on_tree_context_menu,
        )
        self._tree.grid(row=0, column=0, sticky="nsew")
        # Loading spinner (replaces hourglass cursor with elegant animation)
        self._loading_spinner = UniversalSpinner(left, "Refreshing structure...")
        # Cache of last XML selection for preview/movement
        self._last_selected_xml_nodes: List[ET.Element] = []

        # Preview panel on the right
        from orlando_toolkit.ui.widgets.preview_panel import PreviewPanel  # local import to avoid cycles

        self._preview_container = right  # remember where preview/filter panels live
        self._preview_panel = PreviewPanel(
            right,
            on_mode_changed=self._on_preview_mode_changed,
            on_breadcrumb_clicked=self._on_breadcrumb_clicked,
        )
        self._preview_panel.grid(row=0, column=0, sticky="nsew")
        self._filter_panel: Optional[object] = None

        # Preview coordinator
        try:
            self._preview_coordinator = PreviewCoordinator(
                controller_getter=lambda: self._controller,
                panel=self._preview_panel,
                schedule_ui=self.after,
                run_in_thread=self._run_in_thread,
            )
        except Exception:
            self._preview_coordinator = None  # type: ignore[assignment]

        # Filter coordinator (created with panel=None, assigned lazily by right-panel coordinator)
        try:
            self._filter_coordinator = FilterCoordinator(
                controller_getter=lambda: self._controller,
                panel=None,  # type: ignore[arg-type]
                tree=self._tree,
            )
        except Exception:
            self._filter_coordinator = None  # type: ignore[assignment]

        # Right panel coordinator (centralizes preview/filter/none switching)
        try:
            def _make_filter_panel():
                # Try to get any available plugin panel (backward compatibility)
                try:
                    app_context = get_app_context()
                    if app_context:
                        available_panels = app_context.get_document_source_plugin_panels()
                        # Prefer factories that declare a 'filter' role
                        for panel_type in list(available_panels or []):
                            try:
                                panel_factory = app_context.ui_registry.get_panel_factory(panel_type)
                                if not panel_factory:
                                    continue
                                role = getattr(panel_factory, 'get_role', lambda: None)()
                                if isinstance(role, str) and role.lower() == 'filter':
                                    # Support both callable factories and PanelFactory objects
                                    if callable(panel_factory):
                                        # Remember which plugin panel provides the filter
                                        try:
                                            self._active_plugin_panel = panel_type
                                        except Exception:
                                            pass
                                        return panel_factory(
                                            self._preview_container,
                                            on_close=self._on_filter_close,
                                            on_apply=self._on_filter_apply,
                                            on_toggle_style=self._on_filter_toggle_style,
                                        )
                                    elif hasattr(panel_factory, 'create_panel'):
                                        try:
                                            self._active_plugin_panel = panel_type
                                        except Exception:
                                            pass
                                        return panel_factory.create_panel(
                                            self._preview_container,
                                            app_context,
                                            on_close=self._on_filter_close,
                                            on_apply=self._on_filter_apply,
                                            on_toggle_style=self._on_filter_toggle_style,
                                        )
                            except Exception:
                                continue
                        # No legacy fallbacks; only role='filter' factories are considered
                except Exception:
                    pass
                # Fallback to None - no filter panel available without plugin
                return None

            # Get UI registry for plugin panel support
            ui_registry = None
            try:
                app_context = get_app_context()
                if app_context and hasattr(app_context, 'ui_registry'):
                    ui_registry = app_context.ui_registry
            except Exception:
                pass  # Graceful degradation
            
            self._right_panel = RightPanelCoordinator(
                set_toggle_states=self._set_toggle_states,
                update_legend=self._update_style_legend,
                create_filter_panel=_make_filter_panel,
                paned_layout=self._paned_coordinator,
                preview_panel=self._preview_panel,
                preview_container=self._preview_container,
                filter_coordinator=self._filter_coordinator,
                tree=self._tree,
                ui_registry=ui_registry,
            )
        except Exception:
            self._right_panel = None  # type: ignore[assignment]

        # Search coordinator
        try:
            self._search_coord = SearchCoordinator(
                controller_getter=lambda: self._controller,
                tree=self._tree,
                preview=self._preview_coordinator,
                update_legend=self._update_style_legend,
            )
        except Exception:
            self._search_coord = None  # type: ignore[assignment]

        # Initialize toggle visuals to match default active preview
        try:
            self._set_toggle_states(True, False)
        except Exception:
            pass

        # Context menu handler wired to StructureTab callbacks
        self._ctx_menu = ContextMenuHandler(
            self,
            on_merge=self._ctx_merge,
            on_rename=self._ctx_rename,
            on_delete=self._ctx_delete,
        )

        # Context menu coordinator
        try:
            self._ctx_coordinator = ContextMenuCoordinator(
                tree=self._tree,
                menu_handler=self._ctx_menu,
                controller_getter=lambda: self._controller,
                on_action=self._on_context_action,
            )
        except Exception:
            self._ctx_coordinator = None  # type: ignore[assignment]

        # Context actions encapsulation
        try:
            self._ctx_actions = ContextActions(
                controller_getter=lambda: self._controller,
                tree=self._tree,
                refresh_tree=self._refresh_tree,
                select_style=(lambda s: self._right_panel.select_style(s) if getattr(self, "_right_panel", None) is not None else None),
                set_depth=(lambda v: (self._depth_var.set(int(v)), self._on_depth_changed()) if hasattr(self, "_depth_var") else None),
            )
        except Exception:
            self._ctx_actions = None  # type: ignore[assignment]

        # Keyboard shortcuts (non-invasive)
        self.bind("<Control-z>", self._on_shortcut_undo)
        self.bind("<Control-y>", self._on_shortcut_redo)
        # Up/Down perform intelligent movement with level adaptation
        self.bind("<Alt-Up>",   lambda e: self._on_shortcut_move("up"))
        self.bind("<Alt-Down>", lambda e: self._on_shortcut_move("down"))
        # Ensure shortcuts work regardless of focused child by binding at the application level
        try:
            self.bind_all("<Control-z>", self._on_shortcut_undo, add=True)
            self.bind_all("<Control-y>", self._on_shortcut_redo, add=True)
            # Ensure Alt-based movement works when focus is in preview or other widgets
            self.bind_all("<Alt-Up>",   lambda e: self._on_shortcut_move("up"), add=True)
            self.bind_all("<Alt-Down>", lambda e: self._on_shortcut_move("down"), add=True)
        except Exception:
            pass
        # Ensure this widget can receive keyboard focus
        self.focus_set()
        # Initial population
        try:
            self._tree_refresh = TreeRefreshCoordinator(
                controller_getter=lambda: self._controller,
                tree=self._tree,
                toolbar=self._toolbar,
                get_filter_panel=(lambda: getattr(self, "_right_panel", None).get_filter_panel() if getattr(self, "_right_panel", None) is not None else None),
            )
        except Exception:
            self._tree_refresh = None  # type: ignore[assignment]
        
        # Defer tree refresh to avoid blocking UI with large documents
        self._needs_tree_refresh = True
        # Defer sash restoration until after all widgets are fully initialized  
        self._needs_sash_restore = True
            

        # Wire movement predicates during initial setup
        self._wire_movement_predicates()

        # Initialize empty legend
        try:
            self._update_style_legend()
        except Exception:
            pass

        # Background execution helpers state
        self._busy: bool = False
        
        # Perform deferred initialization after widget creation is complete
        self.after(50, self._perform_deferred_initialization)

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
        # Re-wire movement predicates after controller replacement
        self._wire_movement_predicates()
        self._sync_depth_control()
        # Defer tree refresh to avoid blocking with large documents
        self.after(100, self._perform_deferred_tree_refresh)
        # Plugin UI visibility will be updated in deferred initialization

    def attach_controller(self, controller: StructureController) -> None:
        """Attach an externally created controller and refresh the UI."""
        self._controller = controller
        # Re-wire movement predicates after controller attachment
        self._wire_movement_predicates()
        self._sync_depth_control()
        # Defer tree refresh to avoid blocking with large documents
        self.after(100, self._perform_deferred_tree_refresh)
        # Plugin UI visibility will be updated in deferred initialization

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
        """Apply the initial depth to the controller and sync the display.

        Preference order:
        - Use `context.metadata["topic_depth"]` when present
        - Else compute from style analysis (max depth)
        - Fallback to 1
        """
        if not hasattr(self, "_depth_var") or self._controller is None:
            return
        try:
            # Read current depth from metadata; if missing compute from structure
            depth = None
            try:
                ctx = getattr(self._controller, "context", None)
                if ctx is not None and hasattr(ctx, "metadata"):
                    md = getattr(ctx, "metadata", {})
                    if md.get("topic_depth") is not None:
                        depth = int(md.get("topic_depth"))
                    else:
                        try:
                            from orlando_toolkit.core.services.heading_analysis_service import compute_max_depth
                            depth = int(compute_max_depth(ctx))
                        except Exception:
                            depth = None
            except Exception:
                depth = None

            if not isinstance(depth, int) or depth < 1:
                depth = 1

            # Reflect in the UI control
            try:
                self._depth_var.set(depth)
            except Exception:
                pass

            # Apply to controller so the visible tree matches the computed/persisted depth
            if hasattr(self._controller, "handle_depth_change"):
                self._controller.handle_depth_change(depth)
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------------
    
    def _wire_movement_predicates(self) -> None:
        """Wire movement predicates to respect UI expansion state and visible order."""
        try:
            ctrl = self._controller
            if ctrl is not None and hasattr(ctrl, 'editing_service'):
                # Wire section-open predicate
                if hasattr(self._tree, 'is_node_expanded'):
                    try:
                        ctrl.editing_service.set_section_open_predicate(lambda node: self._tree.is_node_expanded(node))  # type: ignore[attr-defined]
                        logging.getLogger(__name__).info("Movement: section-open predicate wired to tree.is_node_expanded")
                    except Exception as e:
                        logging.getLogger(__name__).warning("Movement: failed to wire section-open predicate: %s", e)
                
                # Wire visible neighbor resolver
                if hasattr(self._tree, 'get_visible_neighbor_xml_node'):
                    try:
                        ctrl.editing_service.set_visible_neighbor_resolver(lambda node, direction: self._tree.get_visible_neighbor_xml_node(node, direction))  # type: ignore[attr-defined]
                        logging.getLogger(__name__).info("Movement: visible-neighbor resolver wired to tree.get_visible_neighbor_xml_node")
                    except Exception as e:
                        logging.getLogger(__name__).warning("Movement: failed to wire visible-neighbor resolver: %s", e)
        except Exception as e:
            logging.getLogger(__name__).warning("Movement: failed to wire predicates: %s", e)
    
    def _perform_deferred_initialization(self) -> None:
        """Perform heavy initialization tasks after widget creation."""
        try:
            # Update plugin UI visibility (heavy operation)
            self._update_plugin_ui_visibility()
            
            # Defer tree refresh to allow UI to render first
            if getattr(self, "_needs_tree_refresh", False):
                self._needs_tree_refresh = False
                # Schedule tree refresh after UI is responsive
                self.after(200, self._perform_deferred_tree_refresh)
            
            # Schedule sash restoration after plugin UI is settled
            if getattr(self, "_needs_sash_restore", False):
                self.after(100, self._perform_deferred_sash_restore)
        except Exception:
            pass
    
    def _perform_deferred_sash_restore(self) -> None:
        """Perform sash restoration after all widgets are initialized and geometry is stable."""
        try:
            if getattr(self, "_paned_coordinator", None) is not None:
                self._paned_coordinator.restore_sash()  # type: ignore[attr-defined]
            self._needs_sash_restore = False
        except Exception:
            pass
    
    def _perform_deferred_tree_refresh(self) -> None:
        """Perform tree refresh after UI is fully rendered and responsive."""
        try:
            # Show spinner animation instead of hourglass cursor
            self._set_busy(True)
            
            # Use a small delay to let spinner appear before heavy operation
            self.after(50, self._execute_tree_refresh)
        except Exception:
            pass
    
    def _execute_tree_refresh(self) -> None:
        """Execute the actual tree refresh and hide spinner when done."""
        try:
            self._refresh_tree()
        except Exception:
            pass
        finally:
            # Hide spinner animation
            self._set_busy(False)
    
    def _ensure_depth_coordinator(self) -> None:
        """Lazy load depth coordinator when first needed."""
        if self._depth_coordinator is not None:
            return
        try:
            if hasattr(self, "_depth_var"):
                self._depth_coordinator = DepthControlCoordinator(
                    get_depth_value=lambda: int(self._depth_var.get()),
                    set_depth_value=lambda v: self._depth_var.set(int(v)),
                    controller_getter=lambda: self._controller,
                    on_refresh_tree=self._refresh_tree,
                    is_busy=lambda: bool(getattr(self, "_busy", False)),
                )
        except Exception:
            self._depth_coordinator = None  # type: ignore[assignment]

    def _update_plugin_ui_visibility(self) -> None:
        """Update visibility of plugin-specific UI elements based on document source plugin capabilities."""
        try:
            import logging
            logger = logging.getLogger(__name__)
            
            app_context = get_app_context()
            if app_context:
                # Get all available plugin panels
                available_panels = app_context.get_document_source_plugin_panels()
                logger.info(f"Plugin UI visibility check: available_panels={available_panels}, current_buttons={list(self._plugin_panel_btns.keys())}")
                
                # Update plugin panel buttons
                self._update_plugin_panel_buttons(available_panels)
            else:
                logger.debug("No app context available for plugin UI visibility check")
            
        except Exception as e:
            # Log error but don't crash the UI
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating plugin UI visibility: {e}")

    def _refresh_tree(self) -> None:
        """Delegate to TreeRefreshCoordinator."""
        try:
            if getattr(self, "_tree_refresh", None) is not None:
                self._tree_refresh.refresh()  # type: ignore[attr-defined]
            return
        except Exception:
            pass
        # Fallback: clear tree if no coordinator
            try:
                self._tree.clear()
            except Exception:
                pass

    def _update_plugin_panel_buttons(self, available_panels: List[str]) -> None:
        """Update plugin panel buttons based on available panels.
        
        Args:
            available_panels: List of panel types available from current plugin
        """
        # Remove buttons for panels that are no longer available
        panels_to_remove = []
        for panel_type in self._plugin_panel_btns:
            if panel_type not in available_panels:
                panels_to_remove.append(panel_type)
        
        for panel_type in panels_to_remove:
            self._remove_plugin_panel_button(panel_type)
        
        # Add buttons for new panels
        for panel_type in available_panels:
            if panel_type not in self._plugin_panel_btns:
                self._create_plugin_panel_button(panel_type)
    
    def _create_plugin_panel_button(self, panel_type: str) -> None:
        """Create a button for a plugin panel.
        
        Args:
            panel_type: Type of panel to create button for
        """
        try:
            # Calculate grid position
            column = len(self._plugin_panel_btns)

            # Determine label/icon from plugin factory when available
            label = panel_type.replace('_', ' ').title()
            try:
                app_context = get_app_context()
                if app_context and hasattr(app_context, 'ui_registry'):
                    factory = app_context.ui_registry.get_panel_factory(panel_type)
                    if factory:
                        try:
                            if hasattr(factory, 'get_display_name'):
                                label = str(factory.get_display_name()) or label
                        except Exception:
                            pass
            except Exception:
                pass
            
            # Resolve plugin-provided emoji (preferred over image)
            try:
                emoji = None
                app_context2 = get_app_context()
                if app_context2 and hasattr(app_context2, 'ui_registry'):
                    factory2 = app_context2.ui_registry.get_panel_factory(panel_type)
                    if factory2:
                        if hasattr(factory2, 'get_button_emoji'):
                            emoji = str(factory2.get_button_emoji())
                        elif hasattr(factory2, 'get_emoji'):
                            emoji = str(factory2.get_emoji())
            except Exception:
                emoji = None
            
            # Create button with generic icon and tooltip
            button = ttk.Button(
                self._toggles_frame,
                text="🔧",  # generic tool icon for plugin panels
                command=lambda: self._on_plugin_panel_toggle_clicked(panel_type),
                width=3,
            )
            # Override default content with plugin-provided emoji or label
            try:
                display_text = (emoji if (isinstance(emoji, str) and emoji.strip()) else label)
                button.configure(text=display_text)
            except Exception:
                pass

            button.grid(row=0, column=column, padx=(0, 4))
            
            # Set tooltip
            try:
                button.tooltip_text = f"{label}"  # type: ignore[attr-defined]
            except Exception:
                pass
            
            self._plugin_panel_btns[panel_type] = button
            logger.info(f"Created plugin panel button for '{panel_type}'")
            
        except Exception as e:
            logger.error(f"Failed to create plugin panel button for '{panel_type}': {e}")
    
    def _remove_plugin_panel_button(self, panel_type: str) -> None:
        """Remove a plugin panel button.
        
        Args:
            panel_type: Type of panel to remove button for
        """
        try:
            if panel_type in self._plugin_panel_btns:
                # Close panel if it's currently active
                if self._active_plugin_panel == panel_type:
                    self._on_plugin_panel_close()
                
                # Destroy button
                button = self._plugin_panel_btns[panel_type]
                button.destroy()
                del self._plugin_panel_btns[panel_type]
                
                logger.info(f"Removed plugin panel button for '{panel_type}'")
                
        except Exception as e:
            logger.error(f"Failed to remove plugin panel button for '{panel_type}': {e}")
    
    def _on_plugin_panel_toggle_clicked(self, panel_type: str) -> None:
        """Handle plugin panel toggle button click.
        
        Args:
            panel_type: Type of panel to toggle
        """
        try:
            if self._active_plugin_panel == panel_type:
                # Close current panel
                self._on_plugin_panel_close()
            else:
                # Open/switch to this panel
                self._open_plugin_panel(panel_type)
                
        except Exception as e:
            logger.error(f"Error handling plugin panel toggle for '{panel_type}': {e}")

    def _open_plugin_panel(self, panel_type: str) -> None:
        """Open a specific plugin panel.
        
        Args:
            panel_type: Type of panel to open
        """
        try:
            # Close any currently active panel first
            if self._active_plugin_panel:
                self._on_plugin_panel_close()
            
            # Create and show the new panel using right panel coordinator
            if hasattr(self, '_right_panel') and self._right_panel:
                try:
                    self._right_panel.set_active(panel_type)
                except Exception:
                    try:
                        self._right_panel.set_active("preview")
                    except Exception:
                        pass
                self._active_plugin_panel = panel_type
                # Highlight the active plugin button
                try:
                    self._set_active_plugin_button(panel_type)
                except Exception:
                    pass
                self._filter_active = True  # For compatibility with existing logic
                # Initialize the newly opened panel with the current selection
                try:
                    self._update_active_plugin_panel_selection()
                except Exception:
                    pass
                
                logger.info(f"Opened plugin panel '{panel_type}'")
            
        except Exception as e:
            logger.error(f"Error opening plugin panel '{panel_type}': {e}")

    def _on_plugin_panel_close(self) -> None:
        """Handle plugin panel close event."""
        try:
            if hasattr(self, '_right_panel') and self._right_panel:
                try:
                    # Mirror preview toggle behavior: closing an active plugin panel goes to 'none'
                    self._right_panel.set_active("none")
                except Exception:
                    pass
            
            self._active_plugin_panel = None
            # Clear plugin button highlights
            try:
                self._set_active_plugin_button(None)
            except Exception:
                pass
            self._filter_active = False  # For compatibility with existing logic
            
            logger.info("Closed plugin panel")
            
        except Exception as e:
            logger.error(f"Error closing plugin panel: {e}")
    
    def _on_filter_close(self) -> None:
        """Handle filter panel close event (backward compatibility)."""
        self._on_plugin_panel_close()

    # def _set_initial_sash_position(self) -> None:
    #     """Deprecated; PanedLayoutCoordinator restores the sash."""
    #     try:
    #         if getattr(self, "_paned_coordinator", None) is not None:
    #             self._paned_coordinator.restore_sash()  # type: ignore[attr-defined]
    #     except Exception:
    #         pass

    def _update_style_legend(self) -> None:
        """Update the legend based on current search and style toggles."""
        try:
            # Determine whether search is active
            search_term = ""
            search_active = False
            try:
                if hasattr(self._search, 'get_search_term'):
                    search_term = self._search.get_search_term()
                    search_active = bool(search_term.strip())
            except Exception:
                pass
            
            # Get visible styles from the filter panel or the controller
            active_styles = {}
            try:
                if self._filter_panel is not None and hasattr(self._filter_panel, 'get_visible_styles'):
                    active_styles = self._filter_panel.get_visible_styles()
                elif self._controller is not None and hasattr(self._controller, 'get_style_visibility'):
                    active_styles = self._controller.get_style_visibility()
            except Exception:
                pass
            
            # Update the legend
            if hasattr(self._style_legend, 'update_legend'):
                self._style_legend.update_legend(
                    search_active=search_active,
                    active_styles=active_styles
                )
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Background execution helpers (minimal; keep UI thread clean)
    # ---------------------------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        """Set busy flag and show elegant spinner animation (replaces hourglass cursor)."""
        try:
            self._busy = bool(busy)
            # Use UniversalSpinner widget (automatically handles disabling)
            if hasattr(self, '_loading_spinner'):
                if self._busy:
                    self._loading_spinner.start()
                else:
                    self._loading_spinner.stop()
        except Exception:
            pass

    def _run_in_thread(self, work_fn, done_fn=None) -> None:
        """Run work_fn in a daemon thread; deliver result to done_fn via Tk after()."""
        def _runner():
            try:
                result = work_fn()
            except Exception:
                result = None
            try:
                self.after(0, (lambda r=result: done_fn(r) if callable(done_fn) else None))
            except Exception:
                pass
        try:
            threading.Thread(target=_runner, daemon=True).start()
        except Exception:
            # Fallback: execute inline as last resort
            try:
                res = work_fn()
                if callable(done_fn):
                    done_fn(res)
            except Exception:
                pass

    def _clear_depth_spin_selection(self) -> None:
        """Clear selection highlight in the depth spinbox without changing focus globally."""
        try:
            spin = getattr(self, "_depth_spin", None)
            if spin is None:
                return
            # Many ttk.Spinbox implementations support selection_clear
            try:
                spin.selection_clear()
            except Exception:
                # Fallback: focus a non-text widget to drop selection rendering
                try:
                    self.focus_set()
                except Exception:
                    pass
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
        # ---------------------------------------------------------------------------------
    # Depth control callback
    # ---------------------------------------------------------------------------------

    def _on_depth_changed(self) -> None:
        """Apply depth change asynchronously and refresh UI when done."""
        if not hasattr(self, "_depth_var"):
            return
        ctrl = self._controller
        if ctrl is None:
            return
        if getattr(self, "_busy", False):
            return
        
        # Ensure depth coordinator is loaded
        self._ensure_depth_coordinator()

        try:
            val = int(self._depth_var.get())
        except Exception:
            val = getattr(ctrl, "max_depth", 999)
        if val < 1:
            val = 1
        elif val > 999:
            val = 999
        try:
            if int(self._depth_var.get()) != val:
                self._depth_var.set(val)
        except Exception:
            try:
                self._depth_var.set(val)
            except Exception:
                pass

        # Pre-compute best-effort viewport target
        predicted_target: Optional[str] = None
        current_sel: List[str] = []
        try:
            if hasattr(ctrl, "get_selection"):
                current_sel = list(ctrl.get_selection())  # type: ignore[attr-defined]
            if current_sel:
                sel_ref = current_sel[0]
                predicted_target = self._predict_merge_target_href_for_ref(sel_ref)
        except Exception:
            predicted_target = None

        def _work():
            # Run only the controller mutation off the UI thread; defer all UI refresh to _done
            try:
                if hasattr(ctrl, "handle_depth_change"):
                    return bool(ctrl.handle_depth_change(val))
                return False
            except Exception:
                return False

        def _done(changed: Optional[bool]):
            try:
                if changed:
                    self._refresh_tree()
                    # Center viewport
                    try:
                        target_ref: Optional[str] = None
                        if current_sel:
                            try:
                                if hasattr(self._tree, 'find_item_by_ref') and self._tree.find_item_by_ref(current_sel[0]):  # type: ignore[attr-defined]
                                    target_ref = current_sel[0]
                            except Exception:
                                pass
                        if not target_ref:
                            target_ref = predicted_target
                        if target_ref and hasattr(self._tree, 'focus_item_centered_by_ref'):
                            self._tree.focus_item_centered_by_ref(target_ref)  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    # Re-apply search
                    try:
                        current_search_term = self._search.get_search_term()
                        if current_search_term.strip():
                            self._on_search_term_changed(current_search_term)
                    except Exception:
                        pass
                    # Update preview
                    try:
                        self._update_side_preview()
                    except Exception:
                        pass
            finally:
                self._set_busy(False)

        self._set_busy(True)
        self._run_in_thread(_work, _done)

    # ---------------------------------------------------------------------------------
    # Toolbar callbacks
    # ---------------------------------------------------------------------------------

    def _on_toolbar_move_clicked(self, direction: str) -> None:
        """Handle move operations from the toolbar and refresh tree.
        
        This method now supports both single-topic and multi-topic movement.
        For multi-topic movement, it validates that topics are consecutive
        and uses the appropriate controller method.
        """
        ctrl = self._controller
        if ctrl is None:
            return
        try:
            # Capture current selection before operation
            selected_elements = []
            try:
                selected_elements = self._tree.capture_current_selection()
            except Exception:
                pass
            
            # Prefer XML-centric movement
            if hasattr(ctrl, 'handle_move_selection'):
                result = ctrl.handle_move_selection(selected_elements, direction)  # type: ignore[attr-defined]
            else:
                # Legacy path: fall back to single-item operation
                result = ctrl.handle_move_operation(direction)

            if getattr(result, "success", False):
                # After successful move, refresh tree and maintain selection
                self._refresh_tree()
                # Restore selection using unified system
                try:
                    if selected_elements:
                        self._tree.restore_captured_selection(selected_elements)
                except Exception:
                    pass
            else:
                # Operation failed - optionally show error message in status area
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
        try:
            if getattr(self, "_search_coord", None) is not None:
                self._search_coord.term_changed(term)  # type: ignore[attr-defined]
                return
        except Exception:
            pass
        # No fallback: SearchCoordinator is the single entrance for search handling (DRY)
        return

    def _on_search_navigate(self, direction: "str") -> None:
        """Navigate among stored search results and update selection."""
        try:
            if getattr(self, "_search_coord", None) is not None:
                self._search_coord.navigate(direction)  # type: ignore[attr-defined]
                return
        except Exception:
            pass
        # No fallback: rely solely on SearchCoordinator for navigation
        return

    # ---------------------------------------------------------------------------------
    # Tree callbacks
    # ---------------------------------------------------------------------------------


    def _on_tree_selection_changed(self, selected_nodes: List[ET.Element]) -> None:
        """Update controller selection and toolbar enablement on selection change."""
        ctrl = self._controller
        if ctrl is None:
            return
        try:
            # Extract hrefs from XML nodes for controller (topic previews and legacy paths)
            refs = []
            for node in selected_nodes:
                if hasattr(node, 'get') and hasattr(node, 'tag') and node.tag == 'topicref':
                    href = node.get('href')
                    if href:
                        refs.append(href)
            ctrl.select_items(refs)
            # Cache XML nodes for preview and movement
            try:
                self._last_selected_xml_nodes = list(selected_nodes)
            except Exception:
                self._last_selected_xml_nodes = []  # type: ignore[assignment]
            # Enable toolbar only when selection contains movable nodes (topics or sections)
            movable = any(getattr(n, 'tag', None) in ('topicref', 'topichead') for n in (selected_nodes or []))
            self._toolbar.enable_buttons(bool(movable))
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

        # Also update any active plugin panel with the selected topic's videos
        try:
            if not hasattr(self, "_pending_plugin_panel_job"):
                self._pending_plugin_panel_job = None  # type: ignore[attr-defined]
            if getattr(self, "_pending_plugin_panel_job", None):
                try:
                    self.after_cancel(self._pending_plugin_panel_job)  # type: ignore[attr-defined]
                except Exception:
                    pass
            self._pending_plugin_panel_job = self.after(150, self._update_active_plugin_panel_selection)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _update_active_plugin_panel_selection(self) -> None:
        """If a plugin panel is active and supports topic-scoped data, update it.

        The panel contract is simple: set_topic_data(topic_element, dita_context)
        and clear_data() for non-topic selections.
        """
        try:
            # Ensure we have an active plugin panel and right panel coordination
            active_type = getattr(self, "_active_plugin_panel", None)
            rp = getattr(self, "_right_panel", None)
            ctrl = self._controller
            if not active_type or rp is None or ctrl is None:
                return

            panel = None
            try:
                panel = rp.get_plugin_panel(active_type)  # type: ignore[attr-defined]
            except Exception:
                panel = None
            if panel is None:
                return

            # Resolve current topic selection to a topic element
            topic_ref = self._get_first_selected_ref()
            ctx = getattr(ctrl, "context", None)
            if not topic_ref or not isinstance(topic_ref, str) or not ctx:
                if hasattr(panel, 'clear_data'):
                    try:
                        panel.clear_data()
                    except Exception:
                        pass
                return

            filename = None
            try:
                if topic_ref.startswith('topics/'):
                    filename = topic_ref.split('/')[-1]
            except Exception:
                filename = None

            if filename and hasattr(ctx, 'topics') and filename in ctx.topics:
                topic_el = ctx.topics.get(filename)
                if hasattr(panel, 'set_topic_data') and topic_el is not None:
                    try:
                        panel.set_topic_data(topic_el, ctx)
                    except Exception:
                        # Fall back to clearing to avoid stale items
                        try:
                            panel.clear_data()
                        except Exception:
                            pass
            else:
                # Non-topic selection (e.g., section); clear panel items
                if hasattr(panel, 'clear_data'):
                    try:
                        panel.clear_data()
                    except Exception:
                        pass
        except Exception:
            # Keep UI resilient
            pass

    def _on_tree_item_activated(self, xml_node: Optional[ET.Element]) -> None:
        """Handle activation (double-click/Enter) on a tree item and update preview.
        XML-centric: render for the activated node.
        """
        if xml_node is None:
            return
        try:
            if getattr(self, "_preview_coordinator", None) is not None and hasattr(self._preview_coordinator, 'render_for_node'):
                self._preview_coordinator.render_for_node(xml_node)  # type: ignore[attr-defined]
        except Exception:
            pass

    # Breadcrumb rendering is handled by PreviewCoordinator

    def _on_breadcrumb_clicked(self, nav_id: str) -> None:
        """Handle breadcrumb navigation click."""
        try:
            if nav_id.startswith("section_"):
                # Section navigation - select section directly using XML nodes
                for xml_node in self._tree._xml_node_to_id.keys():
                    try:
                        if (hasattr(xml_node, 'get') and hasattr(xml_node, 'tag') and
                            xml_node.tag == 'topichead' and 
                            xml_node.get('id') == nav_id.replace("section_", "")):
                            self._tree.update_selection_by_xml_nodes([xml_node])
                            break
                    except Exception:
                        continue
            else:
                # Topic navigation - select topic directly using XML nodes
                for xml_node in self._tree._xml_node_to_id.keys():
                    try:
                        if (hasattr(xml_node, 'get') and hasattr(xml_node, 'tag') and
                            xml_node.tag == 'topicref' and xml_node.get('href') == nav_id):
                            self._tree.update_selection_by_xml_nodes([xml_node])
                            # Render preview for the node
                            try:
                                if getattr(self, "_preview_coordinator", None) is not None and hasattr(self._preview_coordinator, 'render_for_node'):
                                    self._preview_coordinator.render_for_node(xml_node)  # type: ignore[attr-defined]
                            except Exception:
                                pass
                            break
                    except Exception:
                        continue
        except Exception:
            pass


    def _on_tree_context_menu(self, event: "tk.Event", selected_nodes: List[ET.Element]) -> None:
        """Ensure latest selection and show context menu via coordinator."""
        # Extract hrefs from XML nodes for context menu systems
        refs = []
        try:
            for node in selected_nodes:
                if hasattr(node, 'get') and hasattr(node, 'tag') and node.tag == 'topicref':
                    href = node.get('href')
                    if href:
                        refs.append(href)
        except Exception:
            pass
            
        try:
            if getattr(self, "_ctx_coordinator", None) is not None:
                self._ctx_coordinator.show(event, refs)  # type: ignore[attr-defined]
                return
        except Exception:
            pass
        # Fallback: retain old behavior if coordinator missing
        try:
            self._ctx_menu.show_context_menu(event, refs, context={})
        except Exception:
            pass

    def _on_context_action(self, action: str, payload: object) -> None:
        """Router for context menu actions emitted by coordinator."""
        try:
            if getattr(self, "_ctx_actions", None) is None:
                return
            if action == "style_action":
                self._ctx_actions.style_action(payload)  # type: ignore[arg-type]
            elif action == "merge_section":
                self._ctx_actions.merge_section(payload)  # type: ignore[arg-type]
            elif action == "rename_section":
                self._ctx_actions.rename_section(payload)  # type: ignore[arg-type]
            elif action == "delete_section":
                self._ctx_actions.delete_section(payload)  # type: ignore[arg-type]
            elif action == "add_section_below":
                self._ctx_actions.add_section_below(payload)  # type: ignore[arg-type]
            elif action == "add_section_inside":
                self._ctx_actions.add_section_inside(payload)  # type: ignore[arg-type]
            elif action == "send_topics_to":
                refs, target = payload  # type: ignore[misc]
                self._ctx_actions.send_topics_to(refs, target)
            elif action == "send_section_to":
                src, target = payload  # type: ignore[misc]
                self._ctx_actions.send_section_to(src, target)
            elif action == "send_sections_to":
                paths, target = payload  # type: ignore[misc]
                self._ctx_actions.send_sections_to(paths, target)
            elif action == "send_mixed_selection_to":
                topics, sections, target = payload  # type: ignore[misc]
                self._ctx_actions.send_mixed_selection_to(topics, sections, target)
        except Exception:
            pass

    def _open_destination_picker_for_topics(self, refs: List[str]) -> None:
        """Open a simple destination picker dialog for topics (lazy-loaded list)."""
        try:
            from orlando_toolkit.ui.dialogs.destination_picker import DestinationPicker
        except Exception:
            DestinationPicker = None  # type: ignore[assignment]
        if DestinationPicker is None:
            return
        try:
            ctrl = self._controller
            if ctrl is None:
                return
            # Build fresh destinations on open
            dests = ctrl.list_send_to_destinations()  # type: ignore[attr-defined]
            picker = DestinationPicker(self, destinations=dests)
            target = picker.show()
            if target is not None:
                self._ctx_send_topics_to(refs, target)
        except Exception:
            pass

    def _open_destination_picker_for_section(self, source_index_path: List[int]) -> None:
        """Open a simple destination picker dialog for moving a section."""
        try:
            from orlando_toolkit.ui.dialogs.destination_picker import DestinationPicker
        except Exception:
            DestinationPicker = None  # type: ignore[assignment]
        if DestinationPicker is None:
            return
        try:
            ctrl = self._controller
            if ctrl is None:
                return
            dests = ctrl.list_send_to_destinations()  # type: ignore[attr-defined]
            # Filter out self
            filt = []
            for d in dests:
                try:
                    ip = d.get("index_path")
                    if isinstance(ip, list) and ip == source_index_path:
                        continue
                    filt.append(d)
                except Exception:
                    continue
            picker = DestinationPicker(self, destinations=filt)
            target = picker.show()
            if target is not None:
                self._ctx_send_section_to(source_index_path, target)
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Context menu command handlers (wired per step 4/4)
    # ---------------------------------------------------------------------------------

    # Removed explicit Open handler; primary action remains style label when available

    # Legacy-specific topic/section handlers have been moved to ContextActions

    def _ctx_rename(self, refs: List[str]) -> None:
        try:
            if getattr(self, "_ctx_actions", None) is not None:
                self._ctx_actions.rename(refs)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _ctx_delete(self, refs: List[str]) -> None:
        try:
            if getattr(self, "_ctx_actions", None) is not None:
                self._ctx_actions.delete(refs)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _ctx_merge(self, refs: List[str]) -> None:
        try:
            if getattr(self, "_ctx_actions", None) is not None:
                self._ctx_actions.merge(refs)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _ctx_merge_section(self, index_path: List[int]) -> None:
        try:
            if getattr(self, "_ctx_actions", None) is not None:
                self._ctx_actions.merge_section(index_path)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _ctx_add_section_below(self, index_path: List[int]) -> None:
        try:
            if getattr(self, "_ctx_actions", None) is not None:
                self._ctx_actions.add_section_below(index_path)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _ctx_rename_section(self, index_path: List[int]) -> None:
        try:
            if getattr(self, "_ctx_actions", None) is not None:
                self._ctx_actions.rename_section(index_path)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _ctx_delete_section(self, index_path: List[int]) -> None:
        try:
            if getattr(self, "_ctx_actions", None) is not None:
                self._ctx_actions.delete_section(index_path)  # type: ignore[attr-defined]
        except Exception:
            pass

    # --------------------------- Send-to handlers ---------------------------
    def _ctx_send_topics_to(self, refs: List[str], target_index_path: Optional[List[int]]) -> None:
        try:
            if getattr(self, "_ctx_actions", None) is not None:
                self._ctx_actions.send_topics_to(refs, target_index_path)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _ctx_send_section_to(self, source_index_path: List[int], target_index_path: Optional[List[int]]) -> None:
        try:
            if getattr(self, "_ctx_actions", None) is not None:
                self._ctx_actions.send_section_to(source_index_path, target_index_path)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _ctx_send_sections_to(self, source_index_paths: List[List[int]], target_index_path: Optional[List[int]]) -> None:
        try:
            if getattr(self, "_ctx_actions", None) is not None:
                self._ctx_actions.send_sections_to(source_index_paths, target_index_path)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _open_destination_picker_for_sections(self, source_index_paths: List[List[int]]) -> None:
        try:
            from orlando_toolkit.ui.dialogs.destination_picker import DestinationPicker
        except Exception:
            DestinationPicker = None  # type: ignore[assignment]
        if DestinationPicker is None:
            return
        try:
            ctrl = self._controller
            if ctrl is None:
                return
            dests = ctrl.list_send_to_destinations()  # type: ignore[attr-defined]
            # Filter out any of the selected paths from choices
            skip = {tuple(p) for p in (source_index_paths or [])}
            filt = []
            for d in dests:
                try:
                    ip = d.get("index_path")
                    if isinstance(ip, list) and tuple(ip) in skip:
                        continue
                    filt.append(d)
                except Exception:
                    continue
            picker = DestinationPicker(self, destinations=filt)
            target = picker.show()
            if target is not None:
                self._ctx_send_sections_to(source_index_paths, target)
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Heading filter
    # ---------------------------------------------------------------------------------

    # Removed: legacy handler (replaced by toggle button path)

    # Removed: legacy ensure helper (logic unified in _set_active_panel)

    def _on_filter_close(self) -> None:
        # Hide filter panel, show preview panel back
        try:
            if self._filter_panel is not None:
                self._filter_panel.clear_selection()
                self._filter_panel.grid_remove()
            if self._preview_panel is not None:
                self._preview_panel.grid()
            try:
                self._tree.clear_filter_highlight_refs()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._set_toggle_states(True, False)
            
            # Update the legend to reflect hidden styles
            self._update_style_legend()
        except Exception:
            pass

    def _on_filter_apply(self, exclusions: dict[str, bool]) -> None:
        ctrl = self._controller
        if ctrl is None:
            return
        if getattr(self, "_busy", False):
            return
        try:
            if getattr(self, "_filter_coordinator", None) is not None:
                self._filter_coordinator.apply_with_ui(  # type: ignore[attr-defined]
                    dict(exclusions or {}),
                    run_in_thread=self._run_in_thread,
                    set_busy=self._set_busy,
                    refresh_tree=self._refresh_tree,
                    # XML-centric selection
                    get_current_selection=(lambda: list(self._tree.get_selected_xml_nodes() or [])),
                    # Predictor not required in XML path; provide no-op
                    predict_target=(lambda _node: None),
                )
                return
        except Exception:
            pass
        # Fallback to legacy implementation omitted for brevity

    def _on_filter_toggle_style(self, style: str, visible: bool) -> None:
        """Handle visibility toggle of a style within the filter panel."""
        try:
            ctrl = self._controller
            if ctrl is None:
                return
                
            # Update visibility in the controller
            ctrl.handle_style_visibility_toggle(style, visible)
            
            # Update markers in the tree widget
            style_visibility = ctrl.get_style_visibility()
            style_colors = ctrl.get_style_colors()
            
            self._tree.set_style_visibility(style_visibility)
            self._tree.update_style_colors(style_colors)
            # Keep filter panel icons in sync with unique color assignment
            try:
                if self._filter_panel is not None and hasattr(self._filter_panel, 'update_style_colors'):
                    self._filter_panel.update_style_colors(style_colors)  # type: ignore[attr-defined]
            except Exception:
                pass
            
            # Update the legend
            self._update_style_legend()
            
        except Exception:
            pass

    # Removed: heading analysis helpers moved to controller/service

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
            if getattr(self, "_right_panel", None) is not None:
                self._right_panel.set_active("preview")  # type: ignore[attr-defined]
            self._update_side_preview()
            return
        except Exception:
            pass
        # Fallback: just refresh preview content
        try:
            self._update_side_preview()
        except Exception:
            pass

    # def _restore_sash_position(self) -> None:
    #     """Deprecated; PanedLayoutCoordinator manages sash."""
    #     try:
    #         if getattr(self, "_paned_coordinator", None) is not None:
    #             self._paned_coordinator.restore_sash()  # type: ignore[attr-defined]
    #     except Exception:
    #         pass

    # def _safe_set_sash(self, pos: int) -> None:
    #     """Deprecated; PanedLayoutCoordinator manages sash."""
    #     try:
    #         if getattr(self, "_paned_coordinator", None) is not None:
    #             self._paned_coordinator.restore_sash()  # type: ignore[attr-defined]
    #     except Exception:
    #         pass

    # def _capture_sash_ratio(self) -> None:
    #     """Deprecated; PanedLayoutCoordinator captures ratios."""
    #     try:
    #         if getattr(self, "_paned_coordinator", None) is not None:
    #             self._paned_coordinator.capture_ratio()  # type: ignore[attr-defined]
    #     except Exception:
    #         pass

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
        try:
            if getattr(self, "_preview_coordinator", None) is not None:
                # Prefer XML-centric update using cached selection
                nodes = list(getattr(self, "_last_selected_xml_nodes", []) or [])
                self._preview_coordinator.update_for_selection(nodes)  # type: ignore[attr-defined]
                return
        except Exception:
            pass
        # No href fallback: if no nodes selected, clear panel
        try:
            panel.clear()
        except Exception:
            pass
        return

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
            if getattr(self, "_right_panel", None) is not None:
                next_kind = "none" if self._right_panel.kind() == "filter" else "filter"  # type: ignore[attr-defined]
                self._right_panel.set_active(next_kind)  # type: ignore[attr-defined]
                return
        except Exception:
            pass
        # Fallback
        try:
            self._set_active_panel("filter")
        except Exception:
            pass

    def _on_preview_toggle_clicked(self) -> None:
        """Toggle the preview panel on/off (hide if already visible)."""
        try:
            if getattr(self, "_right_panel", None) is not None:
                next_kind = "none" if self._right_panel.kind() == "preview" else "preview"  # type: ignore[attr-defined]
                self._right_panel.set_active(next_kind)  # type: ignore[attr-defined]
                return
        except Exception:
            pass
        # Fallback
        try:
                self._set_active_panel("preview")
        except Exception:
            pass

    def _set_toggle_states(self, preview_active: bool, filter_active: bool) -> None:
        try:
            self._preview_active = bool(preview_active)
            self._filter_active = bool(filter_active)
            # If preview becomes active, clear any notion of an active plugin panel
            if self._preview_active:
                try:
                    self._active_plugin_panel = None
                except Exception:
                    pass
            # If a filter panel is active but no plugin panel is marked, infer the filter panel type
            if self._filter_active and not self._preview_active and not self._active_plugin_panel:
                try:
                    app_context = get_app_context()
                    if app_context:
                        available_panels = app_context.get_document_source_plugin_panels()
                        for panel_type in list(available_panels or []):
                            try:
                                panel_factory = app_context.ui_registry.get_panel_factory(panel_type)
                                if not panel_factory:
                                    continue
                                role = getattr(panel_factory, 'get_role', lambda: None)()
                                if isinstance(role, str) and role.lower() == 'filter':
                                    self._active_plugin_panel = panel_type
                                    break
                            except Exception:
                                continue
                except Exception:
                    pass
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
            # Plugin panel buttons: highlight only the active plugin panel
            self._set_active_plugin_button(self._active_plugin_panel if not self._preview_active else None)
        except Exception:
            pass

    def _set_active_plugin_button(self, active_panel_type: Optional[str]) -> None:
        """Set Accent style on the active plugin panel button; reset others."""
        try:
            for p_type, btn in self._plugin_panel_btns.items():
                try:
                    btn.configure(style=("Accent.TButton" if (active_panel_type and p_type == active_panel_type) else "TButton"))
                except Exception:
                    continue
        except Exception:
            pass

    def _set_active_panel(self, kind: str) -> None:
        """Deprecated: maintained for fallback only; use RightPanelCoordinator."""
        try:
            if getattr(self, "_right_panel", None) is not None:
                self._right_panel.set_active(kind)  # type: ignore[attr-defined]
            if kind == "preview":
                try:
                    self._update_side_preview()
                except Exception:
                    pass
                return
        except Exception:
            pass
        # Fallback path is intentionally minimal: keep previous behavior via preview only
        try:
            if kind == "preview":
                self._on_show_preview()
            elif kind == "none":
                # Hide the right pane entirely
                paned = getattr(self, "_paned", None)
                right = getattr(self, "_right_pane", None)
                if paned is not None and right is not None:
                    try:
                        if str(right) in paned.panes():
                            paned.forget(right)
                    except Exception:
                        pass
                self._set_toggle_states(False, False)
        except Exception:
            pass

    # ---------------------------------------------------------------------------------
    # Merge target prediction for centering viewport
    # ---------------------------------------------------------------------------------

    def _predict_merge_target_href_for_ref(self, topic_ref: str) -> Optional[str]:
        from orlando_toolkit.ui.tabs.structure.navigation_utils import predict_merge_target_href_for_ref
        try:
            ctx = getattr(self._controller, 'context', None)
            return predict_merge_target_href_for_ref(ctx, self._tree, topic_ref)
        except Exception:
            return None

    def _collect_hrefs_from_topic_path(self, topic_ref: str) -> List[str]:
        try:
            ctrl = self._controller
            if ctrl is None or not hasattr(ctrl, 'get_topic_path'):
                return []
            path = ctrl.get_topic_path(topic_ref)
            hrefs = [href for (_title, href) in (path or []) if isinstance(href, str) and href]
            hrefs.reverse()
            return hrefs
        except Exception:
            return []

    # Removed: no button binds to this; keep preview refresh via mode/selection changes

    def _on_shortcut_move(self, direction: str) -> str:
        """Handle keyboard shortcut move operations (Alt+Up/Down).
        
        This method now supports both single-topic and multi-topic movement,
        similar to the toolbar handler.
        """
        ctrl = self._controller
        if ctrl is None:
            return "break"
        try:
            # Capture current selection before operation
            selected_elements = []
            try:
                selected_elements = self._tree.capture_current_selection()
            except Exception:
                pass
            
            # Get current selection for controller operations
            selected_refs = getattr(ctrl, "selected_items", []) or []
            
            # Handle based on selection size and type  
            if len(selected_refs) <= 1:
                # Prefer XML-centric movement for single/mixed selections
                if hasattr(ctrl, 'handle_move_selection'):
                    result = ctrl.handle_move_selection(selected_elements, direction)  # type: ignore[attr-defined]
                else:
                    result = ctrl.handle_move_operation(direction)  # OperationResult
            elif len(selected_refs) >= 2 and direction in ["up", "down"]:
                # Legacy path: fall back to single-item operation
                result = ctrl.handle_move_operation(direction)
            else:
                # Multi-selection for promote/demote - use single topic logic for now
                result = ctrl.handle_move_operation(direction)
            
            if getattr(result, "success", False):
                # After successful move, refresh tree and maintain selection
                self._refresh_tree()
                # Restore selection using unified system
                try:
                    if selected_elements:
                        self._tree.restore_captured_selection(selected_elements)
                except Exception:
                    pass
        except Exception:
            pass
        return "break"
