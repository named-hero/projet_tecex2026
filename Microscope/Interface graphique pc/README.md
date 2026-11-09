# Interface graphique PC : traitement des films

Cette interface part d'un film TIFF enregistré avec l'interface d'acquisition du Raspberry Pi (dossier `Interface graphique Rasbery PY`). Elle suit les particules, calcule le rayon moyen et son incertitude, et rejoue le film avec les trajectoires.

## Fichiers
- `interface_traitement.py` : interface du PC (PySide6).
- `analyse_equipe.py` : détection, suivi, correction du mouvement collectif, tri des particules, MSD, rayon.
- `annotation.py` : temps (s), échelle (µm/pixel), conditions, dessinés sur chaque image.

## Lancer le traitement
    cd "Interface graphique pc"
    python3 interface_traitement.py
Dépendances : PySide6 numpy scipy opencv-python Pillow.

## Utilisation
1. **Ouvrir un film TIFF.** Δt, exposition, échelle et profondeur de bit sont lus dans le nom du fichier.
2. **Paramètres** : vérifier objectif, exposition, Δt, profondeur de bit et échelle µm/pixel (tous modifiables, ils sont affichés sur chaque image).
3. **Choix des particules** (onglet Film et sélection) :
   - *Zones* : glisser la souris sur l'image pour tracer un rectangle autour d'une particule (sur une image où elle est nette). Chaque rectangle ajoute une particule. Plusieurs zones donnent un rayon moyen.
   - *La plus lumineuse* : tache la plus lumineuse de l'image affichée (souvent la plus grosse, peu représentative).
   - *Toutes les particules, triées automatiquement* : rayon moyen de l'échantillon.
4. **Correction du mouvement collectif** : case à cocher sous le choix des particules (cochée par défaut). Les particules dérivent ensemble (courant, vibrations) ; la correction retire cette dérive commune, sans elle le rayon est sous-estimé. Décochée, l'analyse se fait sans correction.
5. **Analyser.** Le résultat s'ouvre dans l'onglet Résultats : rayon moyen ± incertitude, tableau par particule (intensité, D, rayon, incertitude), MSD moyen avec axes et barres d'erreur, rayon de chaque particule (ou histogramme au-delà de 20 particules).
6. **Vidéo annotée** : le film rejoué avec les trajectoires (rouge = particule écartée). Zoom avec le curseur ou la molette, déplacement en glissant la souris, ou « Suivre » une particule (zoom automatique x5). La barre d'échelle suit le zoom. Bouton d'export AVI (image entière).

## Tri automatique (mode « toutes les particules »)
Une particule est utilisée si :
1. elle est suivie sur au moins 60 % du film ;
2. son intensité atteint le seuil (40 % de l'intensité de référence, 90e centile des particules suivies) : les particules hors focus sont moins lumineuses ;
3. aucune autre particule n'est plus proche que la distance minimale (20 pixels) : pas de chevauchement ;
4. D > 0 et sa trajectoire n'a pas de saut (un pas supérieur à 8 fois le pas typique) ;
5. log(D) ne s'écarte pas de plus de 3 écarts absolus médians de la médiane (valeurs aberrantes, trop lentes comme trop rapides).
Les seuils sont dans Paramètres. Les particules écartées sont listées avec la raison.

## Moyenne du film entier
Quand on choisit des zones (ou la plus lumineuse), l'interface calcule aussi, à droite, le rayon moyen de toutes les particules exploitables du film (mêmes seuils que le mode automatique). Une particule choisie dont D s'écarte de plus de 3 écarts absolus médians (sur log D) de celui du film est marquée « atypique » : elle reste dans la moyenne choisie, mais elle est signalée (orange) et probablement collée, mal suivie ou confondue avec une autre.

## Colonnes du tableau
- Intensité : contraste médian en % de l'intensité de référence du film.
- Incertitude (± nm) : incertitude statistique sur le rayon de la particule, estimée sur 5 blocs de sa trajectoire.

Tous les paramètres de l'analyse sont affichés sur les graphiques (modèle MSD = 4Dτ + c, D, c, Δt, délais ajustés, nombre de particules).

## Incertitude
- Rayon moyen : a = kB T / (6 pi eta D moyen), avec T = 293,15 K et eta = 1,002 mPa s. D moyen est la moyenne des D des particules utilisées.
- Incertitude statistique : incertitude type de la moyenne de D entre particules (3 particules ou plus), convertie en rayon :

      s(D moyen) = racine( somme(i = 1 à n) (Di - D moyen)^2 / (n (n - 1)) )
      D moyen = (1/n) somme(i = 1 à n) Di

  Pour 1 ou 2 particules : dispersion de D sur 5 blocs de chaque trajectoire.
- La dispersion entre particules (1,48 x écart absolu médian des rayons) est affichée à part.

## Limites connues
- L'échelle µm/pixel (modifiable dans Paramètres) reste à confirmer avec la règle graduée (binning du mode 1332x990 à vérifier). Le rayon varie comme 1/p^2.
- Le suivi suppose des particules bien séparées. Deux particules à moins de 16 pixels peuvent échanger leur trajectoire.
