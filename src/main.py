# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
import os
import shutil
import threading
from datetime import datetime
from typing import Optional
import tempfile

# Nouveaux imports et suppression des anciens
from src.docx_to_dita_converter import (
    convert_docx_to_dita, DitaContext, save_dita_package, 
    update_image_references_and_names, update_topic_references_and_names
)
from src.ui.metadata_tab import MetadataTab
from src.ui.image_tab import ImageTab

logger = logging.getLogger(__name__)

class OrlandoToolkit:
    def __init__(self, root):
        self.root = root
        self.dita_context: Optional[DitaContext] = None
        
        # --- Widgets ---
        self.home_frame: Optional[ttk.Frame] = None
        self.progress_bar: Optional[ttk.Progressbar] = None
        self.status_label: Optional[ttk.Label] = None
        self.load_button: Optional[ttk.Button] = None
        self.notebook = None
        self.metadata_tab = None
        self.image_tab = None
        self.main_actions_frame = None # Frame for "Generate" button
        self.generation_progress = None  # For archive generation progress

        self.create_home_screen()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_home_screen(self):
        """Creates the initial home screen with logo."""
        self.home_frame = ttk.Frame(self.root)
        self.home_frame.pack(expand=True, fill="both", padx=20, pady=20)
        
        center_frame = ttk.Frame(self.home_frame)
        center_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Logo integration
        try:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            logo_path = os.path.join(base_path, 'assets', 'app_icon.png')
            if os.path.exists(logo_path):
                logo_image = tk.PhotoImage(file=logo_path)
                # Resize logo if too large (optional)
                logo_label = ttk.Label(center_frame, image=logo_image)
                logo_label.image = logo_image  # Keep a reference
                logo_label.pack(pady=(0, 20))
        except Exception as e:
            logger.warning(f"Could not load logo: {e}")

        ttk.Label(center_frame, text="Orlando Toolkit", font=("Arial", 24, "bold")).pack(pady=20)
        ttk.Label(center_frame, text="DOCX to DITA converter", 
                 font=("Arial", 12), foreground="gray").pack(pady=(0, 10))
        
        self.load_button = ttk.Button(center_frame, text="Load Document (.docx)", 
                                     command=self.start_conversion_workflow,
                                     style="Accent.TButton")
        self.load_button.pack(pady=20, ipady=10, ipadx=20)
        
        self.status_label = ttk.Label(center_frame, text="", font=("Arial", 10))
        self.status_label.pack(pady=10)
        
        self.progress_bar = ttk.Progressbar(center_frame, mode='indeterminate')
        # Progress bar is "packed" only at the start of processing.

    def start_conversion_workflow(self):
        """Triggers file selection and starts in-memory conversion."""
        filepath = filedialog.askopenfilename(
            title="Select a DOCX file",
            filetypes=(("Word Documents", "*.docx"), ("All files", "*.*"))
        )
        if not filepath:
            return

        if self.load_button: self.load_button.config(state="disabled")
        if self.status_label: self.status_label.config(text="Converting document...")
        if self.progress_bar:
            self.progress_bar.pack(fill="x", expand=True, padx=20, pady=(10, 0))
            self.progress_bar.start()
        
        # Initial metadata no longer includes manual code
        # and date is today's date.
        initial_metadata = {
            'manual_title': os.path.splitext(os.path.basename(filepath))[0],
            'revision_date': datetime.now().strftime('%Y-%m-%d'),
            'revision_number': '1.0'
        }
        
        threading.Thread(target=self.run_conversion_thread, args=(filepath, initial_metadata), daemon=True).start()

    def run_conversion_thread(self, filepath, metadata):
        """Executes DITA conversion in a separate thread."""
        try:
            context = convert_docx_to_dita(filepath, metadata)
            self.root.after(0, self.on_conversion_success, context)
        except Exception as e:
            logger.error("Document conversion failed", exc_info=True)
            self.root.after(0, self.on_conversion_failure, e)

    def on_conversion_success(self, context: DitaContext):
        """Called when in-memory conversion succeeds."""
        self.dita_context = context
        if self.home_frame:
            self.home_frame.destroy()
        self.setup_main_ui() # New function for main UI
        
        if self.metadata_tab and self.image_tab:
            self.metadata_tab.load_context(self.dita_context)
            self.image_tab.load_context(self.dita_context)

    def on_conversion_failure(self, error):
        """Called when conversion fails."""
        if self.progress_bar:
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
        if self.status_label:
            self.status_label.config(text="Conversion failed. Please try again.")
        if self.load_button:
            self.load_button.config(state="normal")
        
        messagebox.showerror("Conversion Error", f"Document processing failed:\n\n{error}")

    def setup_main_ui(self):
        """Creates the main view with tabs and action buttons."""
        # Frame for tabs
        tabs_frame = ttk.Frame(self.root)
        tabs_frame.pack(expand=True, fill='both', padx=10, pady=(10, 0))
        
        self.notebook = ttk.Notebook(tabs_frame)
        self.notebook.pack(expand=True, fill='both')

        # Creating new tabs
        self.metadata_tab = MetadataTab(self.notebook)
        self.notebook.add(self.metadata_tab, text='Metadata')

        self.image_tab = ImageTab(self.notebook)
        self.notebook.add(self.image_tab, text='Images')
        
        # Set up communication between tabs
        self.metadata_tab.set_metadata_change_callback(self.on_metadata_change)
        
        # Frame for global action buttons
        self.main_actions_frame = ttk.Frame(self.root)
        self.main_actions_frame.pack(fill='x', padx=10, pady=10)
        
        # Back button
        back_button = ttk.Button(self.main_actions_frame, text="← Back to Home", 
                                command=self.back_to_home)
        back_button.pack(side='left')
        
        generate_button = ttk.Button(self.main_actions_frame, text="Generate DITA Package", 
                                   command=self.generate_package,
                                   style="Accent.TButton")
        generate_button.pack(side='right')

    def back_to_home(self):
        """Returns to home screen."""
        # Clear current UI
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Reset context
        self.dita_context = None
        self.notebook = None
        self.metadata_tab = None
        self.image_tab = None
        self.main_actions_frame = None
        
        # Recreate home screen
        self.create_home_screen()

    def on_metadata_change(self):
        """Called when metadata changes in metadata tab."""
        if self.image_tab:
            self.image_tab.update_image_names()

    def generate_package(self):
        """
        Orchestrates the final process: updating names, saving to a
        temporary folder, creating zip archive, and cleanup.
        """
        if not self.dita_context:
            messagebox.showerror("Error", "No DITA context is loaded.")
            return

        # Step 1: Final context update from tabs (safety)
        # This ensures that even without FocusOut, data is up to date.
        if self.metadata_tab:
            for key, var in self.metadata_tab.entries.items():
                self.dita_context.metadata[key] = var.get()
        
        # --- FIX FOR DITAMAP TITLE ---
        # Update the <title> element in the XML tree with the final value
        if self.dita_context.ditamap_root is not None:
            title_element = self.dita_context.ditamap_root.find('title')
            if title_element is not None:
                title_element.text = self.dita_context.metadata.get('manual_title', 'Default Title')
        # --- END OF FIX ---

        # Step 2: Ask user where to save the final archive
        manual_code = self.dita_context.metadata.get('manual_code', 'package')
        default_filename = f"{manual_code}.zip" if manual_code else "package.zip"
        
        save_path = filedialog.asksaveasfilename(
            title="Save DITA Package",
            initialfile=default_filename,
            defaultextension=".zip",
            filetypes=[("Zip Archives", "*.zip")]
        )
        if not save_path:
            return # User cancelled

        # Show generation progress
        self.show_generation_progress()
        
        # Run generation in thread to avoid UI freezing
        threading.Thread(target=self.run_generation_thread, args=(save_path,), daemon=True).start()

    def show_generation_progress(self):
        """Shows a progress dialog during archive generation."""
        self.generation_progress = tk.Toplevel(self.root)
        self.generation_progress.title("Generating Archive")
        self.generation_progress.geometry("400x150")
        self.generation_progress.transient(self.root)
        self.generation_progress.grab_set()
        
        # Center the dialog
        self.generation_progress.geometry("+%d+%d" % (
            self.root.winfo_rootx() + 50,
            self.root.winfo_rooty() + 50
        ))
        
        frame = ttk.Frame(self.generation_progress, padding=20)
        frame.pack(expand=True, fill='both')
        
        ttk.Label(frame, text="Generating DITA archive...", font=("Arial", 12)).pack(pady=(0, 20))
        
        progress = ttk.Progressbar(frame, mode='indeterminate')
        progress.pack(fill='x', pady=(0, 20))
        progress.start()
        
        ttk.Label(frame, text="Please wait while the archive is being created.", 
                 font=("Arial", 10), foreground="gray").pack()

    def run_generation_thread(self, save_path):
        """Runs archive generation in a separate thread."""
        try:
            # Step 3: Update topic names and references
            self.dita_context = update_topic_references_and_names(self.dita_context)

            # Step 4: Update image names and references
            self.dita_context = update_image_references_and_names(self.dita_context)

            # Step 5: Create temporary folder
            with tempfile.TemporaryDirectory(prefix="orlando_packager_") as temp_dir:
                
                # Step 6: Save package to temporary folder
                save_dita_package(self.dita_context, temp_dir)
                
                # --- Debug copy logic ---
                debug_archive_path = os.path.join('Reference', 'archive_creer')
                if os.path.exists(debug_archive_path):
                    shutil.rmtree(debug_archive_path)
                shutil.copytree(temp_dir, debug_archive_path)
                logger.info(f"Debug copy created at: {debug_archive_path}")
                # --- End debug copy logic ---
                
                # Step 7: Create zip archive
                # Base name for archive is path without .zip extension
                archive_base_name = os.path.splitext(save_path)[0]
                shutil.make_archive(archive_base_name, 'zip', temp_dir)

            self.root.after(0, self.on_generation_success, save_path)
            
        except Exception as e:
            logger.error("Archive generation failed", exc_info=True)
            self.root.after(0, self.on_generation_failure, e)

    def on_generation_success(self, save_path):
        """Called when archive generation succeeds."""
        if self.generation_progress:
            self.generation_progress.destroy()
            self.generation_progress = None
        
        messagebox.showinfo("Success", f"DITA package generated successfully at:\n{save_path}")

    def on_generation_failure(self, error):
        """Called when archive generation fails."""
        if self.generation_progress:
            self.generation_progress.destroy()
            self.generation_progress = None
        
        messagebox.showerror("Generation Error", f"Archive generation failed:\n\n{error}")

    def on_close(self):
        """Handle application closing."""
        if self.generation_progress:
            self.generation_progress.destroy()
        self.root.quit()
        self.root.destroy()

# Le point d'entrée principal reste run.py, mais ce bloc permet des tests
if __name__ == '__main__':
    root = tk.Tk()
    root.title("Boîte à Outils Orlando - Test Direct")
    root.geometry("600x700")
    
    try:
        # Tenter d'importer et d'appliquer le thème sombre
        from sv_ttk import set_theme
        set_theme("dark")
    except ImportError:
        print("Le thème 'sv-ttk' n'est pas installé. Utilisation du thème par défaut.")

    # Instancier l'application
    app = OrlandoToolkit(root)
    
    root.mainloop() 