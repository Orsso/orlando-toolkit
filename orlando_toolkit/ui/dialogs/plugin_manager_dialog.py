"""Plugin management dialog for installing, configuring, and managing plugins.

Main modal dialog that provides plugin management interface with two-panel layout
showing available plugins and detailed plugin information with action buttons.
"""

from __future__ import annotations

import logging
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any, Callable
from pathlib import Path

from orlando_toolkit.core.plugins.manager import PluginManager
from orlando_toolkit.core.plugins.registry import get_all_official_plugins, get_official_plugin_info
from ..widgets.plugin_list_widget import PluginListWidget
from ..widgets.plugin_details_widget import PluginDetailsWidget

logger = logging.getLogger(__name__)


class PluginManagerDialog:
    """Plugin management modal dialog with two-panel layout.
    
    Provides comprehensive plugin management interface:
    - Left panel: Available plugins (official + custom) with status indicators
    - Right panel: Plugin details with metadata and action buttons
    - GitHub repository URL import functionality
    - Install/Uninstall/Activate/Deactivate operations
    - Progress indicators and error handling
    """
    
    def __init__(self, parent: tk.Tk, plugin_manager: PluginManager):
        """Initialize plugin manager dialog.
        
        Args:
            parent: Parent window
            plugin_manager: Plugin manager instance for operations
        """
        self.parent = parent
        self.plugin_manager = plugin_manager
        self.dialog: Optional[tk.Toplevel] = None
        self.result: Optional[Dict[str, Any]] = None
        self._logger = logging.getLogger(f"{__name__}.PluginManagerDialog")
        
        # UI components
        self.plugin_list: Optional[PluginListWidget] = None
        self.plugin_details: Optional[PluginDetailsWidget] = None
        self.github_url_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        
        # Progress tracking
        self.progress_var = tk.DoubleVar()
        self.progress_bar: Optional[ttk.Progressbar] = None
        
        # Currently selected plugin
        self.selected_plugin_id: Optional[str] = None
        self.selected_plugin_data: Optional[Dict[str, Any]] = None
    
    def show_modal(self) -> Optional[Dict[str, Any]]:
        """Show the plugin manager dialog as modal window.
        
        Returns:
            Dialog result dictionary or None if cancelled
        """
        self._create_dialog()
        self._setup_layout()
        self._populate_plugin_list()
        
        # Make dialog modal
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # Center dialog on parent
        self._center_dialog()
        
        # Wait for dialog to close
        self.parent.wait_window(self.dialog)
        
        return self.result
    
    def _create_dialog(self) -> None:
        """Create the dialog window."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Plugin Manager")
        self.dialog.geometry("900x600")
        self.dialog.minsize(800, 500)
        
        # Configure closing behavior
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Configure grid weights for resizing
        self.dialog.grid_columnconfigure(0, weight=1)
        self.dialog.grid_rowconfigure(0, weight=1)
    
    def _setup_layout(self) -> None:
        """Setup the dialog layout with two-panel design."""
        # Main container
        main_frame = ttk.Frame(self.dialog)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main_frame.grid_columnconfigure(1, weight=2)  # Details panel gets more space
        main_frame.grid_columnconfigure(0, weight=1)  # List panel
        main_frame.grid_rowconfigure(1, weight=1)     # Plugin panels area
        
        # Title
        title_label = ttk.Label(main_frame, text="Plugin Manager", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="w")
        
        # Left panel - Plugin List
        list_frame = ttk.LabelFrame(main_frame, text="Available Plugins", padding=10)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        self.plugin_list = PluginListWidget(
            list_frame, 
            on_selection_changed=self._on_plugin_selected,
            plugin_manager=self.plugin_manager
        )
        self.plugin_list.grid(row=0, column=0, sticky="nsew")
        
        # GitHub URL import section
        import_frame = ttk.LabelFrame(list_frame, text="Import Custom Plugin", padding=5)
        import_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        import_frame.grid_columnconfigure(0, weight=1)
        
        ttk.Label(import_frame, text="GitHub Repository URL:").grid(row=0, column=0, sticky="w")
        
        url_frame = ttk.Frame(import_frame)
        url_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        url_frame.grid_columnconfigure(0, weight=1)
        
        self.url_entry = ttk.Entry(url_frame, textvariable=self.github_url_var)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        self.import_button = ttk.Button(url_frame, text="Import", 
                                       command=self._import_from_github)
        self.import_button.grid(row=0, column=1)
        
        # Right panel - Plugin Details
        details_frame = ttk.LabelFrame(main_frame, text="Plugin Details", padding=10)
        details_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
        details_frame.grid_columnconfigure(0, weight=1)
        details_frame.grid_rowconfigure(0, weight=1)
        
        self.plugin_details = PluginDetailsWidget(
            details_frame,
            on_action=self._on_plugin_action,
            plugin_manager=self.plugin_manager
        )
        self.plugin_details.grid(row=0, column=0, sticky="nsew")
        
        # Bottom action bar
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        action_frame.grid_columnconfigure(0, weight=1)
        
        # Status and progress
        status_frame = ttk.Frame(action_frame)
        status_frame.grid(row=0, column=0, sticky="ew")
        status_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, sticky="w")
        
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var)
        self.status_label.grid(row=0, column=1, sticky="w", padx=(5, 0))
        
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, 
                                           mode="determinate")
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        
        # Action buttons
        button_frame = ttk.Frame(action_frame)
        button_frame.grid(row=0, column=1, sticky="e")
        
        self.refresh_button = ttk.Button(button_frame, text="Refresh", 
                                        command=self._refresh_plugins)
        self.refresh_button.pack(side="left", padx=(0, 5))
        
        self.close_button = ttk.Button(button_frame, text="Close", 
                                      command=self._on_close)
        self.close_button.pack(side="left")
    
    def _center_dialog(self) -> None:
        """Center dialog on parent window."""
        self.dialog.update_idletasks()
        
        # Get parent position and size
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        # Get dialog size
        dialog_width = self.dialog.winfo_width()
        dialog_height = self.dialog.winfo_height()
        
        # Calculate center position
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        self.dialog.geometry(f"+{x}+{y}")
    
    def _populate_plugin_list(self) -> None:
        """Populate the plugin list with official and custom plugins."""
        try:
            self._set_status("Loading plugins...")
            self._set_progress(10)
            
            # Get official plugins
            official_plugins = get_all_official_plugins()
            
            # Get installed/custom plugins
            installed_plugins = self.plugin_manager.get_installed_plugins()
            
            self._set_progress(50)
            
            # Populate list widget
            self.plugin_list.populate_plugins(official_plugins, installed_plugins)
            
            self._set_progress(100)
            self._set_status("Ready")
            
            # Hide progress bar when done
            self.progress_bar.grid_remove()
            
        except Exception as e:
            self._logger.error("Failed to populate plugin list: %s", e)
            self._set_status(f"Error loading plugins: {e}")
            messagebox.showerror("Plugin List Error", 
                               f"Failed to load plugins:\n\n{e}")
    
    def _refresh_plugins(self) -> None:
        """Refresh the plugin list and reload plugin data."""
        try:
            self._set_status("Refreshing plugins...")
            self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
            
            # Refresh plugin loader
            if self.plugin_manager.plugin_loader:
                self.plugin_manager.plugin_loader.discover_plugins()
            
            # Repopulate list
            self._populate_plugin_list()
            
            # Refresh current selection
            if self.selected_plugin_id:
                self._update_plugin_details(self.selected_plugin_id)
                
        except Exception as e:
            self._logger.error("Failed to refresh plugins: %s", e)
            self._set_status(f"Refresh failed: {e}")
            messagebox.showerror("Refresh Error", 
                               f"Failed to refresh plugins:\n\n{e}")
    
    def _on_plugin_selected(self, plugin_id: str, plugin_data: Dict[str, Any]) -> None:
        """Handle plugin selection in list widget.
        
        Args:
            plugin_id: Selected plugin identifier
            plugin_data: Plugin data dictionary
        """
        self.selected_plugin_id = plugin_id
        self.selected_plugin_data = plugin_data
        self._update_plugin_details(plugin_id)
    
    def _update_plugin_details(self, plugin_id: str) -> None:
        """Update plugin details panel with selected plugin information.
        
        Args:
            plugin_id: Plugin identifier to display details for
        """
        try:
            # Get comprehensive plugin information
            plugin_info = self._gather_plugin_info(plugin_id)
            
            # Update details widget
            self.plugin_details.display_plugin(plugin_id, plugin_info)
            
        except Exception as e:
            self._logger.error("Failed to update plugin details for %s: %s", plugin_id, e)
            self.plugin_details.display_error(f"Failed to load plugin details: {e}")
    
    def _gather_plugin_info(self, plugin_id: str) -> Dict[str, Any]:
        """Gather comprehensive information about a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Dictionary with complete plugin information
        """
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
    
    def _import_from_github(self) -> None:
        """Import plugin from GitHub repository URL."""
        repo_url = self.github_url_var.get().strip()
        
        if not repo_url:
            messagebox.showerror("Invalid URL", "Please enter a GitHub repository URL")
            return
        
        if not self._is_valid_github_url(repo_url):
            messagebox.showerror("Invalid URL", 
                               "Please enter a valid GitHub repository URL\n\n"
                               "Format: https://github.com/user/repository")
            return
        
        # Run import in background thread
        self._run_plugin_operation("import", repo_url)
    
    def _is_valid_github_url(self, url: str) -> bool:
        """Validate GitHub repository URL format.
        
        Args:
            url: URL to validate
            
        Returns:
            True if URL is valid GitHub repository URL
        """
        github_pattern = r'^https://github\.com/[\w\-\.]+/[\w\-\.]+/?$'
        return bool(re.match(github_pattern, url))
    
    def _on_plugin_action(self, action: str, plugin_id: str) -> None:
        """Handle plugin action button clicks.
        
        Args:
            action: Action to perform (install, uninstall, activate, deactivate)
            plugin_id: Plugin to perform action on
        """
        self._run_plugin_operation(action, plugin_id)
    
    def _run_plugin_operation(self, operation: str, target: str) -> None:
        """Run plugin operation in background thread.
        
        Args:
            operation: Operation to perform
            target: Target (plugin_id for most operations, URL for import)
        """
        # Disable UI during operation
        self._set_ui_enabled(False)
        
        # Show progress bar
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        
        # Run operation in background
        thread = threading.Thread(
            target=self._execute_plugin_operation,
            args=(operation, target),
            daemon=True
        )
        thread.start()
    
    def _execute_plugin_operation(self, operation: str, target: str) -> None:
        """Execute plugin operation in background thread.
        
        Args:
            operation: Operation to perform
            target: Target (plugin_id or URL)
        """
        try:
            result = None
            
            if operation == "import":
                self._update_status_safe(f"Importing plugin from {target}...")
                result = self.plugin_manager.install_plugin_from_github(target)
            
            elif operation == "install":
                self._update_status_safe(f"Installing plugin {target}...")
                # For official plugins, get repository URL
                official_data = get_official_plugin_info(target)
                if official_data and "repository" in official_data:
                    repo_url = official_data["repository"]
                    branch = official_data.get("branch", "main")
                    result = self.plugin_manager.install_plugin_from_github(repo_url, branch)
                else:
                    result = type('Result', (), {
                        'success': False, 
                        'message': f"No repository URL found for {target}"
                    })()
            
            elif operation == "uninstall":
                self._update_status_safe(f"Uninstalling plugin {target}...")
                success = self.plugin_manager.remove_plugin(target, force=True)
                result = type('Result', (), {
                    'success': success,
                    'plugin_id': target,
                    'message': f"Plugin {target} uninstalled" if success else "Uninstall failed"
                })()
            
            elif operation in ["activate", "deactivate"]:
                # These operations would be handled by plugin loader
                # For now, show as not implemented
                result = type('Result', (), {
                    'success': False,
                    'plugin_id': target,
                    'message': f"{operation.title()} not yet implemented"
                })()
            
            # Update UI on main thread
            self.dialog.after(0, self._operation_completed, operation, result)
            
        except Exception as e:
            self._logger.error("Plugin operation %s failed: %s", operation, e)
            error_result = type('Result', (), {
                'success': False,
                'plugin_id': target,
                'message': f"Operation failed: {e}"
            })()
            self.dialog.after(0, self._operation_completed, operation, error_result)
    
    def _operation_completed(self, operation: str, result: Any) -> None:
        """Handle completion of plugin operation on main thread.
        
        Args:
            operation: Operation that completed
            result: Operation result
        """
        # Stop progress indicator
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.grid_remove()
        
        # Re-enable UI
        self._set_ui_enabled(True)
        
        # Handle result
        if hasattr(result, 'success'):
            if result.success:
                self._set_status(f"{operation.title()} completed successfully")
                
                # Show warnings if any
                if hasattr(result, 'warnings') and result.warnings:
                    warning_text = "\n".join(result.warnings)
                    messagebox.showwarning("Operation Warnings", 
                                         f"{operation.title()} completed with warnings:\n\n{warning_text}")
                else:
                    messagebox.showinfo("Operation Successful", result.message)
                
                # Clear GitHub URL field after successful import
                if operation == "import":
                    self.github_url_var.set("")
                
                # Refresh plugin list and update details
                self._refresh_plugins()
                
            else:
                self._set_status(f"{operation.title()} failed")
                messagebox.showerror("Operation Failed", result.message)
        else:
            self._set_status("Operation completed with unknown result")
    
    def _update_status_safe(self, message: str) -> None:
        """Update status from background thread safely."""
        self.dialog.after(0, lambda: self._set_status(message))
    
    def _set_ui_enabled(self, enabled: bool) -> None:
        """Enable/disable UI components during operations.
        
        Args:
            enabled: True to enable UI, False to disable
        """
        state = "normal" if enabled else "disabled"
        
        # Disable main action buttons
        self.import_button.configure(state=state)
        self.refresh_button.configure(state=state)
        
        # Plugin list and details handle their own state
        if self.plugin_list:
            self.plugin_list.set_enabled(enabled)
        
        if self.plugin_details:
            self.plugin_details.set_enabled(enabled)
    
    def _set_status(self, message: str) -> None:
        """Set status message.
        
        Args:
            message: Status message to display
        """
        self.status_var.set(message)
        self._logger.debug("Status: %s", message)
    
    def _set_progress(self, value: float) -> None:
        """Set progress bar value.
        
        Args:
            value: Progress value (0-100)
        """
        self.progress_var.set(value)
    
    def _on_close(self) -> None:
        """Handle dialog close event."""
        try:
            # Set result
            self.result = {
                "action": "close",
                "selected_plugin": self.selected_plugin_id
            }
            
            # Close dialog
            if self.dialog:
                self.dialog.destroy()
                
        except Exception as e:
            self._logger.error("Error closing dialog: %s", e)