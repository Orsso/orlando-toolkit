import logging
import os
import shutil
import uuid
import zipfile
import tempfile
from lxml import etree
from datetime import datetime

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_transformation(source_zip_path, manual_metadata):
    """
    Point d'entrée principal pour lancer le processus de transformation.
    Prend en paramètres le chemin d'une archive .zip et un dictionnaire de métadonnées.
    """
    logging.info("--- Début de la transformation DITA pour Orlando (Mode ZIP) ---")
    
    if not os.path.isfile(source_zip_path) or not source_zip_path.lower().endswith('.zip'):
        raise ValueError(f"Le chemin fourni '{source_zip_path}' n'est pas un fichier .zip valide.")

    with tempfile.TemporaryDirectory() as temp_source_dir, tempfile.TemporaryDirectory() as temp_output_dir:
        try:
            # --- PHASE DE DÉCOMPRESSION ---
            logging.info(f"Décompression de l'archive {source_zip_path} vers {temp_source_dir}")
            with zipfile.ZipFile(source_zip_path, 'r') as zip_ref:
                # On doit trouver le premier sous-répertoire qui contient le ditamap
                # car les exports Word créent souvent un dossier parent.
                first_level_dirs = {os.path.normpath(f.split('/')[0]) for f in zip_ref.namelist() if '/' in f}
                source_content_dir = temp_source_dir
                if len(first_level_dirs) == 1:
                     # Si la racine du zip ne contient qu'un seul dossier, c'est notre vrai répertoire source
                    source_content_dir = os.path.join(temp_source_dir, list(first_level_dirs)[0])
                zip_ref.extractall(temp_source_dir)
            logging.info("Décompression terminée.")

            # Récupération de la date de révision
            revision_date = manual_metadata.get('revision_date', datetime.now().strftime('%Y-%m-%d'))
            logging.info(f"Date de révision utilisée : {revision_date}")

            # --- PHASE DE PRÉPARATION (dans le dossier de sortie temporaire) ---
            prepare_output_directory(temp_output_dir)

            # --- PHASE DE TRANSFORMATION DU DITAMAP ---
            topic_map = process_ditamap(source_content_dir, temp_output_dir, manual_metadata, revision_date)
            
            # --- PHASE DE TRANSFORMATION DES FICHIERS DITA ---
            process_dita_files(source_content_dir, temp_output_dir, topic_map, revision_date)

            # --- PHASE DE COMPRESSION ---
            base_path = os.path.dirname(source_zip_path)
            source_zip_name = os.path.splitext(os.path.basename(source_zip_path))[0]
            output_zip_path = os.path.join(base_path, f"{source_zip_name}_orlando_compatible.zip")
            
            logging.info(f"Compression du résultat vers {output_zip_path}")
            with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(temp_output_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        archive_path = os.path.relpath(file_path, temp_output_dir)
                        zipf.write(file_path, archive_path)
            
            logging.info("--- Transformation terminée avec succès ---")
            return True, f"Transformation terminée ! Archive créée : {output_zip_path}"

        except Exception as e:
            logging.error(f"ERREUR CRITIQUE: {e}", exc_info=True)
            return False, str(e)

def process_ditamap(source_path, output_path, manual_metadata, revision_date):
    """Analyse, transforme et sauvegarde le fichier .ditamap principal."""
    logging.info("--- Phase 2: Transformation du fichier .ditamap ---")
    ditamap_filename = None
    for filename in os.listdir(source_path):
        if filename.lower().endswith('.ditamap'):
            ditamap_filename = filename
            break
    if not ditamap_filename:
        raise FileNotFoundError(f"Aucun fichier .ditamap trouvé dans {source_path}")
    source_ditamap_path = os.path.join(source_path, ditamap_filename)
    output_ditamap_path = os.path.join(output_path, ditamap_filename)
    logging.info(f"Fichier .ditamap trouvé: {source_ditamap_path}")
    parser = etree.XMLParser(remove_blank_text=True, load_dtd=False, resolve_entities=False)
    tree = etree.parse(source_ditamap_path, parser)
    root = tree.getroot()
    update_ditamap_metadata(root, manual_metadata, revision_date)
    topic_map = restructure_topicrefs(root, source_path)
    doctype_str = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "./dtd/technicalContent/dtd/map.dtd">'
    tree.write(output_ditamap_path, pretty_print=True, xml_declaration=True, encoding='UTF-8', doctype=doctype_str)
    logging.info(f"Fichier .ditamap transformé et sauvegardé dans: {output_ditamap_path}")
    return topic_map

def update_ditamap_metadata(root, manual_metadata, revision_date):
    """Supprime les anciennes métadonnées et ajoute celles requises par Orlando."""
    title_element = root.find('title')
    if title_element is not None:
        title_element.text = manual_metadata.get('manual_title', 'Titre par défaut')
        logging.info("Titre du document mis à jour.")
    old_topicmeta = root.find('topicmeta')
    if old_topicmeta is not None:
        root.remove(old_topicmeta)
        logging.info("Ancien <topicmeta> supprimé.")
    topicmeta = etree.Element('topicmeta')
    critdates = etree.SubElement(topicmeta, 'critdates')
    etree.SubElement(critdates, 'created', date=revision_date)
    etree.SubElement(critdates, 'revised', modified=revision_date)
    etree.SubElement(topicmeta, 'othermeta', name="manualCode", content=manual_metadata.get('manual_code', ''))
    etree.SubElement(topicmeta, 'othermeta', name="manual_reference", content=manual_metadata.get('manual_reference', ''))
    etree.SubElement(topicmeta, 'othermeta', name="revNumber", content="1.0") # À rendre configurable plus tard si besoin
    etree.SubElement(topicmeta, 'othermeta', name="isRevNumberNull", content="false")
    if title_element is not None:
        title_element.addnext(topicmeta)
    else:
        root.insert(0, topicmeta)
    logging.info("Nouveau <topicmeta> pour Orlando ajouté.")

def prepare_output_directory(output_path):
    """Crée le répertoire de sortie et y copie les DTDs internes."""
    logging.info("--- Phase 1: Préparation du répertoire de sortie ---")
    if os.path.exists(output_path):
        logging.info(f"Nettoyage du répertoire de sortie existant: {output_path}")
        shutil.rmtree(output_path)
    output_topics_path = os.path.join(output_path, 'topics')
    os.makedirs(output_topics_path)
    logging.info(f"Répertoire de sortie créé: {output_path}")
    script_dir = os.path.dirname(__file__)
    dtd_source_path = os.path.join(script_dir, '../dtd_package') # On doit remonter d'un niveau (on est dans 'core')
    dtd_dest_path = os.path.join(output_path, 'dtd')
    if not os.path.isdir(dtd_source_path):
        raise NotADirectoryError(f"Le paquetage DTD interne '{dtd_source_path}' est introuvable.")
    shutil.copytree(dtd_source_path, dtd_dest_path)
    logging.info(f"DTDs internes copiées vers {dtd_dest_path}")
    
def process_dita_files(source_path, output_path, topic_map, revision_date):
    """Orchestre la transformation de chaque fichier DITA individuel."""
    logging.info("--- Phase 3: Transformation des fichiers de contenu .dita ---")
    if not topic_map:
        logging.warning("Aucune rubrique à traiter n'a été trouvée dans le .ditamap.")
        return
    for original_href, new_href in topic_map.items():
        source_file_path = os.path.join(source_path, original_href)
        output_file_path = os.path.join(output_path, new_href)
        if not os.path.exists(source_file_path):
            logging.error(f"Fichier source introuvable: {source_file_path}. Il est ignoré.")
            continue
        logging.info(f"Traitement de: {original_href} -> {new_href}")
        transform_single_dita_file(source_file_path, output_file_path, new_href, revision_date)
    logging.info(f"{len(topic_map)} fichiers DITA ont été traités.")

def transform_single_dita_file(source_path, output_path, new_href, revision_date):
    """Charge un fichier DITA, applique toutes les transformations et le sauvegarde."""
    try:
        parser = etree.XMLParser(remove_blank_text=True, load_dtd=False, resolve_entities=False)
        tree = etree.parse(source_path, parser)
        root = tree.getroot()
        if root.tag == 'topic':
            root.tag = 'concept'
            body = root.find('body')
            if body is not None:
                body.tag = 'conbody'
        new_id = os.path.splitext(os.path.basename(new_href))[0]
        root.set('id', new_id)
        inject_prolog(root, revision_date)
        
        # Remplacer les images par un placeholder contextuel
        for image in root.xpath('//image'):
            parent = image.getparent()
            
            # Définir les conteneurs qui ne peuvent contenir que des éléments en ligne
            inline_containers = ['p', 'ph', 'b', 'i', 'u']

            # Créer le placeholder en gras (un élément en ligne)
            placeholder_b = etree.Element('b')
            placeholder_b.text = "[IMAGE PLACEHOLDER]"

            # Si le parent est un conteneur en ligne, on insère directement le <b>
            if parent.tag in inline_containers:
                parent.replace(image, placeholder_b)
            # Sinon, le parent est un conteneur de type bloc, on peut l'englober dans un <p>
            else:
                placeholder_p = etree.Element('p')
                placeholder_p.append(placeholder_b)
                parent.replace(image, placeholder_p)

        transform_tables(root)
        for elem in root.xpath('//*[not(@id)]'):
            elem.set('id', str(uuid.uuid4()))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        doctype_str = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA 1.3 Concept//EN" "../dtd/technicalContent/dtd/concept.dtd">'
        tree.write(output_path, pretty_print=True, xml_declaration=True, encoding='UTF-8', doctype=doctype_str)
    except etree.XMLSyntaxError as e:
        logging.error(f"Erreur de syntaxe XML dans {source_path}: {e}. Fichier ignoré.")
    except Exception as e:
        logging.error(f"Erreur inattendue lors du traitement de {source_path}: {e}. Fichier ignoré.")

def inject_prolog(root, revision_date):
    """Injecte le bloc <prolog> avec les métadonnées de date."""
    if root.find('prolog') is None:
        prolog = etree.Element('prolog')
        critdates = etree.SubElement(prolog, 'critdates')
        etree.SubElement(critdates, 'created', date=revision_date)
        etree.SubElement(critdates, 'revised', modified=revision_date)
        title_element = root.find('title')
        if title_element is not None:
            title_element.addnext(prolog)
        else:
            root.insert(0, prolog)

def transform_tables(root):
    """Applique les transformations spécifiques d'Orlando aux tableaux."""
    for table in root.xpath('//table'):
        parent = table.getparent()
        if parent.tag != 'p':
            p = etree.Element('p')
            parent.replace(table, p)
            p.append(table)
        if 'frame' not in table.attrib:
            table.set('frame', 'none')
        for i, colspec in enumerate(table.xpath('.//colspec')):
            colspec.set('colnum', str(i + 1))
            colspec.set('colname', f'column-{i}')
            colspec.set('colsep', '1')
            colspec.set('rowsep', '1')
            if 'colwidth' in colspec.attrib:
                del colspec.attrib['colwidth']
        for entry in table.xpath('.//entry'):
            entry.set('colsep', '1')
            entry.set('rowsep', '1')

def restructure_topicrefs(root, source_path):
    """Restructure les <topicref> pour correspondre au format Orlando."""
    logging.info("Restructuration hiérarchique des <topicref> en cours...")
    topic_map = {}
    children = list(root)
    new_children_container = []
    for child in children:
        if child.tag == 'topicref':
            root.remove(child)
            transformed_node = transform_topicref_recursively(child, source_path, topic_map)
            new_children_container.append(transformed_node)
    for new_child in new_children_container:
        root.append(new_child)
    logging.info(f"{len(topic_map)} topicrefs ont été restructurés.")
    return topic_map

def transform_topicref_recursively(topicref, source_path, topic_map):
    """Transforme un <topicref> et ses enfants de manière récursive."""
    topicref.set('locktitle', 'yes')
    original_href = topicref.get('href')
    if original_href:
        new_filename = f"topics/_SVC-BEOPS.PROCBEO003.dita_orl{len(topic_map):06d}.dita"
        topic_map[original_href] = new_filename
        topicref.set('href', new_filename)
        topicmeta = etree.Element('topicmeta')
        navtitle_text = get_topic_title(os.path.join(source_path, original_href))
        navtitle = etree.SubElement(topicmeta, 'navtitle')
        navtitle.text = navtitle_text
        topicref.insert(0, topicmeta)
    child_topicrefs = list(topicref.xpath('./topicref'))
    
    if not child_topicrefs:
        # C'est une feuille, on retourne le topicref transformé
        return topicref
    else:
        # C'est un parent, on crée un <topichead> qui va contenir les enfants.
        topichead = etree.Element('topichead')
        
        # Le <topicmeta> du <topichead> est celui du topicref parent.
        # Le <navtitle> est extrait du titre du fichier .dita associé au parent.
        # Si le topicref parent n'a pas de href, son titre n'est pas utilisé, ce qui est correct.
        parent_meta = etree.Element('topicmeta')
        if original_href:
            navtitle_text = get_topic_title(os.path.join(source_path, original_href))
            navtitle = etree.SubElement(parent_meta, 'navtitle')
            navtitle.text = navtitle_text
        topichead.append(parent_meta)
        
        # On ne garde PAS le topicref parent. On ne traite que ses enfants de manière récursive.
        for child in child_topicrefs:
            transformed_child = transform_topicref_recursively(child, source_path, topic_map)
            topichead.append(transformed_child)
            
        return topichead

def get_topic_title(topic_path):
    """Extrait le titre d'un fichier DITA."""
    if not os.path.exists(topic_path):
        return "Titre introuvable"
    try:
        parser = etree.XMLParser(load_dtd=False, resolve_entities=False)
        tree = etree.parse(topic_path, parser)
        title = tree.find('.//title') # Corrigé pour respecter la future version de lxml
        if title is not None and title.text:
            return title.text.strip()
        return "Titre vide"
    except etree.XMLSyntaxError:
        return "Fichier DITA invalide" 