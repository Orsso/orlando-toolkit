import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import datetime
import threading
import logging
import os
import tempfile
import shutil
import zipfile

logger = logging.getLogger(__name__)

class DitaPackagerTab(ttk.Frame):
    def __init__(self, parent, dita_dtd_path, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.dita_dtd_path = dita_dtd_path
        self.project_dir = None
        self.image_dir = None
        self.metadata = {}
        self.setup_widgets()

    def setup_widgets(self):
        # Main layout
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left side for file list
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        ttk.Label(left_frame, text="DITA Project Files", font=("-size 12 -weight bold")).pack(anchor='w', pady=(0,5))
        
        self.file_list = ttk.Treeview(left_frame, columns=("File"), show="headings", height=10)
        self.file_list.heading("File", text="File Path")
        self.file_list.pack(fill=tk.BOTH, expand=True)

        # Right side for metadata and actions
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        metadata_frame = ttk.LabelFrame(right_frame, text="Metadata", padding=10)
        metadata_frame.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(metadata_frame, text="Manual title:").grid(row=0, column=0, sticky='w', pady=2)
        self.title_var = tk.StringVar()
        ttk.Entry(metadata_frame, textvariable=self.title_var, width=30).grid(row=0, column=1, sticky='we')
        
        ttk.Label(metadata_frame, text="Revision date:").grid(row=1, column=0, sticky='w', pady=2)
        self.date_var = tk.StringVar()
        ttk.Entry(metadata_frame, textvariable=self.date_var, width=30).grid(row=1, column=1, sticky='we')
        
        action_frame = ttk.Frame(right_frame)
        action_frame.pack(fill=tk.X)
        
        self.export_button = ttk.Button(action_frame, text="Export Project Archive...", command=self.export_project)
        self.export_button.pack(fill=tk.X)
        self.export_button.config(state='disabled')

    def load_project(self, project_dir, metadata):
        logging.info(f"Loading DITA project from: {project_dir}")
        self.project_dir = project_dir
        self.image_dir = os.path.dirname(project_dir)
        self.metadata = metadata
        
        self.title_var.set(metadata.get('manual_title', ''))
        self.date_var.set(metadata.get('revision_date', ''))
        
        self.file_list.delete(*self.file_list.get_children())
        
        for item in sorted(os.listdir(project_dir)):
            if item.lower().endswith('.dita') or item.lower().endswith('.ditamap'):
                self.file_list.insert("", tk.END, values=(item,))
            
        self.export_button.config(state='normal')

    def export_project(self):
        if not self.project_dir:
            messagebox.showwarning("No Project", "No DITA project is currently loaded.")
            return
        
        initial_filename = f"{self.title_var.get() or 'dita_project'}.zip"
        
        zip_path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("ZIP archives", "*.zip")],
            initialfile=initial_filename,
            title="Save Project Archive As"
        )
        
        if not zip_path:
            return

        try:
            root_dir = self.image_dir
            base_name = zip_path.replace('.zip', '')
            
            shutil.make_archive(base_name, 'zip', root_dir)
            
            logging.info("Export successful.")
            messagebox.showinfo("Export Successful", f"The project has been successfully exported to:\n{zip_path}")
        except Exception as e:
            logging.error(f"Failed to export project: {e}", exc_info=True)
            messagebox.showerror("Export Error", f"An error occurred during export:\n{e}")

    # Les anciennes méthodes de conversion sont maintenant obsolètes
    def browse_dita_input(self): pass
    def run_dita_conversion(self): pass
    def _run_dita_conversion_thread(self, *args): pass 