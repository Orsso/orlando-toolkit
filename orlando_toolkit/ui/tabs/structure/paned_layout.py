from __future__ import annotations

from typing import Callable, Optional


class PanedLayoutCoordinator:
    """Manage right pane visibility (preview/filter/none) and sash ratios.

    Parameters
    ----------
    paned : object
        ttk.PanedWindow-like object with panes(), add(), forget(), paneconfigure(), sashpos().
    right_pane : object
        Frame representing the right pane container.
    after : Callable[[int, Callable[[], None]], object]
        Tk-like scheduler to defer sash operations (widget.after).
    """

    def __init__(self, *, paned: object, right_pane: object, after: Callable[[int, Callable[[], None]], object]) -> None:
        self._paned = paned
        self._right = right_pane
        self._after = after
        self._kind: str = "preview"
        self._ratio_preview: float = 0.5
        self._ratio_filter: float = 0.5
        self._last_ratio: float = 0.5

    # -------------------------------------------------------------- Public API
    def set_kind(self, kind: str) -> None:
        """Set the active right pane kind: 'preview' | 'filter' | 'none'."""
        try:
            paned = self._paned
            right = self._right
            if kind == "none":
                try:
                    if str(right) in paned.panes():
                        paned.forget(right)
                except Exception:
                    pass
                self._kind = "none"
                return

            # Ensure right pane is present
            try:
                if str(right) not in paned.panes():
                    paned.add(right, weight=2)
                    try:
                        paned.paneconfigure(right, minsize=150)
                    except Exception:
                        pass
            except Exception:
                pass

            self._kind = ("filter" if kind == "filter" else "preview")
            try:
                # Defer sash restore to allow geometry to settle
                self._after(0, self.restore_sash)
            except Exception:
                pass
        except Exception:
            pass

    def capture_ratio(self) -> None:
        """Capture the current sash position into the active ratio variable."""
        try:
            paned = self._paned
            width = paned.winfo_width()
            if width <= 1:
                return
            pos = paned.sashpos(0)
            ratio = max(0.05, min(0.95, pos / max(1, width)))
            if self._kind == "filter":
                self._ratio_filter = ratio
            else:
                self._ratio_preview = ratio
            self._last_ratio = ratio
        except Exception:
            pass

    def restore_sash(self) -> None:
        """Restore sash position with geometry-aware timing."""
        try:
            paned = self._paned
            paned.update_idletasks()
            width = paned.winfo_width()
            
            # If width not ready, schedule single retry after geometry settling
            if width <= 1:
                self._after(100, self._restore_sash_final)
                return
                
            self._restore_sash_final()
        except Exception:
            pass
    
    def _restore_sash_final(self) -> None:
        """Final sash restoration without retry loops."""
        try:
            paned = self._paned
            width = paned.winfo_width()
            
            # If still not ready after delay, use fallback positioning
            if width <= 1:
                return
                
            ratio = self._ratio_filter if self._kind == "filter" else self._ratio_preview
            if not isinstance(ratio, float) or ratio <= 0.05 or ratio >= 0.95:
                ratio = 0.5
                
            pos = int(width * ratio)
            paned.sashpos(0, pos)
        except Exception:
            pass

    # ------------------------------------------------------------- Internals

    # --------------- Accessors (optional for external reads/shims) ----------
    @property
    def kind(self) -> str:
        return self._kind

    @property
    def ratios(self) -> tuple[float, float, float]:
        return (self._ratio_preview, self._ratio_filter, self._last_ratio)


