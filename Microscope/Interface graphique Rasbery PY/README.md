# Interface graphique Raspberry Pi : acquisition des films

Cette interface pilote la caméra du Raspberry Pi : réglage des conditions, image en direct, enregistrement d'un film TIFF. Aucun traitement n'est fait ici : le rayon se calcule ensuite sur le PC avec l'interface de traitement (dossier `Interface graphique pc`).

## Fichiers
- `interface_acquisition.py` : interface d'acquisition (PyQt6), style identique à l'interface PC. Contient aussi son lancement.
- `acquisition.py` : partie caméra commune (configuration picamera2, cadence, écriture du film). Utilisée par `interface_acquisition.py`.
- `camera.py` et `main.py` : première interface de Brian (aperçu avec détection de particule). Non modifiés, ils restent utilisables tels quels.

## Lancer (sur le Raspberry Pi)
    cd "Interface graphique Rasbery PY"
    python3 interface_acquisition.py

Essai sans caméra (images fictives) :

    python3 interface_acquisition.py --simulation

Dépendances : PyQt6 numpy scipy opencv-python Pillow (plus picamera2 sur le Pi).

## Utilisation
1. **Conditions d'acquisition** : objectif, temps d'exposition, intervalle entre images (Δt), cadence, durée du film, gain analogique, échelle µm/pixel (case pour la verrouiller une fois mesurée avec la règle).
2. **Enregistrement** : nom du fichier (modifiable), dossier, commentaire. Le nom complet du fichier créé s'affiche en direct sous le champ. Le numéro est incrémenté automatiquement pour ne rien écraser.
3. **Aperçu** : l'image en direct affiche l'échelle, l'objectif, l'exposition, la cadence, la profondeur de bit et le nombre d'images par seconde de l'aperçu. Case « Afficher le centre » pour le placement. Case « Détecter la particule et estimer sa taille en direct » (désactivée par défaut, ralentit le Raspberry Pi) : reprise du code de Brian, avec bouton de remise à zéro de la taille moyenne.
4. **Lancer l'acquisition.** L'aperçu se fige automatiquement pendant l'enregistrement (dernière image affichée, bandeau rouge « ACQUISITION EN COURS »), puis reprend seul à la fin. Le Raspberry Pi consacre alors toute sa puissance à la caméra, ce qui évite de perdre des images (aperçu en direct : environ 15 images par seconde au lieu de 30). Une barre de progression indique l'avancement.

## Fichiers produits
Dans le dossier choisi, pour chaque film :

    <nom>_<numéro>_dt_<dt>s_exp_<exp>s_PixelSize_<pixel>um_Mono_8bit.tif    le film (niveaux de gris, 8 bits)
    <nom>_<numéro>_....json                                                 réglages et instants réels des images

Le nom du .tif contient Δt, exposition et taille de pixel : l'interface de traitement les lit automatiquement.

## Limites connues
- Jamais testée sur le vrai Raspberry Pi (testée en simulation seulement). À vérifier au labo : aucune image manquante, cadence réelle égale à celle demandée, rafraîchissement de l'aperçu (50 ms).
- L'échelle par défaut (0,186 µm/pixel pour l'objectif 20X, NA 0,40) a été calée sur la règle graduée. Elle est à confirmer en mode film (1332x990) : 100 µm doivent mesurer environ 538 pixels.
- Dans `camera.py` de Brian, la détection plante : `Particle((x, y), size)` doit s'écrire `Particle(pos=(x, y), size=size)`. Corrigé dans `interface_acquisition.py`.
