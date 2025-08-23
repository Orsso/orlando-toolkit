from __future__ import annotations

from typing import Callable, Optional


class DepthControlCoordinator:
    """Encapsulate depth spinbox interactions with controller and tree refresh."""

    def __init__(
        self,
        *,
        get_depth_value: Callable[[], int],
        set_depth_value: Callable[[int], None],
        controller_getter: Callable[[], object],
        on_refresh_tree: Callable[[], None],
        is_busy: Callable[[], bool],
    ) -> None:
        self._get = get_depth_value
        self._set = set_depth_value
        self._get_controller = controller_getter
        self._refresh = on_refresh_tree
        self._is_busy = is_busy

    def apply_depth(self) -> bool:
        if self._is_busy():
            return False
        ctrl = self._get_controller()
        if ctrl is None:
            return False
        try:
            val = int(self._get())
        except Exception:
            val = int(getattr(ctrl, "max_depth", 999))
        if val < 1:
            val = 1
        elif val > 999:
            val = 999
        try:
            if int(self._get()) != val:
                self._set(val)
        except Exception:
            try:
                self._set(val)
            except Exception:
                pass
        try:
            changed = bool(ctrl.handle_depth_change(val))
        except Exception:
            changed = False
        if changed:
            try:
                self._refresh()
            except Exception:
                pass
        return changed


