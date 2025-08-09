# -*- coding: utf-8 -*-
"""
Tab for previewing and renaming images found in the converted DITA context.
Image management interface for DITA package generation.
"""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Optional, Dict
import os
from PIL import Image, ImageTk
import io
import subprocess
import tempfile
from pathlib import Path
import shutil
import glob
import threading

if TYPE_CHECKING:
    from orlando_toolkit.core.models import DitaContext


class ImageTab(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.context: Optional["DitaContext"] = None

        # --- Widgets ---
        self.image_listbox: Optional[tk.Listbox] = None
        self.prefix_entry: Optional[ttk.Entry] = None
        self.preview_label: Optional[ttk.Label] = None
        self.info_label: Optional[ttk.Label] = None
        self.section_map: dict[str, str] = {}
        self.download_button: Optional[ttk.Button] = None
        self._proposed_names: Dict[str, str] = {}
        self._current_preview_bytes: Optional[bytes] = None
        self._temp_edit_paths: Dict[str, str] = {}
        self._status_message: str = ""
        self._editor_choice_var: Optional[tk.StringVar] = None
        self._editor_paths: Dict[str, Optional[str]] = {}
        self._last_selected_key: Optional[str] = None

        self.create_widgets()
        # Clear default text selection when the tab becomes visible
        try:
            self.bind("<Visibility>", self._on_tab_visible)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI builders
    # ------------------------------------------------------------------

    def create_widgets(self):
        """Create the widgets for displaying the image list and prefix field."""
        main_frame = ttk.Frame(self)
        main_frame.pack(expand=True, fill="both", padx=15, pady=15)

        # Removed title header for a cleaner tab UI

        # --- Options frame ---
        options_frame = ttk.LabelFrame(main_frame, text="Naming Options", padding=15)
        options_frame.pack(fill="x", pady=(0, 15))

        options_frame.columnconfigure(1, weight=1)
        options_frame.columnconfigure(3, weight=1)

        prefix_label = ttk.Label(options_frame, text="Prefix:", font=("Arial", 11))
        prefix_label.grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)

        self.prefix_entry = ttk.Entry(options_frame, font=("Arial", 11))
        self.prefix_entry.grid(row=0, column=1, sticky="ew", padx=(0, 20), pady=5)
        self.prefix_entry.bind("<KeyRelease>", lambda e: self.update_image_names())

        # Content frame with two panels
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(expand=True, fill="both")
        # Use grid to enforce an 80/20 split (right:preview 80%, left:list 20%)
        # Left column (0) = 1, Right column (1) = 4 → 20/80 ratio
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=4)
        content_frame.rowconfigure(0, weight=1)

        # --- Left panel: Image list ---
        left_panel = ttk.LabelFrame(content_frame, text="File Names Preview", padding=10)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        # Prevent list area width from being driven by content
        try:
            left_panel.grid_propagate(False)
        except Exception:
            pass
        left_panel.columnconfigure(0, weight=1)
        left_panel.columnconfigure(1, weight=0)
        left_panel.rowconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=0)

        # Keep selection when focus moves to other widgets
        self.image_listbox = tk.Listbox(left_panel, font=("Arial", 10), exportselection=False)
        self.image_listbox.grid(row=0, column=0, sticky="nsew")
        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)

        scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=self.image_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.image_listbox.config(yscrollcommand=scrollbar.set)

        # Buttons frame under the list
        buttons_frame = ttk.Frame(left_panel)
        buttons_frame.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        
        # Open folder button with folder icon 
        folder_btn = ttk.Button(buttons_frame, text="▣", width=3, command=self.open_images_folder)
        folder_btn.grid(row=0, column=0, padx=(0, 8))
        try:
            from orlando_toolkit.ui.custom_widgets import Tooltip
            Tooltip(folder_btn, "Open images folder", delay_ms=1000)
        except Exception:
            pass
        
        # Download-all button
        ttk.Button(buttons_frame, text="Download All", command=self.download_all_images).grid(
            row=0, column=1
        )

        # --- Right panel: Image preview ---
        right_panel = ttk.LabelFrame(content_frame, text="Image Preview", padding=10)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        # Prevent preview area width from being driven by image size
        try:
            right_panel.grid_propagate(False)
        except Exception:
            pass
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)

        # Preview canvas/label
        self.preview_label = ttk.Label(
            right_panel,
            text="Select an image to preview",
            font=("Arial", 10),
            foreground="gray",
            anchor="center",
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        # Re-render preview on resize to normalize size
        self.preview_label.bind("<Configure>", self._on_preview_resize)

        # Image info
        self.info_label = ttk.Label(right_panel, text="", font=("Arial", 9), foreground="gray")
        self.info_label.grid(row=1, column=0, sticky="w", pady=(0, 8))

        # Action buttons
        actions = ttk.Frame(right_panel)
        actions.grid(row=2, column=0, sticky="w")
        # Download icon button (leftmost)
        self.download_button = ttk.Button(actions, text="⤓", width=3, command=self.download_selected_image)
        self.download_button.grid(row=0, column=0, padx=(0, 8))
        # Editor selector
        ttk.Label(actions, text="Editor:").grid(row=0, column=1, padx=(0, 6))
        self._editor_choice_var = tk.StringVar(value="")
        self._editor_paths = self._detect_available_editors()
        editor_order = ["Paint", "GIMP", "Photoshop", "System default"]
        editor_names = [name for name in editor_order]
        editor_combo = ttk.Combobox(actions, values=editor_names, textvariable=self._editor_choice_var, state="readonly", width=16)
        # Default to Paint if available, else GIMP, else Photoshop, else System default
        default_choice = "System default"
        for name in ["Paint", "GIMP", "Photoshop"]:
            path = self._editor_paths.get(name)
            if path:
                default_choice = name
                break
        self._editor_choice_var.set(default_choice)
        editor_combo.grid(row=0, column=2, padx=(0, 10))
        # Preserve image selection when changing editor
        editor_combo.bind("<<ComboboxSelected>>", self._on_editor_changed)

        # Action buttons
        ttk.Button(actions, text="Edit Image", command=self.edit_image).grid(row=0, column=3, padx=(0, 6))
        ttk.Button(actions, text="↻", width=3, command=self.reload_edited_image).grid(row=0, column=4, padx=(0, 8))
        # Status label at the far right (errors in red)
        try:
            actions.columnconfigure(5, weight=1)
        except Exception:
            pass
        self._actions_status = ttk.Label(actions, text="", foreground="#cc0000")
        self._actions_status.grid(row=0, column=5, sticky="e")

        # Removed verbose help text to keep UI concise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_context(self, context: "DitaContext") -> None:
        """Load the DITA context and populate UI."""
        self.context = context

        # Simulate default prefix if not present
        if "prefix" not in self.context.metadata:
            self.context.metadata["prefix"] = "CRL"

        if self.prefix_entry:
            self.prefix_entry.delete(0, tk.END)
            self.prefix_entry.insert(0, self.context.metadata.get("prefix", ""))

        self.update_image_names()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def update_image_names(self):
        """Update the filename list based on prefix and metadata."""
        if not self.context or not self.prefix_entry or not self.image_listbox:
            return

        # Update metadata from fields
        prefix = self.prefix_entry.get()
        self.context.metadata["prefix"] = prefix

        # Get manual_code from metadata (set in metadata tab)
        manual_code = self.context.metadata.get("manual_code", "")

        self.image_listbox.delete(0, tk.END)

        if not self.context.images:
            self.image_listbox.insert(tk.END, "No images found.")
            return

        # Create section number mapping and per-section numbering for images
        image_names = self._create_per_section_image_names()
        self._proposed_names = image_names

        # Display the new filenames in order
        for original_filename in self.context.images.keys():
            new_filename = image_names.get(original_filename, original_filename)
            self.image_listbox.insert(tk.END, new_filename)

    def _create_per_section_image_names(self) -> dict[str, str]:
        """Create new filenames with per-section image numbering."""
        if self.context is None or getattr(self.context, "ditamap_root", None) is None:
            return {}
        
        from orlando_toolkit.core.utils import find_topicref_for_image, get_section_number_for_topicref
        
        prefix = self.context.metadata.get("prefix", "")
        manual_code = self.context.metadata.get("manual_code", "")
        
        # Group images by section
        section_images = {}
        for image_filename in self.context.images.keys():
            topicref = find_topicref_for_image(image_filename, self.context)
            if topicref is not None:
                section_number = get_section_number_for_topicref(topicref, self.context.ditamap_root)
            else:
                section_number = "0"
            
            if section_number not in section_images:
                section_images[section_number] = []
            section_images[section_number].append(image_filename)
        
        # Generate new filenames with per-section numbering
        image_names = {}
        for section_number, images_in_section in section_images.items():
            for i, image_filename in enumerate(images_in_section):
                extension = os.path.splitext(image_filename)[1]
                
                # Base filename parts
                if manual_code:
                    base_name = f"{prefix}-{manual_code}-{section_number}"
                else:
                    base_name = f"{prefix}-{section_number}"
                
                # Add image number only if there are multiple images in this section
                if len(images_in_section) > 1:
                    img_num = i + 1
                    new_filename = f"{base_name}-{img_num}{extension}"
                else:
                    new_filename = f"{base_name}{extension}"
                
                image_names[image_filename] = new_filename
        
        return image_names

    def on_image_select(self, event):
        """Callback when an image is selected in the listbox."""
        if not self.context or not self.image_listbox or not self.preview_label:
            return

        selection = self.image_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        if index >= len(self.context.images):
            return

        original_filename = list(self.context.images.keys())[index]
        image_data = self.context.images[original_filename]

        # Remember last selected for robustness when focus changes
        self._last_selected_key = original_filename
        # Clear status when changing image
        self._clear_status()

        self.show_image_preview(original_filename, image_data)

    def _on_tab_visible(self, _event=None) -> None:
        """When switching to this tab, avoid having text pre-selected in entries."""
        try:
            if self.prefix_entry is not None:
                try:
                    # Clear selection and place cursor at end without forcing focus away
                    self.prefix_entry.selection_clear()
                    self.prefix_entry.icursor("end")
                except Exception:
                    pass
        except Exception:
            pass

    def _on_editor_changed(self, _event=None) -> None:
        """Keep the current image context intact when editor dropdown changes.

        - Restores listbox selection to the last selected image if none is selected
        - Does not change preview, only selection and status
        """
        if not self.context or not self.image_listbox:
            return
        try:
            # If selection lost due to focus change, restore it
            sel = self.image_listbox.curselection()
            if (not sel) and self._last_selected_key and self._last_selected_key in self.context.images:
                keys = list(self.context.images.keys())
                try:
                    idx = keys.index(self._last_selected_key)
                    self.image_listbox.selection_set(idx)
                    self.image_listbox.activate(idx)
                    self.image_listbox.see(idx)
                except ValueError:
                    pass
        except Exception:
            pass

    def _ensure_temp_edit_path(self, original_filename: str, proposed_name: str) -> str:
        """Return a temp file path for editing this image, creating it if absent."""
        cached = self._temp_edit_paths.get(original_filename)
        if cached and os.path.exists(cached):
            return cached
        base_dir = Path(tempfile.gettempdir()) / "orlando_toolkit" / "image_edits"
        base_dir.mkdir(parents=True, exist_ok=True)
        # Sanitize filename
        safe_name = proposed_name.replace(os.sep, "_")
        path = str(base_dir / safe_name)
        self._temp_edit_paths[original_filename] = path
        return path

    def _set_status(self, message: str) -> None:
        self._status_message = message or ""
        # Re-render info line to include status, if a preview is present
        if self._current_preview_bytes:
            try:
                self._render_preview_from_bytes(self._current_preview_bytes)
            except Exception:
                pass
        # Also set a small status label near action buttons (errors in red)
        try:
            if hasattr(self, "_actions_status") and self._actions_status:
                # Choose color by message intent
                msg = message or ""
                lower = msg.lower()
                if not msg:
                    color = "#000000"
                elif ("fail" in lower) or ("not found" in lower) or ("no image selected" in lower):
                    color = "#cc0000"  # error
                elif ("updated" in lower) or ("reloaded" in lower):
                    color = "#2e7d32"  # success
                else:
                    color = "#555555"  # neutral info
                self._actions_status.configure(text=msg, foreground=color)
        except Exception:
            pass

    def _clear_status(self) -> None:
        """Clear any transient status messages from actions/info areas."""
        try:
            self._status_message = ""
            if hasattr(self, "_actions_status") and self._actions_status:
                self._actions_status.configure(text="")
            if self._current_preview_bytes:
                self._render_preview_from_bytes(self._current_preview_bytes)
        except Exception:
            pass

    def _detect_available_editors(self) -> Dict[str, Optional[str]]:
        """Detect available editors and return mapping name -> path (None if missing).

        Editors: Photoshop, GIMP, Paint, plus a special "System default" entry with empty string.
        """
        # Photoshop
        candidates_ps = [
            shutil.which("Photoshop.exe"),
            shutil.which("photoshop.exe"),
        ]
        # Common Adobe paths
        try:
            prog_files = os.environ.get("ProgramFiles", r"C:\\Program Files")
            prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)")
            for base in [prog_files, prog_files_x86]:
                if not base:
                    continue
                pattern = os.path.join(base, "Adobe", "Adobe Photoshop*", "Photoshop.exe")
                matches = glob.glob(pattern)
                candidates_ps.extend(matches)
        except Exception:
            pass
        ps_path = next((p for p in candidates_ps if p and os.path.exists(p)), None)

        # GIMP (support both 'GIMP' and 'gimp' names)
        candidates_gimp = [
            shutil.which("gimp"),
            shutil.which("gimp.exe"),
            shutil.which("gimp-2.10"),
            shutil.which("gimp-2.10.exe"),
            shutil.which("gimp-2.8"),
            shutil.which("gimp-2.8.exe"),
            os.path.join(os.environ.get("ProgramFiles", r"C:\\Program Files"), "GIMP 2", "bin", "gimp-2.10.exe"),
            os.path.join(os.environ.get("ProgramFiles", r"C:\\Program Files"), "GIMP 2", "bin", "gimp-2.8.exe"),
        ]
        gimp_path = next((p for p in candidates_gimp if p and os.path.exists(p)), None)

        # Paint
        candidates_paint = [
            shutil.which("mspaint.exe"),
            shutil.which("mspaint"),
            r"C:\\Windows\\System32\\mspaint.exe",
        ]
        paint_path = next((p for p in candidates_paint if p and os.path.exists(p)), None)
        # On some systems, Paint is an app alias; still try 'mspaint' if path not resolved
        if not paint_path:
            paint_path = "mspaint"

        return {
            "Photoshop": ps_path,
            "GIMP": gimp_path,
            "Paint": paint_path,
            "System default": "",
        }

    def edit_image(self) -> None:
        """Open the selected image in an external editor with graceful fallback.

        Preference: Photoshop → GIMP → Paint → default system editor (non-blocking).
        If a blocking editor is used, bytes are reloaded on close and preview updates.
        """
        if not self.context or not self.image_listbox:
            return
        sel = self.image_listbox.curselection()
        if not sel:
            return
        index = sel[0]
        if index >= len(self.context.images):
            return
        original_filename = list(self.context.images.keys())[index]
        proposed = self._proposed_names.get(original_filename, original_filename)
        temp_path = self._ensure_temp_edit_path(original_filename, proposed)
        # Write current bytes to temp
        try:
            with open(temp_path, "wb") as f:
                f.write(self.context.images[original_filename])
        except Exception:
            return

        # Resolve desired editor from dropdown; refresh detection each click
        chosen = self._editor_choice_var.get() if self._editor_choice_var else "System default"
        self._editor_paths = self._detect_available_editors()
        editor_path = self._editor_paths.get(chosen) if self._editor_paths else None
        if chosen == "System default":
            try:
                os.startfile(temp_path)  # type: ignore[attr-defined]
                self._set_status("Opened with default app; click '↻' to reload after saving")
            except Exception:
                self._set_status("Failed to open with default app")
            return

        if editor_path:
            try:
                # Launch editor process
                proc = subprocess.Popen([editor_path, temp_path], shell=False)
                # Inform user immediately
                if chosen in ("GIMP", "Photoshop"):
                    # These apps may spawn and detach; rely on manual reload
                    self._set_status(f"Opened in {chosen}; click '↻' to reload after saving")
                    return
                else:
                    self._set_status(f"Opening {chosen}…")
            except Exception:
                # As a last resort, try default handler
                try:
                    os.startfile(temp_path)  # type: ignore[attr-defined]
                    self._set_status("Opened with default app; click '↻' to reload after saving")
                    return
                except Exception:
                    self._set_status("Failed to open image in external editor")
                    return

            # Auto-reload path (works well with Paint which keeps the process until close)
            def _wait_and_reload() -> None:
                try:
                    proc.wait()
                    with open(temp_path, "rb") as f:
                        new_bytes = f.read()
                except Exception:
                    new_bytes = None  # type: ignore[assignment]

                def _apply():
                    if new_bytes is None:
                        self._set_status("Failed to read edited image")
                        return
                    try:
                        self.context.images[original_filename] = new_bytes  # type: ignore[index]
                        self.show_image_preview(original_filename, new_bytes)
                        self._set_status(f"Updated from {chosen}")
                    except Exception:
                        self._set_status("Failed to update preview from edited image")

                try:
                    self.after(0, _apply)
                except Exception:
                    pass

            threading.Thread(target=_wait_and_reload, daemon=True).start()
        else:
            # Chosen editor not found
            self._set_status(f"{chosen} not found on this system")

    def reload_edited_image(self) -> None:
        """Reload bytes from the temp edited file and update the context/preview."""
        if not self.context or not self.image_listbox:
            return
        # Use current selection or last selected for convenience
        sel = self.image_listbox.curselection()
        if sel:
            index = sel[0]
            if index >= len(self.context.images):
                self._set_status("No image selected")
                return
            original_filename = list(self.context.images.keys())[index]
        elif self._last_selected_key and self._last_selected_key in self.context.images:
            original_filename = self._last_selected_key
        else:
            self._set_status("No image selected")
            return
        proposed = self._proposed_names.get(original_filename, original_filename)
        temp_path = self._ensure_temp_edit_path(original_filename, proposed)
        if not os.path.exists(temp_path):
            self._set_status("No edited file found to reload")
            return
        try:
            with open(temp_path, "rb") as f:
                new_bytes = f.read()
            self.context.images[original_filename] = new_bytes
            self.show_image_preview(original_filename, new_bytes)
            self._set_status("Reloaded edited image")
        except Exception:
            self._set_status("Failed to reload edited image")

    def replace_from_file(self) -> None:
        """Replace current image bytes from a file chosen by the user."""
        if not self.context or not self.image_listbox:
            return
        sel = self.image_listbox.curselection()
        if sel:
            index = sel[0]
            if index >= len(self.context.images):
                self._set_status("No image selected")
                return
            original_filename = list(self.context.images.keys())[index]
        elif self._last_selected_key and self._last_selected_key in self.context.images:
            original_filename = self._last_selected_key
        else:
            self._set_status("No image selected")
            return
        try:
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title="Select replacement image",
                filetypes=(("Images", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.tiff"), ("All files", "*.*")),
            )
        except Exception:
            path = ""
        if not path:
            return
        try:
            with open(path, "rb") as f:
                new_bytes = f.read()
            self.context.images[original_filename] = new_bytes
            self.show_image_preview(original_filename, new_bytes)
        except Exception:
            pass

    def download_selected_image(self) -> None:
        """Save the selected image to disk using the proposed filename."""
        if not self.context or not self.image_listbox:
            return
        # Determine original and proposed filenames from current or last selection
        selection = self.image_listbox.curselection()
        if selection:
            index = selection[0]
            if index >= len(self.context.images):
                self._set_status("No image selected")
                return
            original_filename = list(self.context.images.keys())[index]
        elif self._last_selected_key and self._last_selected_key in self.context.images:
            original_filename = self._last_selected_key
        else:
            self._set_status("No image selected")
            return
        proposed = self._proposed_names.get(original_filename, original_filename)
        # Ask user where to save
        try:
            from tkinter import filedialog
            save_path = filedialog.asksaveasfilename(
                title="Save Image As",
                initialfile=proposed,
                defaultextension=os.path.splitext(proposed)[1] or ".png",
                filetypes=(("Images", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.tiff"), ("All files", "*.*")),
            )
        except Exception:
            save_path = ""
        if not save_path:
            return
        # Write bytes
        try:
            image_data = self.context.images[original_filename]
            with open(save_path, "wb") as f:
                f.write(image_data)
        except Exception:
            # Best-effort; UI-level convenience should not raise
            pass

    def show_image_preview(self, filename: str, image_data: bytes) -> None:
        """Render a normalized preview of the selected image, scaled to fit the panel."""
        try:
            self._current_preview_bytes = image_data
            self._render_preview_from_bytes(image_data)
        except Exception as e:
            self.preview_label.configure(image="", text=f"Cannot preview image\n{str(e)}")
            self.preview_label.image = None
            self.info_label.configure(text="Preview unavailable")

    def _render_preview_from_bytes(self, image_data: bytes) -> None:
        """Render image scaled to available preview area while preserving aspect ratio."""
        if not self.preview_label:
            return
        try:
            image = Image.open(io.BytesIO(image_data))
            original_width, original_height = image.size

            # Determine available area; fallback to sensible defaults
            avail_w = max(400, int(self.preview_label.winfo_width() or 0))
            avail_h = max(300, int(self.preview_label.winfo_height() or 0))

            # Apply padding margins to avoid touching edges
            target_w = max(400, min(1000, avail_w - 24))
            target_h = max(300, min(800, avail_h - 24))

            # Resize keeping aspect ratio
            image.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)

            self.preview_label.configure(image=photo, text="")
            self.preview_label.image = photo

            size_kb = len(image_data) / 1024
            # Determine original format if possible
            try:
                fmt = Image.open(io.BytesIO(image_data)).format
            except Exception:
                fmt = None
            info = [f"Original: {original_width}x{original_height}", f"Size: {size_kb:.1f} KB"]
            if fmt:
                info.append(f"Format: {fmt}")
            if self._status_message:
                info.append(self._status_message)
            self.info_label.configure(text="\n".join(info))
        except Exception:
            # Fallback to plain message
            try:
                self.preview_label.configure(image="", text="Preview unavailable")
                self.preview_label.image = None
            except Exception:
                pass

    def _on_preview_resize(self, _event) -> None:
        if self._current_preview_bytes:
            try:
                self._render_preview_from_bytes(self._current_preview_bytes)
            except Exception:
                pass

    def open_images_folder(self) -> None:
        """Open the images folder used by preview system in the system file explorer."""
        try:
            # Use the same directory as xml_compiler.py for consistency 
            preview_dir = Path(tempfile.gettempdir()) / 'orlando_preview'
            preview_dir.mkdir(parents=True, exist_ok=True)
            
            # Open folder in system explorer
            if os.name == 'nt':  # Windows
                os.startfile(str(preview_dir))
            elif os.name == 'posix':  # macOS and Linux
                if 'darwin' in os.uname().sysname.lower():  # macOS
                    subprocess.run(['open', str(preview_dir)])
                else:  # Linux
                    subprocess.run(['xdg-open', str(preview_dir)])
        except Exception:
            # Fallback: use the temp directory
            try:
                temp_dir = Path(tempfile.gettempdir())
                if os.name == 'nt':
                    os.startfile(str(temp_dir))
                elif os.name == 'posix':
                    if 'darwin' in os.uname().sysname.lower():
                        subprocess.run(['open', str(temp_dir)])
                    else:
                        subprocess.run(['xdg-open', str(temp_dir)])
            except Exception:
                pass

    def download_all_images(self) -> None:
        """Save all images to a chosen directory using proposed filenames."""
        if not self.context or not getattr(self.context, "images", None):
            return
        # Ensure proposed names are current
        if not self._proposed_names:
            self._proposed_names = self._create_per_section_image_names()
        try:
            from tkinter import filedialog
            directory = filedialog.askdirectory(title="Choose folder to save all images")
        except Exception:
            directory = ""
        if not directory:
            return
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception:
            pass
        for original_filename, image_data in self.context.images.items():
            target_name = self._proposed_names.get(original_filename, original_filename)
            target_path = os.path.join(directory, target_name)
            try:
                with open(target_path, "wb") as f:
                    f.write(image_data)
            except Exception:
                continue