import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import shutil
import logging
import tempfile
import re
from PIL import Image, ImageTk
import threading

from docx_parser import analyze_document_structure
from docx_to_dita_converter import convert_docx_to_dita
from ui.dita_packager_tab import DitaPackagerTab
from ui.custom_widgets import ToggledFrame, Thumbnail

logger = logging.getLogger(__name__)

class ImageExtractorTab(ttk.Frame):
    def __init__(self, notebook):
        super().__init__(notebook)
        self.notebook = notebook

        self.sections_data = []
        self.image_directory = None
        self.dita_directory = None
        
        self.create_widgets()

    def create_widgets(self):
        """Crée les widgets de l'onglet."""
        # --- Cadre de Contrôle ---
        self.controls_frame = ttk.Frame(self)
        self.controls_frame.pack(fill="x", padx=10, pady=10)

        self.export_button = ttk.Button(self.controls_frame, text="Exporter les images sélectionnées", command=self.export_selected_images)
        self.export_button.pack(side="left", padx=(0, 10))
        self.export_button.config(state="disabled")

        # --- Affichage principal (arbre et aperçu) ---
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill="both", expand=True)

        # Arbre des sections
        tree_frame = ttk.Frame(main_pane)
        self.tree = ttk.Treeview(tree_frame, columns=("filename",), show="tree headings")
        self.tree.heading("#0", text="Section / Image")
        self.tree.heading("filename", text="Nom de fichier d'origine")
        self.tree.column("filename", width=200, anchor="w")
        
        ysb = ttk.Scrollbar(tree_frame, orient='vertical', command=self.tree.yview)
        xsb = ttk.Scrollbar(tree_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscroll=ysb.set, xscroll=xsb.set)
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        ysb.grid(row=0, column=1, sticky='ns')
        xsb.grid(row=1, column=0, sticky='ew')
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        main_pane.add(tree_frame, weight=1)

        # Aperçu de l'image
        self.preview_frame = ttk.Frame(main_pane)
        self.preview_label = ttk.Label(self.preview_frame, text="Sélectionnez une image pour l'afficher", anchor="center")
        self.preview_label.pack(fill="both", expand=True)
        main_pane.add(self.preview_frame, weight=2)
        
        # --- Bindings ---
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Button-3>", self.on_right_click)

        # --- Menu contextuel ---
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Renommer la section", command=self.rename_selected_section)

    def display_sections(self, analysis_result):
        """
        Affiche la structure hiérarchique du document à partir des résultats de l'analyse.
        """
        self.clear_display()

        if not analysis_result or not analysis_result.get("sections"):
            messagebox.showinfo("Information", "Aucune section ou image n'a été trouvée dans le document.")
            return

        self.sections_data = analysis_result["sections"]
        self.image_directory = analysis_result.get("image_dir")
        self.dita_directory = analysis_result.get("dita_dir")

        if not self.image_directory or not os.path.exists(self.image_directory):
            logger.error("Le répertoire d'images n'a pas été trouvé après l'analyse.")
            messagebox.showerror("Erreur", "Le répertoire contenant les images n'a pas pu être trouvé.")
            return

        level_parents = {}
        for section in self.sections_data:
            level = section.get('level', 0)
            title = section.get('title', 'Titre de section inconnu')
            number = section.get('number', '')
            
            display_title = f"{number} {title}".strip()

            parent_id = level_parents.get(level - 1, "")

            section_id = self.tree.insert(parent_id, "end", text=display_title, open=True, values=("",))
            level_parents[level] = section_id

            for image_path in section.get("images", []):
                filename = os.path.basename(image_path)
                self.tree.insert(section_id, "end", text=f"  > {filename}", values=(filename,))
        
        self.export_button.config(state="normal")
        
    def clear_display(self):
        """Efface l'arbre."""
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.sections_data = []
        self.image_directory = None
        self.dita_directory = None
        self.export_button.config(state="disabled")

    def export_selected_images(self):
        """
        Ouvre une boîte de dialogue pour exporter les images sélectionnées
        vers un dossier choisi par l'utilisateur.
        """
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showinfo("Aucune sélection", "Veuillez sélectionner au moins une image à exporter.")
            return

        image_paths_to_export = []
        for item_id in selected_items:
            # On n'exporte que les images (qui n'ont pas d'enfants dans l'arbre)
            if not self.tree.get_children(item_id):
                item_data = self.tree.item(item_id)
                image_filename = item_data.get('values')[0]
                
                # Le nom de fichier est stocké, on reconstruit le chemin complet
                full_path = os.path.join(self.image_directory, image_filename)
                if os.path.exists(full_path):
                    image_paths_to_export.append(full_path)

        if not image_paths_to_export:
            messagebox.showinfo("Aucune image sélectionnée", "Votre sélection ne contient pas d'images valides à exporter.")
            return

        target_dir = filedialog.askdirectory(title="Choisir le dossier d'exportation")
        if not target_dir:
            return

        exported_count = 0
        try:
            for src_path in image_paths_to_export:
                dest_path = os.path.join(target_dir, os.path.basename(src_path))
                shutil.copy2(src_path, dest_path)
                exported_count += 1
            
            messagebox.showinfo("Exportation réussie", f"{exported_count} image(s) ont été exportées avec succès vers:\n{target_dir}")
        except Exception as e:
            logger.error(f"Erreur lors de l'exportation des images : {e}", exc_info=True)
            messagebox.showerror("Erreur d'exportation", f"Une erreur est survenue lors de l'exportation:\n{e}") 

    def on_tree_select(self, event):
        """Gère les changements de sélection dans l'arbre."""
        selected_ids = self.tree.selection()
        if not selected_ids:
            return
        
        selected_id = selected_ids[0]
        tags = self.tree.item(selected_id, 'tags')
        
        if 'image' in tags:
            try:
                original_filename = self.tree.item(selected_id, 'values')[0]
                image_path = os.path.join(self.image_directory, original_filename)
                
                with Image.open(image_path) as img:
                    # Adapter la taille à la frame d'aperçu
                    w, h = self.preview_frame.winfo_width(), self.preview_frame.winfo_height()
                    if w > 1 and h > 1:
                        img.thumbnail((w, h))
                    
                    self.preview_photo = ImageTk.PhotoImage(img)
                    self.preview_label.config(image=self.preview_photo, text="")

            except Exception as e:
                logger.warning(f"Impossible de charger l'aperçu pour {original_filename}: {e}")
                self.preview_label.config(image="", text="Aperçu indisponible")
        else:
            self.preview_label.config(image="", text="Sélectionnez une image pour l'afficher")

    def on_right_click(self, event):
        """Affiche le menu contextuel sur un clic droit."""
        try:
            item_id = self.tree.identify_row(event.y)
            if not item_id: return
            
            self.tree.selection_set(item_id)
            tags = self.tree.item(item_id, 'tags')
            if 'section' in tags:
                self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def rename_selected_section(self):
        selected_id = self.tree.selection()[0]
        if not selected_id: return

        current_name = self.tree.item(selected_id, 'text')
        new_name = simpledialog.askstring("Rename Section", "Enter new name:", initialvalue=current_name)
        
        if new_name and new_name.strip() != current_name:
            self.tree.item(selected_id, text=new_name)
            
            # Update children image names
            sanitized_title = self.sanitize_filename(new_name)
            for i, child_id in enumerate(self.tree.get_children(selected_id)):
                tags = self.tree.item(child_id, 'tags')
                if 'image' in tags:
                    original_filename = self.tree.item(child_id, 'values')[0]
                    ext = os.path.splitext(original_filename)[1]
                    updated_filename = f"{sanitized_title}_{i+1:02d}{ext}"
                    self.tree.item(child_id, text=updated_filename)

    @staticmethod
    def sanitize_filename(name):
        name = re.sub(r'^\d+(\.\d+)*\s*', '', name).strip() # Remove numbering
        name = re.sub(r'[^\w\s-]', '', name).strip()
        name = re.sub(r'[-\s]+', '_', name)
        return name 