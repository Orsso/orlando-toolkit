"""Plugin list widget for displaying available plugins with status indicators.

Displays official and custom plugins in a tree widget with hierarchical grouping
and visual status indicators for installation and activation state.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, Optional, Callable, List

from orlando_toolkit.core.plugins.manager import PluginManager

logger = logging.getLogger(__name__)


class PluginListWidget(ttk.Frame):
    """Widget displaying available plugins with status indicators.
    
    Provides:
    - Hierarchical display of official and custom plugins
    - Visual status indicators (Not Installed, Installed, Active, Error)
    - Plugin selection and callback handling
    - Search/filter functionality
    """
    
    # Status indicators and colors
    STATUS_INDICATORS = {
        "not_installed": "⚪",    # White circle
        "installed": "🔵",       # Blue circle
        "active": "🟢",          # Green circle  
        "error": "🔴",           # Red circle
        "loading": "🟡",         # Yellow circle
        "unknown": "⚫"          # Black circle
    }
    
    STATUS_COLORS = {
        "not_installed": "#888888",
        "installed": "#0066CC", 
        "active": "#00AA00",
        "error": "#CC0000",
        "loading": "#CCAA00",
        "unknown": "#444444"
    }
    
    def __init__(self, parent: tk.Widget, on_selection_changed: Optional[Callable] = None,
                 plugin_manager: Optional[PluginManager] = None):
        """Initialize plugin list widget.
        
        Args:
            parent: Parent widget
            on_selection_changed: Callback for selection changes (plugin_id, plugin_data)
            plugin_manager: Plugin manager for status queries
        """
        super().__init__(parent)
        
        self.on_selection_changed = on_selection_changed
        self.plugin_manager = plugin_manager
        self._logger = logging.getLogger(f"{__name__}.PluginListWidget")
        
        # Plugin data storage
        self.official_plugins: Dict[str, Any] = {}
        self.custom_plugins: List[str] = []
        self.plugin_status: Dict[str, str] = {}
        
        # UI state
        self.selected_plugin_id: Optional[str] = None
        self._enabled = True
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the widget UI components."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # Tree gets weight
        
        # Search/filter frame
        search_frame = ttk.Frame(self)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        search_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(search_frame, text="Filter:").grid(row=0, column=0, sticky="w")
        
        self.filter_var = tk.StringVar()
        self.filter_var.trace("w", self._on_filter_changed)
        
        self.filter_entry = ttk.Entry(search_frame, textvariable=self.filter_var)
        self.filter_entry.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        
        # Plugin tree
        self.tree = ttk.Treeview(self, columns=("status", "version"), show="tree headings")
        self.tree.grid(row=1, column=0, sticky="nsew")
        
        # Configure tree columns
        self.tree.heading("#0", text="Plugin", anchor="w")
        self.tree.heading("status", text="Status", anchor="center")
        self.tree.heading("version", text="Version", anchor="center")
        
        self.tree.column("#0", width=200, minwidth=150)
        self.tree.column("status", width=80, minwidth=80)
        self.tree.column("version", width=80, minwidth=80)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Bind selection event
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_changed)
        self.tree.bind("<Double-1>", self._on_double_click)
    
    def populate_plugins(self, official_plugins: Dict[str, Any], custom_plugins: List[str]) -> None:
        """Populate the plugin list with official and custom plugins.
        
        Args:
            official_plugins: Dictionary of official plugin data
            custom_plugins: List of custom/installed plugin IDs
        """
        self.official_plugins = official_plugins
        self.custom_plugins = custom_plugins
        
        # Update plugin status
        self._refresh_plugin_status()
        
        # Rebuild tree
        self._rebuild_tree()
    
    def _refresh_plugin_status(self) -> None:
        """Refresh status information for all plugins."""
        self.plugin_status.clear()
        
        if not self.plugin_manager:
            # Default to unknown status if no plugin manager
            for plugin_id in self.official_plugins.keys():
                self.plugin_status[plugin_id] = "unknown"
            for plugin_id in self.custom_plugins:
                self.plugin_status[plugin_id] = "unknown"
            return
        
        # Get status for official plugins
        for plugin_id in self.official_plugins.keys():
            try:
                status_info = self.plugin_manager.get_installation_status(plugin_id)
                self.plugin_status[plugin_id] = self._determine_status(status_info)
            except Exception as e:
                self._logger.warning("Failed to get status for official plugin %s: %s", plugin_id, e)
                self.plugin_status[plugin_id] = "error"
        
        # Get status for custom plugins
        for plugin_id in self.custom_plugins:
            try:
                status_info = self.plugin_manager.get_installation_status(plugin_id)
                self.plugin_status[plugin_id] = self._determine_status(status_info)
            except Exception as e:
                self._logger.warning("Failed to get status for custom plugin %s: %s", plugin_id, e)
                self.plugin_status[plugin_id] = "error"
    
    def _determine_status(self, status_info: Dict[str, Any]) -> str:
        """Determine display status from installation status info.
        
        Args:
            status_info: Installation status dictionary
            
        Returns:
            Status string for display
        """
        if status_info.get("error"):
            return "error"
        elif status_info.get("active"):
            return "active"
        elif status_info.get("loaded"):
            return "installed"
        elif status_info.get("installed"):
            return "installed"
        else:
            return "not_installed"
    
    def _rebuild_tree(self) -> None:
        """Rebuild the tree widget with current plugin data."""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Apply filter if any
        filter_text = self.filter_var.get().lower()
        
        # Add official plugins section
        if self._should_show_section("official", filter_text):
            official_root = self.tree.insert("", "end", iid="official", 
                                            text="Official Plugins", 
                                            values=("", ""), 
                                            tags=("section",))
            
            for plugin_id, plugin_data in self.official_plugins.items():
                if self._should_show_plugin(plugin_id, plugin_data, filter_text):
                    self._add_plugin_item(official_root, plugin_id, plugin_data, is_official=True)
        
        # Add custom plugins section
        if self.custom_plugins and self._should_show_section("custom", filter_text):
            custom_root = self.tree.insert("", "end", iid="custom",
                                         text="Custom Plugins",
                                         values=("", ""),
                                         tags=("section",))
            
            for plugin_id in self.custom_plugins:
                if self._should_show_plugin(plugin_id, {}, filter_text):
                    self._add_plugin_item(custom_root, plugin_id, {}, is_official=False)
        
        # Expand all sections by default
        for item in self.tree.get_children():
            self.tree.item(item, open=True)
        
        # Configure section styling
        self.tree.tag_configure("section", font=("Arial", 10, "bold"))
    
    def _should_show_section(self, section_type: str, filter_text: str) -> bool:
        """Check if a section should be shown based on filter.
        
        Args:
            section_type: Section type ("official" or "custom")
            filter_text: Filter text (lowercase)
            
        Returns:
            True if section should be shown
        """
        if not filter_text:
            return True
        
        # Check if section name matches
        if filter_text in section_type:
            return True
        
        # Check if any plugins in section match
        if section_type == "official":
            for plugin_id, plugin_data in self.official_plugins.items():
                if self._should_show_plugin(plugin_id, plugin_data, filter_text):
                    return True
        elif section_type == "custom":
            for plugin_id in self.custom_plugins:
                if self._should_show_plugin(plugin_id, {}, filter_text):
                    return True
        
        return False
    
    def _should_show_plugin(self, plugin_id: str, plugin_data: Dict[str, Any], filter_text: str) -> bool:
        """Check if a plugin should be shown based on filter.
        
        Args:
            plugin_id: Plugin identifier
            plugin_data: Plugin data dictionary
            filter_text: Filter text (lowercase)
            
        Returns:
            True if plugin should be shown
        """
        if not filter_text:
            return True
        
        # Check plugin ID
        if filter_text in plugin_id.lower():
            return True
        
        # Check description/display name
        description = plugin_data.get("description", "")
        if filter_text in description.lower():
            return True
        
        # Check button text
        button_text = plugin_data.get("button_text", "")
        if filter_text in button_text.lower():
            return True
        
        return False
    
    def _add_plugin_item(self, parent: str, plugin_id: str, plugin_data: Dict[str, Any], 
                        is_official: bool) -> None:
        """Add a plugin item to the tree.
        
        Args:
            parent: Parent tree item ID
            plugin_id: Plugin identifier
            plugin_data: Plugin data dictionary
            is_official: True if this is an official plugin
        """
        # Get plugin status
        status = self.plugin_status.get(plugin_id, "unknown")
        status_indicator = self.STATUS_INDICATORS.get(status, self.STATUS_INDICATORS["unknown"])
        
        # Get version if available
        version = ""
        if self.plugin_manager:
            try:
                metadata = self.plugin_manager.get_plugin_metadata(plugin_id)
                if metadata:
                    version = metadata.version
            except Exception:
                pass
        
        if not version and plugin_data:
            version = plugin_data.get("version", "")
        
        # Get display name
        if is_official:
            display_name = plugin_data.get("description", plugin_id)
        else:
            display_name = plugin_id
        
        # Insert tree item
        item_id = f"plugin_{plugin_id}"
        self.tree.insert(parent, "end", iid=item_id,
                        text=f"{status_indicator} {display_name}",
                        values=(status.replace("_", " ").title(), version),
                        tags=(f"plugin", f"status_{status}"))
        
        # Configure status color
        color = self.STATUS_COLORS.get(status, self.STATUS_COLORS["unknown"])
        self.tree.tag_configure(f"status_{status}", foreground=color)
    
    def _on_selection_changed(self, event: tk.Event) -> None:
        """Handle tree selection change.
        
        Args:
            event: Selection event
        """
        selection = self.tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        
        # Only handle plugin selections (not sections)
        if not item_id.startswith("plugin_"):
            return
        
        # Extract plugin ID
        plugin_id = item_id[7:]  # Remove "plugin_" prefix
        self.selected_plugin_id = plugin_id
        
        # Get plugin data
        plugin_data = {}
        if plugin_id in self.official_plugins:
            plugin_data = self.official_plugins[plugin_id].copy()
            plugin_data["is_official"] = True
        else:
            plugin_data = {"is_official": False}
        
        # Add status information
        plugin_data["status"] = self.plugin_status.get(plugin_id, "unknown")
        
        # Call selection callback
        if self.on_selection_changed and self._enabled:
            try:
                self.on_selection_changed(plugin_id, plugin_data)
            except Exception as e:
                self._logger.error("Error in selection callback: %s", e)
    
    def _on_double_click(self, event: tk.Event) -> None:
        """Handle double-click on plugin item.
        
        Args:
            event: Double-click event
        """
        # For now, double-click does the same as selection
        # Could be extended to trigger default action (install/activate)
        pass
    
    def _on_filter_changed(self, *args) -> None:
        """Handle filter text change."""
        # Rebuild tree with filter applied
        self._rebuild_tree()
        
        # If current selection is filtered out, clear it
        if self.selected_plugin_id:
            filter_text = self.filter_var.get().lower()
            plugin_data = self.official_plugins.get(self.selected_plugin_id, {})
            
            if not self._should_show_plugin(self.selected_plugin_id, plugin_data, filter_text):
                self.selected_plugin_id = None
                if self.on_selection_changed:
                    self.on_selection_changed(None, {})
    
    def refresh_status(self) -> None:
        """Refresh plugin status indicators."""
        self._refresh_plugin_status()
        self._rebuild_tree()
        
        # Restore selection if it still exists
        if self.selected_plugin_id:
            item_id = f"plugin_{self.selected_plugin_id}"
            if self.tree.exists(item_id):
                self.tree.selection_set(item_id)
    
    def select_plugin(self, plugin_id: str) -> bool:
        """Programmatically select a plugin.
        
        Args:
            plugin_id: Plugin to select
            
        Returns:
            True if plugin was selected successfully
        """
        item_id = f"plugin_{plugin_id}"
        if self.tree.exists(item_id):
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.tree.see(item_id)
            return True
        return False
    
    def get_selected_plugin(self) -> Optional[str]:
        """Get currently selected plugin ID.
        
        Returns:
            Selected plugin ID or None
        """
        return self.selected_plugin_id
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the widget.
        
        Args:
            enabled: True to enable, False to disable
        """
        self._enabled = enabled
        
        # Update tree state
        state = "normal" if enabled else "disabled"
        try:
            self.tree.configure(state=state)
            self.filter_entry.configure(state=state)
        except tk.TclError:
            # Some Tkinter versions don't support state for Treeview
            pass
    
    def clear(self) -> None:
        """Clear all plugins from the list."""
        self.official_plugins.clear()
        self.custom_plugins.clear()
        self.plugin_status.clear()
        self.selected_plugin_id = None
        
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)