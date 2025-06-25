# -*- coding: utf-8 -*-

"""
Main entry point for launching the Orlando Toolkit application.
"""

import sys
import os
import tkinter as tk
import logging

# Add 'src' folder to sys.path to allow absolute imports
# from source code root, regardless of where the script is launched.
# This resolves ImportError issues with relative imports.
SRC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from src.logger_config import setup_logging
from src.main import OrlandoToolkit

def main():
    """
    Configure logging, main window, and launch application.
    """
    setup_logging()
    
    root = tk.Tk()
    root.title("Orlando Toolkit")
    # Desired window size
    window_width, window_height = 435, 535
    # Calculate position to center the window
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    pos_x = (screen_width // 2) - (window_width // 2)
    pos_y = (screen_height // 2) - (window_height // 2)
    root.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")

    # Application icon configuration
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_path, 'assets', 'app_icon.png')
        if os.path.exists(icon_path):
            app_icon = tk.PhotoImage(file=icon_path)
            root.iconphoto(True, app_icon)
    except Exception as e:
        print(f"Warning: Could not load icon: {e}")

    # Use modern theme if available
    try:
        from sv_ttk import set_theme
        set_theme("light")  # Changed to light theme for professional look
    except ImportError:
        print("Warning: 'sv-ttk' theme is not installed.")

    app = OrlandoToolkit(root)
    
    root.mainloop()

if __name__ == '__main__':
    main()

    logging.info("===== Application terminated =====") 