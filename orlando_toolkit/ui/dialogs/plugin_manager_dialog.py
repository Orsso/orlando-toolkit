"""Clean plugin management dialog with unified approach."""

from __future__ import annotations
import logging
import threading
import tkinter as tk
from contextlib import contextmanager
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any, List
from pathlib import Path
from PIL import Image, ImageTk
from orlando_toolkit.core.plugins.manager import PluginManager
from orlando_toolkit.ui.widgets.universal_spinner import UniversalSpinner

logger = logging.getLogger(__name__)


class SimplePluginManagerDialog:
    """Simple plugin management dialog with unified plugin cards."""
    
    def __init__(self, parent: tk.Tk, plugin_manager: PluginManager):
        self.parent = parent
        self.plugin_manager = plugin_manager
        self.dialog: Optional[tk.Toplevel] = None
        self.result: Optional[Dict[str, Any]] = None
        self._logger = logging.getLogger(f"{__name__}.SimplePluginManagerDialog")
        
        self.github_url_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.plugin_cards: List[Any] = []
        self.is_busy = False
        self.loading_spinner: Optional[UniversalSpinner] = None
        
    def show_modal(self) -> Optional[Dict[str, Any]]:
        """Show the plugin manager dialog as modal window."""
        self._create_dialog()
        self._setup_layout()
        self._populate_plugins()
        
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self._center_dialog()
        self.parent.wait_window(self.dialog)
        return self.result
    
    def _create_dialog(self) -> None:
        """Create the dialog window."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Plugin Manager")
        self.dialog.geometry("800x500")
        self.dialog.minsize(700, 400)
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self.dialog.grid_columnconfigure(0, weight=1)
        self.dialog.grid_rowconfigure(0, weight=1)
    
    def _setup_layout(self) -> None:
        """Setup dialog layout."""
        main_frame = ttk.Frame(self.dialog)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)
        
        # Title
        ttk.Label(main_frame, text="Plugin Manager", font=("Arial", 14, "bold")).grid(
            row=0, column=0, pady=(0, 15), sticky="w")
        
        # URL input section
        url_frame = ttk.Frame(main_frame)
        url_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        url_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(url_frame, text="GitHub Repository URL:").grid(row=0, column=0, sticky="w")
        ttk.Entry(url_frame, textvariable=self.github_url_var, font=("Arial", 10)).grid(
            row=0, column=1, sticky="ew", padx=(10, 10))
        ttk.Button(url_frame, text="Add Plugin", 
                  command=self._import_from_github).grid(row=0, column=2, sticky="e")
        
        # Scrollable plugin list
        self.canvas = tk.Canvas(main_frame, highlightthickness=0)
        self.canvas.grid(row=2, column=0, sticky="nsew", pady=(0, 15))
        
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=2, column=1, sticky="ns", pady=(0, 15))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Configure scrolling
        def configure_scroll_region(event=None):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            
        self.scrollable_frame.bind("<Configure>", configure_scroll_region)
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        
        # Configure grid for 2-column layout with better spacing
        self.scrollable_frame.grid_columnconfigure(0, weight=1, minsize=180)
        self.scrollable_frame.grid_columnconfigure(1, weight=1, minsize=180)
        
        # Status bar
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side="left")
        ttk.Button(status_frame, text="Close", command=self._on_close).pack(side="right")
    
    def _center_dialog(self) -> None:
        """Center dialog on parent window."""
        self.dialog.update_idletasks()
        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty() 
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        dialog_width = self.dialog.winfo_width()
        dialog_height = self.dialog.winfo_height()
        
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
    
    def _populate_plugins(self) -> None:
        """Populate unified plugin list."""
        try:
            self._set_status("Loading plugins...")
            self.plugin_cards.clear()
            
            # Clear existing widgets
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            
            # Auto-fetch official plugins if missing (non-blocking)
            self._auto_fetch_official_plugins_if_missing()
            
            # Get all plugin data
            all_plugins = []
            index = 0
            
            # Add fetched plugins (ready to install) - skip if already installed
            fetched_plugins = self.plugin_manager.get_fetched_plugins()
            installed_plugins = self.plugin_manager.get_installed_plugins()
            
            for repo_url, plugin_info in fetched_plugins.items():
                if not self._is_plugin_installed(repo_url, installed_plugins):
                    all_plugins.append({
                        "type": "fetched",
                        "data": {"repo_url": repo_url, "plugin_info": plugin_info},
                        "index": index
                    })
                    index += 1
            
            # Add installed plugins
            for plugin_id in installed_plugins:
                all_plugins.append({
                    "type": "installed",
                    "data": plugin_id,
                    "index": index
                })
                index += 1
            
            # Create plugin cards
            if not all_plugins:
                # Center the empty state message properly
                self.scrollable_frame.grid_rowconfigure(0, weight=1)
                self.scrollable_frame.grid_columnconfigure(0, weight=1)
                self.scrollable_frame.grid_columnconfigure(1, weight=1)
                
                empty_frame = ttk.Frame(self.scrollable_frame)
                empty_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=50)
                empty_frame.grid_rowconfigure(0, weight=1)
                empty_frame.grid_columnconfigure(0, weight=1)
                
                empty_label = ttk.Label(empty_frame,
                    text="No plugins available.\nAdd plugins from GitHub to get started.",
                    justify="center", foreground="gray", font=("Arial", 12))
                empty_label.grid(row=0, column=0, sticky="")
            else:
                for plugin in all_plugins:
                    self._create_plugin_card(plugin)
            
            self._set_status("Ready")
            
        except Exception as e:
            self._logger.error("Failed to populate plugins: %s", e)
            self._set_status(f"Error: {e}")
    
    def _is_plugin_installed(self, repo_url: str, installed_plugins: List[str]) -> bool:
        """Check if a repository URL corresponds to an installed plugin."""
        # Get the fetched plugin metadata to compare
        fetched_plugins = self.plugin_manager.get_fetched_plugins()
        fetched_metadata = None
        if repo_url in fetched_plugins:
            fetched_metadata = fetched_plugins[repo_url].get("metadata", {})
        
        for plugin_id in installed_plugins:
            try:
                metadata = self.plugin_manager.get_plugin_metadata(plugin_id)
                if not metadata:
                    continue
                
                # Method 1: Direct homepage URL match
                if hasattr(metadata, 'homepage') and metadata.homepage == repo_url:
                    return True
                
                # Method 2: Expected directory name match
                expected_dir = repo_url.split('/')[-1].replace('.git', '')
                if plugin_id == expected_dir:
                    return True
                
                # Method 3: Plugin name match (for cases where URLs differ)
                if fetched_metadata:
                    fetched_name = fetched_metadata.get("name")
                    installed_name = getattr(metadata, 'name', None)
                    if fetched_name and installed_name and fetched_name == installed_name:
                        return True
                
            except Exception:
                continue
        return False
    
    def _create_plugin_card(self, plugin: dict) -> None:
        """Create a plugin card based on type."""
        try:
            plugin_type = plugin["type"]
            index = plugin["index"]
            
            # Create card frame with better sizing
            card_frame = ttk.LabelFrame(self.scrollable_frame, padding=12)
            card_frame.grid(row=index//2, column=index%2, sticky="ew", padx=8, pady=8)
            card_frame.configure(width=360, height=140)
            card_frame.grid_propagate(False)
            card_frame.grid_columnconfigure(1, weight=1)
            
            # Populate based on type
            if plugin_type == "fetched":
                self._populate_fetched_card(card_frame, plugin["data"])
            elif plugin_type == "installed":
                self._populate_installed_card(card_frame, plugin["data"])
            
            self.plugin_cards.append(card_frame)
            
        except Exception as e:
            self._logger.error("Failed to create plugin card: %s", e)
    
    def _populate_fetched_card(self, card_frame: ttk.Frame, data: dict) -> None:
        """Populate card for fetched plugin."""
        repo_url = data["repo_url"]
        plugin_info = data["plugin_info"]
        metadata = plugin_info["metadata"]
        
        # Icon
        icon_widget = self._create_plugin_icon_from_data(card_frame, plugin_info)
        icon_widget.grid(row=0, column=0, rowspan=5, padx=(0, 12), sticky="nw")
        
        # Header: Plugin name
        display_name = metadata.get("display_name", metadata["name"])
        name_label = ttk.Label(card_frame, text=display_name, font=("Arial", 12, "bold"))
        name_label.grid(row=0, column=1, sticky="w", pady=(0, 2))
        
        # Metadata row: Author and version
        author = metadata.get("author", "Unknown Author")
        version = metadata["version"]
        author_label = ttk.Label(card_frame, text=f"By {author}", font=("Arial", 9), foreground="#666666")
        author_label.grid(row=1, column=1, sticky="w")
        version_label = ttk.Label(card_frame, text=f"v{version}", font=("Arial", 9), foreground="#666666")
        version_label.grid(row=1, column=1, sticky="e")
        
        # Description (if available)
        description = metadata.get("description", "")
        if description and len(description) > 0:
            desc_text = description[:80] + "..." if len(description) > 80 else description
            ttk.Label(card_frame, text=desc_text, font=("Arial", 8), foreground="#888888", wraplength=250).grid(row=2, column=1, sticky="ew", pady=(2, 0))
        
        # Status with icon
        status_frame = ttk.Frame(card_frame)
        status_frame.grid(row=3, column=1, sticky="w", pady=(4, 0))
        ttk.Label(status_frame, text="\u2713", font=("Arial", 10), foreground="green").pack(side="left")
        ttk.Label(status_frame, text="Ready to Install", foreground="green", font=("Arial", 9)).pack(side="left", padx=(4, 0))
        
        # Action buttons
        button_frame = ttk.Frame(card_frame)
        button_frame.grid(row=4, column=1, sticky="ew", pady=(6, 0))
        
        # Repository link button
        repo_btn = ttk.Button(button_frame, text="\U0001f517", width=8,
                             command=lambda: self._open_repository_url(repo_url))
        repo_btn.pack(side="left")
        
        # Install button
        install_btn = ttk.Button(button_frame, text="Install", width=10,
                               command=lambda: self._install_fetched_plugin(repo_url))
        install_btn.pack(side="right")
    
    def _populate_installed_card(self, card_frame: ttk.Frame, plugin_id: str) -> None:
        """Populate card for installed plugin."""
        metadata = self.plugin_manager.get_plugin_metadata(plugin_id)
        if not metadata:
            return
            
        # Icon
        icon_widget = self._create_installed_plugin_icon(card_frame, plugin_id, metadata)
        icon_widget.grid(row=0, column=0, rowspan=5, padx=(0, 12), sticky="nw")
        
        # Header: Plugin name
        display_name = metadata.display_name or plugin_id
        name_label = ttk.Label(card_frame, text=display_name, font=("Arial", 12, "bold"))
        name_label.grid(row=0, column=1, sticky="w", pady=(0, 2))
        
        # Metadata row: Author and version
        author = metadata.author or "Unknown Author"
        version = metadata.version or '1.0.0'
        author_label = ttk.Label(card_frame, text=f"By {author}", font=("Arial", 9), foreground="#666666")
        author_label.grid(row=1, column=1, sticky="w")
        version_label = ttk.Label(card_frame, text=f"v{version}", font=("Arial", 9), foreground="#666666")
        version_label.grid(row=1, column=1, sticky="e")
        
        # Description (if available)
        description = getattr(metadata, 'description', '')
        if description and len(description) > 0:
            desc_text = description[:80] + "..." if len(description) > 80 else description
            ttk.Label(card_frame, text=desc_text, font=("Arial", 8), foreground="#888888", wraplength=250).grid(row=2, column=1, sticky="ew", pady=(2, 0))
        
        # Status with icon
        is_active = self.plugin_manager.is_plugin_active(plugin_id)
        status_frame = ttk.Frame(card_frame)
        status_frame.grid(row=3, column=1, sticky="w", pady=(4, 0))
        
        status_icon = "\u2713" if is_active else "\u23f8"
        status_text = "Active" if is_active else "Inactive"
        status_color = "green" if is_active else "orange"
        
        ttk.Label(status_frame, text=status_icon, font=("Arial", 10), foreground=status_color).pack(side="left")
        ttk.Label(status_frame, text=status_text, foreground=status_color, font=("Arial", 9)).pack(side="left", padx=(4, 0))
        
        # Action buttons
        button_frame = ttk.Frame(card_frame)
        button_frame.grid(row=4, column=1, sticky="ew", pady=(6, 0))
        
        # Repository link button - try to get the actual repository URL
        repo_url = self._get_plugin_repository_url(plugin_id, metadata)
        if repo_url:
            repo_btn = ttk.Button(button_frame, text="\U0001f517 Repo", width=8,
                                 command=lambda: self._open_repository_url(repo_url))
            repo_btn.pack(side="left")
        
        # Control buttons
        controls_frame = ttk.Frame(button_frame)
        controls_frame.pack(side="right")
        
        if is_active:
            ttk.Button(controls_frame, text="Deactivate", width=10,
                     command=lambda: self._plugin_action("deactivate", plugin_id)).pack(side="left", padx=(0, 4))
        else:
            ttk.Button(controls_frame, text="Activate", width=10,
                     command=lambda: self._plugin_action("activate", plugin_id)).pack(side="left", padx=(0, 4))
        
        ttk.Button(controls_frame, text="Remove", width=8,
                 command=lambda: self._plugin_action("remove", plugin_id)).pack(side="left")
    
    def _create_plugin_icon_from_data(self, parent: ttk.Frame, plugin_info: dict) -> ttk.Label:
        """Create plugin icon widget from plugin info data."""
        try:
            if plugin_info.get("has_image") and plugin_info.get("image_data"):
                from io import BytesIO
                image_bytes = plugin_info["image_data"]
                pil_image = Image.open(BytesIO(image_bytes))
                
                # Resize to larger icon size for better visibility
                icon_size = (40, 40)
                pil_image = pil_image.resize(icon_size, Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                photo = ImageTk.PhotoImage(pil_image)
                
                # Create label with image
                icon_label = ttk.Label(parent, image=photo)
                icon_label.image = photo  # Keep reference
                return icon_label
            else:
                return ttk.Label(parent, text="📦", font=("Arial", 24))
        except Exception as e:
            self._logger.error("Failed to create plugin icon: %s", e)
            return ttk.Label(parent, text="📦", font=("Arial", 20))
    
    def _create_installed_plugin_icon(self, parent: ttk.Frame, plugin_id: str, metadata) -> ttk.Label:
        """Create plugin icon widget for installed plugin."""
        try:
            from orlando_toolkit.core.plugins.loader import get_user_plugins_dir
            plugin_dir = get_user_plugins_dir() / plugin_id
            if plugin_dir.exists():
                icon_path = plugin_dir / "plugin-icon.png"
                if icon_path.exists():
                    pil_image = Image.open(icon_path)
                    icon_size = (40, 40)
                    pil_image = pil_image.resize(icon_size, Image.Resampling.LANCZOS)
                    
                    photo = ImageTk.PhotoImage(pil_image)
                    icon_label = ttk.Label(parent, image=photo)
                    icon_label.image = photo  # Keep reference
                    return icon_label
            
            return ttk.Label(parent, text="📦", font=("Arial", 20))
        except Exception as e:
            self._logger.error("Failed to create installed plugin icon for %s: %s", plugin_id, e)
            return ttk.Label(parent, text="📦", font=("Arial", 20))
    
    def _import_from_github(self) -> None:
        """Import plugin from GitHub URL."""
        repo_url = self.github_url_var.get().strip()
        if not repo_url:
            messagebox.showerror("Invalid URL", "Please enter a GitHub repository URL", parent=self.dialog)
        elif not repo_url.startswith("https://github.com/"):
            messagebox.showerror("Invalid URL", 
                               "Please enter a valid GitHub repository URL\\n(https://github.com/owner/repo)", 
                               parent=self.dialog)
        else:
            self._run_operation("add", repo_url)
    
    def _install_fetched_plugin(self, repo_url: str) -> None:
        """Install a previously fetched plugin."""
        self._run_operation("install_fetched", repo_url)
    
    def _plugin_action(self, action: str, plugin_id: str) -> None:
        """Handle plugin action from card buttons."""
        if not self.is_busy:
            self._run_operation(action, plugin_id)
    
    def _run_operation(self, operation: str, target: str) -> None:
        """Run plugin operation in background."""
        if not self.is_busy:
            self.is_busy = True
            self._set_ui_enabled(False)
            self._show_loading_spinner(operation, target)
            threading.Thread(target=self._execute_operation, args=(operation, target), daemon=True).start()
    
    def _show_loading_spinner(self, operation: str, target: str) -> None:
        """Show loading spinner with operation-specific message."""
        try:
            if hasattr(self, 'canvas') and self.canvas:
                # Create or reuse spinner with custom message
                operation_text = {
                    "add": "Fetching Plugin",
                    "install_fetched": "Installing Plugin", 
                    "activate": "Activating Plugin",
                    "deactivate": "Deactivating Plugin",
                    "remove": "Removing Plugin"
                }.get(operation, f"{operation.title()}ing Plugin")
                
                # Create spinner only once to prevent overlapping  
                if not self.loading_spinner:
                    self.loading_spinner = UniversalSpinner(self.canvas, operation_text)
                else:
                    # Update existing spinner message
                    self.loading_spinner.update_message(operation_text)
                
                self.loading_spinner.start()
        except Exception as e:
            self._logger.error("Failed to show loading spinner: %s", e)
    
    def _hide_loading_spinner(self) -> None:
        """Hide the loading spinner."""
        try:
            if self.loading_spinner:
                self.loading_spinner.stop()
                # Keep the spinner instance for reuse instead of setting to None
        except Exception as e:
            self._logger.error("Failed to hide loading spinner: %s", e)
    
    def _execute_operation(self, operation: str, target: str) -> None:
        """Execute plugin operation in background thread."""
        try:
            if operation == "add":
                self.dialog.after(0, lambda: self._set_status("Fetching plugin metadata..."))
                result = self.plugin_manager.add_plugin_from_github(target)
            elif operation == "install_fetched":
                self.dialog.after(0, lambda: self._set_status("Installing plugin..."))
                result = self.plugin_manager.install_fetched_plugin(target)
            elif operation == "activate":
                success = self.plugin_manager.activate_plugin(target)
                msg = "Plugin activated" if success else "Failed to activate plugin"
                result = type('R', (), {'success': success, 'message': msg})()
            elif operation == "deactivate":
                success = self.plugin_manager.deactivate_plugin(target)
                msg = "Plugin deactivated" if success else "Failed to deactivate plugin"
                result = type('R', (), {'success': success, 'message': msg})()
            elif operation == "remove":
                success = self.plugin_manager.remove_plugin(target, force=True)
                msg = "Plugin removed" if success else "Failed to remove plugin"
                result = type('R', (), {'success': success, 'message': msg})()
            else:
                result = type('R', (), {'success': False, 'message': f"Unknown operation: {operation}"})()
            
            self.dialog.after(0, self._operation_completed, operation, result)
            
        except Exception as e:
            self._logger.error("Operation %s failed: %s", operation, e)
            error_result = type('R', (), {'success': False, 'message': f"Operation failed: {e}"})()
            self.dialog.after(0, self._operation_completed, operation, error_result)
    
    def _operation_completed(self, operation: str, result: Any) -> None:
        """Handle operation completion on main thread."""
        self.is_busy = False
        self._set_ui_enabled(True)
        self._hide_loading_spinner()
        
        # Check success for both dictionary and object results
        is_success = False
        if isinstance(result, dict):
            is_success = result.get('success', False)
        elif hasattr(result, 'success'):
            is_success = result.success
            
        if is_success:
            self._set_status("Operation completed successfully")
            
            # Clear URL input after successful add operations
            if operation in ["add"]:
                self.github_url_var.set("")
            
            # Refresh UI to reflect changes
            self._refresh_plugins()
            
            # Trigger splash screen refresh for state-changing operations
            if operation in ["activate", "deactivate", "remove"]:
                self._notify_splash_screen_refresh()
        else:
            # Handle failure case
            if isinstance(result, dict) and 'success' in result and not result['success']:
                self._set_status("Operation failed")
                messagebox.showerror("Operation Failed", result.get('message', 'Unknown error'), parent=self.dialog)
            elif hasattr(result, 'success') and not result.success:
                self._set_status("Operation failed") 
                messagebox.showerror("Operation Failed", getattr(result, 'message', 'Unknown error'), parent=self.dialog)
            else:
                self._set_status("Operation completed")
    
    def _notify_splash_screen_refresh(self) -> None:
        """Notify the main app to refresh splash screen buttons after plugin changes."""
        try:
            # Find the main application instance through multiple approaches
            app_widget = None
            
            # Approach 1: Look for app context
            try:
                from orlando_toolkit.core.context import get_app_context
                context = get_app_context()
                if context:
                    app_widget = getattr(context, '_app_instance', None)
            except Exception:
                pass
            
            # Approach 2: Check if parent has app reference
            if not app_widget:
                app_widget = getattr(self.parent, '_orlando_toolkit_app', None)
            
            if app_widget and hasattr(app_widget, '_refresh_splash_screen'):
                # Schedule refresh on main thread
                self.parent.after(100, app_widget._refresh_splash_screen)
                self._logger.debug("Splash screen refresh scheduled")
            else:
                self._logger.warning("Could not find app instance to refresh splash screen")
                
        except Exception as e:
            self._logger.error("Failed to notify splash screen refresh: %s", e)
    
    def _refresh_plugins(self) -> None:
        """Refresh plugin data and rebuild cards."""
        try:
            self._set_status("Refreshing plugins...")
            self._populate_plugins()
        except Exception as e:
            self._logger.error("Failed to refresh: %s", e)
            self._set_status(f"Refresh failed: {e}")
    
    def _set_ui_enabled(self, enabled: bool) -> None:
        """Enable/disable UI elements during operations."""
        # This could be expanded to disable specific UI elements
        pass
    
    def _set_status(self, message: str) -> None:
        """Set status message."""
        self.status_var.set(message)
        self._logger.debug("Status: %s", message)
    
    def _auto_fetch_official_plugins_if_missing(self) -> None:
        """Auto-fetch official plugins if they haven't been fetched yet."""
        try:
            # Hardcoded official plugin URLs
            OFFICIAL_URLS = [
                "https://github.com/orsso/orlando-docx-plugin"
                "https://github.com/Orsso/orlando-video-plugin"
            ]
            
            # Check which ones are missing from both fetched AND installed plugins
            fetched_plugins = self.plugin_manager.get_fetched_plugins()
            installed_plugins = self.plugin_manager.get_installed_plugins()
            
            missing_urls = []
            for url in OFFICIAL_URLS:
                # Skip if already fetched
                if url in fetched_plugins:
                    continue
                    
                # Skip if already installed
                if self._is_plugin_installed(url, installed_plugins):
                    continue
                    
                missing_urls.append(url)
            
            if missing_urls:
                self._logger.info("Auto-fetching %d official plugins", len(missing_urls))
                for url in missing_urls:
                    threading.Thread(target=self._background_fetch_official_plugin, args=(url,), daemon=True).start()
        except Exception as e:
            self._logger.error("Failed to auto-fetch official plugins: %s", e)
    
    def _background_fetch_official_plugin(self, url: str) -> None:
        """Fetch official plugin in background and refresh UI when done."""
        try:
            self._logger.debug("Auto-fetching official plugin: %s", url)
            result = self.plugin_manager.add_plugin_from_github(url)
            
            if result.get("success"):
                self._logger.info("Auto-fetched official plugin successfully: %s", url)
                # Refresh UI on main thread
                self.dialog.after(0, self._refresh_plugins)
            else:
                self._logger.warning("Failed to auto-fetch official plugin %s: %s", 
                                   url, result.get("message"))
        except Exception as e:
            self._logger.error("Error auto-fetching official plugin %s: %s", url, e)

    def _get_plugin_repository_url(self, plugin_id: str, metadata) -> Optional[str]:
        """Get the actual repository URL for an installed plugin."""
        try:
            # First, try to find the plugin in fetched data (more reliable)
            fetched_plugins = self.plugin_manager.get_fetched_plugins()
            for repo_url, plugin_info in fetched_plugins.items():
                fetched_metadata = plugin_info.get("metadata", {})
                if fetched_metadata.get("name") == getattr(metadata, 'name', None):
                    return repo_url
            
            # Fallback to the homepage from metadata (might be incorrect)
            homepage = getattr(metadata, 'homepage', None)
            if homepage:
                return homepage
                
            return None
        except Exception as e:
            self._logger.error("Failed to get repository URL for plugin %s: %s", plugin_id, e)
            return None

    def _open_repository_url(self, url: str) -> None:
        """Open repository URL in default web browser."""
        try:
            import webbrowser
            webbrowser.open(url)
            self._logger.debug("Opened repository URL: %s", url)
        except Exception as e:
            self._logger.error("Failed to open repository URL %s: %s", url, e)
            messagebox.showerror("Error", f"Failed to open repository URL:\\n{url}", parent=self.dialog)

    def _on_close(self) -> None:
        """Handle dialog close event."""
        try:
            self.result = {"action": "close"}
            if self.dialog:
                self.dialog.destroy()
        except Exception as e:
            self._logger.error("Error closing dialog: %s", e)


# Backward compatibility alias
PluginManagerDialog = SimplePluginManagerDialog