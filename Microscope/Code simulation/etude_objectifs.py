"""Étude de l'objectif : biais relatif B du rayon estimé, avec son incertitude.

Utilisation :
    python etude_objectifs.py

Pour chaque objectif (grossissement, NA) et chaque rayon vrai, le script simule N_PISTES
trajectoires de N_IMAGES images (simuler_mouvement.py, image idéale sans bruit), localise la
particule (analyser_films.py), estime D puis le rayon, et calcule :
    B       = a_est / a_vrai - 1, avec a_est tiré du D moyen sur les trajectoires (estimateur d'ensemble)
    inc_B   = écart-type des rayons estimés / sqrt(nombre de trajectoires) / a_vrai  (incertitude statistique)
    disp    = écart-type / moyenne des rayons estimés d'une trajectoire (dispersion d'une trajectoire)
B est un résultat à rapporter avec son incertitude, sans seuil de réussite.

Les mêmes trajectoires et les mêmes images servent à comparer les techniques de localisation
(LOCALISATIONS) et de suivi, c'est-à-dire d'estimation de D (TECHNIQUES_SUIVI) : comparaison appariée.
Le résultat est enregistré dans resultats/etude_objectifs.csv (une ligne par objectif, rayon,
localisation et technique) et résumé à l'écran.

Durée : environ 8 minutes avec les réglages par défaut (4 objectifs, 5 rayons, 20 trajectoires). Pour un essai
rapide, réduire OBJECTIFS, RAYONS_UM et N_PISTES.
"""
import csv
import time
from pathlib import Path

import numpy as np

import analyser_films as A
import simuler_mouvement as S

# ----------------------------------------------------------------------------- Paramètres
OBJECTIFS = [(10, 0.30), (20, 0.40), (20, 0.45), (40, 0.65)]   # (grossissement, NA) à étudier
RAYONS_UM = [0.1, 0.5, 1.0, 2.0, 5.0]       # rayons vrais (um)
DT_S = 0.02                # temps entre deux images (s)
EXPOSITION_S = 0.02        # temps d'exposition (s), <= DT_S
N_IMAGES = 100             # images par trajectoire
N_PISTES = 20              # trajectoires par configuration
TAILLE_IMAGE_PX = 256      # taille de l'image simulée (pixels) : assez grande pour que la particule ne sorte pas
LOCALISATIONS = ["gauss", "centroide"]
TECHNIQUES_SUIVI = ["msd4", "msd4_o0", "msd10", "cve"]
GRAINE = 20261030          # graine du générateur aléatoire (résultats reproductibles)

DOSSIER_RESULTATS = Path(__file__).resolve().parent / "resultats"


def regler_simulation(M, NA, rayon_um):
    """Le module simuler_mouvement lit ses paramètres comme variables de module : on les règle ici."""
    S.GROSSISSEMENT, S.NA, S.RAYON_UM = M, NA, rayon_um
    S.N_IMAGES, S.DT_S, S.EXPOSITION_S = N_IMAGES, DT_S, EXPOSITION_S
    S.TAILLE_IMAGE_PX = TAILLE_IMAGE_PX
    return S.PIXEL_CAMERA_UM / M, S.KB * S.T_K / (6 * np.pi * S.ETA * rayon_um * 1e-6) * 1e12


def une_trajectoire(D, pixel_um):
    """Simule une trajectoire et retourne les positions vraies et les images idéales."""
    positions = S.simuler_trajectoire(D, S.N_EAU * S.LAMBDA_UM / S.NA ** 2)
    vraies = positions.mean(axis=1)
    champ = S.TAILLE_IMAGE_PX * pixel_um
    if np.any(np.abs(vraies[:, :2]) > champ / 2 - A.DEMI_FENETRE_PX * pixel_um):
        return None, None                      # la particule sort de l'image : trajectoire rejetée
    return vraies, [S.creer_image(p, pixel_um) for p in positions]


def main():
    np.random.seed(GRAINE)
    lignes, debut = [], time.time()
    for M, NA in OBJECTIFS:
        for rayon in RAYONS_UM:
            pixel_um, D_vrai = regler_simulation(M, NA, rayon)
            # a_est[(localisation, technique)] : rayons estimés trajectoire par trajectoire
            a_est = {(l, t): [] for l in LOCALISATIONS for t in TECHNIQUES_SUIVI}
            D_est = {(l, t): [] for l in LOCALISATIONS for t in TECHNIQUES_SUIVI}
            n_rejetees = 0
            for _ in range(N_PISTES):
                vraies, images = une_trajectoire(D_vrai, pixel_um)
                if images is None:
                    n_rejetees += 1
                    continue
                for localisation in LOCALISATIONS:
                    positions = A.localiser_film(images, pixel_um, localisation)
                    for technique in TECHNIQUES_SUIVI:
                        D = A.estimer_D(positions, DT_S, technique)
                        if np.isfinite(D) and D > 0:
                            D_est[(localisation, technique)].append(D)
                            a_est[(localisation, technique)].append(A.rayon_depuis_D(D))
            for (localisation, technique), rayons in a_est.items():
                n = len(rayons)
                ligne = {"M": M, "NA": NA, "rayon_vrai_um": rayon, "localisation": localisation,
                         "technique_suivi": technique, "n_trajectoires": n, "n_rejetees": n_rejetees}
                if n >= 2:
                    D_ens = np.mean(D_est[(localisation, technique)])
                    ligne["B"] = A.rayon_depuis_D(D_ens) / rayon - 1
                    ligne["inc_B"] = np.std(rayons, ddof=1) / np.sqrt(n) / rayon
                    ligne["dispersion_piste"] = np.std(rayons, ddof=1) / np.mean(rayons)
                else:
                    ligne.update({"B": np.nan, "inc_B": np.nan, "dispersion_piste": np.nan})
                lignes.append(ligne)
            print(f"{M}X / NA {NA:g}, a = {rayon:g} um : fait ({time.time() - debut:.0f} s)")

    DOSSIER_RESULTATS.mkdir(exist_ok=True)
    colonnes = list(lignes[0])
    with open(DOSSIER_RESULTATS / "etude_objectifs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colonnes)
        w.writeheader()
        for l in lignes:
            w.writerow({k: (f"{v:.5g}" if isinstance(v, float) else v) for k, v in l.items()})

    print("\nRésumé : |B| moyen (%) ± erreur-type, tous rayons, par objectif (localisation gaussienne, MSD à 4 délais)")
    for M, NA in OBJECTIFS:
        b = [abs(l["B"]) * 100 for l in lignes if l["M"] == M and l["NA"] == NA and l["localisation"] == "gauss"
             and l["technique_suivi"] == "msd4" and np.isfinite(l["B"])]
        if len(b) > 1:
            print(f"  {M}X / NA {NA:g} : {np.mean(b):.1f} ± {np.std(b, ddof=1) / np.sqrt(len(b)):.1f}")
    print("\nRésumé : |B| moyen (%) et dispersion par trajectoire (%), par technique de suivi (localisation gaussienne)")
    for t in TECHNIQUES_SUIVI:
        sel = [l for l in lignes if l["localisation"] == "gauss" and l["technique_suivi"] == t and np.isfinite(l["B"])]
        print(f"  {t:>8} : |B| = {np.mean([abs(l['B']) for l in sel]) * 100:.1f}, "
              f"dispersion = {np.mean([l['dispersion_piste'] for l in sel]) * 100:.1f}")
    print(f"\nTableau enregistré dans : {DOSSIER_RESULTATS / 'etude_objectifs.csv'}")


if __name__ == "__main__":
    main()
