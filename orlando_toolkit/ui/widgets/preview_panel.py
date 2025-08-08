# -*- coding: utf-8 -*-
"""PreviewPanel widget.

A compact, presentation-only panel that displays either HTML or XML content for a
selected topic. It contains:
- Header row with a mode toggle (HTML | XML), a Refresh button, and a status label.
- Body area with either HTMLScrolledText (if tkhtmlview available) or ScrolledText.

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
- HTML content is rendered visually if tkhtmlview is available, otherwise as plain text.
- Automatic fallback ensures the widget works with or without optional dependencies.
"""

from __future__ import annotations

from typing import Callable, Literal, Optional, cast
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

# Optional HTML rendering support (prefer tkinterweb if available)
try:
    from tkinterweb import HtmlFrame  # type: ignore
    HTML_WEB_AVAILABLE = True
except Exception:
    HTML_WEB_AVAILABLE = False
    HtmlFrame = None  # type: ignore

try:
    from tkhtmlview import HTMLScrolledText  # type: ignore
    TKHTMLVIEW_AVAILABLE = True
except Exception:
    TKHTMLVIEW_AVAILABLE = False
    HTMLScrolledText = None  # type: ignore


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

        # Body: HTML-capable text widget with graceful fallback
        self._title_var = tk.StringVar(value="")  # retained for API compatibility
        self._title_label = None  # type: ignore[assignment]

        # Prefer a real HTML widget when available for better table support
        self._html_rendering_enabled = False
        self._html_widget_kind = "text"  # 'tkinterweb' | 'tkhtmlview' | 'text'

        if HTML_WEB_AVAILABLE:
            try:
                self._text = HtmlFrame(
                    self,
                    horizontal_scrollbar="auto",  # type: ignore[arg-type]
                    vertical_scrollbar="auto",    # type: ignore[arg-type]
                    messages_enabled=False,        # silence debug banner
                )
                self._html_rendering_enabled = True
                self._html_widget_kind = "tkinterweb"
            except Exception:
                # Fallback chain continues below
                pass

        if not self._html_rendering_enabled and TKHTMLVIEW_AVAILABLE:
            try:
                self._text = HTMLScrolledText(self, height=10)  # type: ignore[call-arg]
                self._html_rendering_enabled = True
                self._html_widget_kind = "tkhtmlview"
            except Exception:
                pass

        if not self._html_rendering_enabled:
            self._text = ScrolledText(self, wrap="word", height=10)
            self._html_widget_kind = "text"
        
        # Place directly under header and expand
        self._text.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        
        # Configure text selection and read-only behavior
        if self._html_rendering_enabled and self._html_widget_kind == "tkhtmlview":
            try:
                # Make HTMLScrolledText read-only by binding key events
                self._text.configure(state="normal")
                
                # Bind events to prevent editing while allowing selection
                def prevent_edit(event):
                    # Allow Ctrl+C (copy) but prevent other modifications
                    if event.state & 0x4:  # Ctrl key pressed
                        if event.keysym in ('c', 'C'):
                            return  # Allow copy
                    return "break"  # Block all other key input
                
                self._text.bind('<Key>', prevent_edit)
                self._text.bind('<Button-2>', lambda e: "break")  # Block middle click paste
                self._text.bind('<Button-3>', lambda e: "break")  # Block right click for now
                
            except Exception:
                pass
        elif self._html_widget_kind == "text":
            # For ScrolledText, make it read-only but selectable
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
        """Set body content with HTML rendering if available and in HTML mode."""
        try:
            # Prefer HTML engine whenever content looks like HTML (both HTML mode and XML-wrapped-in-<pre>)
            content_str = text or ""
            looks_like_html = isinstance(content_str, str) and content_str.lstrip().startswith("<")

            if self._html_rendering_enabled and looks_like_html:
                if self._html_widget_kind == "tkinterweb" and hasattr(self._text, 'load_html'):
                    try:
                        self._text.load_html(content_str)
                        return
                    except Exception:
                        pass
                if self._html_widget_kind == "tkhtmlview" and hasattr(self._text, 'set_html'):
                    try:
                        self._text.set_html(content_str)
                        return
                    except Exception:
                        pass

            # Fallback: render as plain text (only reliable on ScrolledText)
            if isinstance(getattr(self, "_html_widget_kind", None), str) and self._html_widget_kind == "text":
                try:
                    self._text.configure(state="normal")
                    self._text.delete("1.0", "end")
                    self._text.insert("1.0", content_str)
                    self._text.configure(state="disabled")
                    return
                except Exception:
                    pass
            
        except Exception:
            # Ensure widget remains in a consistent state
            try:
                if hasattr(self._text, 'configure') and not self._html_rendering_enabled:
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

