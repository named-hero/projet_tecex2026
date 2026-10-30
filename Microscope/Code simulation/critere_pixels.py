"""Critère de pixels : le mouvement de la particule est-il résolu par la caméra ?

Utilisation :
    python critere_pixels.py

Le déplacement quadratique moyen d'une particule entre deux images (en 2D) vaut sqrt(4 D dt).
Il est résolu s'il atteint au moins SEUIL_PIXELS pixels (un pixel dans l'échantillon mesure
PIXEL_CAMERA_UM / M). Le rayon maximal qui respecte ce critère est :

    a_max = 4 kB T dt / (6 pi eta p^2) = 2 kB T dt / (3 pi eta p^2)     (croît avec M^2 et dt)

Le script affiche, pour chaque objectif : la taille de pixel, le rayon d'Airy en pixels, le
déplacement par image pour a = 1 um, a_max pour chaque dt, la profondeur de champ zR = n lambda / NA^2
et la largeur du champ. Le tableau est aussi enregistré dans resultats/critere_pixels.csv.
"""
import csv
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------------------- Paramètres
OBJECTIFS = [(4, 0.10), (4, 0.13), (10, 0.25), (10, 0.30), (20, 0.40), (20, 0.45), (20, 0.50),
             (40, 0.65), (40, 0.70), (40, 0.75), (60, 0.85)]      # (grossissement, NA) des objectifs disponibles
DT_S = [0.02, 0.1]         # intervalles entre images testés (s)
SEUIL_PIXELS = 1.0         # déplacement minimal par image (pixels), choix d'équipe
RAYON_REF_UM = 1.0         # rayon de l'échantillon pour le déplacement par image (um)

LAMBDA_UM = 0.575          # longueur d'onde d'émission (um)
N_EAU = 1.33
T_K = 293.15
ETA = 1.002e-3
KB = 1.380649e-23
PIXEL_CAMERA_UM = 1.55
LARGEUR_CAPTEUR_PX = 3040  # plus petit côté du capteur (pixels)

DOSSIER_RESULTATS = Path(__file__).resolve().parent / "resultats"


def coefficient_diffusion(a_um):
    return KB * T_K / (6 * np.pi * ETA * a_um * 1e-6) * 1e12


def main():
    lignes = []
    for M, NA in OBJECTIFS:
        pixel = PIXEL_CAMERA_UM / M
        ligne = {"M": M, "NA": NA, "pixel_um": pixel, "rayon_airy_px": 0.61 * LAMBDA_UM / NA / pixel,
                 "zR_um": N_EAU * LAMBDA_UM / NA ** 2, "champ_um": LARGEUR_CAPTEUR_PX * pixel}
        D_ref = coefficient_diffusion(RAYON_REF_UM)
        for dt in DT_S:
            ligne[f"deplacement_px_dt{dt * 1000:g}ms"] = np.sqrt(4 * D_ref * dt) / pixel
            D_seuil = (SEUIL_PIXELS * pixel) ** 2 / (4 * dt)
            ligne[f"a_max_um_dt{dt * 1000:g}ms"] = KB * T_K / (6 * np.pi * ETA * D_seuil * 1e-12) * 1e6
        lignes.append(ligne)

    colonnes = list(lignes[0])
    print("  ".join(f"{c:>14}" for c in colonnes))
    for l in lignes:
        print("  ".join(f"{v:>14.4g}" if isinstance(v, float) else f"{v:>14}" for v in l.values()))
    DOSSIER_RESULTATS.mkdir(exist_ok=True)
    with open(DOSSIER_RESULTATS / "critere_pixels.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colonnes)
        w.writeheader()
        w.writerows(lignes)
    print(f"\nTableau enregistré dans : {DOSSIER_RESULTATS / 'critere_pixels.csv'}")


if __name__ == "__main__":
    main()
