# Orlando DITA Packager

Cet outil convertit un document `.docx` en une archive DITA structurée selon les conventions spécifiques requises par le logiciel Orlando. Il a été développé en analysant une archive de référence pour reproduire la structure et les métadonnées attendues.

## Fonctionnalités

*   **Conversion DOCX vers DITA** : Transforme les paragraphes, titres, listes, tableaux et images d'un document Word en leurs équivalents DITA.
*   **Interface Graphique** : Utilise Tkinter pour permettre la sélection de fichiers, la modification des métadonnées et le lancement de la conversion.
*   **Respect des Conventions Orlando** : Le DITA généré suit des règles strictes découvertes lors de l'analyse.
*   **Génération d'une Archive Complète** : Crée une archive `.zip` contenant le `.ditamap`, les topics, les médias, et les DTDs nécessaires.

## Conventions DITA Implémentées

L'analyse de l'archive de référence a révélé plusieurs règles de structuration non standards qui sont cruciales pour la compatibilité avec Orlando :

1.  **Structure de l'archive** : Le `.zip` final contient un dossier `DATA` à la racine, qui lui-même contient :
    *   Un fichier `.ditamap` à sa racine.
    *   Un dossier `topics/` pour les fichiers de contenu `.dita`.
    *   Un dossier `media/` pour toutes les images.
    *   Un dossier `dtd/` contenant les DTD standards.

2.  **Identifiants Uniques** : Absolument **chaque élément XML** (de `<p>` à `<b>` en passant par `<table>`, `<row>`, etc.) doit posséder un attribut `id` unique.

3.  **Stylage par `outputclass`** : Le formatage avancé (texte centré, boîtes grisées, etc.) n'est pas géré par des balises DITA sémantiques mais par l'attribut `outputclass` sur des éléments standards. Le convertisseur détecte le formatage direct dans le `.docx` (alignement, couleur de fond du paragraphe, couleur du texte) pour appliquer les classes correspondantes.

4.  **Structure des Tableaux** : Les bordures internes des tableaux ne sont pas gérées par un attribut `frame` ou `colsep`/`rowsep` sur `<tgroup>`, mais par des attributs `colsep="1"` et `rowsep="1"` appliqués à **chaque cellule (`<entry>`)** individuellement.

5.  **Gestion des Images** : Les images sont traitées différemment selon le contexte :
    *   Une image isolée est placée dans une balise `<image>`.
    *   Des images consécutives (dans des paragraphes successifs sans texte) sont regroupées dans une liste simple DITA : `<sl>`. Chaque image est alors dans un `<sli>`.

6.  **Structure du Ditamap** : Le Ditamap utilise des `<topichead>` pour les sections qui ne sont pas des liens directs, et des `<topicref>` pour les fichiers de contenu. La hiérarchie et la numérotation sont gérées par une métadonnée `<othermeta name="tocIndex" ...>`.

## Installation

Il est recommandé d'utiliser un environnement virtuel.

1.  **Créer l'environnement virtuel :**
    ```bash
    python -m venv venv
    ```

2.  **Activer l'environnement :**
    *   Sur Windows : `venv\Scripts\activate`
    *   Sur macOS/Linux : `source venv/bin/activate`

3.  **Installer les dépendances :**
    ```bash
    pip install -r requirements.txt
    ```

## Lancement

Une fois les dépendances installées, lancez l'application avec la commande suivante :

```bash
python run.py
``` 