import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from src.docx_to_dita_converter import DitaContext

logger = logging.getLogger(__name__)

class MetadataTab(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.context: 'DitaContext' = None
        self.entries = {}
        self.on_metadata_change_callback = None  # Callback for notifying other tabs

        form_frame = ttk.Frame(self, padding=20)
        form_frame.pack(fill='x', expand=True)
        form_frame.columnconfigure(1, weight=1)

        # Title
        title_label = ttk.Label(form_frame, text="Document Metadata", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 20))

        metadata_fields = {
            "manual_title": "Manual Title:",
            "manual_code": "Manual Code:",
            "revision_date": "Revision Date:",
            "revision_number": "Revision Number:",
        }
        
        for i, (key, label) in enumerate(metadata_fields.items(), start=1):
            ttk.Label(form_frame, text=label, font=("Arial", 11)).grid(row=i, column=0, sticky='w', pady=8, padx=(0, 15))
            var = tk.StringVar()
            entry = ttk.Entry(form_frame, textvariable=var, font=("Arial", 11))
            entry.grid(row=i, column=1, sticky='ew', padx=5, pady=5)
            entry.bind('<FocusOut>', lambda event, k=key: self.update_context_metadata(k))
            self.entries[key] = var

        # Help text
        help_text = ttk.Label(form_frame, 
                             text="These metadata fields will be included in the generated DITA archive.",
                             font=("Arial", 10), foreground="gray")
        help_text.grid(row=len(metadata_fields)+2, column=0, columnspan=2, sticky='w', pady=(20, 0))

    def load_context(self, context: 'DitaContext'):
        self.context = context
        for key, var in self.entries.items():
            var.set(self.context.metadata.get(key, ''))

    def update_context_metadata(self, key: str):
        if self.context:
            new_value = self.entries[key].get()
            if key in self.context.metadata and self.context.metadata[key] != new_value:
                self.context.metadata[key] = new_value
                logger.info(f"Context updated: {key} = {new_value}")
                # Notify other tabs of metadata change
                if self.on_metadata_change_callback:
                    self.on_metadata_change_callback()
            elif key not in self.context.metadata:
                self.context.metadata[key] = new_value
                logger.info(f"Context updated: {key} = {new_value}")
                # Notify other tabs of metadata change
                if self.on_metadata_change_callback:
                    self.on_metadata_change_callback()

    def set_metadata_change_callback(self, callback):
        """Set callback to be called when metadata changes."""
        self.on_metadata_change_callback = callback

    # The save_metadata_to_context method is redundant and removed.
    # Updates are done via update_context_metadata on FocusOut event. 