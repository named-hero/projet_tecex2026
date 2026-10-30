# Suivi de particules : scripts de base (PHS3910, Mandat 3)

Cinq scripts, chacun dans un seul fichier. La simulation est idéale : une seule particule claire sur
fond noir, sans fond, sans lumière parasite, sans bruit de lecture ni bruit de photons.

| Script | Rôle |
|---|---|
| `analyser_films.py` | Lit un film .tif, localise la particule, calcule le MSD, puis D et le rayon |
| `simuler_mouvement.py` | Fabrique un film .tif d'une particule en mouvement brownien (rayon, objectif, exposition au choix) |
| `visualiser_film.py` | Sélectionne un film `.tiff` dans `films` et l'affiche en animation |
| `critere_pixels.py` | Critère de pixels : déplacement par image en pixels et rayon maximal a_max, pour chaque objectif (instantané) |
| `etude_objectifs.py` | Biais relatif B du rayon estimé avec son incertitude, par objectif et par rayon, et comparaison des techniques de localisation et de suivi |

## Installation (une seule fois)

```
cd "Code simulation"
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
5. Critère de pixels : `python critere_pixels.py`. Le tableau est dans `resultats/critere_pixels.csv`.
6. Étude de l'objectif : régler les listes en haut de `etude_objectifs.py` (objectifs, rayons, nombre de
   trajectoires), puis `python etude_objectifs.py` (environ 8 minutes). Le tableau est dans
   `resultats/etude_objectifs.csv`.

## Ce que fait la chaîne, en 5 étapes

1. La particule diffuse : D = kB T / (6 pi eta a) (Stokes-Einstein), pas gaussiens d'écart-type sqrt(2 D dt) par axe.
2. L'objectif l'image : tache d'Airy, PSF(r) = [2 J1(v)/v]^2 avec v = 2 pi NA r / lambda.
3. La caméra enregistre l'image idéale : la tache est intégrée sur chaque pixel (taille p = 1,55 um / M), sans bruit.
4. La position est retrouvée image par image, par un ajustement gaussien 2D (ou par moyenne pondérée).
5. Le MSD (déplacement carré moyen) suit MSD = 4 D t + c en 2D : la pente donne D, puis a = kB T / (6 pi eta D).

## Critères et techniques comparées

- **Critère de pixels** : le déplacement quadratique moyen par image, sqrt(4 D dt), doit atteindre au moins un
  pixel (seuil d'équipe, `SEUIL_PIXELS`). Il borne le rayon : a_max = 2 kB T dt / (3 pi eta p^2).
- **Biais relatif** B = a_estimé / a_vrai - 1, rapporté avec son incertitude (écart-type / racine du nombre de
  trajectoires). Aucun seuil n'est imposé.
- **Localisation** : ajustement gaussien 2D ou moyenne pondérée (barycentre de l'intensité au-dessus du fond).
- **Suivi (estimation de D)** : `msd4` (MSD sur 4 délais, ordonnée à l'origine libre, technique de référence),
  `msd4_o0` (ordonnée forcée à zéro), `msd10` (10 délais), `cve` (covariance des pas).

## À savoir

- Le signal est idéal : pas de bruit, de fond ni de lumière parasite. Les écarts entre techniques de
  localisation et de suivi seront plus marqués sur de vraies images.
- Un film d'une seule particule de 50 images donne un rayon à environ 20 à 30 % près : c'est normal (peu de
  données). Pour une valeur fiable, il faut moyenner plusieurs trajectoires (voir `etude_objectifs.py`).
- Le nom du film sert à lire la taille de pixel (`PixelSize_0.5um`) et le délai (`dt_0.1s` ou `exp_0.5s`).
