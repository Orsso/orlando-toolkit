from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Tuple


class ExpandDepthPrompt(tk.Toplevel):
    """Modal prompt asking whether to expand depth after creating a deeper section.

    Returns a tuple (expand: bool, dont_ask_again: bool) via show().
    """

    def __init__(self, parent: tk.Widget, *, new_level: int, current_depth: int, target_depth: int) -> None:
        super().__init__(parent)
        self.title("Expand depth?")
        self.transient(parent)
        self.resizable(False, False)
        self.grab_set()

        self._expand = False
        self._cancelled = False
        self._dont_ask = tk.BooleanVar(value=False)

        # Content
        frm = ttk.Frame(self, padding=(12, 12, 12, 12))
        frm.grid(sticky="nsew")

        # Message: explicit and informative
        msg = (
            "You just created a section at level {nl}. The current display depth is {cd}.\n\n"
            "Notes:\n"
            "- At the current depth, content moved inside this section (level {nlp1}) may be hidden by depth filtering.\n"
            "- Keeping the current depth is safe but the section's contents might not appear until you increase depth.\n\n"
            "Would you like to expand the display depth to level {td} now so the new section and its immediate contents remain visible?"
        ).format(nl=int(new_level), cd=int(current_depth), nlp1=int(new_level) + 1, td=int(target_depth))

        lbl = ttk.Label(frm, text=msg, justify="left", wraplength=480)
        lbl.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        # Don't ask again
        chk = ttk.Checkbutton(frm, text="Don't ask again for this session", variable=self._dont_ask)
        chk.grid(row=1, column=0, columnspan=3, sticky="w")

        # Buttons
        btn_expand = ttk.Button(frm, text="Expand to level {td}".format(td=int(target_depth)), command=self._on_expand)
        btn_keep = ttk.Button(frm, text="Keep current depth", command=self._on_keep)
        btn_cancel = ttk.Button(frm, text="Cancel", command=self._on_cancel)
        btn_expand.grid(row=2, column=0, sticky="w", pady=(10, 0))
        btn_keep.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(10, 0))
        btn_cancel.grid(row=2, column=2, sticky="w", padx=(8, 0), pady=(10, 0))

        # Enter/Escape bindings
        self.bind("<Return>", lambda _e: self._on_expand())
        self.bind("<Escape>", lambda _e: self._on_cancel())

        # Center relative to parent
        try:
            self.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w = self.winfo_width()
            h = self.winfo_height()
            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 3)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _on_expand(self) -> None:
        self._expand = True
        self.destroy()

    def _on_keep(self) -> None:
        self._expand = False
        self.destroy()

    def _on_cancel(self) -> None:
        self._expand = False
        self._cancelled = True
        self.destroy()

    def show(self) -> Tuple[bool, bool, bool]:
        self.wait_window(self)
        return (bool(self._expand), bool(self._dont_ask.get()), bool(self._cancelled))


