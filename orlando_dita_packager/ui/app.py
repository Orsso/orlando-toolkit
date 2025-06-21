import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox
import threading
import os
import sys
from datetime import datetime

from orlando_dita_packager.core import transformer

class Application(ttk.Frame):
    
    PADDING = 10

    def __init__(self, master: ttk.Window):
        super().__init__(master, padding=self.PADDING)
        self.master = master
        self.master.title("Orlando DITA Packager")

        # --- Définir l'icône de la fenêtre ---
        try:
            # Le chemin est relatif au fichier app.py.
            # Cela nécessite un dossier 'assets' dans le même répertoire 'ui'.
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'app_icon.ico')
            if os.path.exists(icon_path):
                self.master.iconbitmap(icon_path)
            else:
                # Cet avertissement s'affichera dans la console si l'icône n'est pas trouvée.
                print(f"Avertissement : Fichier d'icône non trouvé à l'emplacement '{icon_path}'.", file=sys.stderr)
        except Exception as e:
            # Attraper d'autres erreurs potentielles (ex: format non supporté sur l'OS)
            print(f"Avertissement : Impossible de charger l'icône. Erreur : {e}", file=sys.stderr)
        
        self.pack(fill=BOTH, expand=YES)
        self.create_widgets()

    def create_widgets(self):
        # --- Frame pour la sélection de l'archive ---
        source_frame = ttk.LabelFrame(self, text="1. Sélection de l'archive .zip à traiter", padding=self.PADDING)
        source_frame.pack(fill=X, expand=YES, pady=self.PADDING / 2)

        self.source_path = ttk.StringVar()
        source_entry = ttk.Entry(source_frame, textvariable=self.source_path, state=READONLY)
        source_entry.pack(side=LEFT, fill=X, expand=YES, padx=(0, self.PADDING))
        
        browse_button = ttk.Button(source_frame, text="Parcourir...", command=self.browse_source, bootstyle=SECONDARY)
        browse_button.pack(side=LEFT)

        # --- Frame pour les métadonnées ---
        meta_frame = ttk.LabelFrame(self, text="2. Informations sur le manuel", padding=self.PADDING)
        meta_frame.pack(fill=X, expand=YES, pady=self.PADDING / 2)
        meta_frame.columnconfigure(1, weight=1)

        # Titre
        ttk.Label(meta_frame, text="Titre du manuel:").grid(row=0, column=0, sticky=W, padx=(0, self.PADDING), pady=self.PADDING/2)
        self.manual_title = ttk.StringVar()
        ttk.Entry(meta_frame, textvariable=self.manual_title).grid(row=0, column=1, sticky=EW)

        # Date de révision
        ttk.Label(meta_frame, text="Date de révision:").grid(row=1, column=0, sticky=W, padx=(0, self.PADDING), pady=self.PADDING/2)
        self.revision_date = ttk.StringVar()
        self.revision_date.set(datetime.now().strftime('%Y-%m-%d')) # Pré-remplissage avec la date du jour
        ttk.Entry(meta_frame, textvariable=self.revision_date).grid(row=1, column=1, sticky=EW)
        
        # --- Frame pour les actions ---
        action_frame = ttk.Frame(self, padding=(0, self.PADDING))
        action_frame.pack(fill=X, expand=YES)

        self.run_button = ttk.Button(
            action_frame, 
            text="Lancer la Transformation", 
            command=self.run_transformation,
            bootstyle=PRIMARY
        )
        self.run_button.pack(side=RIGHT)
        
        # --- Zone de statut ---
        self.status_text = ttk.StringVar()
        self.status_text.set("En attente de sélection de l'archive .zip...")
        status_bar = ttk.Label(
            self.master, 
            textvariable=self.status_text, 
            bootstyle=(INVERSE, SECONDARY),
            padding=self.PADDING / 2
        )
        status_bar.pack(side=BOTTOM, fill=X)

    def browse_source(self):
        """Ouvre une boîte de dialogue pour sélectionner le fichier .zip source."""
        filepath = filedialog.askopenfilename(
            title="Sélectionner l'archive .zip à traiter",
            filetypes=(("Archives Zip", "*.zip"), ("Tous les fichiers", "*.*"))
        )
        if filepath:
            self.source_path.set(filepath)
            self.status_text.set(f"Prêt à traiter : {filepath}")

    def run_transformation_thread(self):
        """Exécute la transformation dans un thread séparé pour garder l'interface réactive."""
        source_dir = self.source_path.get()
        manual_metadata = {
            'manual_title': self.manual_title.get(),
            'revision_date': self.revision_date.get()
        }
        try:
            success, message = transformer.run_transformation(source_dir, manual_metadata)
            if success:
                self.status_text.set("Transformation terminée avec succès !")
                messagebox.showinfo("Succès", "La transformation s'est terminée avec succès.")
            else:
                self.status_text.set(f"ERREUR: {message}")
                messagebox.showerror("Erreur de Transformation", f"Une erreur est survenue :\n\n{message}")
        finally:
            self.run_button.config(state=NORMAL)

    def run_transformation(self):
        """Valide les entrées et lance la transformation dans un nouveau thread."""
        if not self.source_path.get():
            messagebox.showerror("Erreur de validation", "Veuillez sélectionner une archive .zip à traiter.")
            return
        if not self.manual_title.get():
            messagebox.showerror("Erreur de validation", "Veuillez renseigner le titre du manuel.")
            return
        if not self.revision_date.get(): # Validation simple
            messagebox.showerror("Erreur de validation", "Veuillez renseigner la date de révision.")
            return

        self.status_text.set("Transformation en cours...")
        self.run_button.config(state=DISABLED)
        
        thread = threading.Thread(target=self.run_transformation_thread)
        thread.start()

if __name__ == '__main__':

    root = ttk.Window(themename="darkly", size=(600, 430))
    app = Application(master=root)
    app.mainloop() 