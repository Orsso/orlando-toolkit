from __future__ import annotations

from tkinter import ttk


def attach_expand_collapse_overlay(widget: object) -> None:
    try:
        tree = getattr(widget, "_tree", None)
        if tree is None:
            return
        overlay = ttk.Frame(tree)
        btn_expand = ttk.Button(overlay, text="+", width=2, command=widget.expand_all)
        btn_collapse = ttk.Button(overlay, text="-", width=2, command=widget.collapse_all)
        btn_expand.grid(row=0, column=0, padx=(0, 2))
        btn_collapse.grid(row=0, column=1)
        try:
            from orlando_toolkit.ui.custom_widgets import Tooltip  # local import to avoid cycles
            Tooltip(btn_expand, "Expand all")
            Tooltip(btn_collapse, "Collapse all")
        except Exception:
            pass
        overlay.place(relx=1.0, x=-4, y=2, anchor="ne")
        tree.bind("<Configure>", lambda _e: overlay.place_configure(relx=1.0, x=-4, y=2, anchor="ne"))
    except Exception:
        pass


