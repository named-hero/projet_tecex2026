# Journal des modifications, optimisation M4 (spectromètre)

Ce journal décrit ce qui a été conservé, repris ou ajouté par rapport au code initial de l'équipe.

## Code initial conservé (inchangé)

Dans `Spectromètre/` (commit `1fbdb20`, Keira Leveneur, 20 novembre 2026) :

- `reproduire_optimisation_AVEC_GRAPHIQUES.py` : étude géométrique (angles, couverture spectrale, fente, pas du réseau, image RGB illustrative, tableau comparatif).
- `simulation_spectrometre_4f.py` : modèle scalaire 1D du montage 4f (FFT de la fente, masque du réseau, FFT vers la caméra).

Ces deux fichiers ne sont pas modifiés. Les fichiers de `optimisation_M4/` sont des copies de travail dérivées ou de nouveaux fichiers.

## simulation_M4.py (base : reproduire_optimisation_AVEC_GRAPHIQUES.py)

Conservé : convention des angles α et β du même côté de la normale (Littrow à α = β), réseau de 600 traits/mm blazé à 500 nm, capteur IMX477 (pixels de 1,55 µm, 4056 colonnes), incidence candidate α = 3°, fente a = 50 µm (hypothèse), largeur de faisceau Lb = 2 mm (largeur_reseau de `simulation_spectrometre_4f.py`).

Modifié ou ajouté :

- paramètres en unités SI, angle de blaze calculé ;
- efficacité de blaze scalaire η = sinc²(...) ;
- budget de résolution : terme de fente, terme de diffraction (Lb) et terme de pixel, sommés en quadrature (le code initial donnait seulement l'élargissement géométrique de la fente) ;
- focale de sortie maximale f2,max ;
- tableaux imprimés pour les questions guides (ordres 0 à 3, séparation selon l'incidence, largeurs de fente, pas du réseau et pixels) ;
- figures M4_01 à M4_03.

L'image RGB illustrative du code initial n'est pas reprise ici (voir `simulation_fourier_M4.py`).

## simulation_fourier_M4.py (base : simulation_spectrometre_4f.py)

Conservé : la chaîne fente, FFT (L1), réseau, FFT (L2), caméra, en modèle scalaire 1D paraxial, avec f1 = 40 mm, f2 = 25 mm, a = 50 µm, 600 traits/mm.

Modifié ou ajouté :

- le réseau n'est plus une rampe de phase idéale : l'angle de diffraction vient de l'équation du réseau (incidence oblique, facteur anamorphique cos β / cos α) et l'intensité de chaque raie est pondérée par l'efficacité de blaze η(λ) ;
- position de la raie sur le capteur x2c(λ) = f2 tan[β(λ) − β(λ0)] au lieu du retrait d'une pente de phase ;
- défocalisation d4 − f2 (phase quadratique), grille numérique redéfinie (N = 2^14, fenêtre d'au moins Lb et LB_NUM), somme incohérente sur λ d'une source à spectre plat, intégration sur les pixels de 1,55 µm ;
- filtre passe-haut idéal à 545 nm, coupure retrouvée à 50 % et transition 10-90 % ;
- comparaison de f1 = 20, 40, 50, 60 et 100 mm ;
- écriture de `w90_defocalisation.csv`, lu par `incertitudes_M4.py` et `comparaison_f1_M4.py` ;
- image RGB selon la réponse spectrale R, G, B de la caméra HQ (`imx477_reponse_spectrale.csv`) avec son filtre IR-cut, ou selon la fonction `wavelength_to_rgb` du mandat (paramètre `COULEUR`) ;
- figures M4_04 à M4_06.

Modification du 22 novembre 2026 : le bloc RGB (section 3) est calculé sans filtre, à la configuration retenue, avec ses propres constantes `ALPHA_RET` (0°) et `F1_RET` (40 mm). Le panneau « avec filtre » et l'accumulation RGB de la section 2 sont retirés. Les sections 1 et 2 restent à `ALPHA` (3°) et `F1` (60 mm). `M4_06_rgb.png` est la figure 2 du travail préparatoire.

## incertitudes_M4.py (nouveau)

Sensibilité aux paramètres de conception, Monte Carlo sur la conception, Monte Carlo sur la mesure de la longueur d'onde de coupure avec étalonnage par lasers (spectres du dossier `Spectres des lasers-20261108`). Formules du niveau 1 de `simulation_M4.py`, graine fixe 2026. Figures M4_07 à M4_09.

## comparaison_f1_M4.py (nouveau)

Comparaison des focales d'entrée, flux relatif, effet de la défocalisation sur le terme de fente (table de Fourier) et chromatisme de L2 (N-BK7). Figures M4_10 à M4_12.

## Valeurs à mettre à jour

- Les scripts utilisent α = 3° et f1 = 60 mm par défaut. Le travail préparatoire (4.1.2) retient θi = 0° et f1 = 40 mm : les valeurs de 4.1.3 à 4.1.6 restent à recalculer à 0°. Seul le bloc RGB est déjà à 0° et 40 mm.
- Lb = 2 mm est la valeur du code de Keira, non confirmée. Les incertitudes sur a (3 µm) et sur f1 (1 %) sont des hypothèses.
- Notation : α et β des scripts correspondent à θi et θm du document Word.
