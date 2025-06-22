# -*- coding: utf-8 -*-

"""
Widgets Tkinter personnalisés pour l'application OrlandoToolbox.
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

class ToggledFrame(tk.Frame):
    """
    Un conteneur qui peut être affiché ou masqué via un bouton.
    Utilisé pour les sections dépliables.
    """
    def __init__(self, parent, text="", *args, **options):
        super().__init__(parent, *args, **options)

        self.text = text
        self.columnconfigure(1, weight=1)

        self.toggle_button = ttk.Checkbutton(self, width=2, text='+', command=self.toggle, style='Toolbutton')
        self.toggle_button.grid(row=0, column=0, sticky='ns')
        self.title_label = ttk.Label(self, text=text)
        self.title_label.grid(row=0, column=1, sticky='ew')

        self.sub_frame = tk.Frame(self)
        self.sub_frame.grid(row=1, column=1, sticky='nsew')
        self.sub_frame.grid_remove() # Start folded

        self.toggle_button.invoke() # Start folded

    def toggle(self):
        if self.sub_frame.winfo_viewable():
            self.sub_frame.grid_remove()
            self.toggle_button.configure(text='+')
        else:
            self.sub_frame.grid()
            self.toggle_button.configure(text='-')

class Thumbnail(tk.Frame):
    """
    Un widget pour afficher une vignette d'image avec son nom de fichier.
    Gère la sélection et l'affichage.
    """
    def __init__(self, parent, image_path, filename, size=(150, 150)):
        super().__init__(parent, borderwidth=1, relief="solid")
        self.image_path = image_path
        self.filename = filename
        self.size = size
        self.selected = False

        self.image_label = ttk.Label(self)
        self.image_label.pack()

        self.label = ttk.Label(self, text=filename, wraplength=size[0])
        self.label.pack(fill="x", padx=5, pady=5)

        self.load_image()

    def load_image(self):
        try:
            with Image.open(self.image_path) as img:
                img.thumbnail(self.size)
                self.photo_image = ImageTk.PhotoImage(img)
                self.image_label.config(image=self.photo_image)
        except Exception as e:
            # En cas d'erreur, affiche un placeholder
            self.image_label.config(text=f"Erreur\n{e}", relief="solid", width=20, height=10)

    def select(self):
        self.selected = True
        self.config(relief="sunken", bg="lightblue")
        self.label.config(bg="lightblue")

    def deselect(self):
        self.selected = False
        self.config(relief="solid", bg="")
        self.label.config(bg="")

    def toggle_selection(self):
        if self.selected:
            self.deselect()
        else:
            self.select()
        return self.selected 