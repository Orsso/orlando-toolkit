# -*- coding: utf-8 -*-

"""
Point d'entrée principal pour le lancement de l'application OrlandoToolbox.
"""

import sys
import os
import tkinter as tk
import logging

# Ajouter le dossier 'src' au sys.path pour permettre les imports absolus
# depuis la racine du code source, peu importe d'où le script est lancé.
# Cela résout les problèmes d'ImportError avec les imports relatifs.
SRC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from logger_config import setup_logging
from main import OrlandoToolkit
from dtd_package import dtd_package_path

def main():
    """
    Configure le logging, la fenêtre principale, et lance l'application.
    """
    setup_logging()
    
    root = tk.Tk()
    root.title("Orlando Toolbox")
    root.geometry("1000x700")

    # Configuration de l'icône de l'application
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_path, 'assets', 'app_icon.png')
        if os.path.exists(icon_path):
            app_icon = tk.PhotoImage(file=icon_path)
            root.iconphoto(True, app_icon)
    except Exception as e:
        print(f"Avertissement : Impossible de charger l'icône : {e}")

    # Utiliser un thème moderne si disponible
    try:
        from sv_ttk import set_theme
        set_theme("dark")
    except ImportError:
        print("Avertissement : Le thème 'sv-ttk' n'est pas installé.")

    # Définir le chemin vers le package DTD
    dtd_package_path = os.path.join(SRC_PATH, 'dtd_package')
    
    app = OrlandoToolkit(root, dtd_path=dtd_package_path)
    
    root.mainloop()

if __name__ == '__main__':
    main()

    logging.info("===== Application terminée =====") 