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
        self.main_actions_frame = None # Frame pour le bouton "Générer"

        self.create_home_screen()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_home_screen(self):
        """Crée l'écran d'accueil initial."""
        self.home_frame = ttk.Frame(self.root)
        self.home_frame.pack(expand=True, fill="both", padx=20, pady=20)
        
        center_frame = ttk.Frame(self.home_frame)
        center_frame.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(center_frame, text="Bienvenue dans l'Orlando Toolbox", font=("Arial", 24)).pack(pady=20)
        ttk.Label(center_frame, text="Commencez par charger un document DOCX pour le convertir.").pack(pady=10)
        
        self.load_button = ttk.Button(center_frame, text="Charger un document (.docx)", command=self.start_conversion_workflow)
        self.load_button.pack(pady=20, ipady=10, ipadx=20)
        
        self.status_label = ttk.Label(center_frame, text="")
        self.status_label.pack(pady=10)
        
        self.progress_bar = ttk.Progressbar(center_frame, mode='indeterminate')
        # La barre de progression est "packée" uniquement au début du traitement.

    def start_conversion_workflow(self):
        """Déclenche la sélection du fichier et le début de la conversion en mémoire."""
        filepath = filedialog.askopenfilename(
            title="Sélectionner un fichier DOCX",
            filetypes=(("Word Documents", "*.docx"), ("All files", "*.*"))
        )
        if not filepath:
            return

        if self.load_button: self.load_button.config(state="disabled")
        if self.status_label: self.status_label.config(text="Conversion du document en cours...")
        if self.progress_bar:
            self.progress_bar.pack(fill="x", expand=True, padx=20)
            self.progress_bar.start()
        
        # Les métadonnées initiales n'incluent plus de code manuel
        # et la date est celle du jour.
        initial_metadata = {
            'manual_title': os.path.splitext(os.path.basename(filepath))[0],
            'revision_date': datetime.now().strftime('%Y-%m-%d'),
            'revision_number': '1.0'
        }
        
        threading.Thread(target=self.run_conversion_thread, args=(filepath, initial_metadata), daemon=True).start()

    def run_conversion_thread(self, filepath, metadata):
        """Exécute la conversion DITA dans un thread séparé."""
        try:
            context = convert_docx_to_dita(filepath, metadata)
            self.root.after(0, self.on_conversion_success, context)
        except Exception as e:
            logger.error("Échec de la conversion du document", exc_info=True)
            self.root.after(0, self.on_conversion_failure, e)

    def on_conversion_success(self, context: DitaContext):
        """Appelé lorsque la conversion en mémoire réussit."""
        self.dita_context = context
        if self.home_frame:
            self.home_frame.destroy()
        self.setup_main_ui() # Nouvelle fonction pour l'UI principale
        
        if self.metadata_tab and self.image_tab:
            self.metadata_tab.load_context(self.dita_context)
            self.image_tab.load_context(self.dita_context)

    def on_conversion_failure(self, error):
        """Appelé lorsque la conversion échoue."""
        if self.progress_bar:
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
        if self.status_label:
            self.status_label.config(text="La conversion a échoué. Veuillez réessayer.")
        if self.load_button:
            self.load_button.config(state="normal")
        
        messagebox.showerror("Erreur de Conversion", f"Le traitement du document a échoué:\n\n{error}")

    def setup_main_ui(self):
        """Crée la vue principale avec les onglets et les boutons d'action."""
        # Frame pour les onglets
        tabs_frame = ttk.Frame(self.root)
        tabs_frame.pack(expand=True, fill='both', padx=10, pady=(10, 0))
        
        self.notebook = ttk.Notebook(tabs_frame)
        self.notebook.pack(expand=True, fill='both')

        # Création des nouveaux onglets
        self.metadata_tab = MetadataTab(self.notebook)
        self.notebook.add(self.metadata_tab, text='Métadonnées')

        self.image_tab = ImageTab(self.notebook)
        self.notebook.add(self.image_tab, text='Images')
        
        # Frame pour les boutons d'action globaux
        self.main_actions_frame = ttk.Frame(self.root)
        self.main_actions_frame.pack(fill='x', padx=10, pady=10)
        
        generate_button = ttk.Button(self.main_actions_frame, text="Générer le Package DITA", command=self.generate_package)
        generate_button.pack(side='right')

    def generate_package(self):
        """
        Orchestre le processus final : mise à jour des noms, sauvegarde dans un
        dossier temporaire, création de l'archive zip, et nettoyage.
        """
        if not self.dita_context:
            messagebox.showerror("Erreur", "Aucun contexte DITA n'est chargé.")
            return

        # Étape 1: Mise à jour finale du contexte depuis les onglets (sécurité)
        # Ceci garantit que même sans FocusOut, les données sont à jour.
        if self.metadata_tab:
            for key, var in self.metadata_tab.entries.items():
                self.dita_context.metadata[key] = var.get()
        
        # --- CORRECTIF POUR LE TITRE DU DITAMAP ---
        # Mettre à jour l'élément <title> dans l'arbre XML avec la valeur finale
        if self.dita_context.ditamap_root is not None:
            title_element = self.dita_context.ditamap_root.find('title')
            if title_element is not None:
                title_element.text = self.dita_context.metadata.get('manual_title', 'Titre par défaut')
        # --- FIN DU CORRECTIF ---

        # Étape 2: Demander à l'utilisateur où sauvegarder l'archive finale
        save_path = filedialog.asksaveasfilename(
            title="Enregistrer le package DITA",
            defaultextension=".zip",
            filetypes=[("Archives Zip", "*.zip")]
        )
        if not save_path:
            return # L'utilisateur a annulé

        try:
            # Étape 3: Mise à jour des noms des topics et des références
            self.dita_context = update_topic_references_and_names(self.dita_context)

            # Étape 4: Mise à jour des noms d'images et des références
            self.dita_context = update_image_references_and_names(self.dita_context)

            # Étape 5: Créer un dossier temporaire
            with tempfile.TemporaryDirectory(prefix="orlando_packager_") as temp_dir:
                
                # Étape 6: Sauvegarder le package dans le dossier temporaire
                save_dita_package(self.dita_context, temp_dir)
                
                # --- Logique de copie pour le débogage ---
                debug_archive_path = os.path.join('Reference', 'archive_creer')
                if os.path.exists(debug_archive_path):
                    shutil.rmtree(debug_archive_path)
                shutil.copytree(temp_dir, debug_archive_path)
                logger.info(f"Copie de débogage créée dans : {debug_archive_path}")
                # --- Fin de la logique de copie ---
                
                # Étape 7: Créer l'archive zip
                # Le nom de base pour l'archive est le chemin sans l'extension .zip
                archive_base_name = os.path.splitext(save_path)[0]
                shutil.make_archive(archive_base_name, 'zip', temp_dir)

            messagebox.showinfo("Succès", f"Le package DITA a été généré avec succès à l'emplacement :\n{save_path}")

        except Exception as e:
            logger.error(f"Échec de la génération du package : {e}", exc_info=True)
            messagebox.showerror("Erreur de Génération", f"La génération du package a échoué :\n\n{e}")

    def on_close(self):
        """Gère la fermeture de la fenêtre."""
        logger.info("===== Application terminée =====")
        self.root.destroy()

# Le point d'entrée principal reste run.py, mais ce bloc permet des tests
if __name__ == '__main__':
    root = tk.Tk()
    root.title("Boîte à Outils Orlando - Test Direct")
    root.geometry("1100x800")
    
    try:
        # Tenter d'importer et d'appliquer le thème sombre
        from sv_ttk import set_theme
        set_theme("dark")
    except ImportError:
        print("Le thème 'sv-ttk' n'est pas installé. Utilisation du thème par défaut.")

    # Instancier l'application
    app = OrlandoToolkit(root)
    
    root.mainloop() 