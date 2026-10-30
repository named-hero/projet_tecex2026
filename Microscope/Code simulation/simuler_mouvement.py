"""Simulation d'un film de microscopie à fluorescence : une particule en mouvement brownien.

Utilisation :
    python simuler_mouvement.py

Le film est enregistré dans le dossier "films" au format .tif (comme ceux de Moodle), avec :
    - un fichier .json qui contient les vraies valeurs (rayon, D), pour comparer à l'analyse ;
    - un fichier _trajectoire_vraie.csv avec la vraie trajectoire.
Il peut ensuite être analysé avec : python analyser_films.py

Les étapes (une fonction par étape) :
    1. coefficient_diffusion : D = kB T / (6 pi eta a)  (Stokes-Einstein)
    2. simuler_trajectoire   : positions de la particule (marche aléatoire, flou de mouvement inclus)
    3. image_psf             : tache d'Airy de la particule, photons, bruit, conversion en niveaux de gris
    4. enregistrer le film et les vraies valeurs

Modèle de signal (hypothèses, à calibrer avec le vrai montage) : le nombre de photons est
proportionnel au volume de la particule (rayon^3), puis à la fraction de lumière collectée par l'objectif.
"""
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.special import j1

# ----------------------------------------------------------------------------- Paramètres à modifier
RAYON_UM = 1.0             # rayon vrai de la particule (um)
GROSSISSEMENT = 20         # grossissement de l'objectif
NA = 0.40                  # ouverture numérique de l'objectif
N_IMAGES = 50              # nombre d'images du film
DT_S = 0.10                # temps entre deux images (s)
EXPOSITION_S = 0.02        # temps d'exposition (s), doit être <= DT_S
TAILLE_IMAGE_PX = 128      # l'image est carrée : TAILLE_IMAGE_PX x TAILLE_IMAGE_PX pixels

# Valeurs physiques et de la caméra (rarement à changer)
LAMBDA_UM = 0.600          # longueur d'onde d'émission (um), hypothèse : colorant orange-rouge
N_EAU = 1.33               # indice de réfraction de l'eau
T_K = 293.15               # température (K)
ETA = 1.002e-3             # viscosité de l'eau (Pa s)
KB = 1.380649e-23          # constante de Boltzmann (J/K)
PIXEL_CAMERA_UM = 1.55     # taille d'un pixel de la caméra HQ (um)
BITS = 12                  # profondeur de bits
GAIN_E_PAR_ADU = 2.0       # électrons par niveau de gris (hypothèse)
BRUIT_LECTURE_E = 3.0      # bruit de lecture (électrons) (hypothèse)
FLUX_REF = 2.0e5           # photo-électrons par seconde pour a = 0.5 um et NA = 0.85 (hypothèse)
FOND_E_PAR_S_PAR_UM2 = 50  # fond (électrons par seconde et par um^2) (hypothèse)
N_SOUS_PAS = 4             # positions calculées pendant l'exposition (pour le flou de mouvement)

DOSSIER_FILMS = Path(__file__).resolve().parent / "films"


# ----------------------------------------------------------------------------- 2. Trajectoire
def simuler_trajectoire(D, z_max):
    """Positions (um) pendant l'exposition de chaque image : tableau (N_IMAGES, N_SOUS_PAS, 3).

    A chaque pas de durée dt, chaque coordonnée change d'une valeur gaussienne d'écart-type
    sqrt(2 D dt). Pendant l'exposition on calcule N_SOUS_PAS positions : leur moyenne temporelle
    reproduit le flou de mouvement. Le plan focal est z = 0, et z de départ est tiré au hasard
    dans la zone nette [-z_max, z_max].
    """
    dt_sous = EXPOSITION_S / N_SOUS_PAS
    dt_mort = max(DT_S - EXPOSITION_S, 0.0)
    ecarts = np.array([np.sqrt(2 * D * dt_sous)] * N_SOUS_PAS + [np.sqrt(2 * D * dt_mort)])
    pas = np.random.normal(size=(N_IMAGES, N_SOUS_PAS + 1, 3)) * ecarts[None, :, None]
    pos = np.cumsum(pas.reshape(-1, 3), axis=0).reshape(N_IMAGES, N_SOUS_PAS + 1, 3)
    pos[:, :, 2] += np.random.uniform(-z_max, z_max)
    return pos[:, :N_SOUS_PAS, :]


# ----------------------------------------------------------------------------- 3. Image
def efficacite_collection(na):
    """Fraction de la lumière émise (dans toutes les directions) collectée par l'objectif."""
    return 0.5 * (1 - np.sqrt(1 - (na / N_EAU) ** 2))


def psf_airy(r, z, pixel_um):
    """Tache d'Airy normalisée (intégrale 1), avec défocalisation simplifiée.

    PSF(r) = [2 J1(v) / v]^2, avec v = 2 pi NA r / lambda  (éq. 1 du manuel).
    Hors du plan focal (z != 0), la tache s'élargit du facteur sqrt(1 + (z / zR)^2), avec
    zR = n lambda / NA^2, en gardant le même nombre total de photons.
    """
    s = np.sqrt(1 + (z / (N_EAU * LAMBDA_UM / NA ** 2)) ** 2)
    v = 2 * np.pi * NA * (r / s) / LAMBDA_UM
    with np.errstate(divide="ignore", invalid="ignore"):
        brut = np.where(v < 1e-8, 1.0, (2 * j1(v) / v) ** 2)
    return brut * (np.pi * NA ** 2 / LAMBDA_UM ** 2) / s ** 2


def creer_image(positions_sous, pixel_um, n_photons, fond_e):
    """Une image du film, en niveaux de gris (0 à 2^BITS - 1).

    La tache n'est calculée que dans une fenêtre autour de la particule (la lumière loin de
    la particule est négligeable), puis placée dans une image qui contient aussi le fond.
    Chaque pixel reçoit un nombre de photons aléatoire (loi de Poisson), puis le bruit de
    lecture de la caméra est ajouté.
    """
    n = TAILLE_IMAGE_PX
    centre = positions_sous.mean(axis=0)
    xc, yc = centre[0] / pixel_um + n / 2, centre[1] / pixel_um + n / 2     # centre en pixels
    sigma_um = 0.21 * LAMBDA_UM / NA
    demi = int(np.ceil(3 * (LAMBDA_UM / NA) / pixel_um + 3 * np.ptp(positions_sous[:, :2]) / pixel_um)) + 4
    demi = min(demi, n // 2 - 1)
    ix0, iy0 = int(round(xc)) - demi, int(round(yc)) - demi
    attendu = np.full((n, n), fond_e)
    q = int(np.clip(np.ceil(2 * pixel_um / sigma_um), 1, 6))      # sur-échantillonnage dans un pixel
    sous = ((np.arange(q) + 0.5) / q - 0.5) * pixel_um
    largeur = 2 * demi + 1
    coord_x = ((ix0 + np.arange(largeur) - n / 2)[:, None] * pixel_um + sous[None, :]).ravel()
    coord_y = ((iy0 + np.arange(largeur) - n / 2)[:, None] * pixel_um + sous[None, :]).ravel()
    X, Y = np.meshgrid(coord_x, coord_y)
    dens = np.zeros_like(X)
    for x, y, z in positions_sous:
        dens += psf_airy(np.hypot(X - x, Y - y), z, pixel_um)
    dens = dens / len(positions_sous)
    dens = dens.reshape(largeur, q, largeur, q).mean(axis=(1, 3))        # intégrale sur chaque pixel
    xs0, xs1 = max(ix0, 0), min(ix0 + largeur, n)
    ys0, ys1 = max(iy0, 0), min(iy0 + largeur, n)
    if xs1 > xs0 and ys1 > ys0:
        attendu[ys0:ys1, xs0:xs1] += (dens * pixel_um ** 2 * n_photons)[ys0 - iy0:ys1 - iy0, xs0 - ix0:xs1 - ix0]
    electrons = np.random.poisson(attendu) + np.random.normal(0, BRUIT_LECTURE_E, attendu.shape)
    return np.clip(np.round(electrons / GAIN_E_PAR_ADU), 0, 2 ** BITS - 1)


# ----------------------------------------------------------------------------- Programme principal
def main():
    pixel_um = PIXEL_CAMERA_UM / GROSSISSEMENT
    D = KB * T_K / (6 * np.pi * ETA * RAYON_UM * 1e-6) * 1e12
    z_max = N_EAU * LAMBDA_UM / NA ** 2
    positions = simuler_trajectoire(D, z_max)

    # Photons par image : proportionnel à a^3 et à la lumière collectée (hypothèses de signal)
    n_photons = (FLUX_REF * (RAYON_UM / 0.5) ** 3 * EXPOSITION_S * efficacite_collection(NA) / efficacite_collection(0.85))
    fond = FOND_E_PAR_S_PAR_UM2 * pixel_um ** 2 * EXPOSITION_S * efficacite_collection(NA) / efficacite_collection(0.85)

    champ = TAILLE_IMAGE_PX * pixel_um
    sortie = np.any(np.abs(positions[:, :, :2].mean(axis=1)) > champ / 2)
    images = [creer_image(p, pixel_um, n_photons, fond) for p in positions]

    nom = f"Film_simule_a_{RAYON_UM}um_dt_{DT_S}s_exp_{EXPOSITION_S}s_PixelSize_{pixel_um:.4g}um"
    DOSSIER_FILMS.mkdir(exist_ok=True)
    pages = [Image.fromarray(im.astype(np.uint16)) for im in images]
    pages[0].save(DOSSIER_FILMS / (nom + ".tif"), save_all=True, append_images=pages[1:])
    verite = {"rayon_um": RAYON_UM, "D_um2_s": D, "pixel_um": pixel_um, "dt_s": DT_S, "exposition_s": EXPOSITION_S,
              "grossissement": GROSSISSEMENT, "NA": NA, "photons_par_image": n_photons}
    (DOSSIER_FILMS / (nom + ".json")).write_text(json.dumps(verite, indent=2))
    with open(DOSSIER_FILMS / (nom + "_trajectoire_vraie.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "x_um", "y_um", "z_um"])
        for k, p in enumerate(positions):
            w.writerow([k, *np.round(p.mean(axis=0), 5)])

    print(f"Film enregistré : {DOSSIER_FILMS / (nom + '.tif')}")
    print(f"  rayon = {RAYON_UM} um, D = {D:.4f} um^2/s, pixel = {pixel_um:.4f} um, "
          f"champ = {champ:.1f} um, photons par image = {n_photons:.0f}")
    print(f"  pas moyen par image (par axe) = {np.sqrt(2 * D * DT_S):.3f} um")
    if sortie:
        print("  ATTENTION : la particule sort de l'image. Augmente TAILLE_IMAGE_PX ou le grossissement.")


if __name__ == "__main__":
    main()
