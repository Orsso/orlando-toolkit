import ttkbootstrap as ttk
from orlando_dita_packager.ui.app import Application

if __name__ == '__main__':
    """
    Point d'entrée principal de l'application.
    Crée la fenêtre racine avec le thème 'darkly' et lance l'interface utilisateur.
    """
    root = ttk.Window(themename="darkly", size=(600, 430))
    app = Application(master=root)
    app.mainloop() 