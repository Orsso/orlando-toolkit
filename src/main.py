# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
import os
import shutil
import threading

# Ces imports sont relatifs au dossier 'src'
from dtd_package import dtd_package_path
from ui.image_extractor_tab import ImageExtractorTab
from ui.dita_packager_tab import DitaPackagerTab
from docx_parser import analyze_document_structure

logger = logging.getLogger(__name__)

class OrlandoToolkit:
    def __init__(self, root, dtd_path):
        self.root = root
        self.dtd_path = dtd_path
        self.analysis_result = None
        
        # --- Widgets ---
        self.home_frame = None
        self.progress_bar = None
        self.status_label = None
        self.load_button = None
        self.notebook = None
        self.image_extractor_tab = None
        self.dita_packager_tab = None

        self.create_home_screen()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_home_screen(self):
        """Crée l'écran d'accueil initial."""
        self.home_frame = ttk.Frame(self.root)
        self.home_frame.pack(expand=True, fill="both", padx=20, pady=20)
        
        center_frame = ttk.Frame(self.home_frame)
        center_frame.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(center_frame, text="Bienvenue dans l'Orlando Toolbox", font=("Arial", 24)).pack(pady=20)
        ttk.Label(center_frame, text="Commencez par charger un document DOCX pour extraire sa structure et ses images.").pack(pady=10)
        
        self.load_button = ttk.Button(center_frame, text="Charger un document (.docx)", command=self.start_analysis_workflow)
        self.load_button.pack(pady=20, ipady=10, ipadx=20)
        
        self.status_label = ttk.Label(center_frame, text="")
        self.status_label.pack(pady=10)
        
        self.progress_bar = ttk.Progressbar(center_frame, mode='indeterminate')
        # La barre de progression est "packée" uniquement au début du traitement.

    def start_analysis_workflow(self):
        """Déclenche la sélection du fichier et le début de l'analyse."""
        filepath = filedialog.askopenfilename(
            title="Sélectionner un fichier DOCX",
            filetypes=(("Word Documents", "*.docx"), ("All files", "*.*"))
        )
        if not filepath:
            return

        self.load_button.config(state="disabled")
        self.status_label.config(text="Analyse du document en cours...")
        self.progress_bar.pack(fill="x", expand=True, padx=20)
        self.progress_bar.start()
        
        threading.Thread(target=self.run_analysis_thread, args=(filepath,), daemon=True).start()

    def run_analysis_thread(self, filepath):
        """Exécute l'analyse dans un thread séparé."""
        try:
            result = analyze_document_structure(filepath)
            self.root.after(0, self.on_analysis_success, result)
        except Exception as e:
            logger.error("Échec de l'analyse du document", exc_info=True)
            self.root.after(0, self.on_analysis_failure, e)

    def on_analysis_success(self, result):
        """Appelé lorsque l'analyse réussit."""
        self.analysis_result = result
        self.home_frame.destroy()
        self.setup_main_tabs()
        
        # Peuple les onglets avec les données
        self.image_extractor_tab.display_sections(result)
        self.dita_packager_tab.load_project_from_path(result['dita_dir'])

    def on_analysis_failure(self, error):
        """Appelé lorsque l'analyse échoue."""
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.status_label.config(text="L'analyse a échoué. Veuillez réessayer.")
        self.load_button.config(state="normal")
        
        messagebox.showerror("Erreur d'analyse", f"Le traitement du document a échoué:\n\n{error}")

    def setup_main_tabs(self):
        """Crée la vue principale avec les onglets."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)

        self.image_extractor_tab = ImageExtractorTab(self.notebook)
        self.notebook.add(self.image_extractor_tab, text='Étape 1: Extraction & Organisation')

        self.dita_packager_tab = DitaPackagerTab(self.notebook, dita_dtd_path=self.dtd_path)
        self.notebook.add(self.dita_packager_tab, text='Étape 2: Packaging DITA')
        
        self.notebook.bind("<<DitaProjectLoaded>>", lambda e: self.notebook.select(self.dita_packager_tab))

    def on_close(self):
        """Gère la fermeture de la fenêtre."""
        if self.analysis_result and 'temp_dir' in self.analysis_result:
            temp_dir = self.analysis_result['temp_dir']
            if os.path.exists(temp_dir) and 'orlando_toolbox' in temp_dir:
                try:
                    shutil.rmtree(temp_dir)
                    logger.info(f"Nettoyage du répertoire temporaire : {temp_dir}")
                except Exception as e:
                    logger.error(f"Échec du nettoyage du répertoire temporaire : {e}")
        
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
    app = OrlandoToolkit(root, dtd_path=dtd_package_path)
    
    root.mainloop() 