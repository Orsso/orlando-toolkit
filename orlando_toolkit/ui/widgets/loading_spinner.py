"""Reusable loading spinner widget with dynamic message support."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable


class LoadingSpinner:
    """Minimal loading spinner widget for consistent UX across the app.
    
    Features:
    - Same Unicode spinner animation as plugin installation (150ms cycle)
    - Custom title and subtitle messages
    - Dynamic message updates while running
    - Overlay positioning over any parent widget
    - YAGNI-compliant: only essential features
    """

    def __init__(
        self,
        parent: tk.Widget,
        title: str = "Loading",
        subtitle: str = "Please wait...",
        on_show: Optional[Callable[[], None]] = None,
        on_hide: Optional[Callable[[], None]] = None,
    ):
        """Initialize loading spinner.
        
        Args:
            parent: Parent widget to overlay on
            title: Main loading message
            subtitle: Secondary loading message  
            on_show: Optional callback when spinner is shown
            on_hide: Optional callback when spinner is hidden
        """
        self._parent = parent
        self._title = title
        self._subtitle = subtitle
        self._on_show = on_show
        self._on_hide = on_hide
        
        # Animation state
        self._spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_state = 0
        self._after_id: Optional[str] = None
        
        # UI components (created lazily)
        self._overlay: Optional[tk.Frame] = None
        self._spinner_label: Optional[ttk.Label] = None
        self._title_label: Optional[ttk.Label] = None
        self._subtitle_label: Optional[ttk.Label] = None
        
        self._is_visible = False

    def show(self) -> None:
        """Show the loading spinner overlay."""
        if self._is_visible:
            return
            
        try:
            self._create_overlay()
            self._is_visible = True
            self._start_animation()
            
            # Dynamic callback
            if self._on_show:
                self._on_show()
        except Exception:
            pass

    def hide(self) -> None:
        """Hide the loading spinner overlay."""
        if not self._is_visible:
            return
            
        try:
            self._stop_animation()
            self._destroy_overlay()
            self._is_visible = False
            
            # Dynamic callback
            if self._on_hide:
                self._on_hide()
        except Exception:
            pass

    def update_message(self, title: str, subtitle: Optional[str] = None) -> None:
        """Update spinner message while running.
        
        Args:
            title: New main message
            subtitle: New secondary message (optional)
        """
        self._title = title
        if subtitle is not None:
            self._subtitle = subtitle
            
        # Update UI if currently visible
        if self._is_visible:
            try:
                if self._title_label:
                    self._title_label.configure(text=self._title)
                if self._subtitle_label:
                    if subtitle is not None:
                        self._subtitle_label.configure(text=self._subtitle)
                    else:
                        # Update existing subtitle
                        self._subtitle_label.configure(text=self._subtitle)
            except Exception:
                pass
    
    def update_subtitle_only(self, subtitle: str) -> None:
        """Update only the subtitle (for status callbacks).
        
        Args:
            subtitle: New status message
        """
        self._subtitle = subtitle
        if self._is_visible and self._subtitle_label:
            try:
                self._subtitle_label.configure(text=self._subtitle)
            except Exception:
                pass

    def is_visible(self) -> bool:
        """Check if spinner is currently visible."""
        return self._is_visible

    def _create_overlay(self) -> None:
        """Create minimal spinner UI without overlay."""
        # Simple frame that packs into parent without covering everything
        self._overlay = ttk.Frame(self._parent)
        self._overlay.pack(pady=20)
        
        # Spinner animation
        self._spinner_label = ttk.Label(
            self._overlay, 
            text=self._spinner_chars[0],
            font=("Arial", 24), 
            foreground="#0078d4"
        )
        self._spinner_label.pack(pady=(0, 10))
        
        # Title message
        self._title_label = ttk.Label(
            self._overlay, 
            text=self._title, 
            font=("Segoe UI", 12), 
            foreground="#202124"
        )
        self._title_label.pack(pady=(0, 5))
        
        # Status callback area - always create for dynamic updates
        self._subtitle_label = ttk.Label(
            self._overlay, 
            text=self._subtitle if self._subtitle.strip() else "",
            font=("Segoe UI", 10), 
            foreground="#5f6368"
        )
        self._subtitle_label.pack()

    def _destroy_overlay(self) -> None:
        """Destroy spinner overlay UI."""
        if self._overlay and self._overlay.winfo_exists():
            self._overlay.destroy()
        self._overlay = None
        self._spinner_label = None
        self._title_label = None
        self._subtitle_label = None

    def _start_animation(self) -> None:
        """Start 150ms spinner animation cycle."""
        if not self._is_visible or not self._spinner_label:
            return
            
        try:
            if self._spinner_label.winfo_exists():
                self._spinner_state = (self._spinner_state + 1) % 10
                self._spinner_label.configure(text=self._spinner_chars[self._spinner_state])
                self._after_id = self._parent.after(150, self._start_animation)
        except Exception:
            pass

    def _stop_animation(self) -> None:
        """Stop spinner animation."""
        if self._after_id:
            try:
                self._parent.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None