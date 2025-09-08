# -*- coding: utf-8 -*-
"""
Media Tab: unified images and videos management with inline previews.
Keeps ImageTab parity for image naming, preview, and editing.
"""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Optional, Dict, List
import os
import io
import subprocess
import tempfile
from pathlib import Path
import threading
import logging
import shutil

from PIL import Image, ImageTk

if TYPE_CHECKING:
    from orlando_toolkit.core.models import DitaContext

from orlando_toolkit.config import ConfigManager

logger = logging.getLogger(__name__)


class MediaTab(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.context: Optional["DitaContext"] = None

        # Media type tracking
        self._current_media_type = "images"  # "images" or "videos"

        # Image state
        self.image_listbox: Optional[tk.Listbox] = None
        self.prefix_entry: Optional[ttk.Entry] = None
        self.preview_label: Optional[ttk.Label] = None
        self.info_label: Optional[ttk.Label] = None
        self._proposed_names: Dict[str, str] = {}
        self._current_preview_bytes: Optional[bytes] = None
        self._disk_paths: Dict[str, str] = {}
        self._status_message: str = ""
        self._editor_choice_var: Optional[tk.StringVar] = None
        self._editor_paths: Dict[str, Optional[str]] = {}
        self._last_selected_key: Optional[str] = None

        # Video state
        self.video_listbox: Optional[tk.Listbox] = None
        self.video_canvas: Optional[tk.Canvas] = None
        self.play_pause_btn: Optional[ttk.Button] = None
        self.stop_btn: Optional[ttk.Button] = None
        self.time_label: Optional[ttk.Label] = None
        self.video_info_frame: Optional[ttk.Frame] = None
        self.video_player_frame: Optional[ttk.Frame] = None
        self._video_player = None
        self._is_playing = False
        self._current_video_path: Optional[str] = None

        # Build UI
        self._create_widgets()

        # Clear default selection when shown
        try:
            self.bind("<Visibility>", self._on_tab_visible)
        except Exception:
            pass

    def _create_widgets(self) -> None:
        """Create the main UI structure (full-width like ImageTab)."""
        main_frame = ttk.Frame(self)
        main_frame.pack(expand=True, fill="both", padx=15, pady=15)

        # Header area is kept for spacing and potential future controls
        header = ttk.Frame(main_frame)
        header.pack(fill="x", pady=(0, 10))

        # Global naming options (prefix applies to images AND videos)
        options = ttk.LabelFrame(main_frame, text="Naming Options", padding=12)
        options.pack(fill="x", pady=(0, 10))
        options.columnconfigure(1, weight=1)
        ttk.Label(options, text="Prefix:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.prefix_entry = ttk.Entry(options)
        self.prefix_entry.grid(row=0, column=1, sticky="ew", pady=4)
        # Debounce frequent updates while typing to avoid UI lag with many images
        self._prefix_debounce_after_id: Optional[str] = None
        def _on_prefix_key(_: object) -> None:
            try:
                if self._prefix_debounce_after_id:
                    try:
                        self.after_cancel(self._prefix_debounce_after_id)
                    except Exception:
                        pass
                # Delay updates slightly to batch keystrokes
                self._prefix_debounce_after_id = self.after(250, self._apply_prefix_change)
            except Exception:
                # Fallback: direct update
                self._apply_prefix_change()
        self.prefix_entry.bind("<KeyRelease>", _on_prefix_key)

        # Notebook tabs for Images/Videos
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(expand=True, fill="both")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)

        # Sections as tabs
        self._create_images_section()
        self._create_videos_section()

    def _create_media_type_selector(self, parent: ttk.Frame) -> None:
        # Deprecated (using simplified header in _create_widgets)
        pass

    def _create_images_section(self) -> None:
        """Images UI aligned with ImageTab (20/80 split, preview + actions)."""
        self.images_frame = ttk.Frame(self.notebook)
        # (prefix field is global in header)

        # Content split
        split = ttk.Frame(self.images_frame)
        split.pack(expand=True, fill="both")
        split.columnconfigure(0, weight=1)
        split.columnconfigure(1, weight=4)
        split.rowconfigure(0, weight=1)

        # Left list
        left = ttk.LabelFrame(split, text="File Names Preview", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        try:
            left.grid_propagate(False)
        except Exception:
            pass
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        self.image_listbox = tk.Listbox(left, exportselection=False)
        self.image_listbox.grid(row=0, column=0, sticky="nsew")
        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.image_listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.image_listbox.config(yscrollcommand=sb.set)

        buttons = ttk.Frame(left)
        buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        folder_btn = ttk.Button(buttons, text="Open Folder", command=self.open_images_folder)
        folder_btn.grid(row=0, column=0, padx=(0, 8))
        try:
            from orlando_toolkit.ui.custom_widgets import Tooltip
            Tooltip(folder_btn, "Open images folder", delay_ms=800)
        except Exception:
            pass
        ttk.Button(buttons, text="Download", command=self.download_selected_image).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="Download All", command=self.download_all_images).grid(row=0, column=2)

        # Right preview
        right = ttk.LabelFrame(split, text="Image Preview", padding=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        try:
            right.grid_propagate(False)
        except Exception:
            pass
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self.preview_label = ttk.Label(right, text="Select an image to preview", foreground="gray", anchor="center")
        self.preview_label.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self.preview_label.bind("<Configure>", self._on_preview_resize)

        self.info_label = ttk.Label(right, text="", foreground="gray")
        self.info_label.grid(row=1, column=0, sticky="w", pady=(0, 8))

        actions = ttk.Frame(right)
        actions.grid(row=2, column=0, sticky="w")
        ttk.Label(actions, text="Editor:").grid(row=0, column=0, padx=(0, 6))
        self._editor_choice_var = tk.StringVar(value="")
        self._editor_paths = self._detect_available_editors()
        editor_order = ["Paint", "GIMP", "Photoshop", "System default"]
        editor_combo = ttk.Combobox(actions, values=editor_order, textvariable=self._editor_choice_var, state="readonly", width=16)
        default_choice = "System default"
        for name in ["Paint", "GIMP", "Photoshop"]:
            p = self._editor_paths.get(name)
            if p:
                default_choice = name
                break
        self._editor_choice_var.set(default_choice)
        editor_combo.grid(row=0, column=1, padx=(0, 10))
        editor_combo.bind("<<ComboboxSelected>>", self._on_editor_changed)
        ttk.Button(actions, text="Edit Image", command=self.edit_image).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(actions, text="Reload", width=8, command=self.reload_edited_image).grid(row=0, column=3, padx=(0, 8))
        try:
            actions.columnconfigure(4, weight=1)
        except Exception:
            pass
        self._actions_status = ttk.Label(actions, text="", foreground="#cc0000")
        self._actions_status.grid(row=0, column=4, sticky="e")

        # Add as tab
        try:
            self.notebook.add(self.images_frame, text="Images")
        except Exception:
            pass

    def _create_videos_section(self) -> None:
        """Videos UI with inline player (20/80 split)."""
        self.videos_frame = ttk.Frame(self.notebook)
        self.videos_frame.columnconfigure(0, weight=1)
        self.videos_frame.columnconfigure(1, weight=4)
        self.videos_frame.rowconfigure(0, weight=1)

        # Left: list
        left = ttk.LabelFrame(self.videos_frame, text="Videos", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.video_listbox = tk.Listbox(left, exportselection=False)
        self.video_listbox.grid(row=0, column=0, sticky="nsew")
        self.video_listbox.bind("<<ListboxSelect>>", self._on_video_selection)
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.video_listbox.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.video_listbox.configure(yscrollcommand=vsb.set)
        video_buttons = ttk.Frame(left)
        video_buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(video_buttons, text="Open Folder", command=self.open_videos_folder).pack(side="left", padx=(0, 6))
        ttk.Button(video_buttons, text="Download", command=self._download_selected_video).pack(side="left", padx=(0, 6))
        ttk.Button(video_buttons, text="Download All", command=self._download_all_videos).pack(side="left")

        # Right: player + info
        right = ttk.LabelFrame(self.videos_frame, text="Video Preview", padding=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.video_info_frame = ttk.Frame(right)
        self.video_info_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.video_player_frame = ttk.Frame(right, relief="sunken", borderwidth=1)
        self.video_player_frame.grid(row=1, column=0, sticky="nsew")
        self.video_player_frame.grid_rowconfigure(0, weight=1)
        self.video_player_frame.grid_columnconfigure(0, weight=1)
        controls = ttk.Frame(right)
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.video_canvas = tk.Canvas(self.video_player_frame, bg="black", highlightthickness=0)
        self.video_canvas.grid(row=0, column=0, sticky="nsew")
        self.play_pause_btn = ttk.Button(controls, text="Play", command=self._on_play_clicked, state="disabled")
        self.play_pause_btn.pack(side="left", padx=(0, 6))
        self.stop_btn = ttk.Button(controls, text="Stop", command=self._stop_video, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 10))
        self.time_label = ttk.Label(controls, text="00:00 / 00:00")
        self.time_label.pack(side="left")
        self._show_no_video_selected()

        # Add as tab
        try:
            self.notebook.add(self.videos_frame, text="Videos")
        except Exception:
            pass

    def open_videos_folder(self) -> None:
        """Open the folder where videos were materialized."""
        try:
            folder = getattr(self, "_video_disk_dir", None)
            if not folder:
                # Fallback to temp directory
                folder = Path(tempfile.gettempdir())
            if os.name == 'nt':
                os.startfile(str(folder))
            elif os.name == 'posix':
                if 'darwin' in os.uname().sysname.lower():
                    subprocess.run(['open', str(folder)])
                else:
                    subprocess.run(['xdg-open', str(folder)])
        except Exception:
            pass

    def _init_video_player(self) -> None:
        # No-op (constructed in _create_videos_section)
        pass

    def _on_notebook_tab_changed(self, _event=None) -> None:
        try:
            current = self.notebook.select()
            if current == str(self.images_frame):
                # Defer refresh to ensure widgets are mapped
                self.after(0, self._refresh_images)
            elif current == str(self.videos_frame):
                self.after(0, self._refresh_videos)
        except Exception:
            # Best effort fallbacks
            self.after(0, self._refresh_images)

    def _switch_media_type(self, media_type: str) -> None:
        """Switch between images and videos view."""
        # Hide both then show one
        try:
            self.images_frame.grid_remove()
        except Exception:
            pass
        try:
            self.videos_frame.grid_remove()
        except Exception:
            pass

        self._current_media_type = media_type
        if media_type == "images":
            try:
                self.images_btn.configure(state="pressed")
                self.videos_btn.configure(state="normal")
            except Exception:
                pass
            self.images_frame.grid(row=0, column=0, sticky="nsew")
        else:
            try:
                self.videos_btn.configure(state="pressed")
                self.images_btn.configure(state="normal")
            except Exception:
                pass
            self.videos_frame.grid(row=0, column=0, sticky="nsew")

        self._refresh_current_media_type()

    def _refresh_current_media_type(self) -> None:
        if self._current_media_type == "images":
            self._refresh_images()
        else:
            self._refresh_videos()

    def _refresh_images(self) -> None:
        if not (self.context and self.image_listbox and self.prefix_entry):
            return
        prefix = self.context.metadata.get("prefix")
        if not prefix:
            cfg = ConfigManager().get_image_naming()
            prefix = cfg["prefix"]
            self.context.metadata["prefix"] = prefix
        self.prefix_entry.delete(0, tk.END)
        self.prefix_entry.insert(0, prefix)
        self.update_image_names()
        self._materialize_images_async()

    def update_image_names(self) -> None:
        if not (self.context and self.prefix_entry and self.image_listbox):
            return
        new_prefix = self.prefix_entry.get()
        old_prefix = self.context.metadata.get("prefix")
        
        # Update context metadata
        self.context.metadata["prefix"] = new_prefix
        
        # Persist prefix change to user config if it actually changed
        if new_prefix != old_prefix:
            try:
                config_manager = ConfigManager()
                config_manager.update_image_naming_config({"prefix": new_prefix})
            except Exception as e:
                logger.warning("Failed to persist prefix change: %s", e)
        
        self.image_listbox.delete(0, tk.END)
        if not getattr(self.context, "images", None):
            self.image_listbox.insert(tk.END, "No images found.")
            return
        image_names = self._create_per_section_image_names()
        self._proposed_names = image_names
        for original_filename in self.context.images.keys():
            new_filename = image_names.get(original_filename, original_filename)
            self.image_listbox.insert(tk.END, new_filename)
        if self._last_selected_key and self._last_selected_key in self.context.images:
            try:
                idx = list(self.context.images.keys()).index(self._last_selected_key)
                self.image_listbox.selection_set(idx)
                self.image_listbox.activate(idx)
                self.image_listbox.see(idx)
            except ValueError:
                pass

    def _apply_prefix_change(self) -> None:
        """Apply debounced prefix change to both images and videos."""
        try:
            self._prefix_debounce_after_id = None
        except Exception:
            pass
        # Update image and video names based on the current prefix
        self.update_image_names()
        self.update_video_names()

    def update_video_names(self) -> None:
        """Refresh the video list display based on current prefix and mapping."""
        if not (self.context and self.video_listbox):
            return
        self.video_listbox.delete(0, tk.END)
        videos = getattr(self.context, 'videos', {})
        names = self._create_per_section_video_names()
        # Display proposed names but keep index mapping to original order
        for original in videos.keys():
            display = names.get(original, original)
            self.video_listbox.insert(tk.END, display)

    def _create_per_section_video_names(self) -> Dict[str, str]:
        """Create new filenames for videos using same pattern as images.

        Attempts to map videos to section numbers; falls back to "0" when unknown.
        """
        if not self.context:
            return {}
        prefix = self.context.metadata.get("prefix") or ConfigManager().get_image_naming()["prefix"]
        manual_code = self.context.metadata.get("manual_code", "")

        # Try to infer section numbers by scanning topics for media references
        section_videos: Dict[str, List[str]] = {}
        try:
            if getattr(self.context, 'ditamap_root', None) is not None:
                from orlando_toolkit.core.utils import get_section_number_for_topicref
                for vid in self.context.videos.keys():
                    section_number = "0"
                    try:
                        # Search any topicref whose topic contains a reference to this media
                        for topic_filename, topic_element in self.context.topics.items():
                            # common DITA media references: object, video, media elements with @href
                            for tag in ("object", "video", "media"):
                                xpath_expr = f".//{tag}[@href=$href]"
                                media_href = f"../media/{vid}"
                                found = topic_element.xpath(xpath_expr, href=media_href)
                                if found:
                                    for topicref in self.context.ditamap_root.xpath(".//topicref"):
                                        href = topicref.get("href", "")
                                        if href.endswith(topic_filename):
                                            section_number = get_section_number_for_topicref(topicref, self.context.ditamap_root)
                                            raise StopIteration
                    except StopIteration:
                        pass
                    section_videos.setdefault(section_number, []).append(vid)
            else:
                for vid in self.context.videos.keys():
                    section_videos.setdefault("0", []).append(vid)
        except Exception:
            for vid in self.context.videos.keys():
                section_videos.setdefault("0", []).append(vid)

        # Build names
        out: Dict[str, str] = {}
        for section_number, vids in section_videos.items():
            for i, vid in enumerate(vids):
                ext = os.path.splitext(vid)[1]
                base = f"{prefix}-{manual_code}-{section_number}" if manual_code else f"{prefix}-{section_number}"
                if len(vids) > 1:
                    out[vid] = f"{base}-{i+1}{ext}"
                else:
                    out[vid] = f"{base}{ext}"
        return out

    def _create_per_section_image_names(self) -> Dict[str, str]:
        """Create new filenames with per-section numbering (ImageTab rules)."""
        if self.context is None or getattr(self.context, "ditamap_root", None) is None:
            return {}
        from orlando_toolkit.core.utils import find_topicref_for_image, get_section_number_for_topicref
        prefix = self.context.metadata.get("prefix")
        if not prefix:
            prefix = ConfigManager().get_image_naming()["prefix"]
        manual_code = self.context.metadata.get("manual_code", "")
        section_images: Dict[str, List[str]] = {}
        for image_filename in self.context.images.keys():
            topicref = find_topicref_for_image(image_filename, self.context)
            if topicref is not None:
                section_number = get_section_number_for_topicref(topicref, self.context.ditamap_root)
            else:
                section_number = "0"
            section_images.setdefault(section_number, []).append(image_filename)
        image_names: Dict[str, str] = {}
        for section_number, images_in_section in section_images.items():
            for i, image_filename in enumerate(images_in_section):
                extension = os.path.splitext(image_filename)[1]
                base = f"{prefix}-{manual_code}-{section_number}" if manual_code else f"{prefix}-{section_number}"
                if len(images_in_section) > 1:
                    image_names[image_filename] = f"{base}-{i+1}{extension}"
                else:
                    image_names[image_filename] = f"{base}{extension}"
        return image_names

    def open_images_folder(self) -> None:
        try:
            from orlando_toolkit.core.session_storage import get_session_storage
            storage = get_session_storage()
            folder = storage.base_dir
        except Exception:
            folder = Path(tempfile.gettempdir())
        try:
            if os.name == 'nt':
                os.startfile(str(folder))
            elif os.name == 'posix':
                if 'darwin' in os.uname().sysname.lower():
                    subprocess.run(['open', str(folder)])
                else:
                    subprocess.run(['xdg-open', str(folder)])
        except Exception:
            pass

    def download_selected_image(self) -> None:
        if not (self.context and self.image_listbox):
            return
        selection = self.image_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.context.images):
            self._set_status("No image selected")
            return
        original_filename = list(self.context.images.keys())[index]
        proposed = self._proposed_names.get(original_filename, original_filename)
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
        try:
            image_data = self.context.images[original_filename]
            with open(save_path, "wb") as f:
                f.write(image_data)
        except Exception:
            pass

    def download_all_images(self) -> None:
        if not self.context or not getattr(self.context, "images", None):
            return
        if not self._proposed_names:
            self._proposed_names = self._create_per_section_image_names()
        try:
            manual_code = str(self.context.metadata.get("manual_code") or "").strip()
        except Exception:
            manual_code = ""
        if not manual_code:
            try:
                from orlando_toolkit.core.utils import slugify
                title = str(self.context.metadata.get("manual_title") or "").strip()
                manual_code = slugify(title) if title else "images"
            except Exception:
                manual_code = "images"
        folder_name = f"{manual_code}_images"
        try:
            from tkinter import filedialog
            directory = filedialog.askdirectory(title=f"Choose parent folder for '{folder_name}'")
        except Exception:
            directory = ""
        if not directory:
            return
        try:
            target_root = os.path.join(directory, folder_name)
            os.makedirs(target_root, exist_ok=True)
        except Exception:
            pass
        for original_filename, image_data in self.context.images.items():
            target_name = self._proposed_names.get(original_filename, original_filename)
            target_path = os.path.join(target_root, target_name)
            try:
                with open(target_path, "wb") as f:
                    f.write(image_data)
            except Exception:
                continue

    def _materialize_images_async(self) -> None:
        if not (self.context and getattr(self.context, "images", None)):
            return
        self._set_status("Preparing images on disk...")

        def _work():
            try:
                from orlando_toolkit.core.session_storage import get_session_storage
                storage = get_session_storage()
            except Exception:
                storage = None
            for original_filename, data in list(self.context.images.items()):
                try:
                    if storage:
                        path = storage.ensure_image_written(original_filename, data)
                        self._disk_paths[original_filename] = str(path)
                except Exception:
                    continue
            try:
                self.after(0, lambda: self._set_status(""))
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    def _get_disk_path(self, original_filename: str) -> Optional[str]:
        return self._disk_paths.get(original_filename)

    def _show_no_media_message(self) -> None:
        pass

    def load_context(self, context: "DitaContext") -> None:
        """Load media from DITA context and populate both sections."""
        self.context = context
        if "prefix" not in self.context.metadata:
            self.context.metadata["prefix"] = ConfigManager().get_image_naming()["prefix"]
        videos = getattr(context, "videos", {})
        images = getattr(context, "images", {})
        # Select default tab in the notebook
        try:
            if hasattr(self, 'notebook'):
                if videos and not images:
                    self.notebook.select(self.videos_frame)
                else:
                    self.notebook.select(self.images_frame)
        except Exception:
            pass
        # Initial refreshes
        self._refresh_images()
        self._refresh_videos()

    def clear_context(self) -> None:
        self.context = None
        try:
            if self.video_listbox:
                self.video_listbox.delete(0, tk.END)
            self._show_no_video_selected()
        except Exception:
            pass
        try:
            if self.image_listbox:
                self.image_listbox.delete(0, tk.END)
            if self.preview_label:
                self.preview_label.configure(image="", text="")
                self.preview_label.image = None
            if self.info_label:
                self.info_label.configure(text="")
        except Exception:
            pass
        logger.info("Cleared media context")

    # ----------------------- Image editing helpers -----------------------
    def _detect_available_editors(self) -> Dict[str, Optional[str]]:
        # Photoshop
        candidates_ps = [
            shutil.which("Photoshop.exe"),
            shutil.which("photoshop.exe"),
        ]
        try:
            prog_files = os.environ.get("ProgramFiles", r"C:\\Program Files")
            prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)")
            for base in [prog_files, prog_files_x86]:
                if not base:
                    continue
                import glob
                pattern = os.path.join(base, "Adobe", "Adobe Photoshop*", "Photoshop.exe")
                candidates_ps.extend(glob.glob(pattern))
        except Exception:
            pass
        ps_path = next((p for p in candidates_ps if p and os.path.exists(p)), None)

        # GIMP
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
        paint_path = next((p for p in candidates_paint if p and os.path.exists(p)), None) or "mspaint"

        return {"Photoshop": ps_path, "GIMP": gimp_path, "Paint": paint_path, "System default": ""}

    def _on_tab_visible(self, _event=None) -> None:
        try:
            if self.prefix_entry is not None:
                self.prefix_entry.selection_clear()
                self.prefix_entry.icursor("end")
        except Exception:
            pass

    def _on_editor_changed(self, _event=None) -> None:
        if not (self.context and self.image_listbox):
            return
        try:
            sel = self.image_listbox.curselection()
            if (not sel) and self._last_selected_key and self._last_selected_key in self.context.images:
                keys = list(self.context.images.keys())
                idx = keys.index(self._last_selected_key)
                self.image_listbox.selection_set(idx)
                self.image_listbox.activate(idx)
                self.image_listbox.see(idx)
        except Exception:
            pass

    def edit_image(self) -> None:
        if not (self.context and self.image_listbox):
            return
        sel = self.image_listbox.curselection()
        if not sel:
            return
        index = sel[0]
        if index >= len(self.context.images):
            return
        original_filename = list(self.context.images.keys())[index]
        from orlando_toolkit.core.session_storage import get_session_storage
        storage = get_session_storage()
        disk_path = storage.ensure_image_written(original_filename, self.context.images[original_filename])

        chosen = self._editor_choice_var.get() if self._editor_choice_var else "System default"
        self._editor_paths = self._detect_available_editors()
        editor_path = self._editor_paths.get(chosen) if self._editor_paths else None
        if chosen == "System default" or not editor_path:
            try:
                os.startfile(str(disk_path))  # type: ignore[attr-defined]
                self._set_status("Opened with default app; click 'Reload' after saving")
            except Exception:
                self._set_status("Failed to open with default app")
            return

        try:
            proc = subprocess.Popen([editor_path, str(disk_path)], shell=False)
            if chosen in ("GIMP", "Photoshop"):
                self._set_status(f"Opened in {chosen}; click 'Reload' after saving")
                return
            else:
                self._set_status(f"Opening {chosen}...")
        except Exception:
            try:
                os.startfile(str(disk_path))  # type: ignore[attr-defined]
                self._set_status("Opened with default app; click 'Reload' after saving")
                return
            except Exception:
                self._set_status("Failed to open image in external editor")
                return

        def _wait_and_reload() -> None:
            try:
                proc.wait()
                with open(disk_path, "rb") as f:
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

    def reload_edited_image(self) -> None:
        if not (self.context and self.image_listbox):
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
        disk_path = self._get_disk_path(original_filename)
        if not disk_path or not os.path.exists(disk_path):
            self._set_status("No edited file found to reload")
            return
        try:
            with open(disk_path, "rb") as f:
                new_bytes = f.read()
            self.context.images[original_filename] = new_bytes
            self.show_image_preview(original_filename, new_bytes)
            self._set_status("Reloaded edited image")
        except Exception:
            self._set_status("Failed to reload edited image")

    def _set_status(self, message: str) -> None:
        self._status_message = message or ""
        if self._current_preview_bytes:
            try:
                self._render_preview_from_bytes(self._current_preview_bytes)
            except Exception:
                pass
        try:
            if hasattr(self, "_actions_status") and self._actions_status:
                msg = message or ""
                lower = msg.lower()
                if not msg:
                    color = "#000000"
                elif ("fail" in lower) or ("not found" in lower) or ("no image selected" in lower):
                    color = "#cc0000"
                elif ("updated" in lower) or ("reloaded" in lower):
                    color = "#2e7d32"
                else:
                    color = "#555555"
                self._actions_status.configure(text=msg, foreground=color)
        except Exception:
            pass

    def _clear_status(self) -> None:
        try:
            self._status_message = ""
            if hasattr(self, "_actions_status") and self._actions_status:
                self._actions_status.configure(text="")
            if self._current_preview_bytes:
                self._render_preview_from_bytes(self._current_preview_bytes)
        except Exception:
            pass

    def download_all_images(self) -> None:
        if not self.context or not getattr(self.context, "images", None):
            return
        if not self._proposed_names:
            self._proposed_names = self._create_per_section_image_names()
        try:
            manual_code = str(self.context.metadata.get("manual_code") or "").strip()
        except Exception:
            manual_code = ""
        if not manual_code:
            try:
                from orlando_toolkit.core.utils import slugify
                title = str(self.context.metadata.get("manual_title") or "").strip()
                manual_code = slugify(title) if title else "images"
            except Exception:
                manual_code = "images"
        folder_name = f"{manual_code}_images"
        try:
            from tkinter import filedialog
            directory = filedialog.askdirectory(title=f"Choose parent folder for '{folder_name}'")
        except Exception:
            directory = ""
        if not directory:
            return
        try:
            target_root = os.path.join(directory, folder_name)
            os.makedirs(target_root, exist_ok=True)
        except Exception:
            pass
        for original_filename, image_data in self.context.images.items():
            target_name = self._proposed_names.get(original_filename, original_filename)
            target_path = os.path.join(target_root, target_name)
            try:
                with open(target_path, "wb") as f:
                    f.write(image_data)
            except Exception:
                continue

    def _materialize_images_async(self) -> None:
        if not (self.context and getattr(self.context, "images", None)):
            return
        self._set_status("Preparing images on disk...")

        def _work():
            try:
                from orlando_toolkit.core.session_storage import get_session_storage
                storage = get_session_storage()
            except Exception:
                storage = None
            for original_filename, data in list(self.context.images.items()):
                try:
                    if storage:
                        path = storage.ensure_image_written(original_filename, data)
                        self._disk_paths[original_filename] = str(path)
                except Exception:
                    continue
            try:
                self.after(0, lambda: self._set_status(""))
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    def _get_disk_path(self, original_filename: str) -> Optional[str]:
        return self._disk_paths.get(original_filename)

    # ---------------------------- Videos ---------------------------------
    def _refresh_videos(self) -> None:
        if not self.context:
            return
        if not self.video_listbox:
            return
        # Ensure materialized copies ready for open folder
        self._materialize_videos_async()
        # Populate list with proposed names
        self.update_video_names()
        if getattr(self.context, 'videos', {}):
            try:
                self.video_listbox.selection_set(0)
                self._on_video_selection(None)
            except Exception:
                pass
        else:
            self._show_no_video_selected()

    def _on_video_selection(self, _event) -> None:
        selection = self.video_listbox.curselection() if self.video_listbox else ()
        if not selection or not self.context:
            self._show_no_video_selected()
            return
        # Map selection index to original key order
        keys = list(getattr(self.context, 'videos', {}).keys())
        idx = selection[0]
        if idx >= len(keys):
            self._show_no_video_selected()
            return
        video_filename = keys[idx]
        self._show_video_details(video_filename)

    def _show_video_details(self, video_filename: str) -> None:
        for w in (self.video_info_frame.winfo_children() if self.video_info_frame else []):
            w.destroy()
        for w in (self.video_player_frame.winfo_children() if self.video_player_frame else []):
            w.destroy()

        ttk.Label(self.video_info_frame, text=f"Video: {video_filename}", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        try:
            import cv2
            if self.context and video_filename in getattr(self.context, 'videos', {}):
                video_bytes = self.context.videos[video_filename]
                # Write to temp for probing
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(video_filename).suffix or '.mp4') as tf:
                    tf.write(video_bytes)
                    temp_path = tf.name
                try:
                    cap = cv2.VideoCapture(temp_path)
                    if cap.isOpened():
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        fps = cap.get(cv2.CAP_PROP_FPS) or 0
                        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                        duration = frame_count / fps if fps > 0 else 0
                        cap.release()
                        for k, v in {
                            "Resolution": f"{width}x{height}",
                            "Frame Rate": f"{fps:.1f} fps" if fps > 0 else "Unknown",
                            "Duration": f"{duration:.1f}s" if duration > 0 else "Unknown",
                            "Frames": str(frame_count),
                        }.items():
                            ttk.Label(self.video_info_frame, text=f"{k}: {v}").pack(anchor="w")
                finally:
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
        except Exception:
            ttk.Label(self.video_info_frame, text="Limited metadata (OpenCV not available)").pack(anchor="w")

        # Player canvas (recreate to reset)
        self.video_canvas = tk.Canvas(self.video_player_frame, bg="black", highlightthickness=0)
        self.video_canvas.grid(row=0, column=0, sticky="nsew")
        # Make the right-side Play button active to start playback
        if self.play_pause_btn:
            try:
                self.play_pause_btn.configure(state="normal", text="Play")
            except Exception:
                pass

    def _play_selected_video(self) -> None:
        if not self.video_listbox or not self.context:
            return
        selection = self.video_listbox.curselection()
        if not selection:
            return
        keys = list(self.context.videos.keys())
        idx = selection[0]
        if idx >= len(keys):
            return
        video_filename = keys[idx]
        self._play_video_embedded(video_filename)

    def _on_play_clicked(self) -> None:
        """Start playback if not started; otherwise toggle play/pause."""
        try:
            if not self._video_player or (hasattr(self._video_player, 'isOpened') and not self._video_player.isOpened()):
                self._play_selected_video()
            else:
                self._toggle_play_pause()
        except Exception:
            # Fallback to starting playback
            self._play_selected_video()

    def _play_video_embedded(self, video_filename: str) -> None:
        if not self.context or video_filename not in getattr(self.context, 'videos', {}):
            return
        try:
            import cv2
            self._stop_video()
            video_bytes = self.context.videos[video_filename]
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, video_filename)
            with open(temp_path, 'wb') as f:
                f.write(video_bytes)
            self._video_player = cv2.VideoCapture(temp_path)
            self._current_video_path = temp_path
            if not self._video_player.isOpened():
                raise Exception("Cannot open video file")
            fps = self._video_player.get(cv2.CAP_PROP_FPS) or 30.0
            frame_count = int(self._video_player.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = frame_count / fps if fps > 0 else 0
            if self.play_pause_btn:
                self.play_pause_btn.configure(state="normal", text="Pause")
            if self.stop_btn:
                self.stop_btn.configure(state="normal")
            self._is_playing = True
            self._start_playback_thread(duration)
        except ImportError:
            self._play_video_externally(video_filename)
        except Exception as e:
            logger.error(f"Failed to play video: {e}")
            self._play_video_externally(video_filename)

    def _play_video_externally(self, video_filename: str) -> None:
        if not self.context or video_filename not in getattr(self.context, 'videos', {}):
            return
        try:
            video_bytes = self.context.videos[video_filename]
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, video_filename)
            with open(temp_path, 'wb') as f:
                f.write(video_bytes)
            import platform
            if platform.system() == 'Windows':
                os.startfile(temp_path)
            elif platform.system() == 'Darwin':
                subprocess.run(['open', temp_path])
            else:
                subprocess.run(['xdg-open', temp_path])
        except Exception as e:
            logger.error(f"Failed to play video externally: {e}")

    def _download_all_videos(self) -> None:
        """Download all videos using proposed names into chosen folder."""
        if not self.context or not getattr(self.context, 'videos', {}):
            return
        names = self._create_per_section_video_names()
        try:
            manual_code = str(self.context.metadata.get('manual_code') or '').strip()
        except Exception:
            manual_code = ''
        if not manual_code:
            try:
                from orlando_toolkit.core.utils import slugify
                title = str(self.context.metadata.get('manual_title') or '').strip()
                manual_code = slugify(title) if title else 'videos'
            except Exception:
                manual_code = 'videos'
        folder_name = f"{manual_code}_videos"
        try:
            from tkinter import filedialog
            directory = filedialog.askdirectory(title=f"Choose parent folder for '{folder_name}'")
        except Exception:
            directory = ''
        if not directory:
            return
        try:
            target_root = os.path.join(directory, folder_name)
            os.makedirs(target_root, exist_ok=True)
        except Exception:
            pass
        for original, data in self.context.videos.items():
            target_name = names.get(original, original)
            target_path = os.path.join(target_root, target_name)
            try:
                with open(target_path, 'wb') as f:
                    f.write(data)
            except Exception:
                continue

    def _start_playback_thread(self, duration: float) -> None:
        def playback_worker():
            try:
                import cv2
                from PIL import Image as PILImage, ImageTk as PILImageTk
                frame_time = 1.0 / 30.0
                while self._is_playing and self._video_player and self._video_player.isOpened():
                    ret, frame = self._video_player.read()
                    if not ret:
                        break
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_image = PILImage.fromarray(frame_rgb)
                    cw = self.video_canvas.winfo_width() if self.video_canvas else 0
                    ch = self.video_canvas.winfo_height() if self.video_canvas else 0
                    if cw > 1 and ch > 1:
                        img_ratio = pil_image.width / pil_image.height
                        canvas_ratio = cw / ch
                        if img_ratio > canvas_ratio:
                            new_w = max(1, cw - 20)
                            new_h = max(1, int(new_w / img_ratio))
                        else:
                            new_h = max(1, ch - 20)
                            new_w = max(1, int(new_h * img_ratio))
                        pil_image = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)

                    def update_frame():
                        try:
                            photo = PILImageTk.PhotoImage(pil_image)
                            self.video_canvas.delete("all")
                            cx = self.video_canvas.winfo_width() // 2
                            cy = self.video_canvas.winfo_height() // 2
                            self.video_canvas.create_image(cx, cy, image=photo)
                            self.video_canvas.image = photo
                            try:
                                import cv2 as _cv
                                current_time = self._video_player.get(_cv.CAP_PROP_POS_MSEC) / 1000.0
                            except Exception:
                                current_time = 0.0
                            current_str = self._format_time(current_time)
                            duration_str = self._format_time(duration)
                            if self.time_label:
                                self.time_label.configure(text=f"{current_str} / {duration_str}")
                        except Exception as e:
                            logger.debug(f"Frame update error: {e}")

                    if self.video_canvas:
                        self.video_canvas.after(0, update_frame)
                    threading.Event().wait(frame_time)
                if self.video_canvas:
                    self.video_canvas.after(0, self._on_video_ended)
            except Exception as e:
                logger.error(f"Playback thread error: {e}")
                if self.video_canvas:
                    self.video_canvas.after(0, self._on_video_ended)

        threading.Thread(target=playback_worker, daemon=True).start()

    def _materialize_videos_async(self) -> None:
        """Write videos to a temporary directory for OS access/open-folder."""
        if not self.context or not getattr(self.context, 'videos', {}):
            return
        def work():
            try:
                base = Path(tempfile.gettempdir()) / "orlando_videos"
                base.mkdir(parents=True, exist_ok=True)
                self._video_disk_dir = base
                self._video_disk_paths: Dict[str, str] = {}
                for name, b in self.context.videos.items():
                    p = base / name
                    try:
                        p.parent.mkdir(parents=True, exist_ok=True)
                        with open(p, 'wb') as f:
                            f.write(b)
                        self._video_disk_paths[name] = str(p)
                    except Exception:
                        continue
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _toggle_play_pause(self) -> None:
        if self._is_playing:
            self._pause_video()
        else:
            self._resume_video()

    def _pause_video(self) -> None:
        self._is_playing = False
        if self.play_pause_btn:
            self.play_pause_btn.configure(text="Play")

    def _resume_video(self) -> None:
        if self._video_player and self._video_player.isOpened():
            self._is_playing = True
            if self.play_pause_btn:
                self.play_pause_btn.configure(text="Pause")

    def _stop_video(self) -> None:
        self._is_playing = False
        if self._video_player:
            try:
                self._video_player.release()
            except Exception:
                pass
            self._video_player = None
        if self._current_video_path and os.path.exists(self._current_video_path):
            try:
                os.unlink(self._current_video_path)
            except Exception:
                pass
        self._current_video_path = None
        if self.play_pause_btn:
            self.play_pause_btn.configure(text="Play", state="disabled")
        if self.stop_btn:
            self.stop_btn.configure(state="disabled")
        if self.time_label:
            self.time_label.configure(text="00:00 / 00:00")
        if self.video_canvas:
            self.video_canvas.delete("all")

    def _on_video_ended(self) -> None:
        self._stop_video()
        if self.video_canvas:
            self.video_canvas.create_text(
                self.video_canvas.winfo_width() // 2,
                self.video_canvas.winfo_height() // 2,
                text="Video Ended",
                fill="white",
                font=("Arial", 14),
            )

    def _format_time(self, seconds: float) -> str:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def _download_selected_video(self) -> None:
        if not self.video_listbox or not self.context:
            return
        selection = self.video_listbox.curselection()
        if not selection:
            return
        try:
            video_filename = self.video_listbox.get(selection[0])
            from tkinter import filedialog
            filepath = filedialog.asksaveasfilename(
                title="Save Video",
                defaultextension=Path(video_filename).suffix,
                initialname=video_filename,
            )
            if filepath:
                with open(filepath, 'wb') as f:
                    f.write(self.context.videos[video_filename])
        except Exception as e:
            logger.error(f"Failed to download video: {e}")

    def _show_no_video_selected(self) -> None:
        for widget in (self.video_info_frame.winfo_children() if self.video_info_frame else []):
            widget.destroy()
        for widget in (self.video_player_frame.winfo_children() if self.video_player_frame else []):
            widget.destroy()
        if self.video_info_frame:
            ttk.Label(self.video_info_frame, text="No video selected").pack()
        if self.video_player_frame:
            ttk.Label(self.video_player_frame, text="Select a video from the list to view details").pack(expand=True)
    def on_image_select(self, _event) -> None:
        if not (self.context and self.image_listbox):
            return
        selection = self.image_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.context.images):
            return
        original_filename = list(self.context.images.keys())[index]
        self._last_selected_key = original_filename
        self._clear_status()
        self.show_image_preview(original_filename, self.context.images[original_filename])

    def show_image_preview(self, filename: str, image_data: bytes) -> None:
        if not self.preview_label:
            return
        try:
            self._current_preview_bytes = image_data
            self._render_preview_from_bytes(image_data)
        except Exception as e:
            try:
                self.preview_label.configure(image="", text=f"Cannot preview image\n{str(e)}")
                self.preview_label.image = None
            except Exception:
                pass
            if self.info_label:
                self.info_label.configure(text="Preview unavailable")

    def _render_preview_from_bytes(self, image_data: bytes) -> None:
        if not self.preview_label:
            return
        try:
            image = Image.open(io.BytesIO(image_data))
            original_w, original_h = image.size
            avail_w = max(400, int(self.preview_label.winfo_width() or 0))
            avail_h = max(300, int(self.preview_label.winfo_height() or 0))
            target_w = max(400, min(1000, avail_w - 24))
            target_h = max(300, min(800, avail_h - 24))
            image.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.preview_label.configure(image=photo, text="")
            self.preview_label.image = photo
            size_kb = len(image_data) / 1024
            try:
                fmt = Image.open(io.BytesIO(image_data)).format
            except Exception:
                fmt = None
            info = [f"Original: {original_w}x{original_h}", f"Size: {size_kb:.1f} KB"]
            if fmt:
                info.append(f"Format: {fmt}")
            if self._status_message:
                info.append(self._status_message)
            self.info_label.configure(text="\n".join(info))
        except Exception:
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

    # ------------------------- Image actions ----------------------------
    def open_images_folder(self) -> None:
        try:
            from orlando_toolkit.core.session_storage import get_session_storage
            storage = get_session_storage()
            folder = storage.base_dir
        except Exception:
            folder = Path(tempfile.gettempdir())
        try:
            if os.name == 'nt':
                os.startfile(str(folder))
            elif os.name == 'posix':
                if 'darwin' in os.uname().sysname.lower():
                    subprocess.run(['open', str(folder)])
                else:
                    subprocess.run(['xdg-open', str(folder)])
        except Exception:
            pass

    def download_selected_image(self) -> None:
        if not (self.context and self.image_listbox):
            return
        selection = self.image_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.context.images):
            self._set_status("No image selected")
            return
        original_filename = list(self.context.images.keys())[index]
        proposed = self._proposed_names.get(original_filename, original_filename)
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
        try:
            image_data = self.context.images[original_filename]
            with open(save_path, "wb") as f:
                f.write(image_data)
        except Exception:
            pass
