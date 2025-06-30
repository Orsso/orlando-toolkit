from __future__ import annotations

"""Reusable dialog utilities for Orlando Toolkit UI."""

import tkinter as tk

__all__ = ["CenteredDialog"]


class CenteredDialog(tk.Toplevel):
    """A Toplevel that opens centred on *parent* and remembers its last geometry.

    Parameters
    ----------
    parent
        The parent widget (usually the main application window).
    title
        Window title.
    default_size
        Tuple ``(width, height)`` used if the dialog was never opened before.
    key
        Unique key to remember geometry across multiple openings.
    """

    _SIZE_STORE: dict[str, tuple[int, int]] = {}

    def __init__(self, parent: tk.Widget, title: str, default_size: tuple[int, int], key: str, **kwargs):
        super().__init__(parent, **kwargs)
        self.title(title)
        self._geom_key = key

        # Restore previous geometry if known
        size = CenteredDialog._SIZE_STORE.get(key)
        if size:
            w, h = size
        else:
            w, h = default_size
        parent.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        if pw <= 1 or ph <= 1:
            # fall back to screen centre
            sw, sh = parent.winfo_screenwidth(), parent.winfo_screenheight()
            px, py = (sw - w) // 2, (sh - h) // 2
        else:
            px = px + (pw - w) // 2
            py = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{px}+{py}")

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _on_close(self):
        # Save only the *size* so the dialog recentres next time.
        try:
            size_part = self.geometry().split("+")[0]  # e.g. "260x320"
            w_str, h_str = size_part.split("x")
            w, h = int(w_str), int(h_str)
        except Exception:
            w, h = self.winfo_width(), self.winfo_height()

        CenteredDialog._SIZE_STORE[self._geom_key] = (w, h)
        self.destroy() 