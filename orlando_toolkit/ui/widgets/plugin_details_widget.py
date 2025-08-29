"""Plugin details widget for displaying plugin information and action buttons.

Shows comprehensive plugin information including metadata, status, dependencies,
and provides action buttons for plugin management operations.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, Optional, Callable

from orlando_toolkit.core.plugins.manager import PluginManager
from orlando_toolkit.core.plugins.metadata import PluginMetadata

logger = logging.getLogger(__name__)


class PluginDetailsWidget(ttk.Frame):
    """Widget displaying detailed plugin information and action buttons.
    
    Provides:
    - Plugin metadata display (name, version, description, author)
    - Installation status and error information
    - Dependencies list
    - Repository and documentation links
    - Action buttons (Install/Uninstall/Activate/Deactivate)
    """
    
    def __init__(self, parent: tk.Widget, on_action: Optional[Callable] = None,
                 plugin_manager: Optional[PluginManager] = None):
        """Initialize plugin details widget.
        
        Args:
            parent: Parent widget
            on_action: Callback for action buttons (action, plugin_id)
            plugin_manager: Plugin manager for additional information
        """
        super().__init__(parent)
        
        self.on_action = on_action
        self.plugin_manager = plugin_manager
        self._logger = logging.getLogger(f"{__name__}.PluginDetailsWidget")
        
        # Current plugin data
        self.current_plugin_id: Optional[str] = None
        self.current_plugin_info: Dict[str, Any] = {}
        self._enabled = True
        
        self._setup_ui()
        self._show_empty_state()
    
    def _setup_ui(self) -> None:
        """Setup the widget UI components."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Create scrollable frame
        self._create_scrollable_content()
        
    def _create_scrollable_content(self) -> None:
        """Create scrollable content area."""
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        # Configure scrollable frame
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        # Create window in canvas
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Grid canvas and scrollbar
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Configure scrollable frame grid
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        
        # Bind mousewheel to canvas
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
    
    def _on_mousewheel(self, event: tk.Event) -> None:
        """Handle mousewheel scrolling.
        
        Args:
            event: Mouse wheel event
        """
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def _clear_content(self) -> None:
        """Clear all content from the scrollable frame."""
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
    
    def _show_empty_state(self) -> None:
        """Show empty state when no plugin is selected."""
        self._clear_content()
        
        empty_frame = ttk.Frame(self.scrollable_frame)
        empty_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        empty_frame.grid_columnconfigure(0, weight=1)
        empty_frame.grid_rowconfigure(0, weight=1)
        
        ttk.Label(empty_frame, text="Select a plugin to view details", 
                 font=("Arial", 12), foreground="gray").grid(row=0, column=0)
    
    def display_plugin(self, plugin_id: str, plugin_info: Dict[str, Any]) -> None:
        """Display plugin information.
        
        Args:
            plugin_id: Plugin identifier
            plugin_info: Complete plugin information dictionary
        """
        self.current_plugin_id = plugin_id
        self.current_plugin_info = plugin_info
        
        self._clear_content()
        
        # Current row for grid placement
        row = 0
        
        # Plugin header section
        row = self._create_header_section(row, plugin_id, plugin_info)
        
        # Status section
        row = self._create_status_section(row, plugin_info)
        
        # Metadata section
        row = self._create_metadata_section(row, plugin_info)
        
        # Dependencies section (if available)
        if plugin_info.get("metadata"):
            row = self._create_dependencies_section(row, plugin_info["metadata"])
        
        # Repository links section
        row = self._create_links_section(row, plugin_info)
        
        # Action buttons section
        row = self._create_actions_section(row, plugin_id, plugin_info)
        
        # Update scroll region
        self.scrollable_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _create_header_section(self, row: int, plugin_id: str, plugin_info: Dict[str, Any]) -> int:
        """Create plugin header section.
        
        Args:
            row: Current grid row
            plugin_id: Plugin identifier
            plugin_info: Plugin information
            
        Returns:
            Next available row
        """
        header_frame = ttk.Frame(self.scrollable_frame)
        header_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
        header_frame.grid_columnconfigure(0, weight=1)
        
        # Plugin name/title
        if plugin_info.get("metadata"):
            display_name = plugin_info["metadata"].display_name
        elif plugin_info.get("official_data"):
            display_name = plugin_info["official_data"].get("description", plugin_id)
        else:
            display_name = plugin_id
        
        title_label = ttk.Label(header_frame, text=display_name, 
                               font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, sticky="w")
        
        # Plugin ID (if different from display name)
        if display_name.lower() != plugin_id.lower():
            ttk.Label(header_frame, text=f"({plugin_id})", 
                     font=("Arial", 10), foreground="gray").grid(row=1, column=0, sticky="w")
        
        return row + 1
    
    def _create_status_section(self, row: int, plugin_info: Dict[str, Any]) -> int:
        """Create status information section.
        
        Args:
            row: Current grid row
            plugin_info: Plugin information
            
        Returns:
            Next available row
        """
        status_frame = ttk.LabelFrame(self.scrollable_frame, text="Status", padding=10)
        status_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        status_frame.grid_columnconfigure(1, weight=1)
        
        current_row = 0
        
        # Installation status
        status = plugin_info.get("status", "unknown")
        status_display = status.replace("_", " ").title()
        
        ttk.Label(status_frame, text="Status:").grid(row=current_row, column=0, sticky="w")
        status_label = ttk.Label(status_frame, text=status_display)
        status_label.grid(row=current_row, column=1, sticky="w", padx=(5, 0))
        
        # Color code status
        status_colors = {
            "not_installed": "#888888",
            "installed": "#0066CC",
            "active": "#00AA00", 
            "error": "#CC0000",
            "loading": "#CCAA00"
        }
        if status in status_colors:
            status_label.configure(foreground=status_colors[status])
        
        current_row += 1
        
        # Plugin type
        if plugin_info.get("is_official"):
            plugin_type = "Official Plugin"
        else:
            plugin_type = "Custom Plugin"
        
        ttk.Label(status_frame, text="Type:").grid(row=current_row, column=0, sticky="w")
        ttk.Label(status_frame, text=plugin_type).grid(row=current_row, column=1, sticky="w", padx=(5, 0))
        current_row += 1
        
        # Error information (if any)
        installation_status = plugin_info.get("installation_status", {})
        if installation_status.get("error"):
            ttk.Label(status_frame, text="Error:").grid(row=current_row, column=0, sticky="nw")
            error_label = ttk.Label(status_frame, text=str(installation_status["error"]), 
                                   wraplength=300, foreground="#CC0000")
            error_label.grid(row=current_row, column=1, sticky="w", padx=(5, 0))
        
        return row + 1
    
    def _create_metadata_section(self, row: int, plugin_info: Dict[str, Any]) -> int:
        """Create plugin metadata section.
        
        Args:
            row: Current grid row
            plugin_info: Plugin information
            
        Returns:
            Next available row
        """
        metadata_frame = ttk.LabelFrame(self.scrollable_frame, text="Information", padding=10)
        metadata_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        metadata_frame.grid_columnconfigure(1, weight=1)
        
        current_row = 0
        
        # Get metadata source
        metadata = plugin_info.get("metadata")
        official_data = plugin_info.get("official_data")
        
        # Version
        version = ""
        if metadata:
            version = metadata.version
        elif official_data:
            version = official_data.get("version", "")
        
        if version:
            ttk.Label(metadata_frame, text="Version:").grid(row=current_row, column=0, sticky="w")
            ttk.Label(metadata_frame, text=version).grid(row=current_row, column=1, sticky="w", padx=(5, 0))
            current_row += 1
        
        # Description
        description = ""
        if metadata:
            description = metadata.description
        elif official_data:
            description = official_data.get("description", "")
        
        if description:
            ttk.Label(metadata_frame, text="Description:").grid(row=current_row, column=0, sticky="nw")
            desc_label = ttk.Label(metadata_frame, text=description, wraplength=350)
            desc_label.grid(row=current_row, column=1, sticky="w", padx=(5, 0))
            current_row += 1
        
        # Author
        if metadata and metadata.author:
            ttk.Label(metadata_frame, text="Author:").grid(row=current_row, column=0, sticky="w")
            ttk.Label(metadata_frame, text=metadata.author).grid(row=current_row, column=1, sticky="w", padx=(5, 0))
            current_row += 1
        
        # Category
        category = ""
        if metadata:
            category = metadata.category
        elif official_data:
            category = official_data.get("category", "")
        
        if category:
            ttk.Label(metadata_frame, text="Category:").grid(row=current_row, column=0, sticky="w")
            ttk.Label(metadata_frame, text=category.title()).grid(row=current_row, column=1, sticky="w", padx=(5, 0))
            current_row += 1
        
        # Supported formats (if available)
        if metadata and metadata.supported_formats:
            ttk.Label(metadata_frame, text="Formats:").grid(row=current_row, column=0, sticky="nw")
            
            formats_text = []
            for fmt in metadata.supported_formats:
                if isinstance(fmt, dict):
                    ext = fmt.get("extension", "")
                    desc = fmt.get("description", "")
                    if ext and desc:
                        formats_text.append(f"{ext} - {desc}")
                    elif ext:
                        formats_text.append(ext)
                else:
                    formats_text.append(str(fmt))
            
            if formats_text:
                formats_label = ttk.Label(metadata_frame, text="\n".join(formats_text), 
                                        wraplength=350)
                formats_label.grid(row=current_row, column=1, sticky="w", padx=(5, 0))
        
        return row + 1
    
    def _create_dependencies_section(self, row: int, metadata: PluginMetadata) -> int:
        """Create dependencies section.
        
        Args:
            row: Current grid row
            metadata: Plugin metadata
            
        Returns:
            Next available row
        """
        if not metadata.dependencies:
            return row
        
        deps_frame = ttk.LabelFrame(self.scrollable_frame, text="Dependencies", padding=10)
        deps_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        deps_frame.grid_columnconfigure(0, weight=1)
        
        current_row = 0
        
        # Python version requirement
        python_req = metadata.dependencies.get("python")
        if python_req:
            ttk.Label(deps_frame, text=f"Python: {python_req}").grid(row=current_row, column=0, sticky="w")
            current_row += 1
        
        # Package dependencies
        packages = metadata.dependencies.get("packages", [])
        if packages:
            ttk.Label(deps_frame, text="Required Packages:", 
                     font=("Arial", 9, "bold")).grid(row=current_row, column=0, sticky="w")
            current_row += 1
            
            for package in packages:
                ttk.Label(deps_frame, text=f"  • {package}").grid(row=current_row, column=0, sticky="w")
                current_row += 1
        
        return row + 1
    
    def _create_links_section(self, row: int, plugin_info: Dict[str, Any]) -> int:
        """Create repository links section.
        
        Args:
            row: Current grid row
            plugin_info: Plugin information
            
        Returns:
            Next available row
        """
        # Get repository URLs
        repository_url = ""
        homepage_url = ""
        
        if plugin_info.get("metadata"):
            repository_url = plugin_info["metadata"].homepage or ""
        
        if plugin_info.get("official_data"):
            repository_url = plugin_info["official_data"].get("repository", "")
        
        if not repository_url:
            return row  # No links to show
        
        links_frame = ttk.LabelFrame(self.scrollable_frame, text="Links", padding=10)
        links_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        links_frame.grid_columnconfigure(1, weight=1)
        
        current_row = 0
        
        # Repository link
        ttk.Label(links_frame, text="Repository:").grid(row=current_row, column=0, sticky="w")
        repo_link = ttk.Label(links_frame, text=repository_url, foreground="blue", 
                             cursor="hand2")
        repo_link.grid(row=current_row, column=1, sticky="w", padx=(5, 0))
        
        # Make link clickable (placeholder - would need webbrowser import)
        def open_repository(event):
            try:
                import webbrowser
                webbrowser.open(repository_url)
            except Exception as e:
                self._logger.warning("Failed to open repository URL: %s", e)
        
        repo_link.bind("<Button-1>", open_repository)
        
        return row + 1
    
    def _create_actions_section(self, row: int, plugin_id: str, plugin_info: Dict[str, Any]) -> int:
        """Create action buttons section.
        
        Args:
            row: Current grid row
            plugin_id: Plugin identifier
            plugin_info: Plugin information
            
        Returns:
            Next available row
        """
        actions_frame = ttk.LabelFrame(self.scrollable_frame, text="Actions", padding=10)
        actions_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
        
        # Button container
        button_frame = ttk.Frame(actions_frame)
        button_frame.pack(fill="x")
        
        # Determine available actions based on plugin status
        status = plugin_info.get("status", "unknown")
        installation_status = plugin_info.get("installation_status", {})
        
        # Create action buttons based on status
        if status == "not_installed":
            self._create_action_button(button_frame, "Install", "install", plugin_id, "left")
        
        elif status in ["installed", "loaded"]:
            self._create_action_button(button_frame, "Uninstall", "uninstall", plugin_id, "left")
            # Note: Activate/Deactivate would go here when implemented
        
        elif status == "active":
            self._create_action_button(button_frame, "Deactivate", "deactivate", plugin_id, "left")
            self._create_action_button(button_frame, "Uninstall", "uninstall", plugin_id, "left")
        
        elif status == "error":
            self._create_action_button(button_frame, "Reinstall", "install", plugin_id, "left")
            self._create_action_button(button_frame, "Uninstall", "uninstall", plugin_id, "left")
        
        # Always show refresh button
        self._create_action_button(button_frame, "Refresh", "refresh", plugin_id, "right")
        
        return row + 1
    
    def _create_action_button(self, parent: tk.Widget, text: str, action: str, 
                             plugin_id: str, side: str) -> None:
        """Create an action button.
        
        Args:
            parent: Parent widget
            text: Button text
            action: Action identifier
            plugin_id: Plugin identifier
            side: Pack side ("left" or "right")
        """
        button = ttk.Button(
            parent, 
            text=text,
            command=lambda: self._handle_action(action, plugin_id)
        )
        
        button.pack(side=side, padx=(0 if side == "left" else 5, 5 if side == "left" else 0))
        
        # Store button reference for enabling/disabling
        if not hasattr(self, '_action_buttons'):
            self._action_buttons = []
        self._action_buttons.append(button)
    
    def _handle_action(self, action: str, plugin_id: str) -> None:
        """Handle action button click.
        
        Args:
            action: Action to perform
            plugin_id: Plugin identifier
        """
        if action == "refresh":
            # Handle refresh locally
            if self.current_plugin_id:
                # Trigger refresh by calling parent callback with current plugin
                if self.on_action:
                    # For refresh, we'll need to reload the plugin info
                    # This is a bit of a hack - ideally we'd have a dedicated refresh mechanism
                    try:
                        # Re-gather plugin info
                        plugin_info = self._gather_fresh_plugin_info(plugin_id)
                        self.display_plugin(plugin_id, plugin_info)
                    except Exception as e:
                        self._logger.error("Failed to refresh plugin info: %s", e)
            return
        
        # Call parent action handler
        if self.on_action and self._enabled:
            try:
                self.on_action(action, plugin_id)
            except Exception as e:
                self._logger.error("Error handling action %s for plugin %s: %s", 
                                 action, plugin_id, e)
    
    def _gather_fresh_plugin_info(self, plugin_id: str) -> Dict[str, Any]:
        """Re-gather fresh plugin information.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Fresh plugin information dictionary
        """
        # This mirrors the logic from the dialog
        from orlando_toolkit.core.plugins.registry import get_official_plugin_info
        
        info = {
            "plugin_id": plugin_id,
            "status": "unknown",
            "metadata": None,
            "installation_status": {},
            "is_official": False,
            "official_data": None
        }
        
        # Check if official plugin
        official_data = get_official_plugin_info(plugin_id)
        if official_data:
            info["is_official"] = True
            info["official_data"] = official_data
        
        # Get installation status
        if self.plugin_manager:
            info["installation_status"] = self.plugin_manager.get_installation_status(plugin_id)
            
            # Get metadata if installed
            if info["installation_status"]["installed"]:
                metadata = self.plugin_manager.get_plugin_metadata(plugin_id)
                if metadata:
                    info["metadata"] = metadata
        
        # Determine overall status
        if info["installation_status"]["active"]:
            info["status"] = "active"
        elif info["installation_status"]["loaded"]:
            info["status"] = "loaded"
        elif info["installation_status"]["installed"]:
            info["status"] = "installed"
        elif info["installation_status"]["error"]:
            info["status"] = "error"
        else:
            info["status"] = "not_installed"
        
        return info
    
    def display_error(self, error_message: str) -> None:
        """Display error message.
        
        Args:
            error_message: Error message to display
        """
        self._clear_content()
        
        error_frame = ttk.Frame(self.scrollable_frame)
        error_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        error_frame.grid_columnconfigure(0, weight=1)
        error_frame.grid_rowconfigure(0, weight=1)
        
        ttk.Label(error_frame, text="Error", font=("Arial", 14, "bold"), 
                 foreground="red").grid(row=0, column=0)
        
        ttk.Label(error_frame, text=error_message, wraplength=400,
                 foreground="red").grid(row=1, column=0, pady=(10, 0))
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable action buttons.
        
        Args:
            enabled: True to enable, False to disable
        """
        self._enabled = enabled
        
        # Enable/disable action buttons
        if hasattr(self, '_action_buttons'):
            state = "normal" if enabled else "disabled"
            for button in self._action_buttons:
                try:
                    button.configure(state=state)
                except tk.TclError:
                    pass  # Button may have been destroyed
    
    def clear(self) -> None:
        """Clear the details widget."""
        self.current_plugin_id = None
        self.current_plugin_info.clear()
        self._show_empty_state()
        
        # Clear action buttons list
        if hasattr(self, '_action_buttons'):
            self._action_buttons.clear()