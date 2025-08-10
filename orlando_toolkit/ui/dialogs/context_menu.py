"""Context menu handler for structural operations.

This module provides a small, presentation-only helper class that builds and shows
a Tkinter context menu for structure-related actions such as Open, Merge, Rename,
and Delete. It encapsulates the menu creation, item enablement logic, and safe
callback invocation without importing or depending on any services or controllers.

Notes
-----
- This is UI/presentation-layer only.
- Validation methods are conservative and intentionally simple.
- Callbacks are optional and safely wrapped to avoid raising into the Tk mainloop.
- The menu is positioned at the pointer location using the Tk event's root coords.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk  # noqa: F401  # Imported per requirements; reserved for future extension
from tkinter import Menu
from typing import Callable, List, Optional, Dict, Any


class ContextMenuHandler:
    """Builds and displays a context (right-click) menu for structural operations.

    The handler centralizes menu construction, item validation, and safe callback
    dispatch. It is designed to be presentation-only and does not import or
    depend on domain services or controllers.

    Parameters
    ----------
    master : tk.Widget
        The parent widget that will own the context menu.
    on_open : Optional[Callable[[List[str]], None]], optional
        Callback invoked when "Open" is selected. Receives the current selection.
    on_merge : Optional[Callable[[List[str]], None]], optional
        Callback invoked when "Merge" is selected. Receives the current selection.
    on_rename : Optional[Callable[[List[str]], None]], optional
        Callback invoked when "Rename" is selected. Receives the current selection.
    on_delete : Optional[Callable[[List[str]], None]], optional
        Callback invoked when "Delete" is selected. Receives the current selection.
    """

    def __init__(
        self,
        master: "tk.Widget",
        *,
        on_open: Optional[Callable[[List[str]], None]] = None,
        on_merge: Optional[Callable[[List[str]], None]] = None,
        on_rename: Optional[Callable[[List[str]], None]] = None,
        on_delete: Optional[Callable[[List[str]], None]] = None,
    ) -> None:
        self._master = master
        self._on_open = on_open
        self._on_merge = on_merge
        self._on_rename = on_rename
        self._on_delete = on_delete

        # Track a single active menu instance to allow safe teardown.
        self._menu: Optional[Menu] = None

    def show_context_menu(self, event: "tk.Event", selected_items: List[str], context: Optional[Dict[str, Any]] = None) -> None:
        """Build and display the context menu at the event location.

        The menu contains the following items (in order): a primary action
        (either a style label for single-topic selection or "Open"), separator,
        Merge, Rename, and Delete. Each item is enabled/disabled based on the
        selection and the corresponding `can_*` validation methods. When an item
        is invoked, the associated callback is called with `selected_items`.
        Callback execution is wrapped in a try/except block to avoid exceptions
        propagating into the Tk mainloop.

        The menu is automatically torn down on focus loss or when a command is
        dispatched.

        Parameters
        ----------
        event : tk.Event
            The Tkinter event carrying `x_root` and `y_root` coordinates used
            to position the menu at the pointer location.
        selected_items : List[str]
            The current selection for which the menu is requested.
        """
        # Destroy any existing menu to avoid multiple overlapping instances.
        if self._menu is not None:
            try:
                self._menu.unpost()
            except Exception:
                # Be conservative and non-raising.
                pass
            try:
                self._menu.destroy()
            except Exception:
                pass
            self._menu = None

        menu = Menu(self._master, tearoff=False)

        # Compute enable/disable states.
        can_open = len(selected_items) == 1
        can_merge = len(selected_items) >= 2 and self.can_merge_selection(selected_items)
        can_rename = len(selected_items) == 1 and self.can_rename_selection(selected_items)
        can_delete = len(selected_items) >= 1 and self.can_delete_selection(selected_items)

        # Primary action: replace "Open" by style label for single-topic selection when available
        style_label = None
        is_topic = False
        try:
            if isinstance(context, dict):
                # Consider as topic only when not a section and a single item is selected
                is_topic = bool(context.get("is_topic", False) and can_open)
                style_label = context.get("style")
                if isinstance(style_label, str) and not style_label.strip():
                    style_label = None
        except Exception:
            style_label = None
            is_topic = False

        if is_topic and style_label:
            # Show the style label as the primary action
            menu.add_command(
                label=str(style_label),
                state=tk.NORMAL,
                command=lambda: self._execute_style_action(context),
            )
        else:
            # Fallback to default Open behavior
            menu.add_command(
                label="Open",
                state=(tk.NORMAL if can_open else tk.DISABLED),
                command=lambda: self._execute_command(self._on_open, selected_items),
            )

        # Separator
        menu.add_separator()

        # Merge
        menu.add_command(
            label="Merge",
            state=(tk.NORMAL if can_merge else tk.DISABLED),
            command=lambda: self._execute_command(self._on_merge, selected_items),
        )

        # Rename
        menu.add_command(
            label="Rename",
            state=(tk.NORMAL if can_rename else tk.DISABLED),
            command=lambda: self._execute_command(self._on_rename, selected_items),
        )

        # Delete
        menu.add_command(
            label="Delete",
            state=(tk.NORMAL if can_delete else tk.DISABLED),
            command=lambda: self._execute_command(self._on_delete, selected_items),
        )

        # Ensure we tear down the menu on focus loss.
        try:
            menu.bind("<FocusOut>", lambda _e: self._teardown_menu_safe(), add=True)
        except Exception:
            # If binding fails for any reason, do not raise.
            pass

        # Post the menu at the cursor global screen coordinates.
        try:
            x = getattr(event, "x_root", 0) or 0
            y = getattr(event, "y_root", 0) or 0
            menu.tk_popup(x, y)
        finally:
            # Release the grab to avoid blocking other interactions.
            try:
                menu.grab_release()
            except Exception:
                pass

        self._menu = menu

    # Hook for style action; injected via context dict to avoid controller coupling
    def _execute_style_action(self, context: Optional[Dict[str, Any]]) -> None:
        """Dispatch a style-click action if provided in context.

        Expected keys in context: 'on_style', 'style'.
        """
        try:
            if not isinstance(context, dict):
                return
            callback = context.get("on_style")
            style = context.get("style")
            if callable(callback) and isinstance(style, str) and style:
                try:
                    callback(style)
                except Exception:
                    pass
        finally:
            self._teardown_menu_safe()

    def can_merge_selection(self, items: List[str]) -> bool:
        """Return whether the provided selection can be merged.

        Default presentation-layer logic: allow merge when at least two unique
        items are provided.

        Parameters
        ----------
        items : List[str]
            The selection to validate.

        Returns
        -------
        bool
            True if there are at least two unique items; False otherwise.
        """
        try:
            return len(set(items)) >= 2
        except Exception:
            return False

    def can_rename_selection(self, items: List[str]) -> bool:
        """Return whether the provided selection can be renamed.

        Default presentation-layer logic: allow rename when exactly one item is
        selected.

        Parameters
        ----------
        items : List[str]
            The selection to validate.

        Returns
        -------
        bool
            True if exactly one item is selected; False otherwise.
        """
        try:
            return len(items) == 1
        except Exception:
            return False

    def can_delete_selection(self, items: List[str]) -> bool:
        """Return whether the provided selection can be deleted.

        Default presentation-layer logic: allow delete when at least one item is
        selected.

        Parameters
        ----------
        items : List[str]
            The selection to validate.

        Returns
        -------
        bool
            True if at least one item is selected; False otherwise.
        """
        try:
            return len(items) >= 1
        except Exception:
            return False

    def _execute_command(self, callback: Optional[Callable[[List[str]], None]], selected_items: List[str]) -> None:
        """Execute a command callback safely and then tear down the menu.

        This helper method first invokes the provided callback with the selected
        items using safe invocation (catching exceptions), and then tears down
        the active context menu.

        Parameters
        ----------
        callback : Optional[Callable[[List[str]], None]]
            The callback to invoke with the selected items.
        selected_items : List[str]
            The current selection to pass to the callback.
        """
        if callback is not None:
            try:
                callback(list(selected_items))
            except Exception:
                # Presentation-layer: swallow to keep UI responsive.
                pass
        self._teardown_menu_safe()

    def _teardown_menu_safe(self) -> None:
        """Safely unpost and destroy the active context menu if present.

        This is an internal helper to ensure robust teardown without raising
        into the Tk mainloop for routine issues.
        """
        if self._menu is None:
            return
        try:
            self._menu.unpost()
        except Exception:
            pass
        try:
            self._menu.destroy()
        except Exception:
            pass
        finally:
            self._menu = None