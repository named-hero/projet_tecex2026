# Suivi de particules : scripts de base (PHS3910, Mandat 3)

Trois scripts autonomes, chacun dans un seul fichier.

| Script | Rôle |
|---|---|
| `analyser_films.py` | Lit un film .tif, localise la particule, calcule le MSD, puis D et le rayon |
| `simuler_mouvement.py` | Fabrique un film .tif d'une particule en mouvement brownien (rayon, objectif, exposition au choix) |
| `visualiser_film.py` | Sélectionne un film `.tiff` dans `films` et l'affiche en animation |

## Installation (une seule fois)

```
cd scripts_equipe
python3 -m venv .venv
source .venv/bin/activate        (Windows : .venv\Scripts\activate)
pip install -r requirements.txt
```

## Utilisation

1. Analyser les films de Moodle (déjà dans le dossier `films`) :
   `python analyser_films.py`
   Résultat attendu : D proche de 0,1 um^2/s et rayon proche de 2,1 um. Les figures sont dans `resultats`.
2. Simuler un film : modifier les paramètres en haut de `simuler_mouvement.py` (rayon, grossissement, NA,
   exposition...), puis `python simuler_mouvement.py`. Le film arrive dans `films`.
3. Analyser le film simulé : `python analyser_films.py`. Le script affiche aussi les vraies valeurs
   (fichier .json créé par la simulation) et l'erreur sur le rayon.
4. Visualiser un film : `python visualiser_film.py`, puis choisir un fichier `.tiff` dans la fenêtre
   de sélection.

## Ce que fait la chaîne, en 5 étapes

1. La particule diffuse : D = kB T / (6 pi eta a) (Stokes-Einstein), pas gaussiens d'écart-type sqrt(2 D dt) par axe.
2. L'objectif l'image : tache d'Airy, PSF(r) = [2 J1(v)/v]^2 avec v = 2 pi NA r / lambda.
3. La caméra ajoute le bruit : photons (loi de Poisson), bruit de lecture, conversion en niveaux de gris.
4. La position est retrouvée par un ajustement gaussien 2D, image par image.
5. Le MSD (déplacement carré moyen) suit MSD = 4 D t + c en 2D : la pente donne D, puis a = kB T / (6 pi eta D).

## À savoir

- Le nombre de photons, le fond et le bruit de la caméra sont des **hypothèses** (à calibrer sur le vrai montage).
- Un film d'une seule particule de 50 images donne un rayon à environ 20 à 30 % près : c'est normal (peu de
  données). Pour une valeur fiable, il faut moyenner plusieurs particules.
- Le nom du film sert à lire la taille de pixel (`PixelSize_0.5um`) et le délai (`dt_0.1s` ou `exp_0.5s`).
