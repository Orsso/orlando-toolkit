# -*- coding: utf-8 -*-
"""Tk-based GUI front-end for Orlando Toolkit.

Main application widget providing the document conversion interface.
Exposes the :class:`OrlandoToolkit` widget, which is instantiated by ``run.py``.
"""

from __future__ import annotations

import logging
import os
import threading
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.services import ConversionService
from orlando_toolkit.ui.metadata_tab import MetadataTab
from orlando_toolkit.ui.image_tab import ImageTab

logger = logging.getLogger(__name__)

__all__ = ["OrlandoToolkit"]


class OrlandoToolkit:
    """Main application widget wrapping all Tkinter UI components."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.dita_context: Optional[DitaContext] = None
        self.service = ConversionService()

        # --- Widget references -----------------------------------------
        self.home_frame: Optional[ttk.Frame] = None
        self.progress_bar: Optional[ttk.Progressbar] = None
        self.status_label: Optional[ttk.Label] = None
        self.load_button: Optional[ttk.Button] = None
        self.notebook: Optional[ttk.Notebook] = None
        self.metadata_tab: Optional[MetadataTab] = None
        self.image_tab: Optional[ImageTab] = None
        self.main_actions_frame: Optional[ttk.Frame] = None
        self.generation_progress: Optional[ttk.Progressbar] = None

        self.create_home_screen()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------
    # Home / landing screen
    # ------------------------------------------------------------------

    def create_home_screen(self) -> None:
        """Create the initial landing screen with logo and load button."""
        self.home_frame = ttk.Frame(self.root)
        self.home_frame.pack(expand=True, fill="both", padx=20, pady=20)

        center = ttk.Frame(self.home_frame)
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Logo -----------------------------------------------------------
        try:
            logo_path = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
            if logo_path.exists():
                logo_img = tk.PhotoImage(file=logo_path)
                logo_lbl = ttk.Label(center, image=logo_img)
                logo_lbl.image = logo_img  # keep reference
                logo_lbl.pack(pady=(0, 20))
        except Exception as exc:
            logger.warning("Could not load logo: %s", exc)

        ttk.Label(center, text="Orlando Toolkit", font=("Arial", 24, "bold")).pack(pady=20)
        ttk.Label(center, text="DOCX to DITA converter", font=("Arial", 12), foreground="gray").pack(pady=(0, 10))

        self.load_button = ttk.Button(center, text="Load Document (.docx)", style="Accent.TButton", command=self.start_conversion_workflow)
        self.load_button.pack(pady=20, ipadx=20, ipady=10)

        self.status_label = ttk.Label(center, text="", font=("Arial", 10))
        self.status_label.pack(pady=10)

        self.progress_bar = ttk.Progressbar(center, mode="indeterminate")

    # ------------------------------------------------------------------
    # Conversion workflow
    # ------------------------------------------------------------------

    def start_conversion_workflow(self) -> None:
        filepath = filedialog.askopenfilename(title="Select a DOCX file", filetypes=(("Word Documents", "*.docx"), ("All files", "*.*")))
        if not filepath:
            return

        if self.load_button:
            self.load_button.config(state="disabled")
        if self.status_label:
            self.status_label.config(text="Converting document…")
        if self.progress_bar:
            self.progress_bar.pack(fill="x", expand=True, padx=20, pady=(10, 0))
            self.progress_bar.start()

        initial_metadata = {
            "manual_title": Path(filepath).stem,
            "revision_date": datetime.now().strftime("%Y-%m-%d"),
            "revision_number": "1.0",
        }

        threading.Thread(target=self.run_conversion_thread, args=(filepath, initial_metadata), daemon=True).start()

    def run_conversion_thread(self, filepath: str, metadata: dict) -> None:
        try:
            ctx = self.service.convert(filepath, metadata)
            self.root.after(0, self.on_conversion_success, ctx)
        except Exception as exc:
            logger.error("Document conversion failed", exc_info=True)
            self.root.after(0, self.on_conversion_failure, exc)

    # ------------------------------------------------------------------
    # Conversion callbacks
    # ------------------------------------------------------------------

    def on_conversion_success(self, context: DitaContext) -> None:
        self.dita_context = context
        if self.home_frame:
            self.home_frame.destroy()
        self.setup_main_ui()
        if self.metadata_tab and self.image_tab:
            self.metadata_tab.load_context(context)
            self.image_tab.load_context(context)

    def on_conversion_failure(self, error: Exception) -> None:
        if self.progress_bar:
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
        if self.status_label:
            self.status_label.config(text="Conversion failed. Please try again.")
        if self.load_button:
            self.load_button.config(state="normal")
        messagebox.showerror("Conversion Error", f"Document processing failed:\n\n{error}")

    # ------------------------------------------------------------------
    # Main UI after conversion
    # ------------------------------------------------------------------

    def setup_main_ui(self) -> None:
        tabs_frame = ttk.Frame(self.root)
        tabs_frame.pack(expand=True, fill="both", padx=10, pady=(10, 0))

        self.notebook = ttk.Notebook(tabs_frame)
        self.notebook.pack(expand=True, fill="both")

        self.metadata_tab = MetadataTab(self.notebook)
        self.notebook.add(self.metadata_tab, text="Metadata")

        self.image_tab = ImageTab(self.notebook)
        self.notebook.add(self.image_tab, text="Images")

        self.metadata_tab.set_metadata_change_callback(self.on_metadata_change)

        self.main_actions_frame = ttk.Frame(self.root)
        self.main_actions_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(self.main_actions_frame, text="← Back to Home", command=self.back_to_home).pack(side="left")
        ttk.Button(self.main_actions_frame, text="Generate DITA Package", style="Accent.TButton", command=self.generate_package).pack(side="right")

    def back_to_home(self) -> None:
        for widget in self.root.winfo_children():
            widget.destroy()
        self.dita_context = None
        self.notebook = self.metadata_tab = self.image_tab = self.main_actions_frame = None
        self.create_home_screen()

    def on_metadata_change(self) -> None:
        if self.image_tab:
            self.image_tab.update_image_names()

    # ------------------------------------------------------------------
    # Package generation
    # ------------------------------------------------------------------

    def generate_package(self) -> None:
        if not self.dita_context:
            messagebox.showerror("Error", "No DITA context is loaded.")
            return

        manual_code = (self.dita_context.metadata.get("manual_code") or "dita_project") if self.dita_context else "dita_project"
        save_path = filedialog.asksaveasfilename(
            title="Save DITA archive",
            defaultextension=".zip",
            filetypes=(("ZIP", "*.zip"),),
            initialfile=f"{manual_code}.zip",
        )
        if not save_path:
            return

        self.show_generation_progress()
        threading.Thread(target=self.run_generation_thread, args=(save_path,), daemon=True).start()

    def show_generation_progress(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Generating package…")
        dlg.geometry("300x90")
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(dlg, text="Generating DITA package, please wait…").pack(pady=10)
        prog = ttk.Progressbar(dlg, mode="indeterminate")
        prog.pack(fill="x", padx=20, pady=10)
        prog.start()
        self.generation_progress = prog
        self._progress_dialog = dlg

    def run_generation_thread(self, save_path: str):
        try:
            ctx = self.service.prepare_package(self.dita_context)  # type: ignore[arg-type]
            self.service.write_package(ctx, save_path)
            self.root.after(0, self.on_generation_success, save_path)
        except Exception as exc:
            logger.error("Package generation failed", exc_info=True)
            self.root.after(0, self.on_generation_failure, exc)

    def on_generation_success(self, save_path: str):
        if self.generation_progress:
            self.generation_progress.stop()
            self._progress_dialog.destroy()
        messagebox.showinfo("Success", f"Archive written to\n{save_path}")

    def on_generation_failure(self, error: Exception):
        if self.generation_progress:
            self.generation_progress.stop()
            self._progress_dialog.destroy()
        messagebox.showerror("Generation error", str(error))

    # ------------------------------------------------------------------
    # Exit handling
    # ------------------------------------------------------------------

    def on_close(self):
        if messagebox.askokcancel("Quit", "Really quit?"):
            self.root.destroy() 