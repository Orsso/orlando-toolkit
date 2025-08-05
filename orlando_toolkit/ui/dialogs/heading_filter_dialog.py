import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, List


class HeadingFilterDialog:
    """Modal-like dialog to manage heading style exclusions.

    This dialog presents a scrollable list of heading styles, each with a checkbox
    to mark the style as excluded (checked) or included (unchecked). It is designed
    to be presentation-only and self-contained, without mutating external state.
    Instead, it returns a new mapping of style name to exclusion boolean.

    Enhancements:
    - Adds a secondary panel that displays occurrences for the currently selected style.
    - Occurrence rows are read-only and show "title (href)" or "title" when href is absent.
    """

    def __init__(self, master: "tk.Widget") -> None:
        """Initialize the dialog instance."""
        self._master: tk.Widget = master
        self._top: Optional[tk.Toplevel] = None

        # Data provided at show time
        self._headings_cache: Dict[str, int] = {}
        self._original_exclusions: Dict[str, bool] = {}
        self._result_exclusions: Optional[Dict[str, bool]] = None
        self._occurrences: Dict[str, List[Dict[str, str]]] = {}

        # UI state
        self._vars_by_style: Dict[str, tk.BooleanVar] = {}
        self._applied: bool = False

        # Widgets needing later reference
        self._apply_btn: Optional[ttk.Button] = None
        self._cancel_btn: Optional[ttk.Button] = None
        self._reset_btn: Optional[ttk.Button] = None

        # Scrollable list widgets (left styles list)
        self._canvas: Optional[tk.Canvas] = None
        self._scroll_frame: Optional[ttk.Frame] = None
        self._scrollbar_y: Optional[ttk.Scrollbar] = None

        # Right side occurrences widgets
        self._occ_listbox: Optional[tk.Listbox] = None
        self._occ_scroll_y: Optional[ttk.Scrollbar] = None
        self._occ_title_label: Optional[ttk.Label] = None

    def show_dialog(
        self,
        headings_cache: Dict[str, int],
        current_exclusions: Dict[str, bool],
        *,
        occurrences: Optional[Dict[str, List[Dict[str, str]]]] = None,
    ) -> Dict[str, bool]:
        """Display the dialog and return the updated exclusions mapping."""
        # Store incoming data
        self._headings_cache = dict(headings_cache or {})
        self._original_exclusions = dict(current_exclusions or {})
        self._occurrences = dict(occurrences or {})
        self._result_exclusions = None
        self._applied = False
        self._vars_by_style.clear()

        # Build window
        self._build_window()
        # Populate UI with provided data
        self._populate_styles()

        # Center and modal-like grab
        self._center_over_master()
        try:
            self._top.grab_set()  # Modal-like
        except Exception:
            pass

        # Focus and wait for window to close
        try:
            self._top.wait_window()
        except Exception:
            pass

        # Determine result: if applied, collect; otherwise return original mapping
        if self._applied:
            return self.get_exclusion_changes()
        else:
            return dict(self._original_exclusions)

    def get_exclusion_changes(self) -> Dict[str, bool]:
        """Return the latest exclusions mapping based on current checkbox states."""
        if self._result_exclusions is not None:
            return dict(self._result_exclusions)

        result: Dict[str, bool] = {}
        for style, var in self._vars_by_style.items():
            try:
                result[style] = bool(var.get())
            except Exception:
                result[style] = bool(self._original_exclusions.get(style, False))
        self._result_exclusions = dict(result)
        return result

    # -------------------------
    # Internal UI construction
    # -------------------------

    def _build_window(self) -> None:
        # Destroy any previous toplevel to keep dialog instance reusable
        if self._top is not None and self._top.winfo_exists():
            try:
                self._top.destroy()
            except Exception:
                pass

        self._top = tk.Toplevel(self._master)
        self._top.title("Heading Filter")
        self._top.transient(self._master)
        self._top.resizable(True, True)

        # Handle window close as cancel
        self._top.protocol("WM_DELETE_WINDOW", self._on_cancel_safe)

        # Global layout: content frame + buttons frame
        outer = ttk.Frame(self._top, padding=(12, 12, 12, 12))
        outer.grid(row=0, column=0, sticky="nsew")
        self._top.rowconfigure(0, weight=1)
        self._top.columnconfigure(0, weight=1)

        # Title and instructions
        title = ttk.Label(outer, text="Filter Headings", style="HeadingFilterDialog.Title.TLabel")
        title.grid(row=0, column=0, sticky="w")

        instructions = ttk.Label(
            outer,
            text=(
                "Select heading styles to exclude. Checked = Excluded, Unchecked = Included.\n"
                "Use Reset to include all. Press Enter to apply or Esc to cancel."
            ),
            wraplength=520,
            justify="left",
        )
        instructions.grid(row=1, column=0, sticky="w", pady=(4, 10))

        # Split main content into two columns: left styles, right occurrences
        content = ttk.Frame(outer)
        content.grid(row=2, column=0, sticky="nsew")
        outer.rowconfigure(2, weight=1)
        outer.columnconfigure(0, weight=1)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(1, weight=1)

        # Left header row
        header = ttk.Frame(content)
        header.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(header, text="Excluded", width=10, anchor="w").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Style", anchor="w").grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(header, text="Occurrences", width=12, anchor="e").grid(row=0, column=2, sticky="e")

        # Left scrollable area (Canvas + inner frame)
        list_container = ttk.Frame(content, borderwidth=1, relief="solid")
        list_container.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self._canvas = tk.Canvas(list_container, highlightthickness=0)
        self._scrollbar_y = ttk.Scrollbar(list_container, orient="vertical", command=self._canvas.yview)
        self._scroll_frame = ttk.Frame(self._canvas)

        self._scroll_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        window_id = self._canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")

        def _on_canvas_configure(event: tk.Event) -> None:
            try:
                self._canvas.itemconfig(window_id, width=event.width)
            except Exception:
                pass

        self._canvas.bind("<Configure>", _on_canvas_configure)
        self._canvas.configure(yscrollcommand=self._scrollbar_y.set)

        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar_y.grid(row=0, column=1, sticky="ns")
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)

        # Right occurrences panel
        right = ttk.Frame(content)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self._occ_title_label = ttk.Label(right, text="Occurrences", anchor="w")
        self._occ_title_label.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        occ_container = ttk.Frame(right, borderwidth=1, relief="solid")
        occ_container.grid(row=1, column=0, sticky="nsew")
        self._occ_listbox = tk.Listbox(occ_container, activestyle="none")
        self._occ_scroll_y = ttk.Scrollbar(occ_container, orient="vertical", command=self._occ_listbox.yview)
        self._occ_listbox.configure(yscrollcommand=self._occ_scroll_y.set)
        self._occ_listbox.grid(row=0, column=0, sticky="nsew")
        self._occ_scroll_y.grid(row=0, column=1, sticky="ns")
        occ_container.rowconfigure(0, weight=1)
        occ_container.columnconfigure(0, weight=1)

        # Buttons
        btns = ttk.Frame(outer)
        btns.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self._apply_btn = ttk.Button(btns, text="Apply", command=self._on_apply_safe)
        self._cancel_btn = ttk.Button(btns, text="Cancel", command=self._on_cancel_safe)
        self._reset_btn = ttk.Button(btns, text="Reset", command=self._on_reset_safe)
        btns.columnconfigure(0, weight=1)
        ttk.Frame(btns).grid(row=0, column=0, sticky="ew")
        self._reset_btn.grid(row=0, column=1, padx=(0, 8))
        self._cancel_btn.grid(row=0, column=2, padx=(0, 8))
        self._apply_btn.grid(row=0, column=3)

        # Key bindings
        self._top.bind("<Escape>", lambda e: self._on_cancel_safe())
        self._top.bind("<Return>", lambda e: self._on_apply_safe())

        # Initial size hint
        try:
            self._top.minsize(720, 420)
        except Exception:
            pass

    def _populate_styles(self) -> None:
        # Sort styles for deterministic order: by style name
        styles = sorted(set(self._headings_cache.keys()) | set(self._original_exclusions.keys()), key=str)

        # Clear any prior row content if reusing
        for child in list(self._scroll_frame.winfo_children() if self._scroll_frame else []):
            try:
                child.destroy()
            except Exception:
                pass

        self._vars_by_style.clear()

        first_style: Optional[str] = None
        for r, style in enumerate(styles):
            if first_style is None:
                first_style = style

            occ = int(self._headings_cache.get(style, 0))
            # Default included (False) if not present
            excluded_default = bool(self._original_exclusions.get(style, False))

            var = tk.BooleanVar(value=excluded_default)
            self._vars_by_style[style] = var

            # Clicking checkbox or label should update occurrences panel
            def make_update_handler(s: str):
                return lambda *_: self._update_occurrences_panel(s)

            chk = ttk.Checkbutton(self._scroll_frame, variable=var, command=make_update_handler(style))
            lbl_style = ttk.Label(self._scroll_frame, text=str(style), anchor="w")
            lbl_occ = ttk.Label(self._scroll_frame, text=str(occ), width=12, anchor="e")

            # Also bind label click to update occurrences (focus/select behavior)
            try:
                lbl_style.bind("<Button-1>", lambda e, s=style: self._update_occurrences_panel(s))
            except Exception:
                pass

            chk.grid(row=r, column=0, sticky="w", padx=(6, 0), pady=2)
            lbl_style.grid(row=r, column=1, sticky="w", padx=(12, 6), pady=2)
            lbl_occ.grid(row=r, column=2, sticky="e", padx=(6, 6), pady=2)

            # Make style column expand
            self._scroll_frame.columnconfigure(1, weight=1)

        # Initialize occurrences with the first style if available
        if first_style is not None:
            self._update_occurrences_panel(first_style)

    def _update_occurrences_panel(self, style: str) -> None:
        """Populate the occurrences list for the given style."""
        if self._occ_listbox is None:
            return
        try:
            self._occ_listbox.delete(0, tk.END)
        except Exception:
            pass

        # Update title label
        try:
            if self._occ_title_label is not None:
                self._occ_title_label.configure(text=f"Occurrences for: {style}")
        except Exception:
            pass

        items = self._occurrences.get(style, []) if self._occurrences else []
        for entry in items:
            try:
                title = str(entry.get("title", "")).strip() if isinstance(entry, dict) else ""
                href = str(entry.get("href", "")).strip() if isinstance(entry, dict) and "href" in entry else ""
                if href:
                    display = f"{title} ({href})" if title else f"{href}"
                else:
                    display = title or "Untitled"
                self._occ_listbox.insert(tk.END, display)
            except Exception:
                continue

    def _center_over_master(self) -> None:
        try:
            self._top.update_idletasks()
            # Obtain master geometry
            mx = my = mw = mh = 0
            try:
                mgeo = self._master.winfo_rootx(), self._master.winfo_rooty(), self._master.winfo_width(), self._master.winfo_height()
                mx, my, mw, mh = mgeo
            except Exception:
                # Fallback to screen centering
                sw = self._top.winfo_screenwidth()
                sh = self._top.winfo_screenheight()
                tw = self._top.winfo_reqwidth()
                th = self._top.winfo_reqheight()
                x = int((sw - tw) / 2)
                y = int((sh - th) / 2)
                self._top.geometry(f"+{x}+{y}")
                return

            tw = self._top.winfo_reqwidth()
            th = self._top.winfo_reqheight()
            x = mx + int((mw - tw) / 2)
            y = my + int((mh - th) / 2)
            self._top.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    # -------------------------
    # Actions (wrapped safe)
    # -------------------------

    def _on_apply_safe(self) -> None:
        try:
            self._result_exclusions = self._collect_states()
            self._applied = True
            self._close_safe()
        except Exception:
            self._result_exclusions = None
            self._applied = False
            self._close_safe()

    def _on_cancel_safe(self) -> None:
        try:
            self._result_exclusions = None
            self._applied = False
        except Exception:
            pass
        finally:
            self._close_safe()

    def _on_reset_safe(self) -> None:
        try:
            for var in self._vars_by_style.values():
                try:
                    var.set(False)
                except Exception:
                    pass
        except Exception:
            pass

    def _collect_states(self) -> Dict[str, bool]:
        result: Dict[str, bool] = {}
        for style, var in self._vars_by_style.items():
            try:
                result[style] = bool(var.get())
            except Exception:
                result[style] = bool(self._original_exclusions.get(style, False))
        return result

    def _close_safe(self) -> None:
        if self._top is None:
            return
        try:
            try:
                self._top.grab_release()
            except Exception:
                pass
            self._top.destroy()
        except Exception:
            try:
                self._top.withdraw()
            except Exception:
                pass