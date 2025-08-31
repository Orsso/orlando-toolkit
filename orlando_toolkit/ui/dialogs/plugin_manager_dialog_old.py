"""Simplified plugin management dialog following KISS/DRY/YAGNI principles."""

from __future__ import annotations
import logging
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any, List
from pathlib import Path
from PIL import Image, ImageTk
from orlando_toolkit.core.plugins.manager import PluginManager

logger = logging.getLogger(__name__)


class SimplePluginManagerDialog:
    """Simplified plugin management dialog with minimal interface."""
    
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
        self.loading_animations: Dict[str, bool] = {}  # Track loading states by plugin URL/ID
        self.loading_overlay = None  # Global loading overlay
        self.spinner_after_id = None  # Track spinner animation
        
        # Icon cache for performance
        self._icon_cache: Dict[str, Any] = {}
        self._assets_dir = Path(__file__).parent.parent.parent / "assets" / "icons"
    
    def show_modal(self) -> Optional[Dict[str, Any]]:
        """Show the simplified plugin manager dialog as modal window."""
        self._create_dialog()
        self._setup_layout()
        self._populate_plugins()
        
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self._center_dialog()
        self.parent.wait_window(self.dialog)
        return self.result
    
    def _create_dialog(self) -> None:
        """Create the simplified dialog window."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Plugin Manager")
        self.dialog.geometry("800x700")  # Larger size to accommodate 2x2 grid layout
        self.dialog.minsize(700, 600)
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self.dialog.grid_columnconfigure(0, weight=1)
        self.dialog.grid_rowconfigure(0, weight=1)
        
        # Setup custom styles for enhanced visual appearance
        self._setup_custom_styles()
    
    def _setup_layout(self) -> None:
        """Setup simplified single-panel dialog layout."""
        main_frame = ttk.Frame(self.dialog)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)
        
        # Title and GitHub URL section
        ttk.Label(main_frame, text="Plugin Manager", font=("Arial", 14, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 15))
        
        import_frame = ttk.LabelFrame(main_frame, text="Add Plugin from GitHub", padding=10)
        import_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        import_frame.grid_columnconfigure(0, weight=1)
        
        url_frame = ttk.Frame(import_frame)
        url_frame.grid(row=0, column=0, sticky="ew")
        url_frame.grid_columnconfigure(0, weight=1)
        
        self.url_entry = ttk.Entry(url_frame, textvariable=self.github_url_var)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.url_entry.bind('<Return>', lambda e: self._import_from_github())
        
        self.import_button = ttk.Button(url_frame, text="Add", command=self._import_from_github)
        self.import_button.grid(row=0, column=1)
        
        # Unified Plugin List
        self.plugins_container = ttk.LabelFrame(main_frame, text="Plugins", padding=10)
        self.plugins_container.grid(row=1, column=0, sticky="nsew")
        
        canvas = tk.Canvas(self.plugins_container, highlightthickness=0, bg="white")
        scrollbar = ttk.Scrollbar(self.plugins_container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Enable mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Configure grid for responsive 2-3 cards per row
        self.scrollable_frame.grid_columnconfigure(0, weight=1, minsize=320)
        self.scrollable_frame.grid_columnconfigure(1, weight=1, minsize=320)
        
        # Bottom bar
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=2, column=0, sticky="ew", pady=(15, 0))
        bottom_frame.grid_columnconfigure(0, weight=1)
        
        self.status_label = ttk.Label(bottom_frame, textvariable=self.status_var, foreground="blue")
        self.status_label.grid(row=0, column=0, sticky="w")
        
        button_frame = ttk.Frame(bottom_frame)
        button_frame.grid(row=0, column=1, sticky="e")
        
        self.refresh_button = ttk.Button(button_frame, text="Refresh", command=self._refresh_plugins)
        self.refresh_button.pack(side="left", padx=(0, 5))
        
        self.close_button = ttk.Button(button_frame, text="Close", command=self._on_close)
        self.close_button.pack(side="left")
    
    def _setup_custom_styles(self) -> None:
        """Setup custom TTK styles for enhanced visual appearance."""
        style = ttk.Style()
        
        # Configure button styles with colors
        style.configure("Success.TButton", foreground="#2e7d32")
        style.configure("Warning.TButton", foreground="#ef6c00")
        style.configure("Danger.TButton", foreground="#c62828")
        style.configure("Info.TButton", foreground="#1565c0")
        
        # Card frame style
        style.configure("Card.TFrame", relief="flat", borderwidth=1)
    
    def _center_dialog(self) -> None:
        """Center dialog on parent window."""
        self.dialog.update_idletasks()
        px, py = self.parent.winfo_x(), self.parent.winfo_y()
        pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
        dw, dh = self.dialog.winfo_width(), self.dialog.winfo_height()
        self.dialog.geometry(f"+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")
    
    def _populate_plugins(self) -> None:
        """Populate unified plugin list with all plugin states."""
        try:
            self._set_status("Loading plugins...")
            self.plugin_cards.clear()
            
            # Clear the unified list
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            
            # Collect all plugins in order: official → fetched → installed
            all_plugins = []
            index = 0
            
            # Auto-fetch official plugins if missing (non-blocking)
            self._auto_fetch_official_plugins_if_missing()
            
            # Add fetched plugins (ready to install) - but skip if already installed
            fetched_plugins = self.plugin_manager.get_fetched_plugins()
            installed_plugins = self.plugin_manager.get_installed_plugins()
            
            for repo_url, plugin_info in fetched_plugins.items():
                # Check if this fetched plugin is already installed
                is_installed = False
                for plugin_id in installed_plugins:
                    try:
                        metadata = self.plugin_manager.get_plugin_metadata(plugin_id)
                        if metadata and hasattr(metadata, 'homepage') and metadata.homepage == repo_url:
                            is_installed = True
                            break
                        # Also check by expected directory name
                        expected_dir = repo_url.split('/')[-1].replace('.git', '')
                        if plugin_id == expected_dir:
                            is_installed = True
                            break
                    except Exception:
                        continue
                
                if not is_installed:
                    all_plugins.append({
                        "type": "fetched", 
                        "data": {"repo_url": repo_url, "plugin_info": plugin_info},
                        "index": index
                    })
                    index += 1
            
            # Add installed plugins
            installed_plugins = self.plugin_manager.get_installed_plugins()
            for plugin_id in installed_plugins:
                all_plugins.append({
                    "type": "installed",
                    "data": plugin_id,
                    "index": index
                })
                index += 1
            
            # Create unified plugin cards
            if not all_plugins:
                ttk.Label(self.scrollable_frame,
                    text="No plugins available.\nAdd plugins from GitHub or official plugins to get started.",
                    justify="center", foreground="gray").grid(row=0, column=0, columnspan=2, pady=50)
            else:
                for plugin in all_plugins:
                    self._create_unified_plugin_card(plugin)
            
            self._set_status("Ready")
            
        except Exception as e:
            self._logger.error("Failed to populate plugins: %s", e)
            self._set_status(f"Error loading plugins: {e}")
    
    def _create_unified_plugin_card(self, plugin: dict) -> None:
        """Create consistent plugin card for all plugin states."""
        plugin_type = plugin["type"]
        index = plugin["index"] 
        
        # Create main card frame with consistent sizing
        card_frame = ttk.LabelFrame(self.scrollable_frame, padding=15)
        card_frame.grid(row=index//2, column=index%2, sticky="ew", padx=8, pady=6, ipadx=10, ipady=5)
        card_frame.grid_columnconfigure(1, weight=1)
        
        # Set minimum size for consistency
        card_frame.grid_propagate(False)
        card_frame.configure(height=120, width=320)
        
        try:
            if plugin_type == "official":
                self._populate_official_card(card_frame, plugin["data"])
            elif plugin_type == "fetched":
                self._populate_fetched_card(card_frame, plugin["data"])
            elif plugin_type == "installed":
                self._populate_installed_card(card_frame, plugin["data"])
                self.plugin_cards[plugin["data"]] = card_frame
                
        except Exception as e:
            self._logger.error("Failed to create plugin card: %s", e)
    
    def _populate_official_card(self, card_frame: ttk.Frame, plugin: dict) -> None:
        """Populate card for official plugin."""
        # Icon
        icon_label = ttk.Label(card_frame, text="📦", font=("Arial", 20))
        icon_label.grid(row=0, column=0, rowspan=4, padx=(0, 10), sticky="nw")
        
        # Plugin name
        ttk.Label(card_frame, text=plugin["name"], font=("Arial", 11, "bold")).grid(row=0, column=1, sticky="w")
        
        # Author/Source
        ttk.Label(card_frame, text="By Orlando Team", font=("Arial", 9), foreground="gray").grid(row=1, column=1, sticky="w")
        
        # Status
        ttk.Label(card_frame, text="Official Plugin", foreground="blue", font=("Arial", 9)).grid(row=2, column=1, sticky="w", pady=(2, 0))
        
        # Add button
        add_btn = ttk.Button(card_frame, text="Add",
                           command=lambda: self._add_official_plugin(plugin["url"]))
        add_btn.grid(row=3, column=1, sticky="e", pady=(5, 0))
    
    def _populate_fetched_card(self, card_frame: ttk.Frame, data: dict) -> None:
        """Populate card for fetched plugin."""
        repo_url = data["repo_url"]
        plugin_info = data["plugin_info"]
        metadata = plugin_info["metadata"]
        
        # Icon - use actual image or package emoji
        icon_widget = self._create_plugin_icon_from_data(card_frame, plugin_info)
        icon_widget.grid(row=0, column=0, rowspan=4, padx=(0, 10), sticky="nw")
        
        # Plugin name (without version)
        display_name = metadata.get("display_name", metadata["name"])
        ttk.Label(card_frame, text=display_name, font=("Arial", 11, "bold")).grid(row=0, column=1, sticky="w")
        
        # Author and version
        author = metadata.get("author", "Unknown Author")
        version = metadata["version"]
        author_version_text = f"By {author} • v{version}"
        ttk.Label(card_frame, text=author_version_text, font=("Arial", 9), foreground="gray").grid(row=1, column=1, sticky="w")
        
        # Status
        ttk.Label(card_frame, text="Ready to Install", foreground="green", font=("Arial", 9)).grid(row=2, column=1, sticky="w", pady=(2, 0))
        
        # Install button
        install_btn = ttk.Button(card_frame, text="Install", 
                               command=lambda: self._install_fetched_plugin(repo_url))
        install_btn.grid(row=3, column=1, sticky="e", pady=(10, 0))
    
    def _populate_installed_card(self, card_frame: ttk.Frame, plugin_id: str) -> None:
        """Populate card for installed plugin."""
        metadata = self.plugin_manager.get_plugin_metadata(plugin_id)
        if not metadata:
            return
            
        # Icon
        icon_widget = self._create_installed_plugin_icon(card_frame, plugin_id, metadata)
        icon_widget.grid(row=0, column=0, rowspan=4, padx=(0, 10), sticky="nw")
        
        # Plugin name (without version)
        display_name = metadata.display_name or plugin_id
        ttk.Label(card_frame, text=display_name, font=("Arial", 11, "bold")).grid(row=0, column=1, sticky="w")
        
        # Author and version
        author = metadata.author or "Unknown Author"
        version = metadata.version or '1.0.0'
        author_version_text = f"By {author} • v{version}"
        ttk.Label(card_frame, text=author_version_text, font=("Arial", 9), foreground="gray").grid(row=1, column=1, sticky="w")
        
        # Status
        status_text = "Active" if self.plugin_manager.is_plugin_active(plugin_id) else "Inactive"
        status_color = "green" if self.plugin_manager.is_plugin_active(plugin_id) else "orange"
        ttk.Label(card_frame, text=status_text, foreground=status_color, font=("Arial", 9)).grid(row=2, column=1, sticky="w", pady=(2, 0))
        
        # Action buttons
        button_frame = ttk.Frame(card_frame)
        button_frame.grid(row=3, column=1, sticky="e", pady=(10, 0))
        
        if self.plugin_manager.is_plugin_active(plugin_id):
            ttk.Button(button_frame, text="Deactivate", 
                     command=lambda: self._plugin_action("deactivate", plugin_id)).pack(side="left", padx=(0, 5))
        else:
            ttk.Button(button_frame, text="Activate",
                     command=lambda: self._plugin_action("activate", plugin_id)).pack(side="left", padx=(0, 5))
        
        ttk.Button(button_frame, text="Remove",
                 command=lambda: self._plugin_action("remove", plugin_id)).pack(side="left")
    
    def _create_plugin_card(self, plugin_id: str, index: int) -> None:
        """Create an enhanced visual plugin card with icons and state indicators."""
        # Create main card frame with enhanced styling
        card_frame = ttk.Frame(self.scrollable_frame, style="Card.TFrame")
        card_frame.grid(row=index//2, column=index%2, sticky="ew", padx=8, pady=6)
        card_frame.grid_columnconfigure(1, weight=1)
        
        try:
            metadata = self.plugin_manager.get_plugin_metadata(plugin_id)
            status = self.plugin_manager.get_installation_status(plugin_id)
            
            # Create inner frame with border effect
            inner_frame = ttk.LabelFrame(card_frame, padding=15)
            inner_frame.pack(fill="both", expand=True)
            inner_frame.grid_columnconfigure(1, weight=1)
            
            # Top row: Icon and basic info
            top_frame = ttk.Frame(inner_frame)
            top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
            top_frame.grid_columnconfigure(1, weight=1)
            
            # Plugin icon
            icon_widget = self._create_plugin_icon(top_frame, plugin_id, metadata)
            icon_widget.grid(row=0, column=0, padx=(0, 12), sticky="nw")
            
            # Plugin title and basic info
            info_frame = ttk.Frame(top_frame)
            info_frame.grid(row=0, column=1, sticky="ew")
            info_frame.grid_columnconfigure(0, weight=1)
            
            # Plugin name/display name
            display_name = getattr(metadata, 'display_name', None) or plugin_id if metadata else plugin_id
            title_label = ttk.Label(info_frame, text=display_name, font=("Arial", 11, "bold"))
            title_label.grid(row=0, column=0, sticky="w")
            
            # Plugin ID (if different from display name)
            if metadata and metadata.display_name and metadata.display_name != plugin_id:
                id_label = ttk.Label(info_frame, text=f"({plugin_id})", font=("Arial", 8), foreground="gray")
                id_label.grid(row=1, column=0, sticky="w")
                info_row = 2
            else:
                info_row = 1
            
            # Version
            if metadata and hasattr(metadata, 'version'):
                version_label = ttk.Label(info_frame, text=f"v{metadata.version}", font=("Arial", 9), foreground="#666")
                version_label.grid(row=info_row, column=0, sticky="w")
                info_row += 1
            
            # State indicator in top-right
            state_frame = ttk.Frame(top_frame)
            state_frame.grid(row=0, column=2, sticky="ne")
            
            state_indicator = self._create_state_indicator(state_frame, status)
            state_indicator.pack()
            
            # Description (if available)
            if metadata and hasattr(metadata, 'description') and metadata.description:
                desc_text = metadata.description
                if len(desc_text) > 100:
                    desc_text = desc_text[:97] + "..."
                
                desc_label = ttk.Label(inner_frame, text=desc_text, 
                                     font=("Arial", 9), foreground="#555", wraplength=280)
                desc_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
            
            # Author and category info
            meta_frame = ttk.Frame(inner_frame)
            meta_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
            meta_frame.grid_columnconfigure(1, weight=1)
            
            meta_info_parts = []
            if metadata:
                if hasattr(metadata, 'author') and metadata.author:
                    meta_info_parts.append(f"By {metadata.author}")
                if hasattr(metadata, 'category') and metadata.category:
                    meta_info_parts.append(f"Category: {metadata.category}")
            
            if meta_info_parts:
                meta_text = " • ".join(meta_info_parts)
                meta_label = ttk.Label(meta_frame, text=meta_text, font=("Arial", 8), foreground="gray")
                meta_label.grid(row=0, column=0, sticky="w")
            
            # Action buttons
            button_frame = ttk.Frame(inner_frame)
            button_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 0))
            
            # Remove button (always on right)
            remove_btn = ttk.Button(button_frame, text="Remove", 
                                  command=lambda: self._plugin_action("remove", plugin_id),
                                  style="Danger.TButton")
            remove_btn.pack(side="right", padx=(5, 0))
            
            # Activate/Deactivate button
            is_active = status.get("active", False)
            action_text = "Deactivate" if is_active else "Activate"
            action_cmd = "deactivate" if is_active else "activate"
            button_style = "Success.TButton" if not is_active else "Warning.TButton"
            
            action_btn = ttk.Button(button_frame, text=action_text,
                                  command=lambda: self._plugin_action(action_cmd, plugin_id),
                                  style=button_style)
            action_btn.pack(side="right", padx=(5, 0))
            
            # Status information button (for details)
            if status.get("error"):
                error_btn = ttk.Button(button_frame, text="View Error",
                                     command=lambda: self._show_plugin_error(plugin_id, status["error"]),
                                     style="Info.TButton")
                error_btn.pack(side="left")
            
        except Exception as e:
            self._logger.error(f"Error creating card for {plugin_id}: {e}")
            # Fallback simple card for errors
            error_frame = ttk.LabelFrame(card_frame, text=f"Error: {plugin_id}", padding=10)
            error_frame.pack(fill="both", expand=True)
            ttk.Label(error_frame, text="Error loading plugin info", foreground="red").pack()
            ttk.Label(error_frame, text=str(e), font=("Arial", 8), foreground="gray").pack()
        
        self.plugin_cards.append(card_frame)
    
    def _create_plugin_icon_from_data(self, parent: ttk.Frame, plugin_info: dict) -> ttk.Label:
        """Create plugin icon widget from plugin info data."""
        try:
            if plugin_info.get("has_image") and plugin_info.get("image_data"):
                # Convert bytes to PIL Image
                from io import BytesIO
                image_bytes = plugin_info["image_data"]
                pil_image = Image.open(BytesIO(image_bytes))
                
                # Resize to standard icon size
                icon_size = (32, 32)
                pil_image = pil_image.resize(icon_size, Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                photo = ImageTk.PhotoImage(pil_image)
                
                # Create label with image
                icon_label = ttk.Label(parent, image=photo)
                # Keep a reference to prevent garbage collection
                icon_label.image = photo
                
                return icon_label
            else:
                # Fallback to emoji
                return ttk.Label(parent, text="📦", font=("Arial", 20))
                
        except Exception as e:
            self._logger.error("Failed to create plugin icon: %s", e)
            # Fallback to emoji on error
            return ttk.Label(parent, text="📦", font=("Arial", 20))
    
    def _create_installed_plugin_icon(self, parent: ttk.Frame, plugin_id: str, metadata) -> ttk.Label:
        """Create plugin icon widget for installed plugin."""
        try:
            # Get plugin directory
            from orlando_toolkit.core.plugins.loader import get_user_plugins_dir
            plugin_dir = get_user_plugins_dir() / plugin_id
            if plugin_dir.exists():
                icon_path = plugin_dir / "plugin-icon.png"
                if icon_path.exists():
                    # Load and resize image
                    pil_image = Image.open(icon_path)
                    icon_size = (32, 32)
                    pil_image = pil_image.resize(icon_size, Image.Resampling.LANCZOS)
                    
                    # Convert to PhotoImage
                    photo = ImageTk.PhotoImage(pil_image)
                    
                    # Create label with image
                    icon_label = ttk.Label(parent, image=photo)
                    # Keep a reference to prevent garbage collection
                    icon_label.image = photo
                    
                    return icon_label
            
            # Fallback to emoji
            return ttk.Label(parent, text="📦", font=("Arial", 20))
                
        except Exception as e:
            self._logger.error("Failed to create installed plugin icon for %s: %s", plugin_id, e)
            # Fallback to emoji on error
            return ttk.Label(parent, text="📦", font=("Arial", 20))
    
    def _show_loading_animation(self, card_frame: ttk.Frame, operation: str) -> None:
        """Show loading animation on a plugin card."""
        try:
            # Clear existing content
            for widget in card_frame.winfo_children():
                widget.destroy()
            
            # Create loading content
            loading_frame = ttk.LabelFrame(card_frame, padding=15)
            loading_frame.pack(fill="both", expand=True)
            loading_frame.configure(width=320, height=120)
            loading_frame.grid_propagate(False)
            loading_frame.grid_columnconfigure(1, weight=1)
            
            # Animated icon (simple text-based spinner)
            self.spinner_state = getattr(self, 'spinner_state', 0)
            spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spinner_label = ttk.Label(loading_frame, text=spinner_chars[self.spinner_state % len(spinner_chars)], 
                                    font=("Arial", 20))
            spinner_label.grid(row=0, column=0, rowspan=3, padx=(0, 10), sticky="nw")
            
            # Loading message
            operation_text = {
                "add": "Fetching plugin...",
                "install_fetched": "Installing plugin...", 
                "import": "Installing from GitHub...",
                "activate": "Activating plugin...",
                "deactivate": "Deactivating plugin...",
                "remove": "Removing plugin..."
            }.get(operation, f"{operation.title()}ing...")
            
            ttk.Label(loading_frame, text=operation_text, font=("Arial", 11, "bold")).grid(row=0, column=1, sticky="w")
            ttk.Label(loading_frame, text="Please wait...", font=("Arial", 9), foreground="gray").grid(row=1, column=1, sticky="w")
            
            # Schedule spinner update
            self.dialog.after(100, lambda: self._update_spinner_animation(spinner_label))
            
        except Exception as e:
            self._logger.error("Failed to show loading animation: %s", e)
    
    def _update_spinner_animation(self, spinner_label: ttk.Label) -> None:
        """Update the spinner animation."""
        try:
            if spinner_label.winfo_exists():
                self.spinner_state = getattr(self, 'spinner_state', 0) + 1
                spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                spinner_label.configure(text=spinner_chars[self.spinner_state % len(spinner_chars)])
                # Continue animation if widget still exists
                self.dialog.after(100, lambda: self._update_spinner_animation(spinner_label))
        except Exception:
            pass  # Widget was destroyed, stop animation
    
    def _find_plugin_card_by_url(self, url: str) -> Optional[ttk.Frame]:
        """Find a plugin card frame by its associated URL."""
        # This is a simplified approach - in a more complex implementation,
        # we'd store card-to-URL mapping during creation
        for card in self.plugin_cards:
            try:
                if card.winfo_exists():
                    # Check if this card contains the URL (stored in widget data or similar)
                    # For now, we'll identify by operation type and refresh all
                    return card
            except Exception:
                continue
        return None
    
    def _refresh_plugins(self) -> None:
        """Refresh plugin data and rebuild cards."""
        try:
            self._set_status("Refreshing plugins...")
            # Synchronize plugin states before repopulating UI
            self._synchronize_plugin_states()
            # Repopulate with current plugin states
            self._populate_plugins()
        except Exception as e:
            self._logger.error("Failed to refresh: %s", e)
            self._set_status(f"Refresh failed: {e}")
            messagebox.showerror("Refresh Error", f"Failed to refresh plugins:\n\n{e}", parent=self.dialog)
    
    def _synchronize_plugin_states(self) -> None:
        """Ensure plugin states are consistent between loader and manager."""
        try:
            if not self.plugin_manager or not self.plugin_manager.plugin_loader:
                return
            
            # Get all plugin info objects
            all_plugins = self.plugin_manager.plugin_loader.get_all_plugins()
            
            for plugin_id, plugin_info in all_plugins.items():
                # Verify state consistency
                manager_active = self.plugin_manager.is_plugin_active(plugin_id)
                loader_active = plugin_info.is_active()
                
                if manager_active != loader_active:
                    self._logger.warning(
                        "State inconsistency detected for plugin %s: "
                        "manager=%s, loader=%s. Correcting to loader state.", 
                        plugin_id, manager_active, loader_active
                    )
                    # Loader state is the source of truth
                    # No action needed - manager now correctly checks loader state
                
        except Exception as e:
            self._logger.error("Failed to synchronize plugin states: %s", e)
    
    def _import_from_github(self) -> None:
        """Add plugin from GitHub URL (fetch metadata only)."""
        repo_url = self.github_url_var.get().strip()
        
        if not repo_url:
            messagebox.showerror("Invalid URL", "Please enter a GitHub repository URL", parent=self.dialog)
        elif not re.match(r'^https://github\.com/[\w\-\.]+/[\w\-\.]+/?$', repo_url):
            messagebox.showerror("Invalid URL", 
                "Please enter a valid GitHub repository URL\n\nFormat: https://github.com/user/repository",
                parent=self.dialog)
        else:
            self._run_operation("add", repo_url)
    
    def _add_official_plugin(self, repo_url: str) -> None:
        """Add official plugin (fetch metadata)."""
        self._run_operation("add", repo_url)
    
    def _install_fetched_plugin(self, repo_url: str) -> None:
        """Install a previously fetched plugin."""
        self._run_operation("install_fetched", repo_url)
    
    def _plugin_action(self, action: str, plugin_id: str) -> None:
        """Handle plugin action from card buttons (Phase 3 integration point)."""
        if not self.is_busy:
            self._run_operation(action, plugin_id)
    
    def _run_operation(self, operation: str, target: str) -> None:
        """Run plugin operation in background (Phase 3 integration point)."""
        if not self.is_busy:
            self.is_busy = True
            self._set_ui_enabled(False)
            
            # Show loading animation for the specific plugin card
            self._show_operation_loading(operation, target)
            
            threading.Thread(target=self._execute_operation, args=(operation, target), daemon=True).start()
    
    def _show_operation_loading(self, operation: str, target: str) -> None:
        """Show loading animation for the specific operation."""
        try:
            # Set status message
            operation_messages = {
                "add": "Fetching plugin metadata...",
                "install_fetched": "Installing plugin...",
                "import": "Installing from GitHub...",
                "activate": "Activating plugin...",
                "deactivate": "Deactivating plugin...",
                "remove": "Removing plugin..."
            }
            status_msg = operation_messages.get(operation, f"{operation.title()}ing plugin...")
            self._set_status(status_msg)
            
            # Show global loading overlay
            self._show_loading_overlay(operation, target)
                
        except Exception as e:
            self._logger.error("Failed to show operation loading: %s", e)
    
    def _show_loading_overlay(self, operation: str, target: str) -> None:
        """Show a loading overlay on the plugin area."""
        try:
            if hasattr(self, 'scrollable_frame') and self.scrollable_frame:
                # Create overlay frame
                self.loading_overlay = ttk.Frame(self.scrollable_frame)
                self.loading_overlay.place(x=0, y=0, relwidth=1, relheight=1)
                
                # Semi-transparent background effect (using a styled frame)
                bg_frame = ttk.LabelFrame(self.loading_overlay, padding=20)
                bg_frame.place(relx=0.5, rely=0.5, anchor="center")
                
                # Loading content
                content_frame = ttk.Frame(bg_frame)
                content_frame.pack()
                
                # Spinner
                self.spinner_state = 0
                spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                self.spinner_label = ttk.Label(content_frame, text=spinner_chars[0], 
                                             font=("Arial", 24), foreground="blue")
                self.spinner_label.pack(pady=(0, 10))
                
                # Operation message
                operation_text = {
                    "add": "Fetching Plugin",
                    "install_fetched": "Installing Plugin", 
                    "import": "Installing from GitHub",
                    "activate": "Activating Plugin",
                    "deactivate": "Deactivating Plugin",
                    "remove": "Removing Plugin"
                }.get(operation, f"{operation.title()}ing Plugin")
                
                ttk.Label(content_frame, text=operation_text, 
                         font=("Arial", 12, "bold")).pack()
                ttk.Label(content_frame, text="Please wait...", 
                         font=("Arial", 10), foreground="gray").pack()
                
                # Start spinner animation
                self._start_spinner_animation()
                
        except Exception as e:
            self._logger.error("Failed to show loading overlay: %s", e)
    
    def _start_spinner_animation(self) -> None:
        """Start the spinner animation."""
        try:
            if hasattr(self, 'spinner_label') and self.spinner_label and self.spinner_label.winfo_exists():
                self.spinner_state = (self.spinner_state + 1) % 10
                spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                self.spinner_label.configure(text=spinner_chars[self.spinner_state])
                # Schedule next animation frame
                self.spinner_after_id = self.dialog.after(150, self._start_spinner_animation)
        except Exception:
            pass
    
    def _hide_loading_overlay(self) -> None:
        """Hide the loading overlay."""
        try:
            # Cancel spinner animation
            if self.spinner_after_id:
                self.dialog.after_cancel(self.spinner_after_id)
                self.spinner_after_id = None
            
            # Remove overlay
            if self.loading_overlay and self.loading_overlay.winfo_exists():
                self.loading_overlay.destroy()
                self.loading_overlay = None
                
        except Exception as e:
            self._logger.error("Failed to hide loading overlay: %s", e)
    
    def _execute_operation(self, operation: str, target: str) -> None:
        """Execute plugin operation in background thread."""
        try:
            if operation == "add":
                self.dialog.after(0, lambda: self._set_status("Fetching plugin metadata..."))
                result = self.plugin_manager.add_plugin_from_github(target)
            elif operation == "install_fetched":
                self.dialog.after(0, lambda: self._set_status("Installing plugin..."))
                result = self.plugin_manager.install_fetched_plugin(target)
            elif operation == "import":
                # Legacy operation - direct install 
                self.dialog.after(0, lambda: self._set_status("Installing plugin from GitHub..."))
                result = self.plugin_manager.install_plugin_from_github(target)
            else:
                self.dialog.after(0, lambda: self._set_status(f"{operation.title()}ing plugin..."))
                
                if operation == "activate":
                    success = self.plugin_manager.activate_plugin(target)
                elif operation == "deactivate":
                    success = self.plugin_manager.deactivate_plugin(target)
                elif operation == "remove":
                    success = self.plugin_manager.remove_plugin(target, force=True)
                else:
                    success = False
                
                msg = f"Plugin {operation}d" if success else f"Failed to {operation} plugin"
                result = type('R', (), {'success': success, 'message': msg})()
            
            self.dialog.after(0, self._operation_completed, operation, result)
            
        except Exception as e:
            self._logger.error("Operation %s failed: %s", operation, e)
            error_result = type('R', (), {'success': False, 'message': f"Operation failed: {e}"})()
            self.dialog.after(0, self._operation_completed, operation, error_result)
    
    def _operation_completed(self, operation: str, result: Any) -> None:
        """Handle operation completion on main thread."""
        self.is_busy = False
        self._set_ui_enabled(True)
        
        # Hide loading overlay
        self._hide_loading_overlay()
        
        # Check success for both dictionary and object results
        is_success = False
        if isinstance(result, dict):
            is_success = result.get('success', False)
        elif hasattr(result, 'success'):
            is_success = result.success
            
        if is_success:
            self._set_status("Operation completed successfully")
            
            # Clear URL input after successful add operations
            if operation in ["add", "import"]:
                self.github_url_var.set("")
            
            # Force immediate state synchronization for activation/deactivation operations
            if operation in ["activate", "deactivate"]:
                self._synchronize_plugin_states()
                
            # Refresh UI to reflect changes for all operations that modify plugin state
            self._refresh_plugins()
            
            # Trigger splash screen refresh for plugin activation/deactivation/removal
            if operation in ["activate", "deactivate", "remove"]:
                self._notify_splash_screen_refresh()
                
        else:
            # Handle failure case for both dictionary and object results
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
            
            # Approach 1: Check parent for stored reference
            if hasattr(self.parent, '_orlando_toolkit_app'):
                app_widget = getattr(self.parent, '_orlando_toolkit_app', None)
                
            # Approach 2: Use global app context if available
            if not app_widget:
                from orlando_toolkit.core.context import get_app_context
                context = get_app_context()
                if context and hasattr(context, '_app_instance'):
                    app_widget = getattr(context, '_app_instance', None)
            
            # Approach 3: Search through window hierarchy
            if not app_widget:
                current = self.parent
                while current and not app_widget:
                    if hasattr(current, '_orlando_toolkit_app'):
                        app_widget = getattr(current, '_orlando_toolkit_app', None)
                        break
                    current = getattr(current, 'master', None)
            
            if app_widget and hasattr(app_widget, '_refresh_splash_screen'):
                # Schedule refresh on main thread to avoid threading issues
                self.parent.after(100, app_widget._refresh_splash_screen)
                self._logger.debug("Splash screen refresh scheduled")
            else:
                self._logger.warning("Could not find main app instance to refresh splash screen")
        except Exception as e:
            self._logger.error("Failed to trigger splash screen refresh: %s", e)
    
    def _create_plugin_icon(self, parent: ttk.Widget, plugin_id: str, metadata) -> ttk.Widget:
        """Create plugin icon widget with fallback handling."""
        icon_frame = ttk.Frame(parent)
        
        try:
            # Try to load custom plugin icon first
            icon_path = None
            
            # Check if metadata specifies an icon
            if metadata and hasattr(metadata, 'ui') and metadata.ui:
                icon_name = metadata.ui.get('splash_button', {}).get('icon')
                if icon_name:
                    # Look in plugin directory first
                    plugin_dir = self.plugin_manager._plugins_dir / plugin_id
                    plugin_icon_path = plugin_dir / icon_name
                    if plugin_icon_path.exists():
                        icon_path = plugin_icon_path
                    else:
                        # Look in assets directory
                        assets_icon_path = self._assets_dir / icon_name
                        if assets_icon_path.exists():
                            icon_path = assets_icon_path
            
            # Fallback to default plugin icon
            if not icon_path:
                icon_path = self._assets_dir / "default-plugin-icon.png"
                if not icon_path.exists():
                    icon_path = self._assets_dir / "plugin-icon.png"
            
            # Load and resize icon
            if icon_path and icon_path.exists():
                if str(icon_path) not in self._icon_cache:
                    with Image.open(icon_path) as img:
                        # Resize to 48x48 for cards
                        img = img.resize((48, 48), Image.Resampling.LANCZOS)
                        self._icon_cache[str(icon_path)] = ImageTk.PhotoImage(img)
                
                icon_label = ttk.Label(icon_frame, image=self._icon_cache[str(icon_path)])
                icon_label.pack()
                return icon_frame
                
        except Exception as e:
            self._logger.debug(f"Failed to load icon for {plugin_id}: {e}")
        
        # Fallback to text icon
        fallback_label = ttk.Label(icon_frame, text="📦", font=("Arial", 24))
        fallback_label.pack()
        return icon_frame
    
    def _create_state_indicator(self, parent: ttk.Widget, status: Dict[str, Any]) -> ttk.Widget:
        """Create visual state indicator for plugin status."""
        indicator_frame = ttk.Frame(parent)
        
        # Determine state and colors
        if status.get("error"):
            state_text = "Error"
            bg_color = "#ffebee"
            fg_color = "#c62828"
            indicator = "⚠"
        elif status.get("active"):
            state_text = "Active"
            bg_color = "#e8f5e8"
            fg_color = "#2e7d32"
            indicator = "●"
        elif status.get("loaded"):
            state_text = "Loaded"
            bg_color = "#fff3e0"
            fg_color = "#ef6c00"
            indicator = "◐"
        elif status.get("installed"):
            state_text = "Installed"
            bg_color = "#e3f2fd"
            fg_color = "#1565c0"
            indicator = "○"
        else:
            state_text = "Unknown"
            bg_color = "#f5f5f5"
            fg_color = "#757575"
            indicator = "?"
        
        # Create styled state label
        state_label = tk.Label(indicator_frame, 
                              text=f"{indicator} {state_text}",
                              font=("Arial", 8, "bold"),
                              bg=bg_color, fg=fg_color,
                              padx=8, pady=4,
                              relief="solid", bd=1)
        state_label.pack()
        
        return indicator_frame
    
    def _show_plugin_error(self, plugin_id: str, error_msg: str) -> None:
        """Show detailed plugin error in a dialog."""
        messagebox.showerror(
            f"Plugin Error - {plugin_id}",
            f"Plugin '{plugin_id}' has encountered an error:\n\n{error_msg}\n\n"
            f"Try deactivating and reactivating the plugin, or check the plugin logs for more details.",
            parent=self.dialog
        )
    
    def _set_ui_enabled(self, enabled: bool) -> None:
        """Enable/disable UI components during operations."""
        state = "normal" if enabled else "disabled"
        self.import_button.configure(state=state)
        self.refresh_button.configure(state=state)
        
        # Enhanced UI state management for new card structure
        for card in self.plugin_cards:
            self._set_card_enabled(card, enabled)
    
    def _set_card_enabled(self, card_widget: ttk.Widget, enabled: bool) -> None:
        """Recursively enable/disable all buttons in a card widget."""
        state = "normal" if enabled else "disabled"
        
        for child in card_widget.winfo_children():
            if isinstance(child, ttk.Button):
                child.configure(state=state)
            elif hasattr(child, 'winfo_children'):
                self._set_card_enabled(child, enabled)
    
    def _set_status(self, message: str) -> None:
        """Set status message."""
        self.status_var.set(message)
        self._logger.debug("Status: %s", message)
    
    def _auto_fetch_official_plugins_if_missing(self) -> None:
        """Auto-fetch official plugins if they haven't been fetched yet."""
        try:
            # Hardcoded official plugin URLs
            OFFICIAL_URLS = [
                "https://github.com/orsso/orlando-docx-plugin",
                "https://github.com/orsso/orlando-pdf-plugin"
            ]
            
            # Check which ones are missing from both fetched AND installed plugins
            fetched_plugins = self.plugin_manager.get_fetched_plugins()
            installed_plugins = self.plugin_manager.get_installed_plugins()
            
            missing_urls = []
            for url in OFFICIAL_URLS:
                # Skip if already fetched
                if url in fetched_plugins:
                    continue
                    
                # Skip if already installed (check by URL matching)
                is_installed = False
                for plugin_id in installed_plugins:
                    try:
                        metadata = self.plugin_manager.get_plugin_metadata(plugin_id)
                        if metadata and hasattr(metadata, 'homepage') and metadata.homepage == url:
                            is_installed = True
                            break
                        # Also check by expected directory name (fallback)
                        expected_dir = url.split('/')[-1].replace('.git', '')
                        if plugin_id == expected_dir:
                            is_installed = True
                            break
                    except Exception:
                        continue
                
                if not is_installed:
                    missing_urls.append(url)
            
            if missing_urls:
                self._logger.info("Auto-fetching %d official plugins", len(missing_urls))
                # Start background fetch for missing official plugins
                for url in missing_urls:
                    threading.Thread(
                        target=self._background_fetch_official_plugin, 
                        args=(url,), 
                        daemon=True
                    ).start()
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

    def _on_close(self) -> None:
        """Handle dialog close event."""
        try:
            self.result = {"action": "close"}
            if self.dialog:
                self.dialog.destroy()
        except Exception as e:
            self._logger.error("Error closing dialog: %s", e)


# Backward compatibility alias for migration support
PluginManagerDialog = SimplePluginManagerDialog