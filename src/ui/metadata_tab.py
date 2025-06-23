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

        form_frame = ttk.Frame(self, padding=10)
        form_frame.pack(fill='x', expand=True)
        form_frame.columnconfigure(1, weight=1)

        metadata_fields = {
            "manual_title": "Manual Title:",
            "revision_date": "Revision Date:",
            "revision_number": "Revision Number:",
        }
        
        for i, (key, label) in enumerate(metadata_fields.items()):
            ttk.Label(form_frame, text=label).grid(row=i, column=0, sticky='w', pady=2, padx=(0, 10))
            var = tk.StringVar()
            entry = ttk.Entry(form_frame, textvariable=var)
            entry.grid(row=i, column=1, sticky='ew', padx=5)
            entry.bind('<FocusOut>', lambda event, k=key: self.update_context_metadata(k))
            self.entries[key] = var

    def load_context(self, context: 'DitaContext'):
        self.context = context
        for key, var in self.entries.items():
            var.set(self.context.metadata.get(key, ''))

    def update_context_metadata(self, key: str):
        if self.context:
            new_value = self.entries[key].get()
            if key in self.context.metadata and self.context.metadata[key] != new_value:
                self.context.metadata[key] = new_value
                logger.info(f"Contexte mis à jour: {key} = {new_value}")
            elif key not in self.context.metadata:
                self.context.metadata[key] = new_value
                logger.info(f"Contexte mis à jour: {key} = {new_value}")

    # La méthode save_metadata_to_context est redondante et supprimée.
    # La mise à jour se fait via update_context_metadata sur l'événement FocusOut. 