# -*- coding: utf-8 -*-
"""
Custom Tkinter widgets for the Orlando Toolkit UI.
Reusable UI components and specialized controls.
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


class Tooltip:
    """Lightweight tooltip helper for ttk widgets.

    Shows a small label near the mouse pointer on hover. Safe across platforms
    and themes, avoids complex dependencies. Use as:

        Tooltip(widget, text="Your text")

    The instance keeps itself alive by holding references on the target widget.
    """

    def __init__(self, widget: tk.Widget, text: str = "", *, delay_ms: int = 1000) -> None:
        self.widget = widget
        self.text = text
        self._tip_window: tk.Toplevel | None = None
        self._delay_ms: int = max(0, int(delay_ms))
        self._after_id: str | None = None
        try:
            self.widget.bind("<Enter>", self._on_enter, add="+")
            self.widget.bind("<Leave>", self._on_leave, add="+")
            self.widget.bind("<Motion>", self._on_motion, add="+")
        except Exception:
            pass

    def _on_enter(self, _event: tk.Event) -> None:
        # Schedule delayed show
        try:
            self._cancel_scheduled()
            self._after_id = self.widget.after(self._delay_ms, self._show)
        except Exception:
            self._show()

    def _on_leave(self, _event: tk.Event) -> None:
        self._cancel_scheduled()
        self._hide()

    def _on_motion(self, _event: tk.Event) -> None:
        # Move tooltip with the cursor when visible
        if self._tip_window is not None:
            try:
                x = self.widget.winfo_pointerx() + 12
                y = self.widget.winfo_pointery() + 12
                self._tip_window.geometry(f"+{x}+{y}")
            except Exception:
                pass

    def _show(self) -> None:
        if self._tip_window is not None or not self.text:
            return
        self._cancel_scheduled()
        try:
            self._tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_attributes("-topmost", True)
            # Place near mouse pointer
            x = self.widget.winfo_pointerx() + 12
            y = self.widget.winfo_pointery() + 12
            tw.geometry(f"+{x}+{y}")

            # Style-safe tooltip using ttk
            frm = ttk.Frame(tw, padding=(6, 3))
            frm.pack(fill="both", expand=True)
            lbl = ttk.Label(frm, text=self.text)
            lbl.pack()
        except Exception:
            # Best-effort: on any failure, ensure window is cleaned
            self._hide()

    def _hide(self) -> None:
        try:
            if self._tip_window is not None:
                self._tip_window.destroy()
        except Exception:
            pass
        finally:
            self._tip_window = None

    def _cancel_scheduled(self) -> None:
        try:
            if self._after_id is not None:
                self.widget.after_cancel(self._after_id)
        except Exception:
            pass
        finally:
            self._after_id = None


class ToggledFrame(tk.Frame):
    """A collapsible container that can show or hide its content."""

    def __init__(self, parent, text: str = "", *args, **options):
        super().__init__(parent, *args, **options)

        self.text = text
        self.columnconfigure(1, weight=1)

        self.toggle_button = ttk.Checkbutton(self, width=2, text="+", command=self.toggle, style="Toolbutton")
        self.toggle_button.grid(row=0, column=0, sticky="ns")
        self.title_label = ttk.Label(self, text=text)
        self.title_label.grid(row=0, column=1, sticky="ew")

        self.sub_frame = tk.Frame(self)
        self.sub_frame.grid(row=1, column=1, sticky="nsew")
        self.sub_frame.grid_remove()  # Start folded

        self.toggle_button.invoke()  # Start folded

    def toggle(self):
        if self.sub_frame.winfo_viewable():
            self.sub_frame.grid_remove()
            self.toggle_button.configure(text="+")
        else:
            self.sub_frame.grid()
            self.toggle_button.configure(text="-")


class Thumbnail(tk.Frame):
    """A widget that displays an image thumbnail and its filename."""

    def __init__(self, parent, image_path: str, filename: str, size: tuple[int, int] = (150, 150)):
        super().__init__(parent, borderwidth=1, relief="solid")
        self.image_path = image_path
        self.filename = filename
        self.size = size
        self.selected = False

        self.image_label = ttk.Label(self)
        self.image_label.pack()

        self.label = ttk.Label(self, text=filename, wraplength=size[0])
        self.label.pack(fill="x", padx=5, pady=5)

        self.photo_image: ImageTk.PhotoImage | None = None
        self.load_image()

    def load_image(self):
        try:
            with Image.open(self.image_path) as img:
                img.thumbnail(self.size)
                self.photo_image = ImageTk.PhotoImage(img)
                self.image_label.config(image=self.photo_image)
        except Exception as e:
            # Display placeholder on failure
            self.image_label.config(text=f"Error\n{e}", relief="solid", width=20, height=10)

    # --- Selection helpers -------------------------------------------------

    def select(self):
        self.selected = True
        self.config(relief="sunken", bg="lightblue")
        self.label.config(bg="lightblue")

    def deselect(self):
        self.selected = False
        self.config(relief="solid", bg="")
        self.label.config(bg="")

    def toggle_selection(self) -> bool:
        if self.selected:
            self.deselect()
        else:
            self.select()
        return self.selected 