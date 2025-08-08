from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from orlando_toolkit.ui.custom_widgets import Tooltip
from typing import Callable, Optional
from typing import Literal


class ToolbarWidget(ttk.Frame):
    """A compact toolbar widget providing move controls for structural editing.

    This presentation-only widget encapsulates four buttons: Up, Down, Promote, and Demote.
    It delegates all actions to an optional callback without performing any business logic.

    Parameters
    ----------
    master : tk.Widget
        Parent widget.
    on_move : Optional[Callable[[Literal["up", "down", "promote", "demote"]], None]], optional
        Callback invoked when a button is pressed, receiving the direction literal.
        If not provided, button presses are no-ops (beyond local state handling).

    Notes
    -----
    - All callbacks are wrapped in try/except to prevent exceptions from propagating
      into the Tkinter mainloop.
    - The widget provides methods to enable/disable all buttons together and to set
      per-button enabled states individually.
    """

    def __init__(
        self,
        master: "tk.Widget",
        *,
        on_move: Optional[
            Callable[[Literal["up", "down", "promote", "demote"]], None]
        ] = None,
    ) -> None:
        super().__init__(master)
        self._on_move = on_move

        # Create buttons with compact pictograms (arrows) instead of text labels.
        self._btn_up = ttk.Button(self, text="↑", width=3, command=self._make_handler("up"))
        self._btn_down = ttk.Button(self, text="↓", width=3, command=self._make_handler("down"))
        # Promote = move left (outdent), Demote = move right (indent)
        self._btn_promote = ttk.Button(self, text="←", width=3, command=self._make_handler("promote"))
        self._btn_demote = ttk.Button(self, text="→", width=3, command=self._make_handler("demote"))

        # Hover tooltips
        try:
            Tooltip(self._btn_up, "Move up")
            Tooltip(self._btn_down, "Move down")
            Tooltip(self._btn_promote, "Promote (move left)")
            Tooltip(self._btn_demote, "Demote (move right)")
        except Exception:
            pass

        # Compact row layout.
        self._btn_up.grid(row=0, column=0, padx=(0, 4), pady=2)
        self._btn_down.grid(row=0, column=1, padx=(0, 4), pady=2)
        self._btn_promote.grid(row=0, column=2, padx=(0, 4), pady=2)
        self._btn_demote.grid(row=0, column=3, padx=(0, 0), pady=2)

        # Prevent column expansion for compactness.
        for idx in range(4):
            self.grid_columnconfigure(idx, weight=0)
        self.grid_rowconfigure(0, weight=0)

    def _make_handler(self, direction: Literal["up", "down", "promote", "demote"]) -> Callable[[], None]:
        """Create a safe event handler that invokes the on_move callback if provided."""
        def _handler() -> None:
            if self._on_move is None:
                return
            try:
                self._on_move(direction)
            except Exception:
                # Intentionally swallow exceptions to avoid raising into the Tk mainloop.
                # No logging or I/O per requirements.
                pass

        return _handler

    def enable_buttons(self, enabled: bool) -> None:
        """Enable or disable all toolbar buttons at once.

        Parameters
        ----------
        enabled : bool
            True to enable all buttons; False to disable all of them.

        Notes
        -----
        Safe to call regardless of the widget realization state.
        """
        state_value = "normal" if enabled else "disabled"
        for btn in (self._btn_up, self._btn_down, self._btn_promote, self._btn_demote):
            try:
                btn.configure(state=state_value)
            except Exception:
                # Be resilient to calls made before full realization or theme peculiarities.
                pass

    def set_button_states(self, up: bool, down: bool, promote: bool, demote: bool) -> None:
        """Set per-button enabled/disabled states.

        Parameters
        ----------
        up : bool
            Enable state for the Up button.
        down : bool
            Enable state for the Down button.
        promote : bool
            Enable state for the Promote button.
        demote : bool
            Enable state for the Demote button.

        Notes
        -----
        - This method does not perform any business logic or context checks.
        - It is safe to call even if the widget has not been fully realized; any internal
          Tk exceptions are caught and ignored to maintain UI stability.
        """
        mapping = (
            (self._btn_up, up),
            (self._btn_down, down),
            (self._btn_promote, promote),
            (self._btn_demote, demote),
        )
        for btn, flag in mapping:
            state_value = "normal" if flag else "disabled"
            try:
                btn.configure(state=state_value)
            except Exception:
                # Swallow exceptions to avoid propagating into Tk mainloop.
                pass