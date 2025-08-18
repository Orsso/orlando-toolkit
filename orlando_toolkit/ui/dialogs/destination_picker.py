from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Dict, Any


class DestinationPicker(tk.Toplevel):
    """Minimal destination picker dialog for large documents.

    Provides a searchable list of section destinations built from entries of the form:
    {"label": str, "index_path": Optional[List[int]]}

    show() returns the chosen index_path (List[int] or None for root), or None if cancelled.
    """

    def __init__(self, master: tk.Widget, *, destinations: List[Dict[str, Any]]) -> None:
        super().__init__(master)
        self.title("Choose destination")
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()

        self._destinations: List[Dict[str, Any]] = list(destinations or [])
        self._filtered_indices: List[int] = list(range(len(self._destinations)))
        self._result: Optional[Optional[List[int]]] = None

        # Layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Search bar
        search_frame = ttk.Frame(self)
        search_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        search_frame.columnconfigure(1, weight=1)
        ttk.Label(search_frame, text="Search:").grid(row=0, column=0, sticky="w")
        self._search_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self._search_var)
        entry.grid(row=0, column=1, sticky="ew")
        entry.bind("<KeyRelease>", lambda _e: self._apply_filter())

        # Listbox
        list_frame = ttk.Frame(self)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self._list = tk.Listbox(list_frame, exportselection=False)
        self._list.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self._list.yview)
        self._list.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self._list.bind("<Double-Button-1>", lambda _e: self._on_accept())

        # Buttons
        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, sticky="e", padx=8, pady=(0, 8))
        ttk.Button(btns, text="Cancel", command=self._on_cancel).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(btns, text="Send here", command=self._on_accept).grid(row=0, column=1)

        self._populate()
        try:
            entry.focus_set()
        except Exception:
            pass

    def _populate(self) -> None:
        try:
            self._list.delete(0, tk.END)
        except Exception:
            pass
        for idx in self._filtered_indices:
            try:
                d = self._destinations[idx]
                label = d.get("label")
                self._list.insert(tk.END, str(label))
            except Exception:
                continue

    def _apply_filter(self) -> None:
        term = (self._search_var.get() or "").strip().lower()
        self._filtered_indices = []
        if not term:
            self._filtered_indices = list(range(len(self._destinations)))
        else:
            for i, d in enumerate(self._destinations):
                try:
                    label = str(d.get("label") or "")
                    if term in label.lower():
                        self._filtered_indices.append(i)
                except Exception:
                    continue
        self._populate()

    def _on_accept(self) -> None:
        try:
            sel = self._list.curselection()
            if not sel:
                return
            idx = self._filtered_indices[sel[0]]
            entry = self._destinations[idx]
            self._result = entry.get("index_path")  # may be None for root
        except Exception:
            self._result = None
        self.destroy()

    def _on_cancel(self) -> None:
        self._result = None
        self.destroy()

    def show(self) -> Optional[Optional[List[int]]]:
        """Run the dialog and return the chosen index_path (or None)."""
        try:
            self.wait_window(self)
        except Exception:
            pass
        return self._result


