import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Optional
import os
from PIL import Image, ImageTk
import io

if TYPE_CHECKING:
    from src.docx_to_dita_converter import DitaContext

class ImageTab(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        
        self.context: Optional['DitaContext'] = None
        
        # --- Widgets ---
        self.image_listbox: Optional[tk.Listbox] = None
        self.prefix_entry: Optional[ttk.Entry] = None
        self.preview_label: Optional[ttk.Label] = None
        self.info_label: Optional[ttk.Label] = None
        self.section_map = {} # To map original filename to section name

        self.create_widgets()

    def create_widgets(self):
        """Creates widgets to display image list and prefix field."""
        main_frame = ttk.Frame(self)
        main_frame.pack(expand=True, fill='both', padx=15, pady=15)
        
        # Title
        title_label = ttk.Label(main_frame, text="Image Management", font=("Arial", 16, "bold"))
        title_label.pack(anchor='w', pady=(0, 20))
        
        # --- Options frame ---
        options_frame = ttk.LabelFrame(main_frame, text="Naming Options", padding=15)
        options_frame.pack(fill='x', pady=(0, 15))

        options_frame.columnconfigure(1, weight=1)
        options_frame.columnconfigure(3, weight=1)

        prefix_label = ttk.Label(options_frame, text="Prefix:", font=("Arial", 11))
        prefix_label.grid(row=0, column=0, sticky='w', padx=(0, 10), pady=5)
        
        self.prefix_entry = ttk.Entry(options_frame, font=("Arial", 11))
        self.prefix_entry.grid(row=0, column=1, sticky='ew', padx=(0, 20), pady=5)
        self.prefix_entry.bind('<KeyRelease>', lambda e: self.update_image_names())

        # Content frame with two panels
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(expand=True, fill='both')

        # --- Left panel: Image list ---
        left_panel = ttk.LabelFrame(content_frame, text="File Names Preview", padding=10)
        left_panel.pack(side='left', expand=True, fill='both', padx=(0, 10))

        self.image_listbox = tk.Listbox(left_panel, font=("Arial", 10))
        self.image_listbox.pack(side='left', expand=True, fill='both')
        self.image_listbox.bind('<<ListboxSelect>>', self.on_image_select)
        
        scrollbar = ttk.Scrollbar(left_panel, orient='vertical', command=self.image_listbox.yview)
        scrollbar.pack(side='right', fill='y')
        self.image_listbox.config(yscrollcommand=scrollbar.set)

        # --- Right panel: Image preview ---
        right_panel = ttk.LabelFrame(content_frame, text="Image Preview", padding=10)
        right_panel.pack(side='right', fill='both', padx=(10, 0))
        right_panel.configure(width=300)
        right_panel.pack_propagate(False)

        # Preview canvas/label
        self.preview_label = ttk.Label(right_panel, text="Select an image to preview", 
                                      font=("Arial", 10), foreground="gray", anchor="center")
        self.preview_label.pack(expand=True, fill='both', pady=20)

        # Image info
        self.info_label = ttk.Label(right_panel, text="", font=("Arial", 9), foreground="gray")
        self.info_label.pack(pady=(0, 10))

        # Help text
        help_text = ttk.Label(main_frame, 
                             text="Images will be renamed according to the pattern: [PREFIX]-[MANUAL_CODE]-[SECTION]-[NUMBER]",
                             font=("Arial", 10), foreground="gray")
        help_text.pack(anchor='w', pady=(15, 0))

    def load_context(self, context: 'DitaContext'):
        """Loads image list and initializes prefix."""
        self.context = context
        
        # Simulate default prefix if not present
        if 'prefix' not in self.context.metadata:
            self.context.metadata['prefix'] = 'CRL'
        
        if self.prefix_entry:
            self.prefix_entry.delete(0, tk.END)
            self.prefix_entry.insert(0, self.context.metadata.get('prefix', ''))
        
        self.update_image_names()

    def update_image_names(self):
        """Updates filename list based on prefix and metadata."""
        if not self.context or not self.prefix_entry or not self.image_listbox:
            return

        # Update metadata from fields
        prefix = self.prefix_entry.get()
        self.context.metadata['prefix'] = prefix
        
        # Get manual_code from metadata (set in metadata tab)
        manual_code = self.context.metadata.get('manual_code', '')
        
        self.image_listbox.delete(0, tk.END)

        if not self.context.images:
            self.image_listbox.insert(tk.END, "No images found.")
            return

        # Nomenclature: [PREFIX]-[MANUAL_CODE]-[SECTION_NUMBER]-[IMAGE_NUMBER]
        # For now, we don't have section, simplified
        for i, original_filename in enumerate(self.context.images.keys()):
            # Placeholder for section number, using 0 for now
            section_num = "0"
            img_num = i + 1
            extension = os.path.splitext(original_filename)[1]
            
            if manual_code:
                new_filename = f"{prefix}-{manual_code}-{section_num}-{img_num}{extension}"
            else:
                new_filename = f"{prefix}-{section_num}-{img_num}{extension}"
            self.image_listbox.insert(tk.END, new_filename)

    def on_image_select(self, event):
        """Called when an image is selected in the listbox."""
        if not self.context or not self.image_listbox or not self.preview_label:
            return
        
        selection = self.image_listbox.curselection()
        if not selection:
            return
        
        # Get original filename from index
        index = selection[0]
        if index >= len(self.context.images):
            return
        
        original_filename = list(self.context.images.keys())[index]
        image_data = self.context.images[original_filename]
        
        self.show_image_preview(original_filename, image_data)

    def show_image_preview(self, filename, image_data):
        """Shows preview of selected image."""
        try:
            # Load image from bytes
            image = Image.open(io.BytesIO(image_data))
            
            # Get original dimensions
            original_width, original_height = image.size
            
            # Calculate thumbnail size (max 250x250 while maintaining aspect ratio)
            max_size = 250
            ratio = min(max_size / original_width, max_size / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            
            # Create thumbnail
            image.thumbnail((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # Update preview label
            self.preview_label.configure(image=photo, text="")
            self.preview_label.image = photo  # Keep reference
            
            # Update info label
            size_kb = len(image_data) / 1024
            info_text = f"Original: {original_width}x{original_height}\nSize: {size_kb:.1f} KB\nFormat: {image.format or 'Unknown'}"
            self.info_label.configure(text=info_text)
            
        except Exception as e:
            # Show error in preview
            self.preview_label.configure(image="", text=f"Cannot preview image\n{str(e)}")
            self.preview_label.image = None
            self.info_label.configure(text="Preview unavailable") 