# -*- coding: utf-8 -*-
"""Tk-based GUI front-end for Orlando Toolkit.

Main application widget providing the document conversion interface.
Exposes the :class:`OrlandoToolkit` widget, which is instantiated by ``run.py``.
"""

from __future__ import annotations

import logging
import os
import threading
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from copy import deepcopy

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.models.ui_config import (
    SplashLayoutConfig, ButtonConfig, SplashButtonConfig, IconConfig, 
    DEFAULT_SPLASH_LAYOUT, DEFAULT_ICONS
)
from orlando_toolkit.core.context import AppContext, set_app_context
from orlando_toolkit.core.services import ConversionService, StructureEditingService, UndoService, PreviewService, ProgressService
from orlando_toolkit.core.plugins.manager import PluginManager
from orlando_toolkit.core.plugins.loader import PluginLoader
from orlando_toolkit.core.plugins.registry import ServiceRegistry
from orlando_toolkit.core.plugins.ui_registry import UIRegistry
from orlando_toolkit.ui.metadata_tab import MetadataTab
from orlando_toolkit.ui.media_tab import MediaTab
from orlando_toolkit.ui.widgets.loading_spinner import LoadingSpinner
from orlando_toolkit.ui.widgets.metadata_form import MetadataForm
from orlando_toolkit.version import get_app_version
from orlando_toolkit.ui.dialogs.about_dialog import show_about_dialog

logger = logging.getLogger(__name__)

__all__ = ["OrlandoToolkit"]


class OrlandoToolkit:
    """Main application widget wrapping all Tkinter UI components."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.dita_context: Optional[DitaContext] = None
        
        # Store reference to this app instance in the root window for plugin dialog access
        self.root._orlando_toolkit_app = self
        
        # Initialize logger
        self._logger = logging.getLogger(f"{__name__}.OrlandoToolkit")
        
        # Plugin system integration
        self.service_registry = ServiceRegistry()
        self.ui_registry = UIRegistry()
        
        # Check for dev mode via environment variable
        dev_mode = os.getenv('ORLANDO_DEV_MODE', '').lower() in ('1', 'true', 'yes', 'on')
        if dev_mode:
            logger.info("DEV MODE ENABLED - Using local plugins from ./plugins/")
        
        self.plugin_loader = PluginLoader(self.service_registry, dev_mode=dev_mode)
        self.plugin_manager = PluginManager(self.plugin_loader)
        
        # Create AppContext with all services
        self.app_context = AppContext(
            service_registry=self.service_registry,
            plugin_manager=self.plugin_manager,
            ui_registry=self.ui_registry,
            app_instance=self
        )
        
        # Set global context for UI access (Context Bridge Pattern)
        set_app_context(self.app_context)
        
        # Plugin progress callback
        self._current_progress_callback = None
        
        # Update plugin loader to use the shared app_context
        self.plugin_loader.app_context = self.app_context
        
        # Create services with plugin integration
        self.service = ConversionService(service_registry=self.app_context.service_registry)
        self.structure_editing_service = StructureEditingService(app_context=self.app_context)
        self.undo_service = UndoService()
        self.preview_service = PreviewService()
        self.progress_service = ProgressService()
        
        # Update AppContext with services
        self.app_context.update_services(
            conversion_service=self.service,
            structure_editing_service=self.structure_editing_service,
            undo_service=self.undo_service,
            preview_service=self.preview_service,
            progress_service=self.progress_service
        )
        
        # UI configuration
        self.splash_layout = DEFAULT_SPLASH_LAYOUT
        self.icon_cache: dict[str, tk.PhotoImage] = {}

        # --- Widget references -----------------------------------------
        self.home_frame: Optional[ttk.Frame] = None
        self.loading_spinner: Optional[LoadingSpinner] = None
        self.status_label: Optional[ttk.Label] = None
        self.load_button: Optional[ttk.Button] = None
        self.notebook: Optional[ttk.Notebook] = None
        self.metadata_tab: Optional[MetadataTab] = None
        self.media_tab: Optional[MediaTab] = None
        self.structure_tab = None  # will be StructureTab
        self.main_actions_frame: Optional[ttk.Frame] = None
        # generation_progress removed - using main loading spinner
        # Inline metadata editor shown on the post-conversion summary screen
        self.inline_metadata: Optional[MetadataForm] = None
        self.home_center: Optional[ttk.Frame] = None
        self.buttons_container: Optional[ttk.Frame] = None
        self.loading_container: Optional[ttk.Frame] = None
        self.version_label: Optional[ttk.Label] = None

        # Initialize plugin system and load any previously activated plugins
        self._initialize_plugin_system()
        
        self.create_home_screen()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def _initialize_plugin_system(self) -> None:
        """Initialize plugin system and restore previously activated plugins."""
        try:
            # Discover all available plugins
            self.plugin_loader.discover_plugins()
            
            # Restore plugin activation states from previous session
            installed_plugins = self.plugin_manager.get_installed_plugins()
            self.plugin_manager.restore_plugin_states()
                    
            logger.info("Plugin system initialized with %d available plugins", len(installed_plugins))
            
        except Exception as e:
            logger.error("Failed to initialize plugin system: %s", e)

    # ------------------------------------------------------------------
    # Home / landing screen
    # ------------------------------------------------------------------

    def create_home_screen(self) -> None:
        """Create Google-inspired splash screen with prominent Open DITA button."""
        # Adjust window size for new layout while preserving centering
        width, height = self.splash_layout.window_size
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        pos_x = (screen_width // 2) - (width // 2)
        pos_y = (screen_height // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        
        self.home_frame = ttk.Frame(self.root)
        self.home_frame.pack(expand=True, fill="both")
        
        # Plugin management button in top-right corner
        self.create_management_button_top_right()

        # Main content area - centered like Google homepage
        self.home_center = ttk.Frame(self.home_frame)
        self.home_center.place(relx=0.5, rely=0.45, anchor="center")  # Slightly higher than center

        # Logo - smaller and cleaner
        self.create_logo()

        # Title section - cleaner, more focused
        title_frame = ttk.Frame(self.home_center)
        title_frame.pack(pady=(0, self.splash_layout.logo_to_main_spacing))
        
        ttk.Label(title_frame, text="Orlando Toolkit", 
                 font=("Segoe UI", 26, "bold"), foreground="#202124").pack()
        ttk.Label(title_frame, text="DITA Reader and Structure Editor", 
                 font=("Segoe UI", 13), foreground="#5f6368").pack(pady=(8, 0))
        
        # Container for buttons that will be replaced during loading
        self.buttons_container = ttk.Frame(self.home_center)
        self.buttons_container.pack()
        
        # Main prominent "Open DITA" button - Google search box style
        self.create_main_open_dita_button()
        
        # Plugin buttons underneath - like Google's suggestion buttons
        self.create_plugin_buttons_google_style()

        # Status and utility elements at bottom
        self.create_status_elements()
        
        # Version label in bottom-right
        self.create_version_label()

    def create_management_button_top_right(self) -> None:
        """Create plugin management button in top-right corner."""
        # Create custom style for management button - subtle but clickable
        style = ttk.Style()
        style.configure("Management.TButton",
                       padding=(8, 8),
                       borderwidth=1,
                       relief="solid")
        style.map("Management.TButton",
                 background=[("active", "#f8f9fa"), ("pressed", "#e8eaed")],
                 bordercolor=[("focus", "#4285f4"), ("active", "#dadce0"), ("!focus", "#e0e0e0")],
                 relief=[("pressed", "sunken")])
        
        # Create button with gear emoji (no image)
        mgmt_button = ttk.Button(
            self.home_frame,
            text="⚙",  # Gear emoji
            command=self.show_plugin_management,
            style="Management.TButton",
            width=3
        )
        
        mgmt_button.place(relx=1.0, rely=0.0, x=-self.splash_layout.management_button_padding, 
                         y=self.splash_layout.management_button_padding, anchor="ne")
        
        # Add keyboard support for accessibility
        mgmt_button.bind("<Return>", lambda e: self.show_plugin_management())
        mgmt_button.bind("<space>", lambda e: self.show_plugin_management())
        
        self._add_tooltip(mgmt_button, "Manage Plugins")

    def create_logo(self) -> None:
        """Create and display the application logo."""
        try:
            logo_path = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
            if logo_path.exists():
                logo_img = tk.PhotoImage(file=logo_path)
                # Scale logo to smaller, cleaner size
                try:
                    h = logo_img.height()
                    target_h = self.splash_layout.logo_max_height
                    if h > target_h:
                        factor = max(2, int(round(h / float(target_h))))
                        logo_img = logo_img.subsample(factor, factor)
                except Exception:
                    pass
                logo_lbl = ttk.Label(self.home_center, image=logo_img)
                logo_lbl.image = logo_img  # keep reference
                logo_lbl.pack(pady=(0, 20))
        except Exception as exc:
            logger.warning("Could not load logo: %s", exc)

    def create_main_open_dita_button(self) -> None:
        """Create the prominent main Open DITA button - Google search box style."""
        # Container for the main button with shadow effect
        main_button_frame = ttk.Frame(self.buttons_container)
        main_button_frame.pack(pady=(0, self.splash_layout.main_to_plugin_spacing))
        
        # Main button using the app's accent style for proper blue appearance
        main_button = ttk.Button(
            main_button_frame,
            text="Open DITA Project",
            command=self.open_dita_project,
            style="Accent.TButton"
        )
        main_button.pack(ipadx=20, ipady=15)  # Add padding for prominent appearance
        
        self._add_tooltip(main_button, "Open existing DITA project archive")

    def create_plugin_buttons_google_style(self) -> None:
        """Create plugin buttons underneath main button - Google suggestions style."""
        try:
            active_plugin_configs = self.plugin_manager.get_active_pipeline_plugins()
            
            if not active_plugin_configs:
                return
                
            # Container for plugin buttons with proper spacing from main button
            plugin_frame = ttk.Frame(self.buttons_container)
            plugin_frame.pack(pady=(self.splash_layout.main_to_plugin_spacing//2, 10))
            
            # Create style for plugin buttons - smaller, subtle, Google-like
            style = ttk.Style()
            style.configure("PluginAction.TButton",
                           font=("Segoe UI", 10),
                           padding=(12, 8),
                           borderwidth=1,
                           relief="solid")
            style.map("PluginAction.TButton",
                     background=[("active", "#f8f9fa"), ("pressed", "#e8eaed"), ("!active", "#ffffff")],
                     bordercolor=[("focus", "#4285f4"), ("active", "#dadce0"), ("!active", "#e0e0e0")],
                     relief=[("pressed", "sunken")])
            
            # Arrange plugins in rows with centered alignment
            col = 0
            row = 0
            current_row_frame = None
            buttons_per_row = self.splash_layout.plugin_buttons_per_row
            
            for plugin_config in active_plugin_configs:
                if col == 0:
                    # Start new row - center aligned for Google-like appearance
                    current_row_frame = ttk.Frame(plugin_frame)
                    current_row_frame.pack(pady=self.splash_layout.plugin_rows_spacing//2)
                
                try:
                    plugin_id = plugin_config['plugin_id']
                    icon_image = self._load_icon(plugin_config.get('icon', 'default-plugin-icon.png'), plugin_id)
                    
                    # Get button text with proper formatting
                    button_text = plugin_config.get('button_text', plugin_config.get('display_name', plugin_id))
                    
                    plugin_button = ttk.Button(
                        current_row_frame,
                        text=button_text,
                        image=icon_image,
                        compound="left",
                        command=lambda p_id=plugin_id: self.launch_plugin_workflow(p_id),
                        style="PluginAction.TButton"
                    )
                    plugin_button.pack(side="left", padx=self.splash_layout.plugin_button_padding[0])
                    
                    # Store image reference to prevent garbage collection
                    if icon_image:
                        plugin_button.image = icon_image
                    
                    # Add tooltip with proper fallback text
                    tooltip_text = plugin_config.get('tooltip', 
                                                   plugin_config.get('description', 
                                                                   f'Import using {plugin_config.get("display_name", plugin_id)}'))
                    self._add_tooltip(plugin_button, tooltip_text)
                    
                    col += 1
                    if col >= buttons_per_row:
                        col = 0
                        row += 1
                        
                except Exception as e:
                    logger.warning("Failed to create plugin button for %s: %s", plugin_config, e)
                    continue
                    
        except Exception as e:
            logger.error("Failed to create plugin buttons: %s", e)

    def create_status_elements(self) -> None:
        """Create status label and progress bar."""
        # Status label for feedback
        self.status_label = ttk.Label(self.home_center, text="", font=("Segoe UI", 10))
        self.status_label.pack(pady=(20, 5))

        # Initialize unified progress callback system
        if not hasattr(self, "_progress_callback_initialized"):
            self._progress_callback = self._create_smart_progress_callback()
            self._progress_callback_initialized = True

        # LoadingSpinner will be created on-demand

    def _create_smart_progress_callback(self) -> callable:
        """Create progress callback that updates LoadingSpinner when visible, status_label otherwise."""
        def smart_progress_callback(message: str) -> None:
            """Update either LoadingSpinner subtitle or status label based on visibility."""
            try:
                # If LoadingSpinner is visible, update its subtitle
                if hasattr(self, 'loading_spinner') and self.loading_spinner and self.loading_spinner.is_visible():
                    self.root.after(0, lambda: self.loading_spinner.update_subtitle_only(message))
                # Otherwise update the status label
                elif self.status_label and self.status_label.winfo_exists():
                    self.root.after(0, lambda: self.status_label.config(text=message))
            except Exception:
                pass
        return smart_progress_callback

    def _show_loading_spinner(self, title: str = "Loading", subtitle: str = "Please wait...") -> None:
        """Show loading spinner with custom message, replacing buttons but keeping logo/title."""
        try:
            # Hide the buttons container
            if hasattr(self, 'buttons_container') and self.buttons_container:
                self.buttons_container.pack_forget()
            
            # Create a new container in the same location as buttons for the spinner
            if not hasattr(self, 'loading_container') or not self.loading_container:
                self.loading_container = ttk.Frame(self.home_center)
                self.loading_container.pack()
            
            # Create spinner targeting the loading container
            if not self.loading_spinner:
                self.loading_spinner = LoadingSpinner(self.loading_container, title=title, subtitle=subtitle)
            if self.loading_spinner:
                self.loading_spinner.update_message(title, subtitle)
                self.loading_spinner.show()
        except Exception:
            pass

    def _hide_loading_spinner(self) -> None:
        """Hide loading spinner and restore buttons."""
        try:
            if self.loading_spinner:
                self.loading_spinner.hide()
            
            # Remove the loading container
            if hasattr(self, 'loading_container') and self.loading_container:
                self.loading_container.destroy()
                self.loading_container = None
            
            # Restore the buttons container
            if hasattr(self, 'buttons_container') and self.buttons_container:
                self.buttons_container.pack()
        except Exception:
            pass

    def create_version_label(self) -> None:
        """Create version label in bottom-right corner."""
        try:
            version_text = get_app_version()
            if self.version_label is None or not self.version_label.winfo_exists():
                self.version_label = ttk.Label(self.home_frame, text=version_text, 
                                             font=("Segoe UI", 9), foreground="#888888")
                self.version_label.place(relx=1.0, rely=1.0, x=-8, y=-6, anchor="se")
            else:
                self.version_label.configure(text=version_text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI State Management
    # ------------------------------------------------------------------
    
    def _disable_all_ui_elements(self) -> None:
        """Comprehensively disable all interactive UI elements during processing.
        
        This method recursively traverses the entire widget hierarchy and disables
        all interactive elements to prevent user input during background processing.
        Provides professional desktop application behavior during processing.
        """
        def _disable_widget_recursive(widget):
            """Recursively disable a widget and all its children."""
            try:
                # Skip labels with images (like logo) - they should remain visual-only
                if isinstance(widget, ttk.Label) and hasattr(widget, 'image') and widget.image:
                    pass  # Don't disable logo labels
                # Try to disable interactive widgets only
                elif hasattr(widget, 'config'):
                    try:
                        # Check if widget supports 'state' config option
                        current_state = widget.cget('state')
                        widget.config(state='disabled')
                    except tk.TclError:
                        # Widget doesn't support state configuration
                        pass
                
                # Disable all children recursively
                if hasattr(widget, 'winfo_children'):
                    for child in widget.winfo_children():
                        _disable_widget_recursive(child)
                        
            except Exception as e:
                # Continue processing other widgets even if one fails
                logger.debug("Failed to disable widget %s: %s", widget.__class__.__name__, e)
        
        # Disable all children of the home frame
        if self.home_frame and self.home_frame.winfo_exists():
            _disable_widget_recursive(self.home_frame)
        
        # Disable the root window's menu if it exists
        try:
            if hasattr(self.root, 'config'):
                menu = self.root.cget('menu')
                if menu:
                    menu.config(state='disabled')
        except Exception:
            pass
    
    def _enable_all_ui_elements(self) -> None:
        """Re-enable all UI elements after processing completes.
        
        This method traverses the widget hierarchy and re-enables elements
        that were disabled during processing. It's called after successful
        completion or failure to restore normal UI interaction.
        """
        def _enable_widget_recursive(widget):
            """Recursively enable a widget and all its children."""
            try:
                # Skip labels with images (like logo) - they were never disabled
                if isinstance(widget, ttk.Label) and hasattr(widget, 'image') and widget.image:
                    pass  # Don't change logo labels
                # Try to enable interactive widgets only
                elif hasattr(widget, 'config'):
                    try:
                        # Check if widget supports 'state' config option
                        widget.config(state='normal')
                    except tk.TclError:
                        # Widget doesn't support state configuration or should stay disabled
                        pass
                
                # Enable all children recursively
                if hasattr(widget, 'winfo_children'):
                    for child in widget.winfo_children():
                        _enable_widget_recursive(child)
                        
            except Exception as e:
                # Continue processing other widgets even if one fails
                logger.debug("Failed to enable widget %s: %s", widget.__class__.__name__, e)
        
        # Enable all children of the home frame
        if self.home_frame and self.home_frame.winfo_exists():
            _enable_widget_recursive(self.home_frame)
        
        # Re-enable the root window's menu if it exists
        try:
            if hasattr(self.root, 'config'):
                menu = self.root.cget('menu')
                if menu:
                    menu.config(state='normal')
        except Exception:
            pass

    def _handle_plugin_failure(self, error_message: str, filepath: str) -> None:
        """Handle plugin processing failure with proper UI cleanup and user feedback.
        
        Args:
            error_message: Descriptive error message for user
            filepath: Path to the file that failed processing
        """
        # Stop progress indicators
        self._hide_loading_spinner()
        
        # Reset status label
        if self.status_label:
            self.status_label.config(text="Plugin processing failed. Please try again.")
        
        # Re-enable all UI elements
        self._enable_all_ui_elements()
        
        # Show error dialog
        messagebox.showerror("Plugin Processing Error", error_message)
    
    # ------------------------------------------------------------------
    # Plugin Integration and Workflow Management
    # ------------------------------------------------------------------
    
    
    def get_active_pipeline_plugins(self) -> list[str]:
        """Get list of active pipeline plugin IDs (DEPRECATED - use plugin_manager.get_active_pipeline_plugins()).
        
        Returns:
            List of active pipeline plugin identifiers
        """
        try:
            # Delegate to plugin manager for consistent behavior
            active_plugin_configs = self.plugin_manager.get_active_pipeline_plugins()
            return [config['plugin_id'] for config in active_plugin_configs]
        except Exception as e:
            logger.error("Failed to get active plugins: %s", e)
            return []
    
    def _get_plugin_button_config(self, plugin_id: str) -> SplashButtonConfig:
        """Get button configuration for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Button configuration for the plugin
        """
        # Pure discovery model - only get from loaded plugin metadata
        try:
            plugin_info = self.plugin_loader.get_plugin_info(plugin_id)
            if plugin_info and plugin_info.metadata:
                metadata_dict = plugin_info.metadata.__dict__
                return SplashButtonConfig.from_plugin_metadata(
                    plugin_id, metadata_dict,
                    command=lambda: self.launch_plugin_workflow(plugin_id)
                )
        except Exception as e:
            logger.warning("Failed to get plugin metadata for %s: %s", plugin_id, e)
        
        # Fallback configuration
        return SplashButtonConfig(
            text="Import",
            icon="default-plugin-icon.png",
            tooltip=f"Import content using {plugin_id}",
            plugin_id=plugin_id,
            command=lambda: self.launch_plugin_workflow(plugin_id)
        )
    
    def _load_icon(self, icon_name: str, plugin_id: Optional[str] = None) -> Optional[tk.PhotoImage]:
        """Load an icon with plugin-specific support and fallback handling.
        
        Icon resolution hierarchy:
        1. Plugin Directory: ~/.orlando_toolkit/plugins/{plugin_id}/{icon_name}
        2. App Assets: assets/icons/{icon_name}  
        3. Default Fallback: assets/icons/default-plugin-icon.png
        
        Args:
            icon_name: Icon filename
            plugin_id: Optional plugin ID for plugin-specific icon lookup
            
        Returns:
            PhotoImage instance or None if loading fails
        """
        # Create cache key that includes plugin_id for proper isolation
        cache_key = f"{plugin_id}:{icon_name}" if plugin_id else icon_name
        
        # Check cache first
        if cache_key in self.icon_cache:
            return self.icon_cache[cache_key]
        
        icon_path = None
        
        try:
            # Step 1: Plugin Directory - Look for plugin-specific icons first
            if plugin_id:
                from orlando_toolkit.core.plugins.loader import get_user_plugins_dir
                plugin_dir = get_user_plugins_dir() / plugin_id
                
                # First try the metadata-specified icon name
                plugin_icon_path = plugin_dir / icon_name
                if plugin_icon_path.exists():
                    icon_path = plugin_icon_path
                    logger.debug("Using plugin-specific icon: %s", plugin_icon_path)
                # If metadata-specified icon doesn't exist, try standard plugin-icon.png
                elif icon_name != "plugin-icon.png":
                    standard_icon_path = plugin_dir / "plugin-icon.png"
                    if standard_icon_path.exists():
                        icon_path = standard_icon_path
                        logger.debug("Using standard plugin icon: %s", standard_icon_path)
            
            # Step 2: App Assets - Look in app assets directory
            if not icon_path:
                assets_icon_path = Path(__file__).resolve().parent.parent / "assets" / "icons" / icon_name
                if assets_icon_path.exists():
                    icon_path = assets_icon_path
                    logger.debug("Using app assets icon: %s", assets_icon_path)
            
            # Step 3: Default Fallback - Use default plugin icon
            if not icon_path:
                default_icon_path = Path(__file__).resolve().parent.parent / "assets" / "icons" / "default-plugin-icon.png"
                if default_icon_path.exists():
                    icon_path = default_icon_path
                    logger.debug("Using default fallback icon: %s", default_icon_path)
            
            # Load and process the icon if we found one
            if icon_path and icon_path.exists():
                icon_image = tk.PhotoImage(file=icon_path)
                # Scale icon to fit in button (48x48)
                try:
                    icon_config = DEFAULT_ICONS.get(icon_name, IconConfig(icon_name))
                    target_size = icon_config.size
                    
                    # Simple subsample scaling if image is too large
                    w, h = icon_image.width(), icon_image.height()
                    if w > target_size[0] * 2 or h > target_size[1] * 2:
                        factor = max(2, max(w // target_size[0], h // target_size[1]))
                        icon_image = icon_image.subsample(factor, factor)
                except Exception:
                    pass  # Use original size if scaling fails
                
                self.icon_cache[cache_key] = icon_image
                return icon_image
            else:
                logger.debug("No icon found for %s (plugin: %s)", icon_name, plugin_id)
                
        except Exception as e:
            logger.warning("Failed to load icon %s for plugin %s: %s", icon_name, plugin_id, e)
        
        return None
    
    def _add_tooltip(self, widget: tk.Widget, text: str) -> None:
        """Add tooltip to a widget.
        
        Args:
            widget: Widget to add tooltip to
            text: Tooltip text
        """
        # Simple tooltip implementation
        def on_enter(event):
            try:
                # Create tooltip window
                tooltip = tk.Toplevel()
                tooltip.wm_overrideredirect(True)
                tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
                label = ttk.Label(tooltip, text=text, background="lightyellow", 
                                relief="solid", borderwidth=1)
                label.pack()
                widget.tooltip = tooltip
            except Exception:
                pass
        
        def on_leave(event):
            try:
                if hasattr(widget, 'tooltip'):
                    widget.tooltip.destroy()
                    delattr(widget, 'tooltip')
            except Exception:
                pass
        
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
    
    def _refresh_splash_screen(self) -> None:
        """Refresh the splash screen to reflect plugin changes."""
        try:
            # Ensure plugin states are synchronized before refresh
            self._synchronize_plugin_states()
            
            # Destroy current home frame
            if self.home_frame:
                self.home_frame.destroy()
            
            # Recreate splash screen
            self.create_home_screen()
            
            logger.info("Splash screen refreshed")
            
        except Exception as e:
            logger.error("Failed to refresh splash screen: %s", e)
    
    def _synchronize_plugin_states(self) -> None:
        """Synchronize plugin states between loader and manager for consistent display."""
        try:
            if not self.plugin_manager or not self.plugin_loader:
                return
                
            # This forces the plugin manager to re-check states from loader
            # The improved is_plugin_active method now correctly uses PluginInfo.is_active()
            active_count = len(self.plugin_manager.get_active_plugin_ids())
            logger.debug("Plugin state synchronization complete - %d active plugins", active_count)
            
        except Exception as e:
            logger.warning("Failed to synchronize plugin states: %s", e)
    
    # ------------------------------------------------------------------
    # Plugin Management and Workflow Integration
    # ------------------------------------------------------------------
    
    def show_plugin_management(self) -> None:
        """Show plugin management dialog."""
        try:
            from orlando_toolkit.ui.dialogs.plugin_manager_dialog import PluginManagerDialog
            
            dialog = PluginManagerDialog(self.root, self.plugin_manager)
            result = dialog.show_modal()
            
            # Handle dialog result
            if result:
                self._logger.info("Plugin management dialog closed with result: %s", result)
                
                # Refresh plugin buttons if plugins were modified
                if result.get("action") in ["install", "uninstall", "import"]:
                    self._refresh_splash_screen()
        
        except Exception as e:
            self._logger.error("Failed to show plugin management dialog: %s", e)
            messagebox.showerror(
                "Plugin Management Error",
                f"Failed to open plugin management:\n\n{e}"
            )
    
    def open_dita_project(self) -> None:
        """Open existing DITA project from ZIP archive."""
        # Get supported formats for DITA import
        try:
            dita_formats = [fmt for fmt in self.service.get_supported_formats() 
                           if fmt.description and 'DITA' in fmt.description]
            
            if dita_formats:
                # Build file type list for dialog
                filetypes = []
                for fmt in dita_formats:
                    filetypes.append((fmt.description, f"*{fmt.extension}"))
                filetypes.append(("All files", "*.*"))
            else:
                # Fallback to ZIP only
                filetypes = [("ZIP Archives", "*.zip"), ("All files", "*.*")]
                
        except Exception as e:
            logger.warning("Failed to get supported formats for DITA import: %s", e)
            filetypes = [("ZIP Archives", "*.zip"), ("All files", "*.*")]
        
        filepath = filedialog.askopenfilename(
            title="Select a DITA Project Archive", 
            filetypes=filetypes
        )
        if not filepath:
            return
        
        # Check if file is supported
        if not self.service.can_handle_file(filepath):
            messagebox.showerror(
                "Unsupported File Type",
                f"The selected file type is not supported:\n{Path(filepath).name}\n\n"
                f"Supported formats:\n" + 
                "\n".join(f"• {fmt.description} ({fmt.extension})" 
                         for fmt in self.service.get_supported_formats())
            )
            return
        
        # Import DITA project using conversion service
        if self.status_label:
            self.status_label.config(text="")
        self._show_loading_spinner("Opening DITA Project", "")

        # Comprehensively disable all UI elements during processing
        self._disable_all_ui_elements()

        # Extract metadata from filename for initial setup
        initial_metadata = {
            "manual_title": Path(filepath).stem,
            "revision_date": datetime.now().strftime("%Y-%m-%d"),
            # No default revision_number so the package is treated as an edition
        }

        threading.Thread(target=self.run_dita_import_thread, args=(filepath, initial_metadata), daemon=True).start()
    
    def launch_plugin_workflow(self, plugin_id: str) -> None:
        """Launch workflow for a specific plugin.
        
        Args:
            plugin_id: ID of plugin to launch
        """
        try:
            logger.info("Launching plugin workflow for: %s", plugin_id)
            
            # Get plugin metadata to determine supported formats
            plugin_metadata = self.plugin_manager.get_plugin_metadata(plugin_id)
            if not plugin_metadata:
                messagebox.showerror(
                    "Plugin Error", 
                    f"Could not find metadata for plugin: {plugin_id}"
                )
                return
            
            # Build file dialog from plugin's supported formats
            filetypes = []
            if plugin_metadata.supported_formats:
                for fmt in plugin_metadata.supported_formats:
                    if isinstance(fmt, dict):
                        extension = fmt.get("extension", "")
                        description = fmt.get("description", f"{extension.upper()} files")
                        if extension:
                            filetypes.append((description, f"*{extension}"))
            
            if not filetypes:
                # Fallback to all files if no formats specified
                filetypes = [("All files", "*.*")]
            else:
                filetypes.append(("All files", "*.*"))  # Always add all files option
            
            # Choose title based on plugin name
            title = f"Select file for {plugin_metadata.display_name}"
            
            # Open file dialog with plugin-specific formats
            filepath = filedialog.askopenfilename(title=title, filetypes=filetypes)
            if not filepath:
                return
            
            # Get plugin's document handler from service registry
            document_handlers = self.service_registry.get_document_handlers()
            plugin_handler = None
            
            for handler in document_handlers:
                handler_plugin_id = self.service_registry.get_plugin_for_handler(handler)
                if handler_plugin_id == plugin_id:
                    plugin_handler = handler
                    break
            
            if plugin_handler:
                # Use plugin's document handler to process the file
                logger.info("Processing file %s with plugin %s", filepath, plugin_id)
                
                # Show loading UI like regular DITA opening
                if self.status_label:
                    self.status_label.config(text="")
                self._show_loading_spinner("Converting Document", "")
                
                # Comprehensively disable all UI elements during processing
                self._disable_all_ui_elements()
                
                # Process in background thread like regular DITA opening
                metadata = {
                    "manual_title": Path(filepath).stem,
                    "revision_date": datetime.now().strftime("%Y-%m-%d"),
                }
                
                threading.Thread(
                    target=self.run_plugin_processing_thread,
                    args=(plugin_handler, filepath, metadata, plugin_id),
                    daemon=True
                ).start()
            else:
                # No document handler found - plugin may not be fully loaded
                messagebox.showwarning(
                    "Plugin Not Ready", 
                    f"Plugin {plugin_metadata.display_name} does not have a document handler registered.\n\n"
                    f"The plugin may need to be reactivated or may have loading issues."
                )
            
        except Exception as e:
            logger.error("Failed to launch plugin workflow for %s: %s", plugin_id, e)
            messagebox.showerror(
                "Plugin Error", 
                f"Failed to launch plugin {plugin_id}:\n\n{e}"
            )

    def _create_progress_callback(self) -> callable:
        """Create thread-safe progress callback for all processing types."""
        return self._progress_callback

    def run_plugin_processing_thread(self, plugin_handler, filepath: str, metadata: dict, plugin_id: str) -> None:
        """Run plugin processing in background thread (like regular DITA opening).
        
        Args:
            plugin_handler: Plugin's document handler
            filepath: Path to file to process
            metadata: Conversion metadata
            plugin_id: ID of the plugin
        """
        try:
            logger.info("Background plugin processing started for %s", plugin_id)
            
            # Create progress callback for the plugin
            progress_callback = self._create_progress_callback()
            
            # Call the plugin's document handler with progress callback
            logger.info("Calling convert_to_dita with progress callback")
            result = plugin_handler.convert_to_dita(Path(filepath), metadata, progress_callback)
            logger.info("Plugin returned result type: %s", type(result).__name__)
            
            if not result:
                logger.error("Plugin processing returned no result")
                self.root.after(0, lambda: self._handle_plugin_failure("Plugin failed to process the file", filepath))
                return
                
            logger.info("Finalizing DITA conversion")
            
            # Store plugin ID in the DitaContext for UI availability checks
            if hasattr(result, 'plugin_data'):
                result.plugin_data['_source_plugin'] = plugin_id
                logger.debug("Stored source plugin ID: %s in plugin_data", plugin_id)
            else:
                logger.warning("Result has no plugin_data attribute to store source plugin ID")
            
            # Load the converted content into the app
            logger.info("Loading converted content")
            self._load_conversion_result(result, filepath)
            logger.info("Plugin conversion completed successfully")
                
        except Exception as e:
            logger.error("Plugin processing failed: %s", e)
            error_msg = f"Failed to process file:\n\n{e}"
            self.root.after(0, lambda msg=error_msg: self._handle_plugin_failure(msg, filepath))

    def _load_conversion_result(self, result, source_filepath: str) -> None:
        """Load conversion result from plugin into the application.
        
        Args:
            result: Conversion result from plugin (could be DitaContext, file path, etc.)
            source_filepath: Original source file path
        """
        try:
            logger.info("Processing conversion result - type: %s, has dita_context attr: %s", 
                        type(result).__name__, hasattr(result, 'dita_context'))
            
            if hasattr(result, '__dict__'):
                logger.info("Result attributes: %s", list(result.__dict__.keys()))
            
            # Handle different types of plugin results
            if hasattr(result, 'dita_context') and result.dita_context:
                # Plugin returned a result with DITA context
                logger.info("Loading result.dita_context")
                self.dita_context = result.dita_context
                # Use standard workflow to show post-process validation screen
                self.root.after(0, self.on_conversion_success, result.dita_context)
            elif hasattr(result, '__dict__') and hasattr(result, 'topics'):
                # Plugin returned a DITA context-like object directly
                logger.info("Loading result as DitaContext directly - topics: %d", len(result.topics) if hasattr(result, 'topics') else 0)
                self.dita_context = result
                # Use standard workflow to show post-process validation screen  
                self.root.after(0, self.on_conversion_success, result)
            elif isinstance(result, str) and Path(result).exists():
                # Plugin returned a file path - load it
                logger.info("Loading result as file path: %s", result)
                self._load_dita_package(result)
            else:
                # Generic result - show success message
                logger.warning("Unhandled result type - showing generic success message")
                messagebox.showinfo(
                    "Conversion Complete",
                    f"File processed successfully by plugin.\n\n"
                    f"Source: {Path(source_filepath).name}\n"
                    f"Result type: {type(result).__name__}"
                )
                
        except Exception as e:
            logger.error("Failed to load conversion result: %s", e)
            # Handle failure properly with UI cleanup
            self.root.after(0, lambda: self._handle_plugin_failure(f"Failed to load conversion result:\n\n{e}", source_filepath))

    def _transition_to_post_conversion_state(self, source_filepath: str) -> None:
        """Transition application to post-conversion state with loaded DITA content."""
        try:
            logger.info("Starting transition to post-conversion state")
            logger.info("Current dita_context: %s (topics: %d)", 
                        type(self.dita_context).__name__ if self.dita_context else None,
                        len(self.dita_context.topics) if self.dita_context and hasattr(self.dita_context, 'topics') else 0)
            
            # Update AppContext with current document context
            if self.dita_context:
                logger.info("Updating AppContext with DitaContext containing source plugin: %s", 
                           self.dita_context.plugin_data.get('_source_plugin') if hasattr(self.dita_context, 'plugin_data') else 'None')
                self.app_context._set_current_dita_context(self.dita_context)
            
            # Hide home frame and show main interface
            if self.home_frame:
                logger.info("Destroying home frame")
                self.home_frame.destroy()
                self.home_frame = None
            
            # Set up the main interface (tabs, etc.)
            logger.info("Setting up main UI")
            self.setup_main_ui()
            
            logger.info("Successfully loaded conversion result from %s", source_filepath)
            
        except Exception as e:
            logger.error("Failed to transition to post-conversion state: %s", e)
            messagebox.showerror("Interface Error", f"Failed to set up main interface:\n\n{e}")

    # ------------------------------------------------------------------
    # Document conversion workflow
    # ------------------------------------------------------------------

    def start_conversion_workflow(self) -> None:
        # Get all supported formats for dynamic file dialog
        try:
            supported_formats = self.service.get_supported_formats()
            
            # Build file types for dialog
            filetypes = []
            for fmt in supported_formats:
                filetypes.append((fmt.description, f"*{fmt.extension}"))
            filetypes.append(("All files", "*.*"))
            
            # Choose title based on available formats
            if any('DITA' in fmt.description for fmt in supported_formats):
                title = "Select a Document or DITA Package"
            else:
                title = "Select a Document"
                
        except Exception as e:
            logger.warning("Failed to get supported formats: %s", e)
            # Fallback to all files only (plugin-agnostic)
            filetypes = [("All files", "*.*")]
            title = "Select a file"
        
        filepath = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if not filepath:
            return
        
        # Check if file is supported
        if not self.service.can_handle_file(filepath):
            messagebox.showerror(
                "Unsupported File Type",
                f"The selected file type is not supported:\n{Path(filepath).name}\n\n"
                f"Supported formats:\n" + 
                "\n".join(f"• {fmt.description} ({fmt.extension})" 
                         for fmt in self.service.get_supported_formats())
            )
            return

        if self.status_label:
            self.status_label.config(text="")
        self._show_loading_spinner("Converting Document", "")

        # Comprehensively disable all UI elements during processing
        self._disable_all_ui_elements()

        initial_metadata = {
            "manual_title": Path(filepath).stem,
            "revision_date": datetime.now().strftime("%Y-%m-%d"),
            # No default revision_number so the generated package is treated as an edition.
        }

        # Use unified processing thread for both conversions and imports
        threading.Thread(target=self.run_document_processing_thread, args=(filepath, initial_metadata), daemon=True).start()

    def run_document_processing_thread(self, filepath: str, metadata: dict) -> None:
        """Process document (conversion or import) in background thread."""
        try:
            # Determine operation type for logging
            file_path = Path(filepath)
            if file_path.suffix.lower() == '.zip':
                operation = "DITA import"
            else:
                operation = "Document conversion"
            
            logger.info("Starting %s for: %s", operation, filepath)
            
            ctx = self.service.convert(filepath, metadata, self._progress_callback)
            # Treat a None result as a failure
            if ctx is None:
                logger.error("%s returned no result for file: %s", operation, filepath)
                self.root.after(
                    0,
                    self.on_conversion_failure,
                    RuntimeError(f"{operation} returned no result for file: {filepath}"),
                )
                return

            # Set default depth from style analysis (max depth) if not already provided
            # Skip for DITA imports as they already have structure
            if operation == "Document conversion":
                try:
                    if hasattr(ctx, "metadata"):
                        if ctx.metadata.get("topic_depth") is None:
                            from orlando_toolkit.core.services.heading_analysis_service import compute_max_depth
                            computed = compute_max_depth(ctx)
                            ctx.metadata["topic_depth"] = max(1, int(computed))
                except Exception:
                    # Best-effort only; UI can still adjust depth later
                    pass
            
            logger.info("%s completed successfully", operation)
            self.root.after(0, self.on_conversion_success, ctx)
        except Exception as exc:
            logger.error("%s failed for %s", operation, filepath, exc_info=True)
            self.root.after(0, self.on_conversion_failure, exc)

    def run_conversion_thread(self, filepath: str, metadata: dict) -> None:
        """Legacy method - delegate to unified processing."""
        self.run_document_processing_thread(filepath, metadata)

    def run_dita_import_thread(self, filepath: str, metadata: dict) -> None:
        """Legacy method - delegate to unified processing."""
        self.run_document_processing_thread(filepath, metadata)

    # ------------------------------------------------------------------
    # Conversion callbacks
    # ------------------------------------------------------------------

    def on_conversion_success(self, context: DitaContext) -> None:
        """Handle a successful conversion by showing a summary on the home screen.

        Instead of immediately opening the main tabbed UI, we keep a compact
        landing screen with a green success summary, counts, and an inline
        metadata form. A Continue button opens the full workspace.
        """
        self.dita_context = context
        
        # Update AppContext with current document context
        logger.info("Calling app_context._set_current_dita_context with source plugin: %s", 
                   context.plugin_data.get('_source_plugin') if hasattr(context, 'plugin_data') else 'None')
        self.app_context._set_current_dita_context(context)

        # Stop and hide any in-flight progress UI
        self._hide_loading_spinner()
        if self.status_label:
            self.status_label.config(text="")

        # Clear only the buttons area while preserving logo and title for consistency
        if self.buttons_container and self.buttons_container.winfo_exists():
            try:
                self.buttons_container.destroy()
                self.buttons_container = None
            except Exception:
                pass
        
        # Ensure home_center exists for post-conversion content
        if not (self.home_center and self.home_center.winfo_exists()):
            # Recreate if needed
            self.home_frame = ttk.Frame(self.root)
            self.home_frame.pack(expand=True, fill="both", padx=20, pady=20)
            self.home_center = ttk.Frame(self.home_frame)
            self.home_center.place(relx=0.5, rely=0.5, anchor="center")

        self.show_post_conversion_summary()

    def on_conversion_failure(self, error: Exception) -> None:
        self._hide_loading_spinner()
        if self.status_label:
            self.status_label.config(text="Conversion failed. Please try again.")
        
        # Re-enable all UI elements after processing failure
        self._enable_all_ui_elements()
        
        messagebox.showerror("Conversion Error", f"Document processing failed:\n\n{error}")

    # ------------------------------------------------------------------
    # Main UI after conversion
    # ------------------------------------------------------------------

    def setup_main_ui(self) -> None:
        tabs_frame = ttk.Frame(self.root)
        tabs_frame.pack(expand=True, fill="both", padx=10, pady=(10, 0))

        self.notebook = ttk.Notebook(tabs_frame)
        self.notebook.pack(expand=True, fill="both")

        # Place Structure first (leftmost) and select by default
        from orlando_toolkit.ui.structure_tab import StructureTab
        self.structure_tab = StructureTab(self.notebook)
        self.notebook.add(self.structure_tab, text="Structure")
        
        # Load the converted DITA context into the structure tab
        if self.dita_context:
            logger.info("Loading DitaContext into structure tab - topics: %d", len(self.dita_context.topics))
            self.structure_tab.load_context(self.dita_context)
        else:
            logger.warning("No DitaContext available to load into structure tab")

        # Place Media second, Metadata third per updated UX
        self.media_tab = MediaTab(self.notebook)
        self.notebook.add(self.media_tab, text="Media")
        if self.dita_context:
            self.media_tab.load_context(self.dita_context)

        self.metadata_tab = MetadataTab(self.notebook)
        self.notebook.add(self.metadata_tab, text="Metadata")
        if self.dita_context:
            self.metadata_tab.load_context(self.dita_context)

        self.metadata_tab.set_metadata_change_callback(self.on_metadata_change)

        self.main_actions_frame = ttk.Frame(self.root)
        self.main_actions_frame.pack(fill="x", padx=10, pady=10)

        left_actions = ttk.Frame(self.main_actions_frame)
        left_actions.pack(side="left")
        ttk.Button(left_actions, text="← Back to Home", command=self.back_to_home).pack(side="left")
        about_link = ttk.Label(left_actions, text="About", cursor="hand2", foreground="#888888")
        about_link.pack(side="left", padx=(10, 0), pady=(3, 0))
        about_link.bind("<Button-1>", lambda e: show_about_dialog(self.root))

        right_actions = ttk.Frame(self.main_actions_frame)
        right_actions.pack(side="right")
        ttk.Button(right_actions, text="Generate DITA Package", style="Accent.TButton", command=self.generate_package).pack(side="right")

        # Default to Structure view
        try:
            if self.structure_tab is not None:
                self.notebook.select(self.structure_tab)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Post-conversion summary (home screen)
    # ------------------------------------------------------------------

    def show_post_conversion_summary(self) -> None:
        """Render a compact summary with results and metadata on the home screen."""
        assert self.dita_context is not None

        # Keep the exact same window size as the initial landing screen for consistency

        # Logo and title are preserved from the original home screen for consistency
        # No need to recreate them - they should already be visible

        # Success summary with checkmark and separate lines
        summary = ttk.Frame(self.home_center)
        # Center the result lines horizontally under the logo
        summary.pack(pady=(10, 6))
        ok_style = {"foreground": "#2e7d32", "font": ("Arial", 11, "bold")}
        err_style = {"foreground": "#c62828", "font": ("Arial", 11, "bold")}
        num_topics = len(self.dita_context.topics) if self.dita_context.topics else 0
        num_images = len(self.dita_context.images) if self.dita_context.images else 0
        # Line 1: topics
        if num_topics > 0:
            ttk.Label(summary, text=f"✓ {num_topics} topics extracted", **ok_style).pack(anchor="center")
        else:
            ttk.Label(summary, text="✗ No topics found", **err_style).pack(anchor="center")
        # Line 2: images
        if num_images > 0:
            ttk.Label(summary, text=f"✓ {num_images} images extracted", **ok_style).pack(anchor="center")
        else:
            ttk.Label(summary, text="✗ No images found", **err_style).pack(anchor="center")

        # Inline metadata editor
        # Unified metadata form with compact styling
        metadata_frame = ttk.LabelFrame(self.home_center, text="DITA Metadata", padding=8)
        metadata_frame.pack(fill="x", pady=(4, 14))

        # Use MetadataForm directly to avoid tab-specific decorations; reduced padding
        form = MetadataForm(metadata_frame, padding=4, font_size=10, on_change=self.on_metadata_change)
        form.pack(fill="x")
        form.load_context(self.dita_context)
        self.inline_metadata = form  # store for value commit if needed

        # Footer button: Continue if anything found; else Quit
        if num_topics > 0 or num_images > 0:
            ttk.Button(self.home_center, text="Continue", style="Accent.TButton", command=self.open_main_ui_from_summary).pack(pady=16, ipadx=18, ipady=8)
        else:
            ttk.Button(self.home_center, text="Quit", command=self.on_close).pack(pady=16, ipadx=18, ipady=8)

    def _commit_inline_metadata_to_context(self) -> None:
        """Ensure inline metadata edits are persisted to the context."""
        if not self.dita_context or not self.inline_metadata:
            return
        for key, var in self.inline_metadata.entries.items():
            try:
                value = var.get()
            except Exception:
                continue
            if value is None:
                continue
            if key not in self.dita_context.metadata or self.dita_context.metadata.get(key) != value:
                self.dita_context.metadata[key] = value
        # Let dependent widgets react if needed
        try:
            self.on_metadata_change()
        except Exception:
            pass

    def open_main_ui_from_summary(self) -> None:
        """Switch from the summary to the full workspace, defaulting to Structure."""
        # Persist any in-flight edits from the inline metadata form
        self._commit_inline_metadata_to_context()

        # Clear landing UI
        if self.home_frame and self.home_frame.winfo_exists():
            try:
                self.home_frame.destroy()
            except Exception:
                pass
            self.home_frame = None
        self.inline_metadata = None

        # Show an in-window full overlay with a large hourglass icon
        self._show_loading_overlay("Loading structure…")

        # Trigger fullscreen immediately for a stable visual
        try:
            self.root.state("zoomed")
        except Exception:
            try:
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                self.root.geometry(f"{sw-40}x{sh-60}+20+20")
            except Exception:
                pass
        try:
            # Ensure the overlay is painted before heavy UI work
            try:
                self.root.update_idletasks()
            except Exception:
                pass

            # Build tabs and load data under the overlay
            self.setup_main_ui()
            if self.dita_context and self.metadata_tab and self.media_tab and self.structure_tab:
                self.metadata_tab.load_context(self.dita_context)
                self.media_tab.load_context(self.dita_context)
                self.structure_tab.load_context(self.dita_context)
            # Ensure Structure tab is selected
            try:
                if self.structure_tab is not None:
                    self.notebook.select(self.structure_tab)
            except Exception:
                pass
        finally:
            # Remove the overlay even if loading fails
            try:
                self._hide_loading_overlay()
            except Exception:
                pass

    def back_to_home(self) -> None:
        for widget in self.root.winfo_children():
            widget.destroy()
        self.dita_context = None
        
        # Clear AppContext document context
        self.app_context._set_current_dita_context(None)
        
        self.notebook = self.metadata_tab = self.media_tab = self.main_actions_frame = None
        self.inline_metadata = None
        self.create_home_screen()

    # ------------------------------------------------------------------
    # Package generation
    # ------------------------------------------------------------------

    def generate_package(self) -> None:
        if not self.dita_context:
            messagebox.showerror("Error", "No DITA context is loaded.")
            return

        manual_code = (self.dita_context.metadata.get("manual_code") or "dita_project") if self.dita_context else "dita_project"
        save_path = filedialog.asksaveasfilename(
            title="Save DITA archive",
            defaultextension=".zip",
            filetypes=(("ZIP", "*.zip"),),
            initialfile=f"{manual_code}.zip",
        )
        if not save_path:
            return

        self._show_loading_spinner("Generating Package", "")
        threading.Thread(target=self.run_generation_thread, args=(save_path,), daemon=True).start()


    def _show_loading_overlay(self, message: str = "Loading…") -> None:
        """Show a simple full-window overlay with a large hourglass and message."""
        try:
            overlay = ttk.Frame(self.root)
            overlay.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
            center = ttk.Frame(overlay)
            center.place(relx=0.5, rely=0.5, anchor="center")
            try:
                ttk.Label(center, text="⌛", font=("Arial", 72)).pack()
            except Exception:
                ttk.Label(center, text="Loading", font=("Arial", 32, "bold")).pack()
            ttk.Label(center, text=message, font=("Arial", 14)).pack(pady=8)
            try:
                overlay.lift()
            except Exception:
                pass
            self._loading_overlay = overlay  # type: ignore[attr-defined]
        except Exception:
            self._loading_overlay = None  # type: ignore[attr-defined]

    def _hide_loading_overlay(self) -> None:
        try:
            overlay = getattr(self, "_loading_overlay", None)
            if overlay is not None:
                overlay.destroy()
        finally:
            try:
                self._loading_overlay = None  # type: ignore[attr-defined]
            except Exception:
                pass

    def run_generation_thread(self, save_path: str):
        try:
            # Build an up-to-date context snapshot for export. We work on a
            # background thread, so heavy deepcopy does not block the UI.
            if self.structure_tab and getattr(self.structure_tab, "context", None):
                ctx_export = deepcopy(self.structure_tab.context)
                # Preserve latest metadata (may have been edited in other tabs)
                if self.dita_context:
                    # Keep Structure tab's chosen depth from being overwritten by base context
                    # Prefer controller's max_depth if available; else metadata
                    depth_from_structure = None
                    try:
                        depth_from_structure = getattr(self.structure_tab, "max_depth", None)
                    except Exception:
                        depth_from_structure = None
                    if depth_from_structure is None:
                        depth_from_structure = ctx_export.metadata.get("topic_depth")
                    # Merge global metadata
                    ctx_export.metadata.update(self.dita_context.metadata)
                    # Restore the structure depth explicitly if known
                    if depth_from_structure is not None:
                        ctx_export.metadata["topic_depth"] = depth_from_structure
            else:
                ctx_export = deepcopy(self.dita_context)

            ctx = self.service.prepare_package(ctx_export)  # type: ignore[arg-type]
            self.service.write_package(ctx, save_path)
            self.root.after(0, self.on_generation_success, save_path)
        except Exception as exc:
            logger.error("Package generation failed", exc_info=True)
            self.root.after(0, self.on_generation_failure, exc)

    def on_generation_success(self, save_path: str):
        self._hide_loading_spinner()
        messagebox.showinfo("Success", f"Archive written to\n{save_path}")

    def on_generation_failure(self, error: Exception):
        self._hide_loading_spinner()
        messagebox.showerror("Generation error", str(error))

    # ------------------------------------------------------------------
    # Exit handling
    # ------------------------------------------------------------------

    def on_close(self):
        if messagebox.askokcancel("Quit", "Really quit?"):
            # Cleanup session storage (preview/images edits)
            try:
                from orlando_toolkit.core.session_storage import get_session_storage
                get_session_storage().cleanup()
            except Exception:
                pass
            self.root.destroy()

    # ------------------------------------------------------------------
    # Topic depth re-conversion
    # ------------------------------------------------------------------

    def on_topic_depth_change(self, new_depth: int):
        """Update metadata with new depth; no re-parse needed."""
        if self.dita_context:
            self.dita_context.metadata["topic_depth"] = new_depth
        # No further action: Structure tab already filtered in real time

    def on_metadata_change(self) -> None:
        # TODO: Implement image name updating in MediaTab
        # if self.media_tab:
        #     self.media_tab.update_image_names()
        pass


 