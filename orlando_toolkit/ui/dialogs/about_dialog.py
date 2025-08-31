# -*- coding: utf-8 -*-
"""About dialog for Orlando Toolkit.

Kept separate from ``app.py`` to avoid bloating the main UI code. The dialog
shows a brief description, version, author, and convenient GitHub links.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import webbrowser
from pathlib import Path

from orlando_toolkit.version import get_app_version


def show_about_dialog(root: tk.Tk) -> None:
    """Display a compact, centered About dialog (single pane)."""
    top = tk.Toplevel(root)
    try:
        top.title("About Orlando Toolkit")
    except Exception:
        pass
    try:
        top.transient(root)
        top.resizable(False, False)
        top.grab_set()
    except Exception:
        pass

    # Center relative to the main window
    try:
        root.update_idletasks()
        w, h = 400, 320
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = root.winfo_width(), root.winfo_height()
        x = rx + (rw - w) // 2
        y = ry + (rh - h) // 2
        top.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass

    container = ttk.Frame(top, padding=12)
    container.pack(expand=True, fill="both")

    # Single content column
    content = ttk.Frame(container, padding=(8, 12))
    content.pack(expand=True, fill="both")

    # App icon (centered, bounded size)
    icon_img = None
    try:
        logo_path = Path(__file__).resolve().parents[3] / "assets" / "app_icon.png"
        if logo_path.exists():
            icon_img = tk.PhotoImage(file=str(logo_path))
            # Downscale large icons to keep the dialog compact
            try:
                h = icon_img.height()
                target_h = 120
                if h > target_h:
                    # Ceil division to reduce size below or equal to target
                    factor = max(2, int((h + target_h - 1) // target_h))
                    icon_img = icon_img.subsample(factor, factor)
            except Exception:
                pass
    except Exception:
        icon_img = None
    if icon_img is not None:
        lbl_icon = ttk.Label(content, image=icon_img)
        lbl_icon.image = icon_img  # keep reference
        lbl_icon.pack(pady=(0, 10), anchor="center")

    ttk.Label(content, text="Orlando Toolkit", font=("Trebuchet MS", 14, "bold")).pack(anchor="center")
    ttk.Label(content, text=get_app_version(), foreground="#555555").pack(pady=(2, 2), anchor="center")
    # Maintainer email
    email_lbl = ttk.Label(content, text="orssso@proton.me", foreground="#1a73e8", cursor="hand2")
    email_lbl.pack(anchor="center", pady=(0, 6))

    def _open(url: str) -> None:
        try:
            webbrowser.open_new(url)
        except Exception:
            pass

    email_lbl.bind("<Button-1>", lambda e: _open("mailto:orssso@proton.me"))

    ttk.Label(
        content,
        text=(
            "Open-source DITA document processor with extensible plugin architecture. "
        ),
        wraplength=360,
        justify="center",
    ).pack(pady=(4, 10), anchor="center")

    # Links section (centered buttons)
    links = ttk.Frame(content)
    links.pack(pady=(8, 4), anchor="center")

    btn_w = 16
    ttk.Button(links, text="GitHub", width=btn_w, style="Accent.TButton", command=lambda: _open("https://github.com/Orsso/orlando-toolkit")).pack(side="left", padx=(0, 8))
    ttk.Button(links, text="Report an issue", width=btn_w, command=lambda: _open("https://github.com/Orsso/orlando-toolkit/issues/new/choose")).pack(side="left")

    ttk.Label(content, text="MIT Licensed. © Orsso.", foreground="#777777").pack(pady=(12, 0), anchor="center")
    ttk.Label(container, text="Built with love in France", foreground="#777777").pack(anchor="center", pady=(2, 0))

    # Footer with Close button aligned right
    footer = ttk.Frame(container)
    footer.pack(fill="x", pady=(8, 0))
    ttk.Button(footer, text="Close", command=top.destroy).pack(side="right")


