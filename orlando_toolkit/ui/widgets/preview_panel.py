# -*- coding: utf-8 -*-
"""PreviewPanel widget.

A compact, presentation-only panel that displays either HTML or XML content for a
selected topic. It contains:
- Header row with a mode toggle (HTML | XML) and a status label.
- Body area with a tkinterweb HtmlFrame when available, or ScrolledText fallback.

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
- on_refresh: Optional[Callable[[], None]]  # accepted for compatibility; no button is rendered

Notes:
- No business logic is included here. This widget is purely presentational.
- HTML content is rendered visually via tkinterweb when available; otherwise plain text.
- Automatic fallback ensures the widget works even if tkinterweb is missing.
"""

from __future__ import annotations

from typing import Callable, Literal, Optional, cast
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

# HTML rendering support (tkinterweb)
try:
    from tkinterweb import HtmlFrame  # type: ignore
    HTML_WEB_AVAILABLE = True
except Exception:
    HTML_WEB_AVAILABLE = False
    HtmlFrame = None  # type: ignore

# Local imports
from orlando_toolkit.ui.widgets.breadcrumb_widget import BreadcrumbWidget, BreadcrumbItem


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
        on_breadcrumb_clicked: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)

        self.on_mode_changed: Optional[Callable[[Mode], None]] = on_mode_changed
        # Keep for API compatibility, but no UI control triggers it.
        self.on_refresh: Optional[Callable[[], None]] = on_refresh
        self.on_breadcrumb_clicked: Optional[Callable[[str], None]] = on_breadcrumb_clicked

        # Layout
        self.columnconfigure(0, weight=1)
        # With title removed, the text widget is now at row=1
        self.rowconfigure(1, weight=1)

        # Header row (compact)
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=4, pady=2)
        # Columns: 0=left group (radiobuttons + status), 1=spacer, 2=breadcrumb
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
        self._status_label.grid(row=0, column=2, padx=(8, 0), pady=0, sticky="w")

        # Breadcrumb widget (wider spacing in preview panel)
        self._breadcrumb = BreadcrumbWidget(
            header,
            on_item_clicked=self._on_breadcrumb_clicked,
            max_width=560,
            link_max_chars=22,
            current_max_chars=28,
            separator_padx=(4, 4)
        )
        self._breadcrumb.grid(row=0, column=2, sticky="e", padx=(8, 0))

        # Body: HTML-capable text widget with graceful fallback
        self._title_var = tk.StringVar(value="")  # retained for API compatibility
        self._title_label = None  # type: ignore[assignment]

        # Prefer a real HTML widget when available
        self._html_rendering_enabled = False
        self._html_widget_kind = "text"  # 'tkinterweb' | 'text'

        if HTML_WEB_AVAILABLE:
            try:
                # Define external link handler for tkinterweb so clicks open in system browser
                def _open_external(url: str) -> str:
                    try:
                        if isinstance(url, str) and (url.startswith("http://") or url.startswith("https://") or url.startswith("mailto:")):
                            import webbrowser
                            webbrowser.open_new_tab(url)
                            return "break"
                    except Exception:
                        pass
                    # Fallback: allow default handling inside the HtmlFrame
                    return ""
                self._text = HtmlFrame(
                    self,
                    horizontal_scrollbar="auto",  # type: ignore[arg-type]
                    vertical_scrollbar="auto",    # type: ignore[arg-type]
                    messages_enabled=False,        # silence debug banner
                    on_link_click=_open_external,  # open external links in system browser
                )
                self._html_rendering_enabled = True
                self._html_widget_kind = "tkinterweb"
                # Best-effort: open links in external browser when supported by tkinterweb
                try:
                    def _open_external(url: str) -> str:
                        try:
                            import webbrowser
                            if isinstance(url, str) and url:
                                webbrowser.open_new_tab(url)
                        except Exception:
                            pass
                        return "break"
                    for attr_name in ("on_link_click", "on_link", "set_on_link_click", "set_on_link"):
                        cb = getattr(self._text, attr_name, None)
                        if callable(cb):
                            try:
                                cb(_open_external)  # type: ignore[misc]
                                break
                            except Exception:
                                pass
                except Exception:
                    pass
            except Exception:
                # Fallback continues below
                pass

        if not self._html_rendering_enabled:
            self._text = ScrolledText(self, wrap="word", height=10)
            self._html_widget_kind = "text"
        
        # Place directly under header and expand
        self._text.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        
        # Configure read-only behavior for text fallback
        if self._html_widget_kind == "text":
            # For ScrolledText, make it read-only but selectable
            self._text.configure(state="disabled")

        # Loading overlay (indeterminate progress) — hidden by default
        try:
            self._loading_frame = ttk.Frame(self)
            self._loading_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
            self._loading_frame.columnconfigure(0, weight=1)
            self._loading_frame.rowconfigure(0, weight=1)

            inner = ttk.Frame(self._loading_frame)
            inner.grid(row=0, column=0)
            self._loading_prog = ttk.Progressbar(inner, mode="indeterminate", length=160, maximum=100)
            self._loading_prog.grid(row=0, column=0, pady=8)
            # Hidden initially
            self._loading_frame.grid_remove()
        except Exception:
            self._loading_frame = None  # type: ignore[assignment]
            self._loading_prog = None  # type: ignore[assignment]

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
        """Toggle the loading overlay and reset the view while loading."""
        try:
            # Keep status label unobtrusive; no text
            try:
                self._status_var.set("")
            except Exception:
                pass

            if loading:
                # Clear content view
                try:
                    if self._html_widget_kind == "tkinterweb" and hasattr(self._text, 'load_html'):
                        self._text.load_html("<html><body></body></html>")
                    elif self._html_widget_kind == "text":
                        self._text.configure(state="normal")
                        self._text.delete("1.0", "end")
                        self._text.configure(state="disabled")
                except Exception:
                    pass
                # Show overlay, hide content
                try:
                    self._text.grid_remove()
                except Exception:
                    pass
                try:
                    if getattr(self, "_loading_frame", None) is not None:
                        self._loading_frame.grid()
                    if getattr(self, "_loading_prog", None) is not None:
                        self._loading_prog.start(10)
                except Exception:
                    pass
            else:
                # Hide overlay, show content
                try:
                    if getattr(self, "_loading_prog", None) is not None:
                        self._loading_prog.stop()
                except Exception:
                    pass
                try:
                    if getattr(self, "_loading_frame", None) is not None:
                        self._loading_frame.grid_remove()
                except Exception:
                    pass
                try:
                    self._text.grid()
                except Exception:
                    pass
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
        self._breadcrumb.clear()

    def set_breadcrumb_path(self, path_items: list[BreadcrumbItem]) -> None:
        """Set the breadcrumb navigation path."""
        try:
            self._breadcrumb.set_path(path_items)
        except Exception:
            pass

    # Internal callbacks

    def _on_mode_toggle(self) -> None:
        mode = self.get_mode()
        cb = self.on_mode_changed
        if callable(cb):
            try:
                cb(mode)
            except Exception:
                pass

    # Refresh callback retained for compatibility but unused (no button rendered)
    def _on_refresh_clicked(self) -> None:
        cb = self.on_refresh
        if callable(cb):
            try:
                cb()
            except Exception:
                pass

    def _on_breadcrumb_clicked(self, value: str) -> None:
        """Handle breadcrumb item click."""
        callback = self.on_breadcrumb_clicked
        if callable(callback):
            try:
                callback(value)
            except Exception:
                pass

