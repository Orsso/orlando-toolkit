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

from src.style_analyzer import build_style_heading_map

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
    """Yield Paragraph and Table objects in the order they appear, **recursively**.

    Word documents like *Easy Access …* wrap sections in content controls
    (`<w:sdt>`).  These extra XML layers prevent the previous implementation
    (which only looked at direct children of the body) from seeing the real
    paragraphs.  We now traverse recursively so that paragraphs and tables
    nested in any container are discovered.
    """

    if isinstance(parent, _Document):
        root_elm = parent.element.body
        parent_obj = parent  # _Document for Paragraph/Table constructors
    elif isinstance(parent, _Cell):
        root_elm = parent._tc
        parent_obj = parent  # _Cell
    else:
        raise ValueError("Unsupported parent type for iter_block_items")

    def _walk(element):
        for child in element.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent_obj)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent_obj)
            else:
                # Recurse into unknown containers (e.g., w:sdt, w:txbxContent)
                yield from _walk(child)

    yield from _walk(root_elm)

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

def convert_color_to_outputclass(color_value):
    """
    Convertit une couleur (hex, theme, etc.) en classe outputclass Orlando.
    Ne retourne que les couleurs supportées par Orlando : color-red et color-green pour l'instant.
    """
    if not color_value:
        return None
    
    # Mapping STRICT des couleurs vers les classes Orlando confirmées
    color_mappings = {
        # Rouge - différentes nuances (Word utilise souvent des nuances spécifiques)
        '#ff0000': 'color-red',  # Rouge pur
        '#dc143c': 'color-red',  # Crimson
        '#b22222': 'color-red',  # FireBrick
        '#8b0000': 'color-red',  # DarkRed
        '#ff4500': 'color-red',  # OrangeRed
        '#cd5c5c': 'color-red',  # IndianRed
        '#c0504d': 'color-red',  # Rouge de thème Word fréquent
        '#da0000': 'color-red',  # Rouge vif utilisé par Word
        '#ff1d1d': 'color-red',  # Rouge clair de Word
        '#8b0000': 'color-red',  # Rouge sombre
        '#a60000': 'color-red',  # Rouge moyen
        '#cc0000': 'color-red',  # Rouge standard
        '#800000': 'color-red',  # Maroon
        '#e74c3c': 'color-red',  # Rouge moderne
        '#ee0000': 'color-red',  # Rouge détecté dans vos logs
        
        # Vert - différentes nuances (Word utilise souvent des nuances spécifiques)
        '#008000': 'color-green',  # Vert standard
        '#00ff00': 'color-green',  # Lime
        '#32cd32': 'color-green',  # LimeGreen
        '#228b22': 'color-green',  # ForestGreen
        '#006400': 'color-green',  # DarkGreen
        '#adff2f': 'color-green',  # GreenYellow
        '#9acd32': 'color-green',  # YellowGreen
        '#00b050': 'color-green',  # Vert de thème Word fréquent
        '#00a300': 'color-green',  # Vert vif utilisé par Word
        '#1d7d1d': 'color-green',  # Vert sombre de Word
        '#2e8b57': 'color-green',  # SeaGreen
        '#27ae60': 'color-green',  # Vert moderne
    }
    
    # Convertir en minuscules pour la comparaison
    color_lower = color_value.lower()
    
    # Vérifier les couleurs hex exactes
    if color_lower in color_mappings:
        return color_mappings[color_lower]
    
    # Pour les couleurs de thème, mapper vers rouge/vert si possible
    if color_value.startswith('theme-'):
        theme_name = color_value[6:]  # Enlever "theme-"
        # Mapping conservateur : seulement les thèmes qu'on peut mapper vers rouge/vert
        theme_mappings = {
            'accent_1': 'color-red',    # Souvent rouge dans les thèmes
            'accent_6': 'color-green',  # Souvent vert dans les thèmes
        }
        return theme_mappings.get(theme_name, None)  # Retourne None si pas supporté
    
    # Pour les couleurs inconnues, essayer de déduire rouge ou vert
    if color_lower.startswith('#'):
        try:
            r = int(color_lower[1:3], 16)
            g = int(color_lower[3:5], 16) 
            b = int(color_lower[5:7], 16)
            
            # Critères plus souples pour détecter rouge ou vert
            # Rouge : composant rouge dominant (critères assouplis)
            if r > g and r > b and r > 100:  # Rouge dominant et suffisamment intense
                # Vérifier que c'est bien du rouge et pas de l'orange/jaune
                if r > g + 20 or g < 150:  # Éviter les oranges/jaunes
                    return 'color-red'
            
            # Vert : composant vert dominant (critères assouplis)
            if g > r and g > b and g > 100:  # Vert dominant et suffisamment intense
                # Vérifier que c'est bien du vert et pas du cyan/jaune
                if g > r + 20 or r < 150:  # Éviter les cyans/jaunes
                    return 'color-green'
                    
        except ValueError:
            pass
    
    # Si on ne peut pas mapper vers rouge/vert, ne pas appliquer de couleur
    return None

# --- Fonctions de Création DITA ---

def create_dita_table(table: Table, image_map: Dict[str, str]) -> ET.Element:
    """Create a CALS DITA table from *table* handling complex merges (grid reconstruction)."""

    from docx.oxml.ns import qn as _qn
    from dataclasses import dataclass

    def _grid_span(tc):
        gs = tc.tcPr.find(_qn('w:gridSpan')) if tc.tcPr is not None else None
        return int(gs.get(_qn('w:val'))) if gs is not None else 1

    def _vmerge_type(tc):
        vm = tc.tcPr.find(_qn('w:vMerge')) if tc.tcPr is not None else None
        if vm is None:
            return None  # no vertical merge
        val = vm.get(_qn('w:val'))
        return 'restart' if val in ('restart', 'Restart') else 'continue'

    @dataclass
    class CellInfo:
        cell: _Cell  # python-docx cell object for content extraction
        rowspan: int = 1
        colspan: int = 1
        is_start: bool = True

    # ---------- build logical grid --------------------------------------
    grid: list[list[CellInfo | None]] = []
    vertical_tracker: dict[int, CellInfo] = {}
    max_cols = len(table.columns)

    for r_idx, row in enumerate(table.rows):
        grid_row: list[CellInfo | None] = [None] * max_cols
        c_idx = 0
        phys_idx = 0  # index in row.cells (physical order)
        for tc in row._tr.tc_lst:
            # Skip filled columns (due to previous rowspans)
            while c_idx < max_cols and grid_row[c_idx] is not None:
                c_idx += 1
            if c_idx >= max_cols:
                break

            colspan = _grid_span(tc)
            v_type = _vmerge_type(tc)

            if v_type == 'continue':
                # Link to tracker from previous row
                if c_idx in vertical_tracker:
                    starter = vertical_tracker[c_idx]
                    starter.rowspan += 1
                # Mark placeholders
                for span_col in range(colspan):
                    if c_idx + span_col < max_cols:
                        grid_row[c_idx + span_col] = None
                c_idx += colspan
                phys_idx += colspan
                continue

            # New cell (normal or vertical restart)
            cell_info = CellInfo(cell=row.cells[phys_idx], colspan=colspan)
            # Register for vertical continuation
            if v_type == 'restart':
                vertical_tracker[c_idx] = cell_info
            else:
                # clear tracker for this column if no continuation
                vertical_tracker.pop(c_idx, None)

            for span_col in range(colspan):
                if c_idx + span_col < max_cols:
                    grid_row[c_idx + span_col] = cell_info if span_col == 0 else None
            c_idx += colspan
            phys_idx += 1

        # Clean trackers when no continue in this row
        for col_key in list(vertical_tracker.keys()):
            if grid_row[col_key] is not None:  # we placed a real cell here
                continue  # still a restart
            # else continuation expected next row
        grid.append(grid_row)

    # ---------- emit CALS ----------------------------------------------
    dita_table = ET.Element('table', id=generate_dita_id())
    tgroup = ET.SubElement(dita_table, 'tgroup', id=generate_dita_id(), cols=str(max_cols))
    for idx in range(max_cols):
        ET.SubElement(
            tgroup,
            'colspec',
            id=generate_dita_id(),
            colname=f'c{idx+1}',
            colwidth='1*',
            colsep='1',
            rowsep='1',
        )

    thead = ET.SubElement(tgroup, 'thead', id=generate_dita_id())
    tbody = ET.SubElement(tgroup, 'tbody', id=generate_dita_id())

    for r_idx, grid_row in enumerate(grid):
        # Determine if this row has any starting cells
        starters = [ci for ci in grid_row if ci and ci.is_start]
        if not starters:
            continue  # skip empty logical rows

        row_parent = thead if r_idx == 0 else tbody
        row_el = ET.SubElement(row_parent, 'row', id=generate_dita_id())

        col_position = 0
        for c_idx, ci in enumerate(grid_row):
            if ci is None or not ci.is_start:
                continue
            attrs = {'id': generate_dita_id(), 'colsep': '1', 'rowsep': '1'}
            if ci.colspan > 1:
                attrs['namest'] = f'c{c_idx+1}'
                attrs['nameend'] = f'c{c_idx+ci.colspan}'
            if ci.rowspan > 1:
                attrs['morerows'] = str(ci.rowspan - 1)

            entry_el = ET.SubElement(row_el, 'entry', attrs)
            for block in iter_block_items(ci.cell):
                if isinstance(block, Paragraph):
                    p_el = ET.SubElement(entry_el, 'p', id=generate_dita_id())
                    process_paragraph_content_and_images(p_el, block, image_map, None)

    # Ensure tbody not empty
    if not tbody.findall('row'):
        r = ET.SubElement(tbody, 'row', id=generate_dita_id())
        ET.SubElement(r, 'entry', id=generate_dita_id())

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
    Reconstruit le contenu d'un paragraphe (texte, formatage, images, hyperliens) en préservant l'ordre.
    Si exclude_images=True, ignore les images (utilisé pour séparer texte et images).
    Gère maintenant les formatages multiples, les hyperliens et consolide les runs adjacents identiques.
    """
    last_element = None
    
    # Utiliser iter_inner_content() pour gérer les hyperliens
    try:
        content_items = list(paragraph.iter_inner_content())
    except AttributeError:
        # Fallback pour les versions plus anciennes de python-docx
        content_items = paragraph.runs
    
    # Traiter chaque élément dans l'ordre séquentiel
    # Grouper les runs adjacents pour éviter la fragmentation
    current_group = []
    current_formatting = None

    def process_current_group():
        """Traite et ajoute le groupe de runs en cours"""
        nonlocal last_element, current_group, current_formatting
        
        if not current_group:
            return
            
        consolidated_text = ''.join(current_group)
        
        # Extraire le formatage et la couleur
        formatting_tuple = current_formatting[0] if current_formatting else ()
        run_color = current_formatting[1] if current_formatting and len(current_formatting) > 1 else None
        
        if formatting_tuple or run_color:
            # Créer l'imbrication des formatages
            # Si on a une couleur, on commence par un <ph> avec style
            target_element = None
            innermost_element = None
            
            # Si on a une couleur, créer un élément <ph> au niveau le plus haut
            if run_color:
                target_element = ET.Element('ph', id=generate_dita_id())
                target_element.set('class', '- topic/ph ')
                # Utiliser outputclass au lieu de style pour Orlando
                color_class = convert_color_to_outputclass(run_color)
                if color_class:
                    target_element.set('outputclass', color_class)
                innermost_element = target_element
            
            # Créer l'imbrication des formatages à l'intérieur du <ph> (ordre : bold > italic > underline)
            if 'bold' in formatting_tuple:
                bold_element = ET.Element('b', id=generate_dita_id())
                bold_element.set('class', '+ topic/ph hi-d/b ')
                if innermost_element is not None:
                    innermost_element.append(bold_element)
                    innermost_element = bold_element
                else:
                    target_element = bold_element
                    innermost_element = bold_element
            
            if 'italic' in formatting_tuple:
                italic_element = ET.Element('i', id=generate_dita_id())
                italic_element.set('class', '+ topic/ph hi-d/i ')
                if innermost_element is not None:
                    innermost_element.append(italic_element)
                    innermost_element = italic_element
                else:
                    target_element = italic_element
                    innermost_element = italic_element
            
            if 'underline' in formatting_tuple:
                underline_element = ET.Element('u', id=generate_dita_id())
                underline_element.set('class', '+ topic/ph hi-d/u ')
                if innermost_element is not None:
                    innermost_element.append(underline_element)
                    innermost_element = underline_element
                else:
                    target_element = underline_element
                    innermost_element = underline_element
            
            # Ajouter le texte à l'élément le plus profond
            if innermost_element is not None:
                innermost_element.text = consolidated_text
                p_element.append(target_element)
                last_element = target_element
        else:
            # Texte sans formatage
            if last_element is not None:
                last_element.tail = (last_element.tail or '') + consolidated_text
            else:
                p_element.text = (p_element.text or '') + consolidated_text
        
        # Réinitialiser le groupe
        current_group = []
        current_formatting = None

    for item in content_items:
        # Gérer les hyperliens
        if hasattr(item, 'address'):  # C'est un hyperlink
            # Finaliser le groupe en cours avant l'hyperlien
            process_current_group()
            
            # Créer l'élément xref pour l'hyperlien
            if item.address or item.url:  # Liens externes ou avec URL
                xref_element = ET.Element('xref', id=generate_dita_id())
                xref_element.set('class', '- topic/xref ')
                xref_element.set('format', 'html')
                xref_element.set('scope', 'external')
                xref_element.set('href', item.url or item.address)
                xref_element.text = item.text
                
                # Ajouter l'hyperlien à la bonne position
                if last_element is not None:
                    # Utiliser l'attribut tail pour placer l'hyperlien après l'élément précédent
                    # Mais comme c'est un élément, on doit l'insérer dans le parent
                    p_element.append(xref_element)
                else:
                    p_element.append(xref_element)
                last_element = xref_element
            else:
                # Lien interne (fragment seulement), traiter comme du texte normal
                if last_element is not None:
                    last_element.tail = (last_element.tail or '') + item.text
                else:
                    p_element.text = (p_element.text or '') + item.text
            continue
        
        # Si ce n'est pas un hyperlien, c'est un run normal
        run = item
        # --- Gestion des images ---
        r_ids = run.element.xpath(".//@r:embed")
        if r_ids:
            # Finaliser le groupe en cours avant l'image
            process_current_group()
            
            # Ajouter l'image comme élément isolé
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

        # Identifier tous les formatages du run
        run_formatting = []
        if run.bold:
            run_formatting.append('bold')
        if run.italic:
            run_formatting.append('italic')  
        if run.underline:
            run_formatting.append('underline')
            
        # Gestion des couleurs de texte
        run_color = None
        try:
            if run.font.color.type is not None:
                if run.font.color.type == 1:  # MSO_COLOR_TYPE.RGB
                    rgb = run.font.color.rgb
                    if rgb is not None:
                        # Méthode d'extraction robuste pour RGBColor
                        try:
                            # Méthode 1: Utiliser l'API interne de l'objet RGBColor
                            if hasattr(rgb, '_color_val'):
                                color_val = rgb._color_val
                                if color_val is not None:
                                    r = (color_val >> 16) & 0xFF
                                    g = (color_val >> 8) & 0xFF
                                    b = color_val & 0xFF
                                    run_color = f"#{r:02x}{g:02x}{b:02x}"
                        except Exception:
                            pass
                        
                        # Méthode 2: Parsing de la représentation string
                        if run_color is None:
                            try:
                                rgb_str = str(rgb)
                                
                                # Cas 1: Format RGBColor(0x.., 0x.., 0x..)
                                hex_match = re.search(r'RGBColor\(0x([0-9a-fA-F]+),\s*0x([0-9a-fA-F]+),\s*0x([0-9a-fA-F]+)\)', rgb_str)
                                if hex_match:
                                    r, g, b = [int(val, 16) for val in hex_match.groups()]
                                    run_color = f"#{r:02x}{g:02x}{b:02x}"
                                else:
                                    # Cas 2: Format direct comme "EE0000" (6 caractères hex)
                                    if re.match(r'^[0-9a-fA-F]{6}$', rgb_str):
                                        run_color = f"#{rgb_str.lower()}"
                                    # Cas 3: Format avec préfixe comme "0xEE0000"
                                    elif rgb_str.startswith('0x') and len(rgb_str) == 8:
                                        run_color = f"#{rgb_str[2:].lower()}"
                                        
                            except Exception:
                                pass
                        
                        # Méthode 3: Essayer d'accéder directement aux propriétés
                        if run_color is None:
                            try:
                                for attr_set in [('red', 'green', 'blue'), ('r', 'g', 'b')]:
                                    if all(hasattr(rgb, attr) for attr in attr_set):
                                        r = getattr(rgb, attr_set[0])
                                        g = getattr(rgb, attr_set[1])
                                        b = getattr(rgb, attr_set[2])
                                        run_color = f"#{r:02x}{g:02x}{b:02x}"
                                        break
                            except Exception:
                                pass
                                
                elif run.font.color.type == 2:  # MSO_COLOR_TYPE.THEME
                    # Pour les couleurs de thème
                    theme_color = getattr(run.font.color, 'theme_color', None)
                    if theme_color is not None:
                        # Nettoyer la valeur theme_color qui peut contenir des parenthèses et espaces
                        theme_str = str(theme_color)
                        # Extraire juste le nom de la couleur avant les parenthèses
                        theme_name = theme_str.split(' ')[0] if ' ' in theme_str else theme_str
                        # Convertir en minuscules pour la classe CSS
                        run_color = f"theme-{theme_name.lower()}"
                        
        except Exception:
            # Ne pas faire crasher la conversion en cas d'erreur de couleur
            pass
        
        # Convertir en tuple pour pouvoir comparer (inclure la couleur)
        run_formatting_tuple = (tuple(run_formatting), run_color)
        
        # Si le formatage ET la couleur sont identiques au groupe en cours, ajouter au groupe
        if current_formatting == run_formatting_tuple:
            current_group.append(run_text)
        else:
            # Finaliser le groupe précédent s'il existe
            process_current_group()
            
            # Commencer un nouveau groupe
            current_group = [run_text]
            current_formatting = run_formatting_tuple
    
    # Finaliser le dernier groupe
    process_current_group()

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

        # Build automatic style->level map from document styles (outline + numbered styles)
        style_heading_map = build_style_heading_map(doc)

        # Merge with global STYLE_MAP overrides (global constants win in case of conflict)
        style_heading_map.update(STYLE_MAP)

        # Finally, merge any map coming from metadata (advanced use-case)
        if 'style_heading_map' in metadata and isinstance(metadata['style_heading_map'], dict):
            style_heading_map.update(metadata['style_heading_map'])

        for block in iter_block_items(doc):
            if isinstance(block, Table):
                if current_conbody is None:
                    continue
                current_list = None  # A table ends normal/bullet lists
                current_sl = None

                p_for_table = ET.SubElement(current_conbody, 'p', id=generate_dita_id())
                dita_table = create_dita_table(block, all_images_map_rid)
                p_for_table.append(dita_table)

            elif isinstance(block, Paragraph):
                heading_level = get_heading_level(block, style_heading_map)
                is_heading = heading_level is not None

                # A paragraph is considered part of a list only if it is *not* a heading.
                is_list_item = (not is_heading) and (block._p.pPr is not None and block._p.pPr.numPr is not None)

                text = block.text.strip()
                is_image_para = any(run.element.xpath(".//@r:embed") for run in block.runs) and not text

                if is_heading and text:
                    current_list = None
                    current_sl = None
                    level = heading_level

                    if current_concept is not None:
                        context.topics[old_file_name] = current_concept

                    # Génération du tocIndex
                    heading_counters[level - 1] += 1
                    for i in range(level, len(heading_counters)):
                        heading_counters[i] = 0
                    toc_index = ".".join(str(c) for c in heading_counters[:level] if c > 0)

                    # Création du nouveau topic et topicref
                    parent_level = level - 1
                    parent_element = parent_elements.get(parent_level, map_root)
                    file_name = f"topic_{uuid.uuid4().hex[:10]}.dita"
                    topic_id = file_name.replace('.dita', '')

                    current_concept, current_conbody = create_dita_concept(
                        text,
                        topic_id,
                        context.metadata.get('revision_date', datetime.now().strftime('%Y-%m-%d')),
                    )

                    topicref = ET.SubElement(
                        parent_element,
                        'topicref',
                        {'href': f'topics/{file_name}', 'locktitle': 'yes'},
                    )
                    topicmeta_ref = ET.SubElement(topicref, 'topicmeta')
                    navtitle_ref = ET.SubElement(topicmeta_ref, 'navtitle')
                    navtitle_ref.text = text
                    critdates_ref = ET.SubElement(topicmeta_ref, 'critdates')
                    ET.SubElement(critdates_ref, 'created', date=context.metadata.get('revision_date'))
                    ET.SubElement(critdates_ref, 'revised', modified=context.metadata.get('revision_date'))
                    ET.SubElement(topicmeta_ref, 'metadata')
                    ET.SubElement(topicmeta_ref, 'othermeta', name='tocIndex', content=toc_index)
                    ET.SubElement(topicmeta_ref, 'othermeta', name='foldout', content='false')
                    ET.SubElement(topicmeta_ref, 'othermeta', name='tdm', content='false')
                    parent_elements[level] = topicref

                    # Nettoyer les niveaux plus profonds
                    for k in [l for l in parent_elements if l > level]:
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

# NEW HELPER ---------------------------------------------------------------

def get_heading_level(paragraph: Paragraph, style_map: dict | None = None) -> int | None:
    """Return heading level for *paragraph* or None if it is not a heading.

    Strategy (hybrid):
    1. Explicit *style_map* provided by the user {style_name: level}.
    2. Word outline level (<w:outlineLvl val="n"/>): level = n+1.
    3. Numbered paragraph with decimal/roman/alpha format: level = ilvl+1.
       Bullet formats are ignored.
    """
    try:
        # 1) Style-name mapping -------------------------------------------------
        style_name = ""
        if paragraph.style is not None and paragraph.style.name:
            style_name = paragraph.style.name
            if style_map and style_name in style_map:
                return int(style_map[style_name])
            # Classic "Heading X" catch-all
            if style_name.startswith("Heading ") and style_name.split(" ")[-1].isdigit():
                return int(style_name.split(" ")[-1])

        # 2) Outline level -----------------------------------------------------
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        outline_vals = paragraph._p.xpath("./w:pPr/w:outlineLvl/@w:val", namespaces=ns)
        if outline_vals:
            try:
                return int(outline_vals[0]) + 1  # Word stores 0-based levels
            except ValueError:
                pass

        # 3) Numbering heuristic ----------------------------------------------
        if paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None:
            numPr = paragraph._p.pPr.numPr
            ilvl = getattr(numPr.ilvl, "val", None)
            numId = getattr(numPr.numId, "val", None)
            if ilvl is not None and numId is not None:
                # Try to inspect numbering.xml to reject bullet formats
                try:
                    numbering_part = paragraph._p.part.numbering_part
                    num_root = numbering_part._element  # lxml element
                    # Resolve abstractNumId for this numId
                    abs_ids = num_root.xpath(
                        f'.//w:num[@w:numId="{numId}"]/w:abstractNumId/@w:val', namespaces=ns
                    )
                    if abs_ids:
                        abs_id = abs_ids[0]
                        # Get numFmt for the current level
                        numfmts = num_root.xpath(
                            f'.//w:abstractNum[@w:abstractNumId="{abs_id}"]/w:lvl[@w:ilvl="{ilvl}"]/w:numFmt/@w:val',
                            namespaces=ns,
                        )
                        if numfmts:
                            numfmt = numfmts[0]
                            if numfmt in {"bullet", "none"}:
                                return None  # ignore bullet lists
                    # Default: treat as heading
                    return int(ilvl) + 1
                except Exception:
                    # Fallback: treat any numbered list as heading level ilvl+1
                    try:
                        return int(ilvl) + 1
                    except Exception:
                        pass
    except Exception:
        # We intentionally swallow exceptions here to avoid breaking conversion.
        pass

    return None 