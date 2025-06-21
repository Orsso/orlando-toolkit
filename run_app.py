import ttkbootstrap as ttk
from orlando_dita_packager.ui.app import Application
import sys

def set_dark_title_bar_on_windows(window):
    """
    Force la barre de titre de la fenêtre à utiliser le mode sombre sur Windows 11+.
    N'a aucun effet sur les autres systèmes d'exploitation.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            
            # Identifiant de l'attribut pour le mode sombre de la barre de titre
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            attribute = 20
            
            # Valeur '2' pour forcer le mode sombre. '0' pour le désactiver.
            value = 2

            # Obtenir le "handle" de la fenêtre (son identifiant pour Windows)
            hwnd = window.winfo_id()
            
            # Préparer les arguments pour l'appel à l'API
            attribute_ptr = ctypes.c_int(attribute)
            value_ptr = ctypes.c_int(value)

            # Appeler la fonction de l'API Windows
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                attribute_ptr,
                ctypes.byref(value_ptr),
                ctypes.sizeof(value_ptr)
            )
            
        except Exception as e:
            # En cas d'erreur (ex: version de Windows trop ancienne), on l'ignore.
            print(f"Avertissement : Impossible de définir le thème de la barre de titre. Erreur : {e}", file=sys.stderr)


if __name__ == '__main__':
    """
    Point d'entrée principal de l'application.
    Crée la fenêtre racine avec le thème 'darkly' et lance l'interface utilisateur.
    """
    root = ttk.Window(themename="darkly", size=(600, 430))
    
    # Appliquer le thème sombre à la barre de titre (Windows uniquement)
    set_dark_title_bar_on_windows(root)
    
    app = Application(master=root)
    app.mainloop() 