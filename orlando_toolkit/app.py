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
from copy import deepcopy

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.services import ConversionService
from orlando_toolkit.ui.metadata_tab import MetadataTab
from orlando_toolkit.ui.image_tab import ImageTab
from orlando_toolkit.ui.widgets.metadata_form import MetadataForm

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
        self.structure_tab = None  # will be StructureTab
        self.main_actions_frame: Optional[ttk.Frame] = None
        self.generation_progress: Optional[ttk.Progressbar] = None
        # Inline metadata editor shown on the post-conversion summary screen
        self.inline_metadata: Optional[MetadataForm] = None
        self.home_center: Optional[ttk.Frame] = None
        self.version_label: Optional[ttk.Label] = None

        self.create_home_screen()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------
    # Home / landing screen
    # ------------------------------------------------------------------

    def create_home_screen(self) -> None:
        """Create the initial landing screen with logo and load button."""
        self.home_frame = ttk.Frame(self.root)
        self.home_frame.pack(expand=True, fill="both", padx=20, pady=20)

        self.home_center = ttk.Frame(self.home_frame)
        self.home_center.place(relx=0.5, rely=0.5, anchor="center")

        # Logo -----------------------------------------------------------
        try:
            logo_path = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
            if logo_path.exists():
                logo_img = tk.PhotoImage(file=logo_path)
                logo_lbl = ttk.Label(self.home_center, image=logo_img)
                logo_lbl.image = logo_img  # keep reference
                logo_lbl.pack(pady=(0, 20))
        except Exception as exc:
            logger.warning("Could not load logo: %s", exc)

        ttk.Label(self.home_center, text="Orlando Toolkit", font=("Trebuchet MS", 26, "bold"), foreground="#0098e4").pack(pady=20)
        ttk.Label(self.home_center, text="DOCX to DITA converter", font=("Arial", 12), foreground="gray").pack(pady=(0, 10))

        self.load_button = ttk.Button(self.home_center, text="Load Document (.docx)", style="Accent.TButton", command=self.start_conversion_workflow)
        self.load_button.pack(pady=20, ipadx=20, ipady=10)

        self.status_label = ttk.Label(self.home_center, text="", font=("Arial", 10))
        self.status_label.pack(pady=10)

        # Attach logging→GUI bridge the first time the home screen is built
        if not hasattr(self, "_log_to_status"):
            self._log_to_status = _TkStatusHandler(self.status_label)
            fmt = logging.Formatter("%(message)s")
            self._log_to_status.setFormatter(fmt)
            # Attach to converter & service hierarchies only
            logging.getLogger("orlando_toolkit.core").addHandler(self._log_to_status)
            logging.getLogger("orlando_toolkit.core").setLevel(logging.INFO)

        self.progress_bar = ttk.Progressbar(self.home_center, mode="indeterminate")

        # Discreet version label anchored to the bottom-right of the landing area
        try:
            if self.version_label is None or not self.version_label.winfo_exists():
                self.version_label = ttk.Label(self.home_frame, text="v1.1", font=("Arial", 9), foreground="#888888")
                self.version_label.place(relx=1.0, rely=1.0, x=-8, y=-6, anchor="se")
        except Exception:
            pass

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
            # Default topic depth: split up to Heading 3
            "topic_depth": 3,
            # No default revision_number so the generated package is treated as an edition.
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
        """Handle a successful conversion by showing a summary on the home screen.

        Instead of immediately opening the main tabbed UI, we keep a compact
        landing screen with a green success summary, counts, and an inline
        metadata form. A Continue button opens the full workspace.
        """
        self.dita_context = context

        # Stop and hide any in-flight progress UI
        if self.progress_bar:
            try:
                self.progress_bar.stop()
            except Exception:
                pass
            self.progress_bar.pack_forget()
        if self.status_label:
            self.status_label.config(text="")

        # Clear the content area and build the summary UI in-place keeping the same layout
        if self.home_center and self.home_center.winfo_exists():
            for child in self.home_center.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass
        else:
            # Recreate if needed
            self.home_frame = ttk.Frame(self.root)
            self.home_frame.pack(expand=True, fill="both", padx=20, pady=20)
            self.home_center = ttk.Frame(self.home_frame)
            self.home_center.place(relx=0.5, rely=0.5, anchor="center")

        self.show_post_conversion_summary()

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

        # Place Structure first (leftmost) and select by default
        from orlando_toolkit.ui.structure_tab import StructureTab
        self.structure_tab = StructureTab(self.notebook)
        self.notebook.add(self.structure_tab, text="Structure")

        # Place Images second, Metadata third per updated UX
        self.image_tab = ImageTab(self.notebook)
        self.notebook.add(self.image_tab, text="Images")

        self.metadata_tab = MetadataTab(self.notebook)
        self.notebook.add(self.metadata_tab, text="Metadata")

        self.metadata_tab.set_metadata_change_callback(self.on_metadata_change)

        self.main_actions_frame = ttk.Frame(self.root)
        self.main_actions_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(self.main_actions_frame, text="← Back to Home", command=self.back_to_home).pack(side="left")
        ttk.Button(self.main_actions_frame, text="Generate DITA Package", style="Accent.TButton", command=self.generate_package).pack(side="right")

        # Default to Structure view
        try:
            if self.structure_tab is not None:
                self.notebook.select(self.structure_tab)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Post-conversion summary (home screen)
    # ------------------------------------------------------------------

    def show_post_conversion_summary(self) -> None:
        """Render a compact summary with results and metadata on the home screen."""
        assert self.dita_context is not None

        # Keep the exact same window size as the initial landing screen for consistency

        # Header: show a larger logo without extra titles for a cleaner summary
        try:
            logo_path = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
            if logo_path.exists():
                logo_img = tk.PhotoImage(file=logo_path)
                try:
                    h = logo_img.height()
                    # Prefer a larger logo on the summary screen; scale up when small
                    if h > 0 and h < 128:
                        # Simple 2x upscale for small logos
                        logo_img = logo_img.zoom(2, 2)
                    elif h >= 220:
                        # If excessively large, scale down moderately
                        logo_img = logo_img.subsample(2, 2)
                except Exception:
                    pass
                logo_lbl = ttk.Label(self.home_center, image=logo_img)
                logo_lbl.image = logo_img
                logo_lbl.pack(pady=(0, 12))
        except Exception:
            pass
        # Remove textual headers on the summary view for a minimalist look

        # Success summary with checkmark and separate lines
        summary = ttk.Frame(self.home_center)
        # Center the result lines horizontally under the logo
        summary.pack(pady=(10, 6))
        ok_style = {"foreground": "#2e7d32", "font": ("Arial", 11, "bold")}
        err_style = {"foreground": "#c62828", "font": ("Arial", 11, "bold")}
        num_topics = len(self.dita_context.topics) if self.dita_context.topics else 0
        num_images = len(self.dita_context.images) if self.dita_context.images else 0
        # Line 1: topics
        if num_topics > 0:
            ttk.Label(summary, text=f"✓ {num_topics} topics extracted", **ok_style).pack(anchor="center")
        else:
            ttk.Label(summary, text="✗ No topics found", **err_style).pack(anchor="center")
        # Line 2: images
        if num_images > 0:
            ttk.Label(summary, text=f"✓ {num_images} images extracted", **ok_style).pack(anchor="center")
        else:
            ttk.Label(summary, text="✗ No images found", **err_style).pack(anchor="center")

        # Inline metadata editor
        # Unified metadata form with compact styling
        metadata_frame = ttk.LabelFrame(self.home_center, text="DITA Metadata", padding=8)
        metadata_frame.pack(fill="x", pady=(4, 14))

        # Use MetadataForm directly to avoid tab-specific decorations; reduced padding
        form = MetadataForm(metadata_frame, padding=4, font_size=10, on_change=self.on_metadata_change)
        form.pack(fill="x")
        form.load_context(self.dita_context)
        self.inline_metadata = form  # store for value commit if needed

        # Footer button: Continue if anything found; else Quit
        if num_topics > 0 or num_images > 0:
            ttk.Button(self.home_center, text="Continue", style="Accent.TButton", command=self.open_main_ui_from_summary).pack(pady=16, ipadx=18, ipady=8)
        else:
            ttk.Button(self.home_center, text="Quit", command=self.on_close).pack(pady=16, ipadx=18, ipady=8)

    def _commit_inline_metadata_to_context(self) -> None:
        """Ensure inline metadata edits are persisted to the context."""
        if not self.dita_context or not self.inline_metadata:
            return
        for key, var in self.inline_metadata.entries.items():
            try:
                value = var.get()
            except Exception:
                continue
            if value is None:
                continue
            if key not in self.dita_context.metadata or self.dita_context.metadata.get(key) != value:
                self.dita_context.metadata[key] = value
        # Let dependent widgets react if needed
        try:
            self.on_metadata_change()
        except Exception:
            pass

    def open_main_ui_from_summary(self) -> None:
        """Switch from the summary to the full workspace, defaulting to Structure."""
        # Persist any in-flight edits from the inline metadata form
        self._commit_inline_metadata_to_context()

        # Clear landing UI
        if self.home_frame and self.home_frame.winfo_exists():
            try:
                self.home_frame.destroy()
            except Exception:
                pass
            self.home_frame = None
        self.inline_metadata = None

        # Show an in-window full overlay with a large hourglass icon
        self._show_loading_overlay("Loading structure…")

        # Trigger fullscreen immediately for a stable visual
        try:
            self.root.state("zoomed")
        except Exception:
            try:
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                self.root.geometry(f"{sw-40}x{sh-60}+20+20")
            except Exception:
                pass
        try:
            # Ensure the overlay is painted before heavy UI work
            try:
                self.root.update_idletasks()
            except Exception:
                pass

            # Build tabs and load data under the overlay
            self.setup_main_ui()
            if self.dita_context and self.metadata_tab and self.image_tab and self.structure_tab:
                self.metadata_tab.load_context(self.dita_context)
                self.image_tab.load_context(self.dita_context)
                self.structure_tab.load_context(self.dita_context)
            # Ensure Structure tab is selected
            try:
                if self.structure_tab is not None:
                    self.notebook.select(self.structure_tab)
            except Exception:
                pass
        finally:
            # Remove the overlay even if loading fails
            try:
                self._hide_loading_overlay()
            except Exception:
                pass

    def back_to_home(self) -> None:
        for widget in self.root.winfo_children():
            widget.destroy()
        self.dita_context = None
        self.notebook = self.metadata_tab = self.image_tab = self.main_actions_frame = None
        self.inline_metadata = None
        self.create_home_screen()

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

    def _show_progress_dialog(self, title: str, message: str):
        """Create and show a small modal-ish progress dialog. Returns (top, progressbar)."""
        top = tk.Toplevel(self.root)
        try:
            top.title(title)
        except Exception:
            pass
        try:
            top.transient(self.root)
        except Exception:
            pass
        try:
            self.root.update_idletasks()
            w, h = 300, 90
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            x = rx + (rw - w) // 2
            y = ry + (rh - h) // 2
            top.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass
        try:
            ttk.Label(top, text=message).pack(pady=10)
        except Exception:
            pass
        prog = ttk.Progressbar(top, mode="indeterminate")
        try:
            prog.pack(fill="x", padx=20, pady=10)
        except Exception:
            pass
        try:
            prog.start()
        except Exception:
            pass
        return top, prog

    def show_generation_progress(self):
        # Reuse generic progress dialog builder
        top, prog = self._show_progress_dialog("Generating package…", "Generating DITA package, please wait…")
        self.generation_progress = prog
        self._progress_dialog = top

    def _show_loading_overlay(self, message: str = "Loading…") -> None:
        """Show a simple full-window overlay with a large hourglass and message."""
        try:
            overlay = ttk.Frame(self.root)
            overlay.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
            center = ttk.Frame(overlay)
            center.place(relx=0.5, rely=0.5, anchor="center")
            try:
                ttk.Label(center, text="⌛", font=("Arial", 72)).pack()
            except Exception:
                ttk.Label(center, text="Loading", font=("Arial", 32, "bold")).pack()
            ttk.Label(center, text=message, font=("Arial", 14)).pack(pady=8)
            try:
                overlay.lift()
            except Exception:
                pass
            self._loading_overlay = overlay  # type: ignore[attr-defined]
        except Exception:
            self._loading_overlay = None  # type: ignore[attr-defined]

    def _hide_loading_overlay(self) -> None:
        try:
            overlay = getattr(self, "_loading_overlay", None)
            if overlay is not None:
                overlay.destroy()
        finally:
            try:
                self._loading_overlay = None  # type: ignore[attr-defined]
            except Exception:
                pass

    def run_generation_thread(self, save_path: str):
        try:
            # Build an up-to-date context snapshot for export. We work on a
            # background thread, so heavy deepcopy does not block the UI.
            if self.structure_tab and getattr(self.structure_tab, "context", None):
                ctx_export = deepcopy(self.structure_tab.context)
                # Preserve latest metadata (may have been edited in other tabs)
                if self.dita_context:
                    # Keep Structure tab's chosen depth from being overwritten by base context
                    # Prefer controller's max_depth if available; else metadata
                    depth_from_structure = None
                    try:
                        depth_from_structure = getattr(self.structure_tab, "max_depth", None)
                    except Exception:
                        depth_from_structure = None
                    if depth_from_structure is None:
                        depth_from_structure = ctx_export.metadata.get("topic_depth")
                    # Merge global metadata
                    ctx_export.metadata.update(self.dita_context.metadata)
                    # Restore the structure depth explicitly if known
                    if depth_from_structure is not None:
                        ctx_export.metadata["topic_depth"] = depth_from_structure
            else:
                ctx_export = deepcopy(self.dita_context)

            ctx = self.service.prepare_package(ctx_export)  # type: ignore[arg-type]
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

    # ------------------------------------------------------------------
    # Topic depth re-conversion
    # ------------------------------------------------------------------

    def on_topic_depth_change(self, new_depth: int):
        """Update metadata with new depth; no re-parse needed."""
        if self.dita_context:
            self.dita_context.metadata["topic_depth"] = new_depth
        # No further action: Structure tab already filtered in real time

    def on_metadata_change(self) -> None:
        if self.image_tab:
            self.image_tab.update_image_names()


# ----------------------------------------------------------------------
# Utility: bridge Python logging to a Tkinter label for user feedback.
# ----------------------------------------------------------------------


class _TkStatusHandler(logging.Handler):
    """Logging handler that pushes log messages to a Tkinter label."""

    def __init__(self, target_label: ttk.Label, *, level=logging.INFO):
        super().__init__(level=level)
        self._label = target_label

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        # Use .after to ensure thread-safe update from background threads.
        msg = self.format(record)
        if self._label.winfo_exists():
            self._label.after(0, lambda m=msg: self._label.config(text=m)) 