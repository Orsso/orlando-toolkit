import logging
import os
import re
import shutil
import uuid
import io
import xml.dom.minidom
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import random

from docx import Document
from docx.document import Document as _Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from lxml import etree as ET
from PIL import Image

logger = logging.getLogger(__name__)

# --- Configuration du Mapping des Styles ---
# L'utilisateur devra remplir ce dictionnaire avec les noms de style
# de son document Word et la balise/outputclass DITA correspondante.
STYLE_MAP = {}

# --- Nouvel Objet de Contexte ---
@dataclass
class DitaContext:
    ditamap_root: Optional[ET.Element] = None
    topics: Dict[str, ET.Element] = field(default_factory=dict)
    images: Dict[str, bytes] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

# --- Fonctions de Bas Niveau ---

def extract_images_to_context(doc, context: DitaContext):
    """
    Extrait les images du document et les stocke dans l'objet de contexte.
    Retourne un map rId -> nom de fichier pour la conversion.
    """
    image_map_rid = {}
    image_counter = 1
    for rel_id, rel in doc.part.rels.items():
        if "image" in rel.target_ref:
            image_data = rel.target_part.blob
            try:
                img = Image.open(io.BytesIO(image_data))
                img_format = img.format.lower() if img.format else 'png'
                # Le nom de fichier sera finalisé plus tard, on utilise un nom temporaire
                image_filename = f"image_{image_counter}.{img_format}"
                context.images[image_filename] = image_data
                image_map_rid[rel_id] = image_filename
                image_counter += 1
            except Exception as e:
                logger.error(f"Impossible de traiter une image : {e}", exc_info=True)
    return image_map_rid

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

def save_xml_file(element, path, doctype_str, pretty=True):
    """
    Sauvegarde un élément XML dans un fichier.
    Le formatage est "pretty-print" par défaut, peut être désactivé.
    """
    xml_str_bytes = ET.tostring(element, pretty_print=pretty, xml_declaration=True, encoding='UTF-8', doctype=doctype_str)
    
    with open(path, "wb") as f:
        f.write(xml_str_bytes)

def save_minified_xml_file(element, path, doctype_str):
    """Sauvegarde un élément XML dans un fichier sur une seule ligne (minifié)."""
    # On utilise la librairie standard pour un contrôle plus simple de la sortie
    xml_str_bytes = ET.tostring(element, encoding='UTF-8')
    # On parse avec minidom pour ensuite sortir une chaîne minifiée
    dom = xml.dom.minidom.parseString(xml_str_bytes)
    # toxml() ajoute une déclaration XML par défaut, on la retire pour ne garder que le contenu.
    minified_content = ""
    if dom.documentElement:
        minified_content = dom.documentElement.toxml()
    
    full_content = f'<?xml version="1.0" encoding="UTF-8"?>{doctype_str}{minified_content}'

    with open(path, "w", encoding="utf-8") as f:
        f.write(full_content)

def generate_dita_id():
    """Génère un ID unique pour les éléments DITA."""
    return f"id-{uuid.uuid4()}"

# --- Fonctions de Création DITA ---

def create_dita_table(table: Table, image_map: Dict[str, str]) -> ET.Element:
    """Crée un élément de table DITA à partir d'un objet Table de docx."""
    dita_table = ET.Element('table', id=generate_dita_id())
    
    # L'attribut frame="all" est retiré pour correspondre à la nouvelle référence
    # dita_table.set('frame', 'all')

    tgroup = ET.SubElement(dita_table, 'tgroup', {
        'id': generate_dita_id(),
        'cols': str(len(table.columns))
        # Les attributs colsep et rowsep sont déplacés sur les 'entry' et 'colspec'
    })

    # Définir la largeur des colonnes
    for i in range(len(table.columns)):
        ET.SubElement(tgroup, 'colspec', {
            'id': generate_dita_id(),
            'colname': f'c{i+1}',
            'colwidth': '1*',
            'colsep': '1',
            'rowsep': '1'
        })

    # --- NOUVELLE LOGIQUE a THEAD/TBODY ---
    # La première ligne du tableau Word est traitée comme un <thead>
    header_row = table.rows[0]
    thead = ET.SubElement(tgroup, 'thead', id=generate_dita_id())
    row_element_head = ET.SubElement(thead, 'row', id=generate_dita_id())
    for cell in header_row.cells:
        entry = ET.SubElement(row_element_head, 'entry', id=generate_dita_id(), colsep='1', rowsep='1')
        for block in iter_block_items(cell):
            if isinstance(block, Paragraph):
                p_element = ET.SubElement(entry, 'p', id=generate_dita_id())
                process_paragraph_content_and_images(p_element, block, image_map, None)

    # Les autres lignes vont dans le <tbody>
    tbody = ET.SubElement(tgroup, 'tbody', id=generate_dita_id())
    for row in table.rows[1:]: # On commence à la deuxième ligne
        row_element = ET.SubElement(tbody, 'row', id=generate_dita_id())
        for cell in row.cells:
            entry = ET.SubElement(row_element, 'entry', id=generate_dita_id(), colsep='1', rowsep='1')
            # Traiter le contenu de la cellule
            for block in iter_block_items(cell):
                if isinstance(block, Paragraph):
                    p_element = ET.SubElement(entry, 'p', id=generate_dita_id())
                    process_paragraph_content_and_images(p_element, block, image_map, None)
    return dita_table

def create_dita_concept(title, topic_id, revision_date):
    """Crée une structure de base pour un concept DITA, sans prolog."""
    concept_root = ET.Element('concept', id=topic_id)
    title_elem = ET.SubElement(concept_root, 'title')
    title_elem.text = title
    
    # Le prolog n'est pas souhaité dans les topics de référence
    # prolog = ET.SubElement(concept_root, 'prolog')
    # critdates = ET.SubElement(prolog, 'critdates')
    # ET.SubElement(critdates, 'created', date=revision_date)
    # ET.SubElement(critdates, 'revised', modified=revision_date)
    
    conbody = ET.SubElement(concept_root, 'conbody')
    return concept_root, conbody

def add_orlando_topicmeta(map_root, metadata):
    """Ajoute le bloc <topicmeta> spécifique à Orlando."""
    topicmeta = ET.Element('topicmeta')
    critdates = ET.SubElement(topicmeta, 'critdates')
    rev_date = metadata.get('revision_date', datetime.now().strftime('%Y-%m-%d'))
    ET.SubElement(critdates, 'created', date=rev_date)
    ET.SubElement(critdates, 'revised', modified=rev_date)
    
    # Générer les codes et références s'ils sont absents
    manual_code = metadata.get('manual_code', '')
    if not manual_code:
        manual_code = slugify(metadata.get('manual_title', 'default_code'))
    
    manual_ref = metadata.get('manual_reference', '')
    if not manual_ref:
        manual_ref = slugify(metadata.get('manual_title', 'default_ref')).upper()
    
    ET.SubElement(topicmeta, 'othermeta', attrib={'name': "manualCode", 'content': manual_code})
    ET.SubElement(topicmeta, 'othermeta', attrib={'name': "manual_reference", 'content': manual_ref})
    ET.SubElement(topicmeta, 'othermeta', attrib={'name': "revNumber", 'content': metadata.get('revision_number', '1.0')})
    ET.SubElement(topicmeta, 'othermeta', attrib={'name': "isRevNumberNull", 'content': "false"})
    
    title_element = map_root.find('title')
    if title_element is not None:
        # Insérer après l'élément titre
        map_root.insert(list(map_root).index(title_element) + 1, topicmeta)
    else:
        # Insérer au début si pas de titre
        map_root.insert(0, topicmeta)

def process_paragraph_content_and_images(p_element, paragraph, image_map, conbody):
    """
    Traite le contenu d'un paragraphe en séparant les images du texte.
    Les images sont placées dans des paragraphes séparés après le texte.
    Si conbody est None (tableaux, listes), utilise le comportement original.
    """
    if conbody is None:
        # Dans les tableaux et listes, on garde le comportement original
        process_paragraph_runs(p_element, paragraph, image_map, exclude_images=False)
        return
    
    images_found = []
    
    # Collecter les images présentes dans le paragraphe
    for run in paragraph.runs:
        r_ids = run.element.xpath(".//@r:embed")
        if r_ids and r_ids[0] in image_map:
            img_filename = os.path.basename(image_map[r_ids[0]])
            images_found.append(img_filename)
    
    # Traiter le texte normalement (sans les images)
    process_paragraph_runs(p_element, paragraph, image_map, exclude_images=True)
    
    # Ajouter les images dans des paragraphes séparés seulement si conbody existe
    for img_filename in images_found:
        img_p = ET.SubElement(conbody, 'p', id=generate_dita_id(), outputclass='align-center')
        ET.SubElement(img_p, 'image', href=f'../media/{img_filename}', id=generate_dita_id())

def process_paragraph_runs(p_element, paragraph, image_map, exclude_images=False):
    """
    Reconstruit le contenu d'un paragraphe (texte, formatage, images) en préservant l'ordre.
    Si exclude_images=True, ignore les images (utilisé pour séparer texte et images).
    """
    last_element = None

    for run in paragraph.runs:
        # --- Gestion des images ---
        r_ids = run.element.xpath(".//@r:embed")
        if r_ids:
            if not exclude_images and r_ids[0] in image_map:
                img_filename = os.path.basename(image_map[r_ids[0]])
                image_element = ET.Element('image', href=f'../media/{img_filename}', id=generate_dita_id())
                p_element.append(image_element)
                last_element = image_element
            continue

        # --- Gestion du texte ---
        run_text = run.text
        if not run_text:
            continue

        # Gérer le formatage simple. Une gestion plus complexe
        # (imbrication, couleurs) nécessiterait une arborescence plus détaillée.
        target_element = None
        if run.bold:
            target_element = ET.Element('b', id=generate_dita_id())
        elif run.italic:
            target_element = ET.Element('i', id=generate_dita_id())
        elif run.underline:
            target_element = ET.Element('u', id=generate_dita_id())

        if target_element is not None:
            target_element.text = run_text
            p_element.append(target_element)
            last_element = target_element
        else:
            # Si c'est du texte normal
            if last_element is not None:
                last_element.tail = (last_element.tail or '') + run_text
            else:
                p_element.text = (p_element.text or '') + run_text

# --- Fonction Principale (Modifiée) ---
def convert_docx_to_dita(file_path: str, metadata: Dict[str, Any]) -> DitaContext:
    """
    Convertit un fichier DOCX en un objet DitaContext en mémoire.
    """
    logger.info(f"Début de la conversion en mémoire pour : {file_path}")
    context = DitaContext(metadata=metadata)
    
    try:
        doc = Document(file_path)
        all_images_map_rid = extract_images_to_context(doc, context)

        # --- Forçage du code manuel pour le débogage ---
        # On ignore le titre du fichier pour correspondre à la référence
        # context.metadata['manual_code'] = "PROCBEO001"  # SUPPRIMÉ
        # ---------------------------------------------

        map_root = ET.Element('map')
        # L'attribut xml:lang est un cas spécial qui doit être défini avec son namespace complet
        map_root.set('{http://www.w3.org/XML/1998/namespace}lang', 'en-US')
        context.ditamap_root = map_root

        map_title = ET.SubElement(map_root, 'title')
        # Correction: Utiliser le titre des métadonnées fournies par l'UI
        map_title.text = metadata.get('manual_title', 'Titre du document')
        
        add_orlando_topicmeta(map_root, context.metadata)

        # --- Logique de Hiérarchie ---
        heading_counters = [0] * 9  # Supporte jusqu'à 9 niveaux de titres
        # On ne stocke plus des topicrefs mais les éléments parents (map, topichead, topicref)
        parent_elements = {0: map_root} 
        # ---------------------------
        
        current_concept = None
        old_file_name = ""
        current_conbody = None
        current_list = None # Pour suivre la liste <ol> ou <ul> en cours
        current_sl = None # Pour suivre la liste <sl> d'images en cours

        for block in iter_block_items(doc):
            if isinstance(block, Table):
                if current_conbody is None: continue
                current_list = None # Un tableau arrête les listes
                current_sl = None

                # La référence montre la table dans un <p>
                p_for_table = ET.SubElement(current_conbody, 'p', id=generate_dita_id())
                dita_table = create_dita_table(block, all_images_map_rid)
                p_for_table.append(dita_table)

            elif isinstance(block, Paragraph):
                style_name = ""
                if block.style and block.style.name:
                    style_name = block.style.name
                
                is_list_item = block._p.pPr is not None and block._p.pPr.numPr is not None
                is_heading = style_name.startswith('Heading')
                text = block.text.strip()
                is_image_para = any(run.element.xpath(".//@r:embed") for run in block.runs) and not text

                if is_heading and text:
                    current_list = None
                    current_sl = None
                    level = int(style_name.split(' ')[-1])

                    if current_concept is not None:
                        # add_unique_ids(current_concept) # On ne veut plus d'ID partout
                        context.topics[old_file_name] = current_concept

                    # --- Toute la logique de titre doit être ICI ---
                    # 1. Générer le numéro de section pour tocIndex
                    heading_counters[level - 1] += 1
                    for i in range(level, len(heading_counters)):
                        heading_counters[i] = 0
                    toc_index = ".".join(str(c) for c in heading_counters[:level] if c > 0)

                    # 2. Logique de Ditamap avec <topichead>
                    parent_level = level - 1
                    parent_element = parent_elements.get(parent_level, map_root)
                    
                    if level == 1: # Les titres de niveau 1 sont des conteneurs
                        current_container = ET.SubElement(parent_element, 'topichead')
                        topicmeta = ET.SubElement(current_container, 'topicmeta')
                        navtitle = ET.SubElement(topicmeta, 'navtitle')
                        navtitle.text = text
                        # Ajout des éléments manquants
                        critdates = ET.SubElement(topicmeta, 'critdates')
                        ET.SubElement(critdates, 'created', date=context.metadata.get('revision_date'))
                        ET.SubElement(critdates, 'revised', modified=context.metadata.get('revision_date'))
                        ET.SubElement(topicmeta, 'metadata') # Metadata vide
                        ET.SubElement(topicmeta, 'othermeta', name='tocIndex', content=toc_index)
                        parent_elements[level] = current_container
                    
                    # 3. Création du fichier de topic dans tous les cas
                    # --- Nomenclature temporaire des topics ---
                    file_name = f"topic_{uuid.uuid4().hex[:10]}.dita"
                    topic_id = file_name.replace('.dita', '')
                    # ------------------------------------------
                    
                    current_concept, current_conbody = create_dita_concept(
                        text, 
                        topic_id,
                        context.metadata.get('revision_date', datetime.now().strftime('%Y-%m-%d'))
                    )
                    
                    if level > 1:
                        topicref = ET.SubElement(parent_element, 'topicref', {
                            'href': f'topics/{file_name}',
                            'locktitle': 'yes'
                        })
                        topicmeta_ref = ET.SubElement(topicref, 'topicmeta')
                        navtitle_ref = ET.SubElement(topicmeta_ref, 'navtitle')
                        navtitle_ref.text = text
                        # Ajout des éléments manquants
                        critdates_ref = ET.SubElement(topicmeta_ref, 'critdates')
                        ET.SubElement(critdates_ref, 'created', date=context.metadata.get('revision_date'))
                        ET.SubElement(critdates_ref, 'revised', modified=context.metadata.get('revision_date'))
                        ET.SubElement(topicmeta_ref, 'metadata') # Metadata vide
                        ET.SubElement(topicmeta_ref, 'othermeta', name='tocIndex', content=toc_index)
                        ET.SubElement(topicmeta_ref, 'othermeta', name='foldout', content='false')
                        ET.SubElement(topicmeta_ref, 'othermeta', name='tdm', content='false')
                        parent_elements[level] = topicref
                    
                    # 4. Réinitialisation
                    keys_to_delete = [l for l in parent_elements if l > level]
                    for k in keys_to_delete:
                        del parent_elements[k]
                    
                    old_file_name = file_name
                
                # --- NOUVELLE LOGIQUE POUR LE CONTENU ---
                elif current_conbody is not None:
                    # A. Gestion des paragraphes contenant uniquement une image
                    if is_image_para:
                        current_list = None # Une image arrête une liste normale
                        if current_sl is None:
                            current_sl = ET.SubElement(current_conbody, 'sl', id=generate_dita_id())
                        
                        sli = ET.SubElement(current_sl, 'sli', id=generate_dita_id())
                        # L'image est dans un <p> dans le docx, mais on la veut directement dans le <sli>
                        for run in block.runs:
                            r_ids = run.element.xpath(".//@r:embed")
                            if r_ids and r_ids[0] in all_images_map_rid:
                                img_filename = os.path.basename(all_images_map_rid[r_ids[0]])
                                ET.SubElement(sli, 'image', href=f'../media/{img_filename}', id=generate_dita_id())
                                break # On suppose une seule image par paragraphe

                    # B. Gestion des listes à puces/numéros
                    elif is_list_item:
                        current_sl = None # Une liste normale arrête une liste d'images
                        list_style = 'ul' 
                        if current_list is None or current_list.tag != list_style:
                            current_list = ET.SubElement(current_conbody, list_style, id=generate_dita_id())
                        
                        li = ET.SubElement(current_list, 'li', id=generate_dita_id())
                        p_in_li = ET.SubElement(li, 'p', id=generate_dita_id())
                        process_paragraph_content_and_images(p_in_li, block, all_images_map_rid, None)

                    # C. Gestion du texte et paragraphes normaux
                    else:
                        current_list = None # Un paragraphe normal arrête les listes
                        current_sl = None
                        
                        # Ignorer les paragraphes totalement vides
                        if not text:
                            continue

                        p_element = ET.SubElement(current_conbody, 'p', id=generate_dita_id())
                        
                        # Appliquer les outputclass (align, roundedbox, etc.)
                        apply_paragraph_formatting(p_element, block)
                        
                        process_paragraph_content_and_images(p_element, block, all_images_map_rid, current_conbody)

        if current_concept is not None:
            # add_unique_ids(current_concept) # On ne veut plus d'ID partout
            context.topics[old_file_name] = current_concept # Sauvegarde du dernier topic
        
        # add_unique_ids(map_root) # On ne veut plus d'ID partout

    except Exception as e:
        logger.error(f"Erreur lors de la conversion en mémoire: {e}", exc_info=True)
        raise

    logger.info(f"Conversion en mémoire terminée avec succès.")
    return context

def apply_paragraph_formatting(p_element, paragraph):
    """Applique les classes de formatage (outputclass) à un élément <p>."""
    classes = []
    # 1. Alignement
    if paragraph.alignment:
        if paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER:
            classes.append('align-center')
        elif paragraph.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
            classes.append('align-justify')
    
    # 2. Ombrage (pour roundedbox)
    p_pr = paragraph._p.pPr
    if p_pr is not None:
        shd = p_pr.find(qn('w:shd'))
        if shd is not None and shd.attrib.get(qn('w:fill')) == 'F2F2F2':
            classes.append('roundedbox')
    
    if classes:
        p_element.set('outputclass', " ".join(classes))

# --- Nouvelle Fonction de Sauvegarde ---
def save_dita_package(context: DitaContext, output_dir: str):
    """
    Sauvegarde le contenu d'un DitaContext dans une structure de dossiers sur le disque.
    """
    logger.info(f"Sauvegarde du package DITA dans : {output_dir}")
    
    data_dir = os.path.join(output_dir, 'DATA')
    topics_dir = os.path.join(data_dir, 'topics')
    media_dir = os.path.join(data_dir, 'media')
    dtd_dir = os.path.join(data_dir, 'dtd')
    os.makedirs(topics_dir, exist_ok=True)
    os.makedirs(media_dir, exist_ok=True)
    
    # Copie des DTDs en ignorant les fichiers et dossiers Python
    reference_dtd_dir = os.path.join('src', 'dtd_package')
    if os.path.exists(reference_dtd_dir):
        ignore_patterns = shutil.ignore_patterns('__pycache__', '*.pyc', '__init__.py')
        shutil.copytree(reference_dtd_dir, dtd_dir, dirs_exist_ok=True, ignore=ignore_patterns)
    else:
        logger.warning(f"Dossier DTD de référence non trouvé : {reference_dtd_dir}")

    # Si le code manuel n'est pas défini, on le dérive du titre.
    if not context.metadata.get('manual_code'):
        title = context.metadata.get('manual_title', 'default_title')
        context.metadata['manual_code'] = slugify(title)

    # Sauvegarde du Ditamap (pretty-printed)
    manual_code = context.metadata.get('manual_code')
    ditamap_path = os.path.join(data_dir, f'{manual_code}.ditamap')
    doctype_str = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "./dtd/technicalContent/dtd/map.dtd">'
    save_xml_file(context.ditamap_root, ditamap_path, doctype_str)

    # Création et sauvegarde du fichier .ditaval
    ditaval_path = os.path.join(data_dir, f'{manual_code}.ditaval')
    ditaval_content = """<?xml version="1.0" encoding="UTF-8"?>
<val>
  <revprop val="20250528" action="flag" changebar="solid" color="#32cd32"/>
  <revprop val="20250528-tr" action="flag" changebar="dotted" color="#32cd32"/>
</val>
"""
    with open(ditaval_path, "w", encoding="utf-8") as f:
        f.write(ditaval_content)

    # Sauvegarde des Topics (minifiés)
    doctype_str_concept = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "../dtd/technicalContent/dtd/concept.dtd">'
    for filename, topic_element in context.topics.items():
        topic_path = os.path.join(topics_dir, filename)
        save_minified_xml_file(topic_element, topic_path, doctype_str_concept)

    # Sauvegarde des Images
    for filename, image_data in context.images.items():
        image_path = os.path.join(media_dir, filename)
        with open(image_path, "wb") as f:
            f.write(image_data)
            
    logger.info("Sauvegarde du package DITA terminée.")

def update_image_references_and_names(context: DitaContext):
    """
    Met à jour les noms de fichiers des images dans le contexte selon la nomenclature,
    et met à jour les références <image href="..."> dans tous les topics.
    """
    logger.info("Mise à jour des noms et des références d'images...")
    
    new_images_dict = {}
    manual_code = context.metadata.get('manual_code', 'MANUAL')
    prefix = context.metadata.get('prefix', 'IMG')
    
    # Étape 1: Créer une map de renommage (ancien nom -> nouveau nom)
    rename_map = {}
    for i, original_filename in enumerate(context.images.keys()):
        # TODO: Avoir la vraie section plus tard. On utilise 0 pour l'instant.
        section_num = "0" 
        img_num = i + 1
        extension = os.path.splitext(original_filename)[1]
        
        new_filename = f"{prefix}-{manual_code}-{section_num}-{img_num}{extension}"
        rename_map[original_filename] = new_filename

    # Étape 2: Mettre à jour les href dans tous les topics
    for topic_element in context.topics.values():
        for image_tag in topic_element.iter('image'):
            original_href = image_tag.get('href')
            if original_href:
                original_basename = os.path.basename(original_href)
                if original_basename in rename_map:
                    new_basename = rename_map[original_basename]
                    image_tag.set('href', f'../media/{new_basename}')

    # Étape 3: Créer le nouveau dictionnaire d'images avec les noms de fichiers mis à jour
    for original_filename, image_data in context.images.items():
        if original_filename in rename_map:
            new_filename = rename_map[original_filename]
            new_images_dict[new_filename] = image_data
        else:
            new_images_dict[original_filename] = image_data # Conserver si non trouvé (ne devrait pas arriver)
            
    context.images = new_images_dict
    logger.info("Mise à jour des images terminée.")
    return context

def update_topic_references_and_names(context: DitaContext):
    """
    Met à jour les noms des fichiers topics et les références href dans le Ditamap
    en utilisant les métadonnées finales.
    """
    logger.info("Mise à jour des noms et des références de topics (logique dépréciée conservée pour la structure)...")
    if not context.ditamap_root:
        return context

    # Le nommage ne dépend plus de 'manual_code' ou 'fleet'
    # Il se base sur des UUIDs temporaires qui sont ensuite remplacés.
    # Cette fonction pourrait être revue si un nommage plus sémantique est nécessaire.
    
    new_topics_dict = {}
    
    # On itère sur une copie car on modifie le dict
    original_topics = list(context.topics.items()) 

    for old_filename, topic_element in original_topics:
        # Le nommage final est maintenant plus simple.
        # On pourrait se baser sur le slug du titre du topic si on voulait un nom lisible.
        new_filename = f"topic_{uuid.uuid4().hex[:12]}.dita"
        
        # Mettre à jour l'ID du topic lui-même
        topic_element.set('id', new_filename.replace('.dita', ''))

        # Mettre à jour la référence dans le Ditamap
        topicref = context.ditamap_root.find(f".//topicref[@href='topics/{old_filename}']")
        if topicref is not None:
            topicref.set('href', f'topics/{new_filename}')
        
        # Ajouter au nouveau dictionnaire avec le nouveau nom
        new_topics_dict[new_filename] = topic_element

    context.topics = new_topics_dict
    logger.info("Mise à jour des topics terminée.")
    return context 