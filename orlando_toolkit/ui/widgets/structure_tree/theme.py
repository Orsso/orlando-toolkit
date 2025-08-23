from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont


def init_tree_style(master: tk.Widget) -> str:
    """Create and return a dedicated Treeview style name with stable selection colors."""
    try:
        style = ttk.Style(master)
        style_name = "Orlando.Treeview"
        default_bg = style.lookup("Treeview", "fieldbackground") or style.lookup("Treeview", "background") or ""
        try:
            setattr(master, "_style", style)
            setattr(master, "_style_name", style_name)
            setattr(master, "_default_row_bg", default_bg)
        except Exception:
            pass
        style.map(
            style_name,
            background=[('selected', default_bg), ('!focus selected', default_bg)],
            foreground=[('selected', '#0098e4'), ('!focus selected', '#0098e4')],
        )
        return style_name
    except Exception:
        return "Treeview"


def configure_tags_and_fonts(widget: object) -> None:
    """Configure Treeview tags and derived fonts for section/selection visuals."""
    try:
        tree = getattr(widget, "_tree", None)
        if tree is None:
            return
        # Ensure tags exist
        tree.tag_configure("search-match")
        tree.tag_configure("filter-match")
        tree.tag_configure("selected-row", background="")

        # Build fonts
        base_font = None
        try:
            base_font = tkfont.nametofont("TkDefaultFont")
        except Exception:
            base_font = None
        if base_font is not None:
            try:
                base_size = int(tkfont.Font(widget, font=base_font).cget("size"))
            except Exception:
                base_size = 9
            font_section = tkfont.Font(widget, font=base_font)
            try:
                font_section.configure(weight="bold", size=base_size + 2)
            except Exception:
                font_section.configure(weight="bold")
            tree.tag_configure("section", font=font_section)

            font_selected = tkfont.Font(widget, font=base_font)
            try:
                font_selected.configure(size=base_size + 4)
            except Exception:
                font_selected.configure()
            tree.tag_configure("selected-row", font=font_selected, foreground="#0098e4")

            font_selected_highlight = tkfont.Font(widget, font=base_font)
            try:
                font_selected_highlight.configure(size=base_size + 4, underline=1)
            except Exception:
                font_selected_highlight.configure(underline=1)
            tree.tag_configure("selected-highlight", font=font_selected_highlight, foreground="#0098e4")

            try:
                setattr(widget, "_font_section", font_section)
                setattr(widget, "_font_selected", font_selected)
                setattr(widget, "_font_selected_highlight", font_selected_highlight)
            except Exception:
                pass
        else:
            tree.tag_configure("section", font=("", 11, "bold"))
            tree.tag_configure("selected-row", font=("", 13), foreground="#0098e4")
            tree.tag_configure("selected-highlight", font=("", 13, "underline"), foreground="#0098e4")
    except Exception:
        pass


