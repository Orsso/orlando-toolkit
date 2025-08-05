# -*- coding: utf-8 -*-
"""PreviewPanel widget.

A compact, presentation-only panel that displays either HTML or XML text for a
selected topic. It contains:
- Header row with a mode toggle (HTML | XML), a Refresh button, and a status label.
- Body area with a read-only ScrolledText.

Public API (UI-only, no services/I/O):
- set_mode(mode: Literal["html","xml"]) -> None
- get_mode() -> Literal["html","xml"]
- set_loading(loading: bool) -> None
- set_title(text: str) -> None
- set_content(text: str) -> None
- show_error(message: str) -> None
- clear() -> None

Callbacks:
- on_mode_changed: Optional[Callable[[Literal["html","xml"]], None]]
- on_refresh: Optional[Callable[[], None]]

Notes:
- No business logic is included here. This widget is purely presentational.
- The HTML/XML strings are rendered as plain text; no embedded webview is used.
"""

from __future__ import annotations

from typing import Callable, Literal, Optional, cast
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


Mode = Literal["html", "xml"]


__all__ = ["PreviewPanel"]


class PreviewPanel(ttk.Frame):
    """A compact panel for previewing HTML or XML as read-only text."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        on_mode_changed: Optional[Callable[[Mode], None]] = None,
        on_refresh: Optional[Callable[[], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)

        self.on_mode_changed: Optional[Callable[[Mode], None]] = on_mode_changed
        self.on_refresh: Optional[Callable[[], None]] = on_refresh

        # Layout
        self.columnconfigure(0, weight=1)
        # With title removed, the text widget is now at row=1
        self.rowconfigure(1, weight=1)

        # Header row (compact)
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=4, pady=2)
        # Columns: 0=left group (radiobuttons + status), 1=spacer, 2=refresh btn
        header.columnconfigure(0, weight=0)
        header.columnconfigure(1, weight=1)  # stretch spacer
        header.columnconfigure(2, weight=0)

        # Mode toggle - compact
        self._mode_var = tk.StringVar(value="html")
        toggle = ttk.Frame(header)
        toggle.grid(row=0, column=0, sticky="w", padx=(0, 0), pady=0)

        self._rb_html = ttk.Radiobutton(
            toggle, text="HTML", value="html", variable=self._mode_var, command=self._on_mode_toggle
        )
        self._rb_xml = ttk.Radiobutton(
            toggle, text="XML", value="xml", variable=self._mode_var, command=self._on_mode_toggle
        )
        # Tight paddings for radios
        self._rb_html.grid(row=0, column=0, padx=(0, 4), pady=0, sticky="w")
        self._rb_xml.grid(row=0, column=1, padx=(0, 4), pady=0, sticky="w")

        # Status label - small, empty when idle
        self._status_var = tk.StringVar(value="")

        self._status_label = ttk.Label(toggle, textvariable=self._status_var)
        self._status_label.grid(row=0, column=2, padx=(8, 0), pady=0, sticky="w")        # Spacer column (1) stretches

        # Refresh button aligned right, compact paddings
        self._refresh_btn = ttk.Button(header, text="Refresh", command=self._on_refresh_clicked)
        self._refresh_btn.grid(row=0, column=2, padx=(4, 0), pady=0, sticky="e")

        # Body: ScrolledText only (title row removed to reclaim vertical space)
        self._title_var = tk.StringVar(value="")  # retained for API compatibility
        self._title_label = None  # type: ignore[assignment]

        self._text = ScrolledText(self, wrap="word", height=10)
        # Place directly under header and expand
        self._text.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self._text.configure(state="disabled")

    # Public API

    def set_mode(self, mode: Mode) -> None:
        """Set the preview mode."""
        val = "html" if mode == "html" else "xml"
        try:
            if self._mode_var.get() != val:
                self._mode_var.set(val)
        except Exception:
            self._mode_var.set(val)

    def get_mode(self) -> Mode:
        """Get the current preview mode."""
        val = str(self._mode_var.get() or "html").lower()
        return cast(Mode, "xml" if val == "xml" else "html")

    def set_loading(self, loading: bool) -> None:
        """Update loading status indicator."""
        try:
            self._status_var.set("Loading…" if loading else "")
            # Optionally disable refresh while loading
            self._refresh_btn.configure(state=("disabled" if loading else "normal"))
        except Exception:
            pass

    def set_title(self, text: str) -> None:
        """No-op to keep API stable; title is visually hidden to save space."""
        try:
            # Keep variable updated for potential external reads, but do not render a label.
            self._title_var.set("")
        except Exception:
            pass

    def set_content(self, text: str) -> None:
        """Set body content as read-only text."""
        try:
            self._text.configure(state="normal")
            self._text.delete("1.0", "end")
            self._text.insert("1.0", text or "")
            self._text.configure(state="disabled")
        except Exception:
            # Ensure it's at least read-only
            try:
                self._text.configure(state="disabled")
            except Exception:
                pass

    def show_error(self, message: str) -> None:
        """Display an error message in the body."""
        msg = message or "An error occurred."
        # Do not set a visual title; write the error directly in the content area.
        self.set_content(msg)

    def clear(self) -> None:
        """Clear content and reset loading; title row is removed to save space."""
        self._title_var.set("")
        self.set_content("")
        self.set_loading(False)

    # Internal callbacks

    def _on_mode_toggle(self) -> None:
        mode = self.get_mode()
        cb = self.on_mode_changed
        if callable(cb):
            try:
                cb(mode)
            except Exception:
                pass

    def _on_refresh_clicked(self) -> None:
        cb = self.on_refresh
        if callable(cb):
            try:
                cb()
            except Exception:
                pass