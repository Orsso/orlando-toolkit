# -*- coding: utf-8 -*-
"""
Reusable metadata form widget.

Provides a themed, compact form for editing DITA metadata fields. This widget
is GUI-only and raises a callback when values change so callers can propagate
updates to the broader application (e.g., image names, structure previews).
"""

from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING
import tkinter as tk
from tkinter import ttk

if TYPE_CHECKING:
    from orlando_toolkit.core.models import DitaContext


class MetadataForm(ttk.Frame):
    def __init__(self, parent, *, padding: int = 8, font_size: int = 11, on_change: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, padding=padding, **kwargs)
        self.context: Optional["DitaContext"] = None
        self.on_change: Optional[Callable[[], None]] = on_change
        self.entries: dict[str, tk.StringVar] = {}
        self._font_main = ("Arial", font_size)

        # Grid layout
        self.columnconfigure(1, weight=1)

        metadata_fields = {
            "manual_title": "Manual Title:",
            "manual_code": "Manual Short Name:",
            "revision_date": "Revision Date:",
        }

        for i, (key, label_text) in enumerate(metadata_fields.items(), start=0):
            label = ttk.Label(self, text=label_text, font=self._font_main)
            label.grid(row=i, column=0, sticky="w", padx=(0, 14), pady=6)

            var = tk.StringVar()
            entry = ttk.Entry(self, textvariable=var, font=self._font_main)
            entry.grid(row=i, column=1, sticky="ew", padx=(0, 0), pady=6, ipady=2)
            entry.bind("<FocusOut>", lambda _e, k=key: self._on_field_blur(k))
            self.entries[key] = var

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_context(self, context: "DitaContext") -> None:
        self.context = context
        for key, var in self.entries.items():
            var.set(self.context.metadata.get(key, ""))

    def set_on_change(self, callback: Optional[Callable[[], None]]) -> None:
        self.on_change = callback

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _on_field_blur(self, key: str) -> None:
        if not self.context:
            return
        new_value = self.entries[key].get()
        # Update context only when changed
        if key not in self.context.metadata or self.context.metadata.get(key) != new_value:
            self.context.metadata[key] = new_value
            if self.on_change:
                try:
                    self.on_change()
                except Exception:
                    pass


