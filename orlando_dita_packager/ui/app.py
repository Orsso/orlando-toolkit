import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from datetime import datetime

from orlando_dita_packager.core import transformer

class Application(tk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.master = master
        self.master.title("Outil de Transformation DITA pour Orlando")
        self.master.geometry("600x400")
        self.pack(fill="both", expand=True, padx=10, pady=10)
        self.create_widgets()

    def create_widgets(self):
        # --- Frame pour la sélection de l'archive ---
        source_frame = ttk.LabelFrame(self, text="1. Sélection de l'archive .zip à traiter")
        source_frame.pack(fill="x", expand=True, pady=5)

        self.source_path = tk.StringVar()
        source_entry = ttk.Entry(source_frame, textvariable=self.source_path, state="readonly")
        source_entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        browse_button = ttk.Button(source_frame, text="Parcourir...", command=self.browse_source)
        browse_button.pack(side="left", padx=5)

        # --- Frame pour les métadonnées ---
        meta_frame = ttk.LabelFrame(self, text="2. Informations sur le manuel")
        meta_frame.pack(fill="x", expand=True, pady=5)

        # Titre
        ttk.Label(meta_frame, text="Titre du manuel:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.manual_title = tk.StringVar()
        ttk.Entry(meta_frame, textvariable=self.manual_title).grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        # Date de révision
        ttk.Label(meta_frame, text="Date de révision:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.revision_date = tk.StringVar()
        self.revision_date.set(datetime.now().strftime('%Y-%m-%d')) # Pré-remplissage avec la date du jour
        ttk.Entry(meta_frame, textvariable=self.revision_date).grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        
        meta_frame.columnconfigure(1, weight=1)

        # --- Frame pour les actions ---
        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", expand=True, pady=20)

        self.run_button = ttk.Button(action_frame, text="Lancer la Transformation", command=self.run_transformation)
        self.run_button.pack(side="right")
        
        # --- Zone de statut ---
        self.status_text = tk.StringVar()
        self.status_text.set("En attente de sélection de l'archive .zip...")
        status_bar = ttk.Label(self, textvariable=self.status_text, relief=tk.SUNKEN, anchor="w")
        status_bar.pack(side="bottom", fill="x")

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
                messagebox.showerror("Erreur de Transformation", f"Une erreur est survenue:\n\n{message}")
        finally:
            self.run_button.config(state="normal")

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
        self.run_button.config(state="disabled")
        
        thread = threading.Thread(target=self.run_transformation_thread)
        thread.start()

if __name__ == '__main__':
    root = tk.Tk()
    app = Application(master=root)
    app.mainloop() 