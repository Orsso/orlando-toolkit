# -*- coding: utf-8 -*-
"""
Metadata tab for entering document information.
User interface for configuring document metadata and revision information.
"""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from orlando_toolkit.core.models import DitaContext

logger = logging.getLogger(__name__)


class MetadataTab(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        from orlando_toolkit.ui.widgets.metadata_form import MetadataForm

        self.context: "DitaContext" | None = None
        self.on_metadata_change_callback = None  # Callback for notifying other tabs

        wrapper = ttk.Frame(self, padding=20)
        wrapper.pack(fill="both", expand=True)

        title_label = ttk.Label(wrapper, text="Document Metadata", font=("Arial", 16, "bold"))
        title_label.pack(anchor="w", pady=(0, 14))

        # Reuse the unified metadata form widget to ensure consistent style.
        self._form = MetadataForm(wrapper, padding=6, on_change=self._on_form_change)
        self._form.pack(fill="x")

        help_text = ttk.Label(
            wrapper,
            text="These metadata fields will be included in the generated DITA archive.",
            font=("Arial", 10),
            foreground="gray",
        )
        help_text.pack(anchor="w", pady=(12, 0))

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def load_context(self, context: "DitaContext") -> None:
        self.context = context
        self._form.load_context(context)

    def _on_form_change(self) -> None:
        # Form already synced context; just propagate to other tabs and caller
        if not self.context:
            return
        # Keep Structure tab context copies synchronized for export
        if hasattr(self.master.master, "structure_tab") and self.master.master.structure_tab:
            st = self.master.master.structure_tab
            for ctx_attr in ("context", "_orig_context", "_main_context"):
                if hasattr(st, ctx_attr) and getattr(st, ctx_attr):
                    getattr(st, ctx_attr).metadata.update(self.context.metadata)
        if self.on_metadata_change_callback:
            self.on_metadata_change_callback()

    def set_metadata_change_callback(self, callback):
        """Register a callback that is called whenever metadata changes."""
        self.on_metadata_change_callback = callback 