from __future__ import annotations

"""A compact vertical marker bar for indicating positions along a scrollable view.

This widget is purely presentational. It renders:
- A light viewport band representing the currently visible portion (first..last)
- Horizontal ticks for search and filter markers at normalized positions [0.0, 1.0]

Public API:
- set_markers(search_positions: list[float], filter_positions: list[float]) -> None
- set_viewport(first: float, last: float) -> None

No I/O, no controller/service imports.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Callable


class ScrollMarkerBar(ttk.Frame):
    """A thin vertical bar that draws normalized markers and viewport band."""

    def __init__(self, master: "tk.Widget", width: int = 12, *, on_jump: Optional[Callable[[float], None]] = None, on_set_viewport: Optional[Callable[[float], None]] = None) -> None:
        super().__init__(master)
        self._canvas = tk.Canvas(self, width=width, highlightthickness=0, bd=0)
        self._canvas.grid(row=0, column=0, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)

        # State
        self._search_positions: List[float] = []
        self._filter_positions: List[float] = []
        self._style_markers: dict[str, tuple[List[float], str]] = {}  # style_name -> (positions, color)
        self._viewport_first: Optional[float] = None
        self._viewport_last: Optional[float] = None
        self._on_jump: Optional[Callable[[float], None]] = on_jump
        self._on_set_viewport: Optional[Callable[[float], None]] = on_set_viewport
        self._drag_active: bool = False
        self._drag_offset: float = 0.0
        self._band_height: float = 0.0

        # Colors aligned with StructureTreeWidget markers
        self._color_search = "#0098e4"  # blue
        self._color_filter = "#F57C00"  # orange
        self._color_view = "#E6E6E6"    # light gray band

        # Redraw on resize
        self._canvas.bind("<Configure>", lambda _e: self._redraw(), add="+")
        # Click-to-jump: report normalized Y to caller
        self._canvas.bind("<Button-1>", self._on_click, add="+")
        # Drag the viewport band like a slider
        self._canvas.bind("<B1-Motion>", self._on_drag, add="+")
        self._canvas.bind("<ButtonRelease-1>", self._on_release, add="+")

    # ------------------------------------------------------------------ API
    def set_markers(self, search_positions: List[float], filter_positions: List[float]) -> None:
        try:
            self._search_positions = [float(p) for p in (search_positions or [])]
            self._filter_positions = [float(p) for p in (filter_positions or [])]
        except Exception:
            self._search_positions = []
            self._filter_positions = []
        self._redraw()

    def set_style_markers(self, style_markers: dict[str, tuple[List[float], str]]) -> None:
        """Set style markers with their colors.
        
        Parameters
        ----------
        style_markers : dict[str, tuple[List[float], str]]
            Dictionary mapping style_name -> (positions, color_hex)
        """
        try:
            self._style_markers = dict(style_markers or {})
        except Exception:
            self._style_markers = {}
        self._redraw()

    def set_viewport(self, first: float, last: float) -> None:
        try:
            self._viewport_first = float(first)
            self._viewport_last = float(last)
            try:
                self._band_height = max(0.0, self._viewport_last - self._viewport_first)
            except Exception:
                self._band_height = 0.0
        except Exception:
            self._viewport_first = None
            self._viewport_last = None
            self._band_height = 0.0
        self._redraw()

    # ---------------------------------------------------------------- Internals
    def _redraw(self) -> None:
        try:
            c = self._canvas
            c.delete("all")

            width = max(1, int(c.winfo_width()))
            height = max(1, int(c.winfo_height()))

            # Draw viewport band if available
            if (
                isinstance(self._viewport_first, float)
                and isinstance(self._viewport_last, float)
                and self._viewport_last > self._viewport_first
            ):
                y0 = max(0, min(height, int(self._viewport_first * height)))
                y1 = max(0, min(height, int(self._viewport_last * height)))
                if y1 == y0:
                    y1 = min(height, y0 + 2)
                # Filled rectangle (light gray) without outline
                c.create_rectangle(0, y0, width, y1, fill=self._color_view, outline="")

            # Helper to draw a horizontal tick line at normalized position
            def draw_tick(norm_y: float, color: str) -> None:
                try:
                    y = int(max(0.0, min(1.0, norm_y)) * height)
                    # Ensure visible at least 1px within canvas
                    y = max(0, min(height - 1, y))
                    c.create_line(1, y, width - 2, y, fill=color, width=2)
                except Exception:
                    pass

            # Draw search then filter ticks; overlapping is acceptable
            for p in self._search_positions:
                draw_tick(p, self._color_search)
            for p in self._filter_positions:
                draw_tick(p, self._color_filter)
            
            # Draw style markers with their specific colors
            for style_name, (positions, color) in self._style_markers.items():
                for p in positions:
                    draw_tick(p, color)
        except Exception:
            # Never raise from UI redraw
            pass

    def _on_click(self, event: tk.Event) -> None:
        try:
            if self._on_jump is None:
                return
            h = max(1, int(self._canvas.winfo_height()))
            y = int(getattr(event, "y", 0))
            norm = max(0.0, min(1.0, y / float(h)))
            self._on_jump(norm)
            # Initialize drag state relative to current band
            if (
                isinstance(self._viewport_first, float)
                and isinstance(self._viewport_last, float)
                and self._on_set_viewport is not None
            ):
                self._drag_active = True
                # Preserve relative position within band if clicking inside it; else center the band on click
                if self._viewport_first <= norm <= self._viewport_last and self._band_height > 0.0:
                    self._drag_offset = norm - self._viewport_first
                else:
                    self._drag_offset = self._band_height / 2.0
        except Exception:
            pass

    def _on_drag(self, event: tk.Event) -> None:
        try:
            if not self._drag_active or self._on_set_viewport is None:
                return
            if not isinstance(self._viewport_first, float) or not isinstance(self._viewport_last, float):
                return
            h = max(1, int(self._canvas.winfo_height()))
            y = int(getattr(event, "y", 0))
            norm = max(0.0, min(1.0, y / float(h)))
            band = max(0.0, self._band_height)
            # Compute new top preserving offset; clamp to [0, 1 - band]
            new_first = norm - self._drag_offset
            if band >= 1.0:
                new_first = 0.0
            else:
                new_first = max(0.0, min(1.0 - band, new_first))
            self._on_set_viewport(new_first)
        except Exception:
            pass

    def _on_release(self, _event: tk.Event) -> None:
        self._drag_active = False


