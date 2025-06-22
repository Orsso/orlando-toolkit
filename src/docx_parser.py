# -*- coding: utf-8 -*-

"""
Module pour l'analyse de documents Word (.docx) en se basant sur le XML sous-jacent.

Ce module extrait la structure hiérarchique et la numérotation réelles des listes
en lisant les propriétés de formatage du document, plutôt que de se fier au texte brut.
"""

import os
import tempfile
import shutil
import logging
import docx
from docx.document import Document
from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)

def analyze_document_structure(docx_path):
    """
    Analyse un document DOCX pour en extraire la structure hiérarchique et les images.

    Args:
        docx_path (str): Le chemin vers le fichier .docx.

    Returns:
        dict: Un dictionnaire contenant les sections et le chemin vers le dossier des images.
    """
    output_folder = tempfile.mkdtemp(prefix="orlando_toolbox_")
    image_dir = os.path.join(output_folder, "images")
    os.makedirs(image_dir, exist_ok=True)
    
    doc = docx.Document(docx_path)
    
    # Mapper les rId des images à un chemin de fichier concret
    image_map = {}
    for rel_id, rel in doc.part.rels.items():
        if "image" in rel.target_ref:
            image_data = rel.target_part.blob
            image_path = os.path.join(image_dir, f"image_{len(image_map) + 1}.png")
            with open(image_path, "wb") as f:
                f.write(image_data)
            image_map[rel_id] = image_path

    sections = []
    current_section = None
    
    # Dictionnaire pour suivre les compteurs de chaque liste de numérotation (numId)
    numbering_counters = {}

    for p in doc.paragraphs:
        is_heading = False
        number = None
        level = 0
        title = p.text.strip()
        
        # Accéder au XML bas-niveau pour les propriétés de numérotation
        if p._p.pPr and p._p.pPr.numPr:
            is_heading = True
            numId = p._p.pPr.numPr.numId.val
            ilvl = p._p.pPr.numPr.ilvl.val
            level = ilvl + 1 # Niveau 1 pour ilvl=0

            if numId not in numbering_counters:
                # Initialiser les compteurs pour cette nouvelle liste
                numbering_counters[numId] = [0] * 10 # Supporte 10 niveaux
            
            # Incrémenter le compteur du niveau actuel
            numbering_counters[numId][ilvl] += 1
            # Réinitialiser les compteurs des niveaux inférieurs
            for i in range(ilvl + 1, 10):
                numbering_counters[numId][i] = 0
            
            # Construire la chaîne de numéro
            number = ".".join(str(c) for c in numbering_counters[numId][:ilvl + 1] if c > 0)

        if is_heading:
            if current_section:
                sections.append(current_section)
            
            current_section = {
                "title": title,
                "number": number,
                "level": level,
                "images": []
            }
        
        # Extraire les images du paragraphe et les lier à la section actuelle
        if current_section:
            for run in p.runs:
                for r_id in run.element.xpath(".//@r:embed"):
                    if r_id in image_map:
                        img_path = image_map[r_id]
                        if img_path not in current_section["images"]:
                            current_section["images"].append(img_path)
                            
    # Ajouter la dernière section si elle existe
    if current_section:
        sections.append(current_section)
    
    # Supprimer les sections vides qui n'ont ni titre ni image
    final_sections = [s for s in sections if s['title'] or s['images']]

    return {"sections": final_sections, "image_dir": image_dir, "dita_dir": None, "temp_dir": output_folder}

if __name__ == '__main__':
    # Cette section peut être utilisée pour des tests rapides pendant le développement.
    test_document_path = 'FOR002A - Feuille de Renseignement NewPN.docx'
    
    if os.path.exists(test_document_path):
        analysis_result = analyze_document_structure(test_document_path)
        if analysis_result:
            print("\n--- Résultat de l'Analyse (basé sur DITA) ---")
            for section in analysis_result.get('sections', []):
                indent = "  " * (section['level'] - 1)
                print(f"{indent}Section (Niv. {section['level']}): '{section['title']}' - Num: {section.get('number', 'N/A')}")
                for img_path in section['images']:
                    print(f"{indent}  - Image : {os.path.basename(img_path)}")
            print("---------------------------------------------\n")
    else:
        print(f"Fichier de test non trouvé : {test_document_path}")
        print("Veuillez vous assurer que le fichier est à la racine du projet.") 