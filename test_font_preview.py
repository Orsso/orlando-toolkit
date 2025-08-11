#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fenêtre de test pour prévisualiser différentes polices et couleurs 
pour le titre "Orlando Toolkit"
"""

import tkinter as tk
from tkinter import ttk

class FontPreviewWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Test de polices - Orlando Toolkit")
        self.root.geometry("800x900")
        
        # Créer un frame principal avec scrollbar
        main_frame = ttk.Frame(root)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Titre de la fenêtre
        title_label = ttk.Label(main_frame, text="Choisissez votre style préféré pour 'Orlando Toolkit'", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 20))
        
        # Liste des propositions
        self.proposals = [
            # Police, taille, style, couleur, description
            ("Segoe UI", 28, "bold", "#2c3e50", "Moderne et élégant"),
            ("Segoe UI", 30, "bold", "#34495e", "Moderne, plus grand"),
            ("Calibri", 26, "bold", "#2c3e50", "Professionnel"),
            ("Arial", 28, "bold", "#1abc9c", "Classique avec couleur verte"),
            ("Segoe UI Light", 32, "normal", "#2c3e50", "Léger et moderne"),
            ("Trebuchet MS", 26, "bold", "#3498db", "Dynamique bleu"),
            ("Verdana", 24, "bold", "#8e44ad", "Lisible violet"),
            ("Century Gothic", 26, "bold", "#e74c3c", "Géométrique rouge"),
            ("Segoe UI Semibold", 28, "normal", "#27ae60", "Semi-gras vert"),
            ("Tahoma", 26, "bold", "#f39c12", "Compact orange"),
            ("Georgia", 26, "bold", "#2c3e50", "Serif élégant"),
            ("Segoe UI", 28, "bold", "#9b59b6", "Moderne violet"),
        ]
        
        # Créer chaque proposition
        for i, (font_family, size, weight, color, description) in enumerate(self.proposals, 1):
            self.create_proposal(main_frame, i, font_family, size, weight, color, description)
        
        # Instructions
        instruction_frame = ttk.Frame(main_frame)
        instruction_frame.pack(pady=(20, 0), fill="x")
        
        ttk.Label(instruction_frame, 
                 text="Indiquez le numéro de votre proposition préférée à Claude!",
                 font=("Arial", 12, "italic")).pack()

    def create_proposal(self, parent, number, font_family, size, weight, color, description):
        """Créer une proposition avec numéro, exemple et description"""
        
        # Frame pour chaque proposition
        prop_frame = ttk.LabelFrame(parent, text=f"Proposition #{number}", padding=10)
        prop_frame.pack(fill="x", pady=5)
        
        # Affichage du titre avec le style proposé
        try:
            title_label = tk.Label(prop_frame, 
                                 text="Orlando Toolkit",
                                 font=(font_family, size, weight),
                                 fg=color)
            title_label.pack(pady=10)
        except tk.TclError:
            # Si la police n'est pas disponible, utiliser Arial par défaut
            title_label = tk.Label(prop_frame, 
                                 text="Orlando Toolkit (Police non disponible)",
                                 font=("Arial", size, weight),
                                 fg=color)
            title_label.pack(pady=10)
        
        # Description technique
        info_text = f"Police: {font_family} | Taille: {size} | Style: {weight} | Couleur: {color}"
        ttk.Label(prop_frame, text=info_text, font=("Arial", 9)).pack()
        
        # Description qualitative
        ttk.Label(prop_frame, text=description, 
                 font=("Arial", 10, "italic"), 
                 foreground="gray").pack(pady=(5, 0))

if __name__ == "__main__":
    root = tk.Tk()
    app = FontPreviewWindow(root)
    root.mainloop()