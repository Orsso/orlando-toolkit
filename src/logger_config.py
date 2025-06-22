import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Configure le logging pour l'application."""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, "app.log")

    # Créer un logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # Capture tout, du DEBUG à CRITICAL

    # Empêcher les logs de se propager au logger racine de base de Python
    logger.propagate = False

    # Supprimer les anciens handlers pour éviter les logs multiples
    if logger.hasHandlers():
        logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Handler pour le fichier avec rotation
    # 5MB par fichier, garde 5 fichiers en backup
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Handler pour la console (utile pour le développement)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO) # Affiche INFO et plus dans la console
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logging.info("===== Logging setup complete =====") 