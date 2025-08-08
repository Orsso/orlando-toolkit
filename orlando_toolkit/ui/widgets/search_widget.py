from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from typing import Literal


class SearchWidget(ttk.Frame):
    """A reusable Tkinter search widget with navigation controls.

    This widget encapsulates a search entry field with optional clear button and
    "Prev"/"Next" navigation buttons. It exposes callback hooks for responding to
    search term changes and navigation requests, while keeping a conservative and
    robust behavior suitable for embedding in various UI contexts.

    Parameters
    ----------
    master : tk.Widget
        Parent Tkinter widget.
    on_term_changed : Optional[Callable[[str], None]], optional
        Callback invoked when the search term changes. Receives the current term
        as a string. The widget debounces identical repeated values within the same
        event loop iteration to avoid redundant calls.
    on_navigate : Optional[Callable[[Literal["prev","next"]], None]], optional
        Callback invoked when navigation is requested, either by clicking the
        "Prev"/"Next" buttons or by pressing Return/Shift+Return in the entry. The
        callback receives either "prev" or "next".

    Notes
    -----
    - The widget maintains its own internal state using a ``tk.StringVar`` that
      is synchronized with the entry widget.
    - Keyboard bindings:
        * Return / Enter: triggers ``on_navigate("next")`` if provided.
        * Shift+Return: triggers ``on_navigate("prev")`` if provided.
        * Escape: clears the term and triggers ``on_term_changed("")`` if provided.
    - All callbacks are invoked inside try/except blocks to avoid raising into
      the Tkinter mainloop.
    - The clear button (×) clears the term when pressed.
    """

    def __init__(
        self,
        master: "tk.Widget",
        *,
        on_term_changed: Optional[Callable[[str], None]] = None,
        on_navigate: Optional[Callable[[Literal["prev", "next"]], None]] = None,
        entry_width: Optional[int] = None,
    ) -> None:
        super().__init__(master)

        self._on_term_changed = on_term_changed
        self._on_navigate = on_navigate

        # Internal state
        self._term_var = tk.StringVar(value="")
        self._last_notified_term: Optional[str] = None

        # Layout: Entry | Clear | Prev | Next
        self.columnconfigure(0, weight=1)

        entry_kwargs = {"textvariable": self._term_var}
        if isinstance(entry_width, int) and entry_width > 0:
            entry_kwargs["width"] = entry_width
        self._entry = ttk.Entry(self, **entry_kwargs)
        self._entry.grid(row=0, column=0, padx=(0, 4), pady=0, sticky="w")

        # Optional clear button (×)
        self._clear_btn = ttk.Button(self, text="×", width=2, command=self._on_clear_clicked)
        self._clear_btn.grid(row=0, column=1, padx=(0, 4), pady=0, sticky="nsew")

        # Navigation buttons (pictograms)
        self._prev_btn = ttk.Button(self, text="◀", width=3, command=lambda: self.navigate_results("prev"))
        self._prev_btn.grid(row=0, column=2, padx=(0, 4), pady=0, sticky="nsew")

        self._next_btn = ttk.Button(self, text="▶", width=3, command=lambda: self.navigate_results("next"))
        self._next_btn.grid(row=0, column=3, padx=0, pady=0, sticky="nsew")

        # Optional hover hints
        try:
            from orlando_toolkit.ui.custom_widgets import Tooltip
            Tooltip(self._prev_btn, "Previous match")
            Tooltip(self._next_btn, "Next match")
        except Exception:
            pass

        # Bindings
        # Use variable trace to catch programmatic and user edits
        self._term_var.trace_add("write", self._on_term_var_changed)
        # Key bindings for entry-specific interactions
        self._entry.bind("<KeyRelease>", self._on_key_released, add="+")
        self._entry.bind("<Return>", self._on_return, add="+")
        self._entry.bind("<KP_Enter>", self._on_return, add="+")
        self._entry.bind("<Shift-Return>", self._on_shift_return, add="+")
        self._entry.bind("<Shift-KP_Enter>", self._on_shift_return, add="+")
        self._entry.bind("<Escape>", self._on_escape, add="+")

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def set_search_term(self, term: str) -> None:
        """Set the current search term.

        Parameters
        ----------
        term : str
            The search term to populate into the entry and internal variable.

        Notes
        -----
        This method updates the underlying ``StringVar``. The ``on_term_changed``
        callback may be invoked as a result of this update, but redundant notifications
        for identical values within the same loop are suppressed.
        """
        try:
            if term is None:
                term = ""
        except Exception:
            # Be conservative; ensure term remains a string
            term = ""
        self._term_var.set(term)

    def get_search_term(self) -> str:
        """Get the current search term.

        Returns
        -------
        str
            The current text contained in the search entry.
        """
        try:
            return self._term_var.get()
        except Exception:
            # Robust fallback
            return ""

    def navigate_results(self, direction: Literal["prev", "next"]) -> None:
        """Request navigation in the specified direction.

        Parameters
        ----------
        direction : {"prev", "next"}
            The direction in which to navigate search results.

        Notes
        -----
        If an ``on_navigate`` callback was provided, it is invoked with the
        given direction. Any exceptions raised by the callback are caught and
        suppressed to protect the Tkinter mainloop.
        """
        if self._on_navigate is None:
            return
        try:
            if direction in ("prev", "next"):
                self._on_navigate(direction)  # type: ignore[arg-type]
        except Exception:
            # Suppress exceptions to keep UI stable
            pass

    def focus_entry(self) -> None:
        """Give focus to the search entry."""
        try:
            self._entry.focus_set()
            # Place cursor at end for convenience
            self._entry.icursor("end")
        except Exception:
            # Be conservative; no raising
            pass

    # ---------------------------------------------------------------------
    # Internal helpers and handlers
    # ---------------------------------------------------------------------
    def _maybe_notify_term_changed(self) -> None:
        """Notify term changed callback with light debouncing."""
        if self._on_term_changed is None:
            return
        term = self.get_search_term()
        # Light debounce: ignore identical repeated values within same run loop
        if term == self._last_notified_term:
            return
        self._last_notified_term = term
        try:
            self._on_term_changed(term)
        except Exception:
            # Suppress exceptions to keep UI stable
            pass

    def _on_term_var_changed(self, *args) -> None:
        # Variable changes (programmatic or user typing)
        self._maybe_notify_term_changed()

    def _on_key_released(self, event: tk.Event) -> None:
        # Extra safeguard: treat key releases as opportunities to notify.
        # The variable trace will typically cover this already, but this helps
        # ensure responsiveness across platforms and input methods.
        self._maybe_notify_term_changed()

    def _on_return(self, event: tk.Event) -> str:
        # Enter/Return navigates next
        self.navigate_results("next")
        return "break"  # Prevent default beep/focus traversal

    def _on_shift_return(self, event: tk.Event) -> str:
        # Shift+Enter navigates prev
        self.navigate_results("prev")
        return "break"

    def _on_escape(self, event: tk.Event) -> str:
        # Escape clears term and notifies empty term
        self.set_search_term("")
        # _maybe_notify_term_changed is invoked by trace; ensure empty is sent even if already empty
        # Force a notification if identical by resetting last notified snapshot
        self._last_notified_term = None
        self._maybe_notify_term_changed()
        return "break"

    def _on_clear_clicked(self) -> None:
        # Clear button action
        self.set_search_term("")
        # Force notification similar to Escape behavior
        self._last_notified_term = None
        self._maybe_notify_term_changed()