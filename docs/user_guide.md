# Guide Utilisateur de l'Orlando Toolkit

## 1. Introduction

Bienvenue dans le guide utilisateur de l'Orlando Toolkit ! Cette application de bureau vous permet de convertir facilement des documents Microsoft Word (.docx) en archives DITA (Darwin Information Typing Architecture) conformes aux spécifications d'Orlando.

### 1.1. Qu'est-ce que l'Orlando Toolkit ?

L'Orlando Toolkit est un outil de conversion qui transforme vos manuels Word en projets DITA autonomes prêts à être importés dans le système de gestion de contenu Orlando. L'application préserve la structure de votre document, le formatage, les images et les tableaux tout en assurant la conformité avec les conventions DITA spécifiques à Orlando.

### 1.2. Fonctionnalités principales

L'Orlando Toolkit offre les fonctionnalités suivantes :

- **Conversion DOCX vers DITA** : Transforme vos documents Word en fichiers DITA conformes
- **Gestion automatique des images** : Extrait les images intégrées et les normalise au format PNG
- **Édition de la structure** : Permet de déplacer, promouvoir, rétrograder, renommer ou supprimer des éléments de la structure
- **Fusion de sujets** : Fusionne les hiérarchies profondes avec une profondeur configurable
- **Configuration des métadonnées** : Interface conviviale pour configurer les propriétés du document
- **Génération de package** : Crée des archives ZIP prêtes à être importées dans Orlando
- **Historique des actions** : Fonctionnalité d'annulation/répétition pour les modifications de structure

### 1.3. Public cible

Ce guide est destiné aux rédacteurs techniques et gestionnaires de contenu qui doivent migrer des documents Word vers le format DITA pour les workflows de publication Orlando. Aucune connaissance technique approfondie n'est requise pour utiliser cette application.
## 2. Installation

L'Orlando Toolkit peut être installé de deux manières : à partir d'un fichier exécutable Windows ou à partir du code source.

### 2.1. Installation à partir du fichier exécutable Windows

Pour une installation facile sous Windows, suivez ces étapes :

1. Téléchargez le fichier exécutable `OrlandoToolkit.exe` depuis le site officiel
2. Double-cliquez sur le fichier téléchargé pour lancer l'installation
3. Suivez les instructions à l'écran pour terminer l'installation
4. Une icône de raccourci sera créée sur votre bureau

L'installateur effectue automatiquement les opérations suivantes :
- Télécharge un Python portable (WinPython)
- Installe PyInstaller et les dépendances nécessaires
- Construit l'application et l'installe dans `%LOCALAPPDATA%\OrlandoToolkit\App\`
- Crée un raccourci sur le bureau
- Enregistre les journaux dans `%LOCALAPPDATA%\OrlandoToolkit\Logs\`

### 2.2. Installation à partir du code source

Si vous préférez exécuter l'application à partir du code source, vous aurez besoin de Python 3.10 ou supérieur :

1. Clonez le dépôt GitHub :
   ```
   git clone https://github.com/Orsso/orlando-toolkit
   cd orlando-toolkit
   ```
2. Installez les dépendances requises :
   ```
   python -m pip install -r requirements.txt
   ```
3. Lancez l'application :
   ```
   python run.py
   ```

### 2.3. Configuration requise

- **Système d'exploitation** : Windows 7 ou supérieur (exécutable), Windows/macOS/Linux (code source)
- **Mémoire** : 4 Go de RAM minimum recommandé
- **Espace disque** : 500 Mo d'espace libre pour l'installation
## 3. Premiers pas

### 3.1. Lancement de l'application

Après l'installation, vous pouvez lancer l'Orlando Toolkit de deux manières :

1. Double-cliquez sur l'icône de raccourci sur votre bureau
2. Recherchez "Orlando Toolkit" dans le menu Démarrer de Windows

L'application s'ouvrira sur un écran d'accueil avec le logo de l'application et un bouton pour charger un document.

![Écran d'accueil de l'application](*insérer une capture d'écran de l'écran d'accueil*)

### 3.2. Interface utilisateur principale

L'interface de l'Orlando Toolkit est conçue pour être intuitive et conviviale. L'écran d'accueil comprend :

- Le logo de l'application
- Un bouton "Charger un document (.docx)"
- Une zone d'affichage des messages de statut
- Un indicateur de progression pour les opérations en cours

### 3.3. Chargement d'un document Word

Pour commencer à utiliser l'Orlando Toolkit, vous devez charger un document Word (.docx) :

1. Cliquez sur le bouton "Charger un document (.docx)" sur l'écran d'accueil
2. Dans la boîte de dialogue qui s'ouvre, naviguez jusqu'à l'emplacement de votre fichier Word
3. Sélectionnez le fichier et cliquez sur "Ouvrir"

L'application commencera immédiatement à convertir votre document. Vous verrez une barre de progression et des messages de statut pendant le processus de conversion.

Une fois la conversion terminée, un résumé s'affichera avec :
- Le nombre de sujets extraits
- Le nombre d'images extraites
- Un formulaire pour modifier les métadonnées du document

![Écran de résumé après conversion](*insérer une capture d'écran de l'écran de résumé*)

Cliquez sur le bouton "Continuer" pour accéder à l'interface principale de l'application avec les onglets Structure, Images et Métadonnées.
## 4. Onglet Structure

L'onglet Structure est l'interface principale pour visualiser et modifier la structure de votre document converti. Il vous permet de réorganiser, renommer, fusionner et supprimer des éléments de la structure de votre document.

### 4.1. Aperçu de l'onglet

L'onglet Structure se compose de plusieurs éléments :

- **Barre d'outils** : Boutons pour les opérations de déplacement et d'édition
- **Fonction de recherche** : Pour trouver rapidement des éléments dans la structure
- **Arbre de structure** : Affichage hiérarchique des sujets de votre document
- **Panneau d'aperçu** : Visualisation du contenu du sujet sélectionné
- **Panneau de filtres** : Options pour filtrer les titres affichés

![Interface de l'onglet Structure](*insérer une capture d'écran de l'onglet Structure*)

### 4.2. Arbre de structure

L'arbre de structure affiche la hiérarchie de votre document converti. Chaque nœud représente un sujet ou une section de votre document :

- Les éléments en gras représentent généralement les titres de niveau supérieur
- Les éléments indentés représentent les sous-sections

Vous pouvez interagir avec l'arbre de structure de plusieurs manières :
- **Sélection** : Cliquez sur un élément pour le sélectionner
- **Expansion/Réduction** : Cliquez sur les flèches à côté des éléments pour développer ou réduire les sous-sections
- **Navigation** : Utilisez les boutons +/- en haut pour développer ou réduire tous les éléments

### 4.3. Barre d'outils

La barre d'outils en haut de l'onglet Structure fournit des boutons pour les opérations d'édition courantes :

- **Déplacer vers le haut (↑)** : Déplace l'élément sélectionné vers le haut dans sa hiérarchie
- **Déplacer vers le bas (↓)** : Déplace l'élément sélectionné vers le bas dans sa hiérarchie
- **Promouvoir (←)** : Monte l'élément sélectionné d'un niveau dans la hiérarchie
- **Rétrograder (→)** : Descend l'élément sélectionné d'un niveau dans la hiérarchie
- **Renommer** : Change le titre de l'élément sélectionné
- **Supprimer** : Supprime l'élément sélectionné
- **Fusionner** : Fusionne plusieurs éléments sélectionnés en un seul sujet

Vous pouvez également utiliser des raccourcis clavier pour ces opérations :
- **Alt + ↑** : Déplacer vers le haut
- **Alt + ↓** : Déplacer vers le bas
- **Ctrl + Z** : Annuler la dernière action
- **Ctrl + Y** : Répéter la dernière action

### 4.4. Fonction de recherche

La fonction de recherche vous permet de trouver rapidement des éléments dans la structure de votre document :

1. Saisissez un terme de recherche dans la zone de texte en haut de l'onglet
2. Les résultats correspondants seront mis en surbrillance dans l'arbre de structure
3. Utilisez les boutons ← et → pour naviguer entre les résultats

### 4.5. Aperçu du contenu

Le panneau d'aperçu à droite affiche le contenu du sujet sélectionné dans l'arbre de structure. Vous pouvez basculer entre deux modes d'aperçu :

- **Mode HTML** : Affiche un rendu formaté du contenu
- **Mode XML** : Affiche le code source XML brut

### 4.6. Édition de la structure

Vous pouvez modifier la structure de votre document de plusieurs manières :

#### Déplacement des éléments
Pour réorganiser les éléments de votre document :
1. Sélectionnez un ou plusieurs éléments dans l'arbre de structure
2. Utilisez les boutons de déplacement dans la barre d'outils ou les raccourcis clavier

#### Renommage des éléments
Pour changer le titre d'un élément :
1. Sélectionnez l'élément dans l'arbre de structure
2. Cliquez sur le bouton "Renommer" dans la barre d'outils ou faites un clic droit et sélectionnez "Renommer"
3. Saisissez le nouveau titre dans la boîte de dialogue

#### Suppression d'éléments
Pour supprimer un élément :
1. Sélectionnez l'élément dans l'arbre de structure
2. Cliquez sur le bouton "Supprimer" dans la barre d'outils ou faites un clic droit et sélectionnez "Supprimer"

#### Fusion d'éléments
Pour fusionner plusieurs éléments en un seul sujet :
1. Sélectionnez plusieurs éléments consécutifs dans l'arbre de structure
2. Cliquez sur le bouton "Fusionner" dans la barre d'outils ou faites un clic droit et sélectionnez "Fusionner"

### 4.7. Filtres de titres

Le panneau de filtres vous permet de contrôler quels titres sont affichés dans l'arbre de structure :

1. Cliquez sur le bouton "Filtres" (pictogramme 📃) pour ouvrir le panneau de filtres
2. Dans le panneau, vous pouvez :
   - Ajuster la profondeur maximale des titres affichés
## 5. Onglet Images

L'onglet Images vous permet de gérer les images extraites de votre document Word pendant le processus de conversion. Vous pouvez prévisualiser les images, les renommer selon une convention spécifique et même les éditer avec des applications externes.

### 5.1. Aperçu de l'onglet

L'onglet Images se compose de deux panneaux principaux :

- **Liste des images** : Affiche tous les fichiers image extraits avec leurs noms proposés
- **Aperçu de l'image** : Affiche une prévisualisation de l'image sélectionnée avec ses détails

![Interface de l'onglet Images](*insérer une capture d'écran de l'onglet Images*)

### 5.2. Liste des images

La liste sur le côté gauche affiche toutes les images extraites de votre document. Pour chaque image, vous voyez :

- Le nom de fichier proposé selon la convention de nommage
- Un indicateur visuel de l'image sélectionnée

Vous pouvez interagir avec cette liste de plusieurs manières :
- **Sélection** : Cliquez sur une image pour la sélectionner et afficher son aperçu
- **Navigation** : Utilisez la barre de défilement pour parcourir la liste

### 5.3. Aperçu des images

Le panneau d'aperçu à droite affiche l'image sélectionnée avec ses détails :

- **Prévisualisation** : Affichage redimensionné de l'image
- **Informations** : Dimensions originales, taille du fichier et format
- **Options d'édition** : Boutons pour télécharger, éditer ou recharger l'image

### 5.4. Renommage des images

L'Orlando Toolkit applique automatiquement une convention de nommage pour les images basée sur le code du manuel et la numérotation des sections :

1. Le préfixe par défaut est "CRL" mais peut être modifié
2. Les images sont numérotées par section du document
3. Le format est : `PREFIX-CODE_MANUEL-NUMERO_SECTION[-NUMERO_IMAGE].EXTENSION`

Pour modifier le préfixe :
1. Saisissez un nouveau préfixe dans le champ "Préfixe" en haut de l'onglet
2. La liste des noms de fichiers sera automatiquement mise à jour

### 5.5. Édition des images

Vous pouvez éditer les images directement depuis l'Orlando Toolkit :

1. Sélectionnez une image dans la liste
2. Choisissez un éditeur dans la liste déroulante (Paint, GIMP, Photoshop ou l'éditeur par défaut du système)
3. Cliquez sur le bouton "Éditer l'image"

L'image sera ouverte dans l'éditeur sélectionné. Selon l'éditeur utilisé :

- **Éditeurs non bloquants** (GIMP, Photoshop) : Vous devrez cliquer sur le bouton "↻" pour recharger l'image après l'avoir enregistrée
- **Éditeurs bloquants** (Paint) : L'image sera automatiquement rechargée lorsque vous fermerez l'éditeur

### 5.6. Téléchargement des images

## 6. Onglet Métadonnées

L'onglet Métadonnées vous permet de configurer les informations de base de votre document qui seront incluses dans le package DITA généré. Ces métadonnées sont essentielles pour une intégration correcte dans le système de gestion de contenu Orlando.

### 6.1. Aperçu de l'onglet

L'onglet Métadonnées présente un formulaire simple avec les champs de métadonnées essentiels :

- **Titre du manuel** : Le titre principal de votre document
- **Code du manuel** : Un code identifiant unique pour votre document
- **Date de révision** : La date de la dernière révision du document

![Interface de l'onglet Métadonnées](*insérer une capture d'écran de l'onglet Métadonnées*)

### 6.2. Champs de métadonnées

#### Titre du manuel
Ce champ définit le titre principal de votre document. Par défaut, il est rempli avec le nom du fichier Word d'origine, mais vous pouvez le modifier selon vos besoins.

#### Code du manuel
Le code du manuel est un identifiant unique qui est utilisé dans le système Orlando. Il est également utilisé dans le nommage des images et des fichiers du package généré.

#### Date de révision
Cette date indique quand le document a été dernièrement révisé. Par défaut, elle est définie à la date actuelle, mais vous pouvez la modifier pour refléter la date de révision réelle de votre document.

### 6.3. Édition des métadonnées

Pour modifier les métadonnées :

1. Accédez à l'onglet "Métadonnées"
2. Modifiez les valeurs dans les champs de texte selon vos besoins
3. Les modifications sont automatiquement enregistrées et appliquées au document

Les modifications apportées aux métadonnées sont immédiatement répercutées dans les autres onglets, notamment dans le nommage des images dans l'onglet Images.

### 6.4. Importance des métadonnées

Les métadonnées sont cruciales pour le processus de génération du package DITA et son intégration dans le système Orlando :

- Elles sont incluses dans le fichier de carte DITA (.ditamap)
- Elles sont utilisées pour nommer les fichiers dans le package généré
- Elles fournissent des informations contextuelles pour le système de gestion de contenu

Assurez-vous que toutes les métadonnées sont correctement renseignées avant de générer le package final.
## 7. Génération du package

Une fois que vous avez terminé toutes les modifications nécessaires à votre document (structure, images, métadonnées), vous pouvez générer le package DITA final prêt à être importé dans le système Orlando.

### 7.1. Processus de génération

Pour générer le package DITA :

1. Assurez-vous que tous les onglets ont été vérifiés et que toutes les modifications souhaitées ont été apportées
2. Cliquez sur le bouton "Générer le package DITA" en bas de la fenêtre principale
3. Dans la boîte de dialogue qui s'ouvre, choisissez l'emplacement où vous souhaitez enregistrer le package
4. Le nom de fichier par défaut est basé sur le code du manuel que vous avez défini dans l'onglet Métadonnées
5. Cliquez sur "Enregistrer" pour lancer le processus de génération

![Bouton de génération du package](*insérer une capture d'écran du bouton de génération*)

Pendant le processus de génération, une barre de progression s'affiche pour indiquer l'avancement. Ce processus peut prendre quelques instants selon la taille de votre document.

### 7.2. Contenu du package généré

Le package généré est une archive ZIP contenant tous les éléments nécessaires pour l'importation dans le système Orlando :

- **Fichier de carte DITA** (`.ditamap`) : Contient la structure globale du document et les métadonnées
- **Dossier des sujets** (`DATA/topics/`) : Contient tous les fichiers de sujet DITA individuels
- **Dossier des médias** (`DATA/media/`) : Contient toutes les images extraites et renommées

### 7.3. Structure du package

L'arborescence du package généré respecte la structure suivante :

```
NOM_DU_PACKAGE.ZIP
├── DATA/
│   ├── topics/
│   │   ├── topic_1.dita
│   │   ├── topic_2.dita
│   │   └── ...
│   ├── media/
│   │   ├── image_1.png
│   │   ├── image_2.png
│   │   └── ...
│   └── NOM_DU_MANUEL.ditamap
```

### 7.4. Importation dans Orlando

Le package généré est prêt à être importé dans le système de gestion de contenu Orlando :

1. Connectez-vous à l'interface d'administration d'Orlando
2. Accédez à la section d'importation de documents
3. Sélectionnez le fichier ZIP généré par l'Orlando Toolkit
## 8. Conclusion

### 8.1. Résumé des fonctionnalités

L'Orlando Toolkit est un outil complet pour la conversion de documents Word en format DITA conforme aux spécifications Orlando. Grâce à son interface intuitive, vous pouvez facilement :

- Convertir des documents Word en structures DITA bien organisées
- Éditer et réorganiser la structure de votre document
- Gérer et renommer les images selon une convention spécifique
- Configurer les métadonnées essentielles pour l'intégration Orlando
- Générer des packages prêts à l'emploi pour l'importation

### 8.2. Conseils d'utilisation

Pour tirer le meilleur parti de l'Orlando Toolkit, suivez ces conseils :

1. **Préparez votre document Word** : Assurez-vous que votre document utilise des styles de titre cohérents pour une conversion optimale
2. **Vérifiez la structure** : Après la conversion, examinez attentivement l'arbre de structure dans l'onglet Structure pour vous assurer qu'elle correspond à vos attentes
3. **Personnalisez les métadonnées** : Prenez le temps de remplir correctement les champs de métadonnées pour faciliter l'intégration dans Orlando
4. **Gérez les images** : Vérifiez que les images sont correctement extraites et nommées selon la convention requise
5. **Utilisez l'historique** : N'hésitez pas à utiliser les fonctions d'annulation/répétition si vous faites des modifications incorrectes

### 8.3. Support et ressources

Si vous rencontrez des problèmes ou avez des questions sur l'utilisation de l'Orlando Toolkit :

- Consultez la documentation technique dans le dossier `docs/` du projet
- Vérifiez les journaux d'application dans `%LOCALAPPDATA%\OrlandoToolkit\Logs\` pour les installations Windows
- Contactez l'équipe de développement si vous identifiez des bugs ou souhaitez proposer des améliorations

### 8.4. Notes importantes

- L'Orlando Toolkit est un projet open-source indépendant et n'est pas affilié à 'Orlando TechPubs' ou Infotel
- Les noms 'Orlando' et toute marque associée appartiennent à leurs propriétaires respectifs
- Cette application est fournie telle quelle, sans garantie expresse ou implicite

Nous espérons que l'Orlando Toolkit facilitera votre transition vers le format DITA et améliorera votre productivité dans la création de documentation technique.
4. Suivez le processus d'importation standard d'Orlando

### 7.5. Retour à l'écran d'accueil

Après avoir généré un package, vous pouvez revenir à l'écran d'accueil pour commencer un nouveau projet :

1. Cliquez sur le bouton "← Retour à l'accueil" en bas de la fenêtre
2. L'application vous demandera de confirmer que vous souhaitez quitter le projet actuel
3. Après confirmation, vous serez redirigé vers l'écran d'accueil initial

Toutes les modifications non sauvegardées dans un package seront perdues, donc assurez-vous d'avoir généré le package avant de retourner à l'accueil si vous souhaitez conserver vos modifications.
Vous pouvez télécharger des images individuelles ou toutes les images à la fois :

#### Télécharger une image individuelle
1. Sélectionnez l'image dans la liste
2. Cliquez sur le bouton "⤓" à côté de l'aperçu ou sur "Télécharger" dans la barre d'outils

#### Télécharger toutes les images
1. Cliquez sur le bouton "Télécharger tout" sous la liste des images
2. Choisissez un dossier de destination dans la boîte de dialogue
3. Toutes les images seront enregistrées dans ce dossier avec leurs noms proposés

### 5.7. Remplacement d'images

Si vous souhaitez remplacer une image par un fichier différent :

1. Sélectionnez l'image dans la liste
2. Utilisez la fonction de remplacement (si disponible) pour choisir un nouveau fichier
3. L'image dans le document sera mise à jour avec le nouveau fichier
   - Exclure des styles de titre spécifiques
   - Appliquer des filtres pour simplifier l'affichage

### 4.8. Historique des actions

L'Orlando Toolkit conserve un historique des actions effectuées dans l'onglet Structure, vous permettant d'annuler ou de répéter des modifications :

- **Annuler** : Ctrl + Z
- **Répéter** : Ctrl + Y

Toutes les modifications apportées à la structure sont enregistrées dans cet historique, vous permettant de revenir en arrière si nécessaire.