from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class RenameDialog:
    """Minimal reusable rename dialog with a larger default width.

    Use: value = RenameDialog.ask_string(parent, title, prompt, initialvalue)
    Returns the entered string or None if cancelled.
    """

    @staticmethod
    def ask_string(parent: tk.Widget, title: str, prompt: str, initialvalue: str = "") -> str | None:
        top = tk.Toplevel(parent)
        try:
            top.title(title)
        except Exception:
            pass
        try:
            top.transient(parent.winfo_toplevel())
        except Exception:
            pass
        try:
            top.grab_set()
        except Exception:
            pass
        try:
            top.resizable(True, False)
        except Exception:
            pass

        # Layout
        container = ttk.Frame(top, padding=(12, 10))
        container.grid(row=0, column=0, sticky="nsew")
        try:
            top.columnconfigure(0, weight=1)
            top.rowconfigure(0, weight=1)
            container.columnconfigure(0, weight=1)
        except Exception:
            pass

        lbl = ttk.Label(container, text=prompt)
        lbl.grid(row=0, column=0, sticky="w", pady=(0, 6))

        var = tk.StringVar(value=str(initialvalue or ""))
        entry = ttk.Entry(container, textvariable=var, width=60)
        entry.grid(row=1, column=0, sticky="ew")

        btns = ttk.Frame(container)
        btns.grid(row=2, column=0, sticky="e", pady=(10, 0))

        result: list[str | None] = [None]

        def _ok() -> None:
            try:
                result[0] = var.get()
            except Exception:
                result[0] = None
            try:
                top.destroy()
            except Exception:
                pass

        def _cancel() -> None:
            result[0] = None
            try:
                top.destroy()
            except Exception:
                pass

        btn_ok = ttk.Button(btns, text="OK", style="Accent.TButton", command=_ok)
        btn_cancel = ttk.Button(btns, text="Cancel", command=_cancel)
        btn_cancel.grid(row=0, column=0, padx=(0, 6))
        btn_ok.grid(row=0, column=1)

        # Key bindings
        try:
            entry.bind("<Return>", lambda _e: _ok())
            entry.bind("<Escape>", lambda _e: _cancel())
        except Exception:
            pass

        # Initial focus and selection
        try:
            entry.focus_set()
            entry.selection_range(0, tk.END)
        except Exception:
            pass

        # Default size and centering relative to parent
        try:
            top.update_idletasks()
            # Aim for a wider dialog (~520px) and compact height
            w, h = 520, max(140, top.winfo_height())
            try:
                # Center over parent toplevel
                pr = parent.winfo_toplevel()
                px, py = pr.winfo_rootx(), pr.winfo_rooty()
                pw, ph = pr.winfo_width(), pr.winfo_height()
                x = px + (pw - w) // 2
                y = py + (ph - h) // 3
            except Exception:
                # Fallback: center on screen
                sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
                x = (sw - w) // 2
                y = (sh - h) // 3
            top.geometry(f"{w}x{h}+{x}+{y}")
            try:
                top.minsize(420, 120)
            except Exception:
                pass
        except Exception:
            pass

        # Modal loop
        try:
            top.wait_window(top)
        except Exception:
            pass
        return result[0]


