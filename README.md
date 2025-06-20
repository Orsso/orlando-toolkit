# Orlando DITA Packager

## 1. Description

Cet outil est conçu pour automatiser la transformation d'archives DITA (générées à partir de documents Word) vers un format structuré et entièrement compatible avec la plateforme de publication Orlando.

Il prend en entrée une archive `.zip` contenant une structure DITA standard et produit en sortie une nouvelle archive `.zip` prête à être importée dans Orlando.

### Périmètre Actuel

**Attention :** Dans sa version actuelle, cet outil **ne gère pas** la conversion initiale du document `.docx` vers le format DITA.

Cette première étape doit être réalisée manuellement à l'aide d'un outil externe. Nous utilisons actuellement le convertisseur en ligne de **[XMLmind](https://www.xmlmind.com/w2x/docx_to_dita.html)**. L'intégration de cette conversion directement dans l'application est prévue pour une future version.

### Fonctionnalités principales

- Mise à jour du `DOCTYPE` et des métadonnées du fichier `.ditamap`.
- Création d'une hiérarchie de `topichead` pour la table des matières.
- Conversion des fichiers `<topic>` en `<concept>`.
- Injection d'un `<prolog>` et d'IDs uniques dans chaque fichier DITA.
- Remplacement des images par des placeholders textuels valides.
- Normalisation de la structure des tableaux.
- Copie des DTD requis pour la validation par Orlando.

## 2. Stack Technique

- **Langage :** Python 3
- **Interface Graphique :** Tkinter (bibliothèque standard de Python)
- **Manipulation XML :** `lxml`

## 3. Prérequis

- Python 3.6 ou supérieur.

## 4. Installation

1.  Clonez ce dépôt sur votre machine locale.
2.  Ouvrez un terminal ou une invite de commande à la racine du projet.
3.  Il est recommandé de créer un environnement virtuel :
    ```bash
    python -m venv venv
    ```
    Activez-le :
    -   Sur Windows : `venv\Scripts\activate`
    -   Sur macOS/Linux : `source venv/bin/activate`
4.  Installez les dépendances nécessaires :
    ```bash
    pip install -r requirements.txt
    ```

## 5. Utilisation

1.  Lancez l'application en exécutant le script `run_app.py` depuis la racine du projet :
    ```bash
    python run_app.py
    ```
2.  La fenêtre de l'application s'ouvre.
3.  Cliquez sur **Parcourir...** pour sélectionner l'archive `.zip` que vous souhaitez transformer.
4.  Renseignez le **Titre du manuel**.
5.  Vérifiez ou modifiez la **Date de révision** (pré-remplie avec la date du jour).
6.  Cliquez sur le bouton **Lancer la Transformation**.
7.  Une fois le processus terminé, un message de succès s'affiche. Une nouvelle archive nommée `[nom_de_l_archive_originale]_orlando_compatible.zip` sera créée dans le même dossier que votre archive d'origine. 