# Optimisation du spectromètre, mandat 4 (PHS3910)

Travail d'optimisation des paramètres de conception (réseau 600 traits/mm, focales f1 et f2, fente, caméra Raspberry Pi HQ) : scripts, figures, données et travail préparatoire. Le code initial de l'équipe (`../reproduire_optimisation_AVEC_GRAPHIQUES.py`, `../simulation_spectrometre_4f.py`) n'est pas modifié. Voir `CHANGELOG.md` pour ce qui a été repris ou ajouté.

## Contenu

| Fichier | Rôle |
|---|---|
| `simulation_M4.py` | modèle analytique : ordres, séparation, couverture du capteur, budget de résolution (figures M4_01 à M4_03) |
| `simulation_fourier_M4.py` | optique de Fourier 1D, défocalisation, filtre passe-haut, image RGB (figures M4_04 à M4_06) |
| `incertitudes_M4.py` | sensibilité, Monte Carlo conception et coupure (figures M4_07 à M4_09) |
| `comparaison_f1_M4.py` | comparaison des focales d'entrée, défocalisation, chromatisme (figures M4_10 à M4_12) |
| `imx477_reponse_spectrale.csv` | réponse spectrale R, G, B de la caméra HQ et filtre IR-cut (fiche Raspberry Pi RP-008148) |
| `w90_defocalisation.csv` | table écrite par `simulation_fourier_M4.py`, lue par les deux scripts suivants |
| `Spectres des lasers-20261108/` | spectres des lasers fournis avec le cours, utilisés par `incertitudes_M4.py` |
| `doc/Travail_preparatoire_M4_eq5_AM-7.docx` | travail préparatoire (version du 22 novembre 2026) |
| `M4_*.png` | figures produites par les scripts |

## Exécution

Dépendances : Python 3, numpy, matplotlib. Chaque script écrit ses figures dans son propre dossier.

1. `simulation_M4.py` (indépendant).
2. `simulation_fourier_M4.py` en premier parmi les trois autres : il écrit `w90_defocalisation.csv` (environ 15 s).
3. `incertitudes_M4.py` et `comparaison_f1_M4.py`, qui lisent ce fichier.

## Hypothèses à retenir

- Lb = 2 mm (valeur du code de départ), a = 50 µm, incertitudes de 3 µm sur a et de 1 % sur f1 : hypothèses non confirmées.
- Source à spectre plat, modèle scalaire 1D paraxial, chromatisme de L1 non modélisé.
