"""Progress callback service for unified status updates across the application."""

from typing import Callable, Optional
import tkinter as tk


class ProgressService:
    """Centralized service for managing progress callbacks and status updates."""
    
    def __init__(self):
        """Initialize the progress service."""
        self._current_callback: Optional[Callable[[str], None]] = None
        
    def set_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Set the current progress callback."""
        self._current_callback = callback
        
    def update(self, message: str) -> None:
        """Send progress update if callback is available."""
        if self._current_callback:
            self._current_callback(message)
            
    def create_ui_callback(self, status_label: tk.Widget, root: tk.Tk) -> Callable[[str], None]:
        """Create thread-safe progress callback for UI updates.
        
        Args:
            status_label: The UI label widget to update
            root: The root Tkinter window for thread-safe scheduling
            
        Returns:
            Thread-safe progress callback function
        """
        def progress_callback(message: str) -> None:
            """Update status label with progress message."""
            if status_label and status_label.winfo_exists():
                # Schedule UI update on main thread
                root.after(0, lambda: status_label.config(text=message))
        return progress_callback