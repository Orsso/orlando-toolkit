from __future__ import annotations

import logging
from typing import Callable, Optional, Dict, Any

try:
    from orlando_toolkit.core.plugins.ui_registry import UIRegistry, PanelFactory
    from orlando_toolkit.core.context import get_app_context
except ImportError:
    # Graceful degradation if plugin system not available
    UIRegistry = None  # type: ignore
    PanelFactory = None  # type: ignore
    get_app_context = lambda: None  # type: ignore

logger = logging.getLogger(__name__)


class RightPanelCoordinator:
    """Coordinate right-side panel visibility (preview | filter | plugin panels | none).

    This orchestrates grid/show logic for the preview, filter, and plugin-provided panels,
    delegates sash management to a PanedLayoutCoordinator, and manages panel lifecycle
    including plugin panel creation and cleanup.

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
        Parent container where panels should be created.
    filter_coordinator : object
        FilterCoordinator instance.
    tree : object
        Structure tree widget (used for clearing filter highlights).
    ui_registry : Optional[UIRegistry]
        UI registry for plugin panel factories (optional for graceful degradation).
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
        ui_registry: Optional['UIRegistry'] = None,
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
        
        # Plugin panel support
        self._ui_registry = ui_registry
        self._plugin_panels: Dict[str, object] = {}
        self._plugin_panel_factories: Dict[str, PanelFactory] = {}
        
        # Initialize plugin support if available
        self._initialize_plugin_support()

    # ------------------------------------------------------------------
    def _initialize_plugin_support(self) -> None:
        """Initialize plugin panel support if UI registry is available."""
        if self._ui_registry is None:
            try:
                app_context = get_app_context()
                if app_context and hasattr(app_context, 'ui_registry'):
                    self._ui_registry = app_context.ui_registry
            except Exception as e:
                logger.debug(f"Plugin support not available: {e}")
        
        if self._ui_registry:
            self._refresh_plugin_panel_factories()
    
    def _refresh_plugin_panel_factories(self) -> None:
        """Refresh available plugin panel factories."""
        if not self._ui_registry:
            return
        
        try:
            # Get all registered panel types
            panel_types = self._ui_registry.get_registered_panel_types()
            
            # Update factory cache
            self._plugin_panel_factories.clear()
            for panel_type in panel_types:
                factory = self._ui_registry.get_panel_factory(panel_type)
                if factory:
                    self._plugin_panel_factories[panel_type] = factory
            
            logger.debug(f"Refreshed {len(self._plugin_panel_factories)} plugin panel factories")
            
        except Exception as e:
            logger.error(f"Error refreshing plugin panel factories: {e}")
    
    def _create_plugin_panel(self, panel_type: str) -> Optional[object]:
        """Create a plugin panel of the specified type.
        
        Args:
            panel_type: Type of plugin panel to create
            
        Returns:
            Created panel instance or None if creation fails
        """
        if not self._ui_registry:
            return None
        
        try:
            factory = self._plugin_panel_factories.get(panel_type)
            if not factory:
                logger.warning(f"No factory found for panel type '{panel_type}'")
                return None
            
            # Get app context for panel creation
            app_context = None
            try:
                app_context = get_app_context()
            except Exception:
                pass
            
            # Create panel with error isolation
            panel = factory.create_panel(self._container, app_context)
            logger.info(f"Created plugin panel '{panel_type}'")
            return panel
            
        except Exception as e:
            logger.error(f"Failed to create plugin panel '{panel_type}': {e}")
            return None
    
    def _cleanup_plugin_panel(self, panel_type: str) -> None:
        """Clean up a plugin panel.
        
        Args:
            panel_type: Type of plugin panel to clean up
        """
        if panel_type not in self._plugin_panels:
            return
        
        try:
            panel = self._plugin_panels[panel_type]
            
            # Call factory cleanup if available
            factory = self._plugin_panel_factories.get(panel_type)
            if factory:
                try:
                    factory.cleanup_panel(panel)
                except Exception as e:
                    logger.error(f"Error in factory cleanup for '{panel_type}': {e}")
            
            # Remove from grid
            try:
                if hasattr(panel, 'grid_remove'):
                    panel.grid_remove()
            except Exception as e:
                logger.error(f"Error removing panel from grid: {e}")
            
            # Clean up panel reference
            del self._plugin_panels[panel_type]
            logger.debug(f"Cleaned up plugin panel '{panel_type}'")
            
        except Exception as e:
            logger.error(f"Error cleaning up plugin panel '{panel_type}': {e}")
    
    def get_available_panel_types(self) -> list[str]:
        """Get list of all available panel types (core + plugin).
        
        Returns:
            List of available panel type identifiers
        """
        # Core panel types
        core_types = ['preview', 'filter', 'none']
        
        # Plugin panel types
        plugin_types = list(self._plugin_panel_factories.keys())
        
        return core_types + plugin_types
    
    def is_plugin_panel_type(self, panel_type: str) -> bool:
        """Check if panel type is provided by a plugin.
        
        Args:
            panel_type: Panel type to check
            
        Returns:
            True if panel type is provided by a plugin
        """
        return panel_type in self._plugin_panel_factories
    
    # ------------------------------------------------------------------
    def set_active(self, kind: str) -> None:
        """Switch active right panel between 'preview', 'filter', plugin panels, or 'none'."""
        if kind == "none":
            self._hide_all()
            self._set_toggles(False, False)
            self._kind = "none"
            return

        if kind == "preview":
            # Hide all other panels, show preview
            self._hide_all_panels()
            self._ensure_pane_present()
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

        if kind == "filter":
            # Hide all other panels, show filter
            self._hide_all_panels()
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
                    
            # Show filter panel
            try:
                if self._filter_panel is not None:
                    self._filter_panel.grid(row=0, column=0, sticky="nsew")
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
            return

        # Check if it's a plugin panel type
        if self.is_plugin_panel_type(kind):
            self._activate_plugin_panel(kind)
            return
        
        # Unknown panel type - default to preview
        logger.warning(f"Unknown panel type '{kind}', defaulting to preview")
        self.set_active("preview")

    def _hide_all_panels(self) -> None:
        """Hide all panels (core and plugin)."""
        # Hide filter panel
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
        
        # Hide preview panel
        try:
            self._preview_panel.grid_remove()
        except Exception:
            pass
        
        # Hide all plugin panels
        plugin_types_to_cleanup = list(self._plugin_panels.keys())
        for panel_type in plugin_types_to_cleanup:
            try:
                panel = self._plugin_panels[panel_type]
                if hasattr(panel, 'grid_remove'):
                    panel.grid_remove()
            except Exception as e:
                logger.error(f"Error hiding plugin panel '{panel_type}': {e}")

    def _activate_plugin_panel(self, panel_type: str) -> None:
        """Activate a plugin panel of the specified type.
        
        Args:
            panel_type: Type of plugin panel to activate
        """
        # Hide all other panels first
        self._hide_all_panels()
        self._ensure_pane_present()
        
        # Clear tree filter highlights
        try:
            if hasattr(self._tree, 'clear_filter_highlight_refs'):
                self._tree.clear_filter_highlight_refs()  # type: ignore[attr-defined]
        except Exception:
            pass
        
        # Create plugin panel if it doesn't exist
        if panel_type not in self._plugin_panels:
            panel = self._create_plugin_panel(panel_type)
            if panel is None:
                logger.error(f"Failed to create plugin panel '{panel_type}'")
                # Fallback to preview
                self.set_active("preview")
                return
            self._plugin_panels[panel_type] = panel
        
        # Show the plugin panel
        try:
            panel = self._plugin_panels[panel_type]
            panel.grid(row=0, column=0, sticky="nsew")
        except Exception as e:
            logger.error(f"Failed to show plugin panel '{panel_type}': {e}")
            # Fallback to preview
            self.set_active("preview")
            return
        
        # Set paned layout for plugin panel
        try:
            self._paned_layout.set_kind(panel_type)
        except Exception as e:
            logger.debug(f"Paned layout doesn't support '{panel_type}': {e}")
            # Try generic plugin layout
            try:
                self._paned_layout.set_kind("plugin")
            except Exception:
                # Fallback to filter layout
                try:
                    self._paned_layout.set_kind("filter")
                except Exception:
                    pass
        
        # Update toggle states (no specific toggle for plugin panels)
        self._set_toggles(False, False)
        self._kind = panel_type
        
        # Update legend
        try:
            self._update_legend()
        except Exception:
            pass
        
        logger.info(f"Activated plugin panel '{panel_type}'")

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
        """Hide all panels and set paned layout to none."""
        # Use the shared helper to hide all panels
        self._hide_all_panels()
        
        # Set paned layout to none
        try:
            self._paned_layout.set_kind("none")
        except Exception:
            pass
        
        # Clear tree filter highlights
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

    # Plugin lifecycle management
    def refresh_plugin_panels(self) -> None:
        """Refresh plugin panel availability.
        
        This should be called when plugins are loaded/unloaded to update
        the available panel types.
        """
        if not self._ui_registry:
            return
        
        # Get currently active plugin panel type if any
        current_plugin_type = None
        if self.is_plugin_panel_type(self._kind):
            current_plugin_type = self._kind
        
        # Refresh factory cache
        self._refresh_plugin_panel_factories()
        
        # If currently showing a plugin panel that's no longer available, switch to preview
        if current_plugin_type and current_plugin_type not in self._plugin_panel_factories:
            logger.info(f"Plugin panel '{current_plugin_type}' no longer available, switching to preview")
            self.set_active("preview")
    
    def cleanup_plugin_panels(self) -> None:
        """Clean up all plugin panels.
        
        This should be called during application shutdown or plugin unloading.
        """
        # Clean up all created plugin panels
        plugin_types_to_cleanup = list(self._plugin_panels.keys())
        for panel_type in plugin_types_to_cleanup:
            self._cleanup_plugin_panel(panel_type)
        
        # Clear factory cache
        self._plugin_panel_factories.clear()
        
        # If currently showing a plugin panel, switch to preview
        if self.is_plugin_panel_type(self._kind):
            self.set_active("preview")

    def get_plugin_panel(self, panel_type: str) -> Optional[object]:
        """Get a plugin panel instance if it exists.
        
        Args:
            panel_type: Type of plugin panel to get
            
        Returns:
            Plugin panel instance or None if not created
        """
        return self._plugin_panels.get(panel_type)
    
    def get_plugin_panels_info(self) -> Dict[str, Any]:
        """Get information about plugin panels.
        
        Returns:
            Dictionary with plugin panel information
        """
        return {
            'available_types': list(self._plugin_panel_factories.keys()),
            'created_panels': list(self._plugin_panels.keys()),
            'current_panel': self._kind if self.is_plugin_panel_type(self._kind) else None,
            'ui_registry_available': self._ui_registry is not None
        }


