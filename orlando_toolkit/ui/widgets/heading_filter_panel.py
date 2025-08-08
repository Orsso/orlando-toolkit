from __future__ import annotations

from typing import Callable, Dict, List, Optional

import tkinter as tk
from tkinter import ttk


__all__ = ["HeadingFilterPanel"]


class HeadingFilterPanel(ttk.Frame):
    """Non-modal panel to manage heading style filters grouped by level.

    Public API:
    - set_data(headings_count, occurrences_by_style, style_levels, current_exclusions)
    - update_status(text)

    Callbacks:
    - on_close(): called when the Close button is clicked
    - on_apply(exclusions: Dict[str, bool]): called when Apply is clicked
    - on_select_style(style: str): called when a style label is clicked
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        on_close: Optional[Callable[[], None]] = None,
        on_apply: Optional[Callable[[Dict[str, bool]], None]] = None,
        on_select_style: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)

        self.on_close = on_close
        self.on_apply = on_apply
        self.on_select_style = on_select_style

        # Data state
        self._headings_count: Dict[str, int] = {}
        self._occurrences: Dict[str, List[Dict[str, str]]] = {}
        self._style_levels: Dict[str, Optional[int]] = {}
        self._exclusions: Dict[str, bool] = {}
        self._vars_by_style: Dict[str, tk.BooleanVar] = {}

        # Layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Header row with actions
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="Heading Filter", style="HeadingFilter.Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        actions = ttk.Frame(header)
        actions.grid(row=0, column=1, sticky="e")
        self._btn_reset = ttk.Button(actions, text="Reset", command=self._on_reset)
        self._btn_reset.grid(row=0, column=0, padx=(0, 6))
        self._btn_apply = ttk.Button(actions, text="Apply", command=self._on_apply)
        self._btn_apply.grid(row=0, column=1, padx=(0, 6))
        self._btn_close = ttk.Button(actions, text="Close", command=self._on_close)
        self._btn_close.grid(row=0, column=2)

        # Status label (warnings/info)
        self._status_var = tk.StringVar(value="")
        self._status = ttk.Label(self, textvariable=self._status_var)
        self._status.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 4))

        # Notebook to group by levels
        self._notebook = ttk.Notebook(self)
        self._notebook.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 6))

        # Internal per-tab widgets: level -> (canvas, inner_frame)
        self._level_frames: Dict[str, ttk.Frame] = {}
        self._level_canvases: Dict[str, tk.Canvas] = {}
        self._level_inners: Dict[str, ttk.Frame] = {}

    # --- Public API ---

    def set_data(
        self,
        headings_count: Dict[str, int],
        occurrences_by_style: Dict[str, List[Dict[str, str]]],
        style_levels: Dict[str, Optional[int]],
        current_exclusions: Dict[str, bool],
    ) -> None:
        self._headings_count = dict(headings_count or {})
        self._occurrences = dict(occurrences_by_style or {})
        self._style_levels = dict(style_levels or {})
        self._exclusions = dict(current_exclusions or {})
        self._vars_by_style.clear()
        self._populate_tabs()

    def update_status(self, text: str) -> None:
        try:
            self._status_var.set(text or "")
        except Exception:
            pass

    # --- UI construction helpers ---

    def _populate_tabs(self) -> None:
        # Clear existing tabs
        try:
            for tab_id in self._notebook.tabs():
                self._notebook.forget(tab_id)
        except Exception:
            pass

        # Group styles by levels
        grouped: Dict[str, List[str]] = {}
        for style in sorted(set(self._headings_count.keys()) | set(self._occurrences.keys()) | set(self._style_levels.keys())):
            lvl = self._style_levels.get(style)
            key = f"Level {lvl}" if isinstance(lvl, int) else "Other"
            grouped.setdefault(key, []).append(style)

        # Build each tab
        for level_key in sorted(grouped.keys(), key=lambda k: (k != "Other", int(k.split(" ")[-1]) if k != "Other" else 0)):
            frame = ttk.Frame(self._notebook)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            self._notebook.add(frame, text=level_key)
            self._level_frames[level_key] = frame

            # Scrollable list area
            container = ttk.Frame(frame, borderwidth=1, relief="solid")
            container.grid(row=0, column=0, sticky="nsew")
            canvas = tk.Canvas(container, highlightthickness=0)
            vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
            inner = ttk.Frame(canvas)
            inner.bind("<Configure>", lambda e, c=canvas: c.configure(scrollregion=c.bbox("all")))
            window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

            def on_canvas_configure(event: tk.Event, c=canvas, wid=window_id):
                try:
                    c.itemconfig(wid, width=event.width)
                except Exception:
                    pass
            canvas.bind("<Configure>", on_canvas_configure)
            canvas.configure(yscrollcommand=vsb.set)

            canvas.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            container.columnconfigure(0, weight=1)
            container.rowconfigure(0, weight=1)

            # Header labels
            header = ttk.Frame(inner)
            header.grid(row=0, column=0, sticky="ew", padx=(4, 4), pady=(4, 2))
            ttk.Label(header, text="Excluded", width=10, anchor="w").grid(row=0, column=0, sticky="w")
            ttk.Label(header, text="Style", anchor="w").grid(row=0, column=1, sticky="w", padx=(12, 0))
            ttk.Label(header, text="Occurrences", width=12, anchor="e").grid(row=0, column=2, sticky="e")

            # Rows
            styles = grouped[level_key]
            for i, style in enumerate(styles, start=1):
                excluded_default = bool(self._exclusions.get(style, False))
                var = tk.BooleanVar(value=excluded_default)
                self._vars_by_style[style] = var

                chk = ttk.Checkbutton(inner, variable=var)
                lbl_style = ttk.Label(inner, text=str(style), anchor="w")
                occ = int(self._headings_count.get(style, 0))
                lbl_occ = ttk.Label(inner, text=str(occ), width=12, anchor="e")

                # Clicking style label triggers selection highlight callback
                if self.on_select_style is not None:
                    try:
                        lbl_style.bind("<Button-1>", lambda _e, s=style: self.on_select_style(s))
                    except Exception:
                        pass

                chk.grid(row=i, column=0, sticky="w", padx=(6, 0), pady=2)
                lbl_style.grid(row=i, column=1, sticky="w", padx=(12, 6), pady=2)
                lbl_occ.grid(row=i, column=2, sticky="e", padx=(6, 6), pady=2)

                inner.columnconfigure(1, weight=1)

        # Select the first tab by default
        try:
            if self._notebook.tabs():
                self._notebook.select(self._notebook.tabs()[0])
        except Exception:
            pass

    # --- Actions ---

    def _on_close(self) -> None:
        if callable(self.on_close):
            self.on_close()

    def _on_apply(self) -> None:
        # Collect exclusions and fire callback
        try:
            for style, var in self._vars_by_style.items():
                self._exclusions[style] = bool(var.get())
        except Exception:
            pass
        if callable(self.on_apply):
            self.on_apply(dict(self._exclusions))

    def _on_reset(self) -> None:
        try:
            for var in self._vars_by_style.values():
                try:
                    var.set(False)
                except Exception:
                    pass
            # Also reset our mirror map
            for k in list(self._exclusions.keys()):
                self._exclusions[k] = False
        except Exception:
            pass
        # Clear status upon reset
        self.update_status("")



