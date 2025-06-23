import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Optional
import os

if TYPE_CHECKING:
    from src.docx_to_dita_converter import DitaContext

class ImageTab(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        
        self.context: Optional['DitaContext'] = None
        
        # --- Widgets ---
        self.image_listbox: Optional[tk.Listbox] = None
        self.prefix_entry: Optional[ttk.Entry] = None
        self.manual_code_entry: Optional[ttk.Entry] = None
        self.section_map = {} # Pour mapper le nom de fichier original au nom de la section

        self.create_widgets()

    def create_widgets(self):
        """Crée les widgets pour afficher la liste des images et le champ de préfixe."""
        main_frame = ttk.Frame(self)
        main_frame.pack(expand=True, fill='both', padx=10, pady=10)
        
        # --- Frame pour les options ---
        options_frame = ttk.LabelFrame(main_frame, text="Options de nommage")
        options_frame.pack(fill='x', pady=(0, 5), padx=5)

        options_frame.columnconfigure(1, weight=1)
        options_frame.columnconfigure(3, weight=1)

        prefix_label = ttk.Label(options_frame, text="Préfixe:")
        prefix_label.grid(row=0, column=0, sticky='w', padx=5, pady=5)
        
        self.prefix_entry = ttk.Entry(options_frame)
        self.prefix_entry.grid(row=0, column=1, sticky='ew', padx=5, pady=5)
        self.prefix_entry.bind('<KeyRelease>', lambda e: self.update_image_names())

        manual_code_label = ttk.Label(options_frame, text="Code du manuel:")
        manual_code_label.grid(row=0, column=2, sticky='w', padx=5, pady=5)

        self.manual_code_entry = ttk.Entry(options_frame)
        self.manual_code_entry.grid(row=0, column=3, sticky='ew', padx=5, pady=5)
        self.manual_code_entry.bind('<KeyRelease>', lambda e: self.update_image_names())

        # --- Frame pour la liste ---
        list_frame = ttk.LabelFrame(main_frame, text="Aperçu des noms de fichiers")
        list_frame.pack(expand=True, fill='both')

        self.image_listbox = tk.Listbox(list_frame)
        self.image_listbox.pack(side='left', expand=True, fill='both', padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.image_listbox.yview)
        scrollbar.pack(side='right', fill='y')
        self.image_listbox.config(yscrollcommand=scrollbar.set)

    def load_context(self, context: 'DitaContext'):
        """Charge la liste des images et initialise le préfixe."""
        self.context = context
        
        # Simuler un préfixe par défaut si non présent
        if 'prefix' not in self.context.metadata:
            self.context.metadata['prefix'] = 'CRL'
        
        if self.prefix_entry:
            self.prefix_entry.delete(0, tk.END)
            self.prefix_entry.insert(0, self.context.metadata.get('prefix', ''))
        
        if self.manual_code_entry:
            self.manual_code_entry.delete(0, tk.END)
            self.manual_code_entry.insert(0, self.context.metadata.get('manual_code', ''))

        self.update_image_names()

    def update_image_names(self):
        """Met à jour la liste des noms de fichiers en fonction du préfixe et des métadonnées."""
        if not self.context or not self.prefix_entry or not self.manual_code_entry or not self.image_listbox:
            return

        # Mettre à jour les métadonnées depuis les champs
        prefix = self.prefix_entry.get()
        manual_code = self.manual_code_entry.get()
        self.context.metadata['prefix'] = prefix
        self.context.metadata['manual_code'] = manual_code
        
        self.image_listbox.delete(0, tk.END)

        if not self.context.images:
            self.image_listbox.insert(tk.END, "Aucune image trouvée.")
            return

        # Nomenclature: [PREFIXE]-[NOMDUMANUEL][NUMERO DE SECTION]-[NUMERO IMAGE]
        # Pour l'instant, on n'a pas la section, on simplifie
        for i, original_filename in enumerate(self.context.images.keys()):
            # Placeholder pour le numéro de section, on utilise 0 pour l'instant
            section_num = "0"
            img_num = i + 1
            extension = os.path.splitext(original_filename)[1]
            
            new_filename = f"{prefix}-{manual_code}-{section_num}-{img_num}{extension}"
            self.image_listbox.insert(tk.END, new_filename) 