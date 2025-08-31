"""Universal loading spinner that works everywhere - KISS/DRY/YAGNI implementation."""

from typing import Optional, Callable, Any, Dict
import tkinter as tk
from tkinter import ttk


class UniversalSpinner:
    """One spinner widget for all loading scenarios - automatically adapts to context.
    
    KISS Principle: 
    - One widget for all use cases
    - Automatic context detection
    - Simple start()/stop() API
    
    DRY Principle:
    - Same animation code everywhere
    - Single implementation for all contexts
    - Shared styling and behavior
    
    YAGNI Principle:
    - No complex configuration options
    - No over-engineered abstractions
    - Just works everywhere without setup
    """
    
    def __init__(self, parent: tk.Widget, message: str = "Loading..."):
        """Initialize universal spinner.
        
        Args:
            parent: Any tkinter widget (Frame, Canvas, Text, etc.)
            message: Loading message to display
        """
        self._parent = parent
        self._message = message
        self._is_active = False
        
        # Spinner animation
        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._frame_index = 0
        self._after_id: Optional[str] = None
        
        # State management
        self._overlay: Optional[tk.Frame] = None
        self._spinner_label: Optional[ttk.Label] = None
        self._message_label: Optional[ttk.Label] = None
        self._original_state: Optional[str] = None
        
    def start(self) -> None:
        """Start loading animation - automatically handles all contexts."""
        if self._is_active:
            return
            
        self._is_active = True
        self._create_overlay()
        self._disable_parent()
        self._animate()
    
    def stop(self) -> None:
        """Stop loading animation and restore original state."""
        if not self._is_active:
            return
            
        self._is_active = False
        
        # Stop animation
        if self._after_id:
            try:
                self._parent.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        
        # Clean up overlay
        if self._overlay and self._overlay.winfo_exists():
            self._overlay.destroy()
        self._overlay = None
        self._spinner_label = None
        self._message_label = None
        
        # Restore parent interaction
        self._restore_parent()
    
    def update_message(self, message: str) -> None:
        """Update loading message while active."""
        self._message = message
        if self._message_label and self._message_label.winfo_exists():
            try:
                self._message_label.configure(text=message)
            except tk.TclError:
                pass
    
    def is_active(self) -> bool:
        """Check if spinner is currently active."""
        return self._is_active
    
    def _create_overlay(self) -> None:
        """Create overlay that covers parent completely."""
        if self._overlay:
            return
            
        # Create overlay frame using place() for guaranteed top Z-order
        self._overlay = tk.Frame(self._parent, bg='white', relief='flat')
        # Cover entire parent widget
        self._overlay.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        
        # Center container
        center_frame = ttk.Frame(self._overlay)
        center_frame.place(relx=0.5, rely=0.5, anchor='center')
        
        # Spinner animation
        self._spinner_label = ttk.Label(
            center_frame,
            text=self._frames[0],
            font=("Arial", 24),
            foreground="#0078d4"
        )
        self._spinner_label.pack(pady=(0, 10))
        
        # Message
        self._message_label = ttk.Label(
            center_frame,
            text=self._message,
            font=("Segoe UI", 11),
            foreground="#202124"
        )
        self._message_label.pack()
        
        # Ensure overlay is on top
        try:
            self._overlay.lift()
        except tk.TclError:
            pass
    
    def _disable_parent(self) -> None:
        """Disable parent widget to block interaction."""
        try:
            # Store original state
            if hasattr(self._parent, 'cget'):
                try:
                    self._original_state = self._parent.cget('state')
                    self._parent.configure(state='disabled')
                except tk.TclError:
                    # Parent doesn't support state - that's OK
                    pass
        except Exception:
            pass
    
    def _restore_parent(self) -> None:
        """Restore parent widget interaction."""
        try:
            if hasattr(self._parent, 'configure') and self._original_state:
                try:
                    self._parent.configure(state=self._original_state)
                except tk.TclError:
                    pass
            self._original_state = None
        except Exception:
            pass
    
    def _animate(self) -> None:
        """Animate spinner frames."""
        if not self._is_active or not self._spinner_label:
            return
        
        try:
            if self._spinner_label.winfo_exists():
                self._spinner_label.configure(text=self._frames[self._frame_index])
                self._frame_index = (self._frame_index + 1) % len(self._frames)
                self._after_id = self._parent.after(150, self._animate)
        except tk.TclError:
            # Widget was destroyed
            self._is_active = False