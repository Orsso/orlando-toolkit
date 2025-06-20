import tkinter as tk
from orlando_dita_packager.ui.app import Application

if __name__ == '__main__':
    """
    Point d'entrée principal de l'application.
    Crée la fenêtre racine et lance l'interface utilisateur.
    """
    root = tk.Tk()
    app = Application(master=root)
    app.mainloop() 