# -*- coding: utf-8 -*-
"""
Tab for previewing and renaming images found in the converted DITA context.
Image management interface for DITA package generation.
"""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Optional
import os
from PIL import Image, ImageTk
import io

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

        self.create_widgets()

    # ------------------------------------------------------------------
    # UI builders
    # ------------------------------------------------------------------

    def create_widgets(self):
        """Create the widgets for displaying the image list and prefix field."""
        main_frame = ttk.Frame(self)
        main_frame.pack(expand=True, fill="both", padx=15, pady=15)

        # Title
        title_label = ttk.Label(main_frame, text="Image Management", font=("Arial", 16, "bold"))
        title_label.pack(anchor="w", pady=(0, 20))

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

        # --- Left panel: Image list ---
        left_panel = ttk.LabelFrame(content_frame, text="File Names Preview", padding=10)
        left_panel.pack(side="left", expand=True, fill="both", padx=(0, 10))

        self.image_listbox = tk.Listbox(left_panel, font=("Arial", 10))
        self.image_listbox.pack(side="left", expand=True, fill="both")
        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)

        scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=self.image_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.image_listbox.config(yscrollcommand=scrollbar.set)

        # --- Right panel: Image preview ---
        right_panel = ttk.LabelFrame(content_frame, text="Image Preview", padding=10)
        right_panel.pack(side="right", fill="both", padx=(10, 0))
        right_panel.configure(width=300)
        right_panel.pack_propagate(False)

        # Preview canvas/label
        self.preview_label = ttk.Label(
            right_panel,
            text="Select an image to preview",
            font=("Arial", 10),
            foreground="gray",
            anchor="center",
        )
        self.preview_label.pack(expand=True, fill="both", pady=20)

        # Image info
        self.info_label = ttk.Label(right_panel, text="", font=("Arial", 9), foreground="gray")
        self.info_label.pack(pady=(0, 10))

        # Help text
        help_text = ttk.Label(
            main_frame,
            text="Images will be renamed with per-section numbering: [PREFIX]-[MANUAL_CODE]-[SECTION]-[NUMBER] (number only if multiple images in section)",
            font=("Arial", 10),
            foreground="gray",
        )
        help_text.pack(anchor="w", pady=(15, 0))

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

        # Display the new filenames in order
        for original_filename in self.context.images.keys():
            new_filename = image_names.get(original_filename, original_filename)
            self.image_listbox.insert(tk.END, new_filename)

    def _create_per_section_image_names(self) -> dict[str, str]:
        """Create new filenames with per-section image numbering."""
        if not self.context or not self.context.ditamap_root:
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

        self.show_image_preview(original_filename, image_data)

    def show_image_preview(self, filename: str, image_data: bytes) -> None:
        """Render a thumbnail preview of the selected image."""
        try:
            image = Image.open(io.BytesIO(image_data))

            original_width, original_height = image.size

            max_size = 250
            ratio = min(max_size / original_width, max_size / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)

            image.thumbnail((new_width, new_height), Image.Resampling.LANCZOS)

            photo = ImageTk.PhotoImage(image)

            self.preview_label.configure(image=photo, text="")
            self.preview_label.image = photo

            size_kb = len(image_data) / 1024
            info_text = f"Original: {original_width}x{original_height}\nSize: {size_kb:.1f} KB\nFormat: {image.format or 'Unknown'}"
            self.info_label.configure(text=info_text)

        except Exception as e:
            self.preview_label.configure(image="", text=f"Cannot preview image\n{str(e)}")
            self.preview_label.image = None
            self.info_label.configure(text="Preview unavailable") 