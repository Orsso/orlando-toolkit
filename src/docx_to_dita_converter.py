import os
import xml.etree.ElementTree as ET
import xml.dom.minidom
import re
import uuid
from datetime import datetime
from docx import Document
from docx.document import Document as _Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
import io
from PIL import Image
import logging

logger = logging.getLogger(__name__)

# --- Fonctions de Bas Niveau ---

def extract_and_save_images(doc, images_dir):
    """
    Extrait les images du document, les sauvegarde dans images_dir,
    et retourne un dictionnaire mappant leur ID interne (rId) à leur nouveau chemin.
    """
    image_map = {}
    image_counter = 1
    for rel_id, rel in doc.part.rels.items():
        if "image" in rel.target_ref:
            image_data = rel.target_part.blob
            try:
                img = Image.open(io.BytesIO(image_data))
                img_format = img.format.lower() if img.format else 'png'
                image_filename = f"image_{image_counter}.{img_format}"
                image_path = os.path.join(images_dir, image_filename)
                
                with open(image_path, "wb") as f:
                    f.write(image_data)
                
                image_map[rel_id] = image_path
                image_counter += 1
            except Exception as e:
                logger.error(f"Impossible de traiter une image : {e}", exc_info=True)
    return image_map

def slugify(text):
    """Crée un nom de fichier propre à partir d'un texte."""
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    text = re.sub(r'[-\s]+', '_', text)
    return text

def iter_block_items(parent):
    """
    Génère les objets Paragraph et Table d'un document ou d'une cellule de tableau, dans l'ordre.
    """
    if isinstance(parent, _Document):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError("Type de parent non supporté")

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)

def save_xml_file(element, path, doctype_str):
    """Sauvegarde un élément XML dans un fichier avec un formatage propre."""
    xml_str = ET.tostring(element, encoding='unicode', method='xml')
    dom = xml.dom.minidom.parseString(xml_str)
    
    pretty_xml_str = "\n".join(dom.toprettyxml(indent="  ").splitlines()[1:])

    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(f"{doctype_str}\n")
        f.write(pretty_xml_str)

# --- Fonctions de Création DITA ---

def create_dita_concept(title, topic_id, revision_date):
    """Crée une structure de base pour un concept DITA."""
    concept_root = ET.Element('concept', id=topic_id)
    title_elem = ET.SubElement(concept_root, 'title')
    title_elem.text = title
    
    prolog = ET.SubElement(concept_root, 'prolog')
    critdates = ET.SubElement(prolog, 'critdates')
    ET.SubElement(critdates, 'created', date=revision_date)
    ET.SubElement(critdates, 'revised', modified=revision_date)
    
    conbody = ET.SubElement(concept_root, 'conbody')
    return concept_root, conbody

def add_orlando_topicmeta(map_root, metadata):
    """Ajoute le bloc <topicmeta> spécifique à Orlando."""
    topicmeta = ET.Element('topicmeta')
    critdates = ET.SubElement(topicmeta, 'critdates')
    ET.SubElement(critdates, 'created', date=metadata.get('revision_date', ''))
    ET.SubElement(critdates, 'revised', modified=metadata.get('revision_date', ''))
    
    ET.SubElement(topicmeta, 'othermeta', attrib={'name': "manualCode", 'content': metadata.get('manual_code', '')})
    ET.SubElement(topicmeta, 'othermeta', attrib={'name': "manual_reference", 'content': metadata.get('manual_reference', '')})
    ET.SubElement(topicmeta, 'othermeta', attrib={'name': "revNumber", 'content': metadata.get('revision_number', '1.0')})
    ET.SubElement(topicmeta, 'othermeta', attrib={'name': "isRevNumberNull", 'content': "false"})
    
    title_element = map_root.find('title')
    if title_element is not None:
        children = list(map_root)
        index = children.index(title_element)
        map_root.insert(index + 1, topicmeta)
    else:
        map_root.insert(0, topicmeta)

def add_unique_ids(root_element):
    """Ajoute un ID unique à tous les éléments qui n'en ont pas."""
    for elem in root_element.iter():
        if 'id' not in elem.attrib:
            elem.set('id', str(uuid.uuid4()))

# --- Fonction Principale ---

def convert_docx_to_dita(file_path, output_dir, metadata):
    """
    Convertit un fichier DOCX en une structure de base DITA, en respectant la hiérarchie des titres.
    """
    logger.info(f"Début de la conversion DITA pour le fichier : {file_path}")
    
    os.makedirs(output_dir, exist_ok=True)
    images_dir = os.path.join(output_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)
    
    try:
        doc = Document(file_path)
        all_images_map = extract_and_save_images(doc, images_dir)

        map_root = ET.Element('map')
        map_root.set('title', metadata['manual_title'])

        # --- Logique de Hiérarchie ---
        heading_counters = [0] * 9  # Supporte jusqu'à 9 niveaux de titres
        parent_topicrefs = {0: map_root}
        # ---------------------------
        
        current_concept = None
        old_file_name = ""

        for block in iter_block_items(doc):
            if isinstance(block, Paragraph):
                style_name = block.style.name if block.style else 'Normal'
                text = block.text.strip()

                if style_name.startswith('Heading') and text:
                    if current_concept is not None:
                        doctype_str = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
                        save_xml_file(current_concept, os.path.join(output_dir, old_file_name), doctype_str)

                    try:
                        level = int(style_name.split(' ')[-1])
                    except (ValueError, IndexError):
                        level = 1
                    
                    # 1. Générer le numéro de section
                    heading_counters[level - 1] += 1
                    # Réinitialiser les compteurs des niveaux inférieurs
                    for i in range(level, len(heading_counters)):
                        heading_counters[i] = 0
                    number_str = ".".join(str(c) for c in heading_counters[:level] if c > 0)

                    # Créer le concept DITA (le fichier .dita)
                    current_concept = ET.Element('concept')
                    current_concept.set('id', slugify(text))
                    title_el = ET.SubElement(current_concept, 'title')
                    title_el.text = text # Titre sans numéro dans le fichier lui-même
                    
                    # 2. Construire la hiérarchie dans le Ditamap
                    parent_element = parent_topicrefs.get(level - 1, map_root)

                    file_name = f"{slugify(text)}.dita"
                    topicref = ET.SubElement(parent_element, 'topicref')
                    topicref.set('href', file_name)
                    topicref.set('navtitle', f"{number_str} {text}") # Titre avec numéro pour la navigation
                    
                    # Mettre à jour le parent pour le niveau actuel et supprimer les niveaux plus profonds
                    parent_topicrefs[level] = topicref
                    keys_to_delete = [l for l in parent_topicrefs if l > level]
                    for k in keys_to_delete:
                        del parent_topicrefs[k]
                    
                    old_file_name = file_name
                
                elif current_concept is not None:
                    # Gérer les images et le contenu de la section actuelle
                    body = current_concept.find('conbody')
                    if body is None:
                        body = ET.SubElement(current_concept, 'conbody')

                    p_element = ET.SubElement(body, 'p')
                    p_element.text = text
                    
                    for run in block.runs:
                        for r_id in run.element.xpath(".//@r:embed"):
                            if r_id in all_images_map:
                                img_path = all_images_map[r_id]
                                img_filename = os.path.basename(img_path)
                                
                                image_element = ET.SubElement(p_element, 'image')
                                # Le chemin d'accès doit être relatif au fichier DITA
                                image_element.set('href', os.path.join('images', img_filename))

        if current_concept is not None:
            doctype_str = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
            save_xml_file(current_concept, os.path.join(output_dir, old_file_name), doctype_str)
        
        ditamap_path = os.path.join(output_dir, 'map.ditamap')
        doctype_str = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'
        save_xml_file(map_root, ditamap_path, doctype_str)

    except Exception as e:
        logger.error(f"Erreur lors de la conversion DITA: {e}", exc_info=True)
        raise

    logger.info(f"Conversion DITA terminée avec succès pour le fichier : {file_path}") 