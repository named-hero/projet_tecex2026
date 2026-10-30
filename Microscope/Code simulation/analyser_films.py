"""Analyse d'un film de particule : localisation, MSD, coefficient de diffusion D et rayon.

Utilisation (dans le terminal, depuis ce dossier) :
    python analyser_films.py                      analyse tous les .tif du dossier "films"
    python analyser_films.py chemin/vers/film.tif analyse un seul film
    python analyser_films.py chemin/vers/dossier  analyse tous les .tif d'un dossier

Les films de Moodle ont leur taille de pixel et leur exposition dans le nom du fichier
(ex. Film_D_0.1_exp_0.5s_PixelSize_0.5um_Mono_16bit.tif). Le script les lit automatiquement.
Si le nom ne les contient pas, les valeurs PAR DEFAUT ci-dessous sont utilisées.

Les étapes (une fonction par étape) :
    1. lire_film          : lit les images du fichier .tif
    2. localiser_film     : trouve la position de la particule dans chaque image (ajustement gaussien)
    3. calculer_msd       : déplacement carré moyen en fonction du délai
    4. ajuster_msd        : droite MSD = 4 D t + c, donc D
    5. rayon_depuis_D     : relation de Stokes-Einstein, a = kB T / (6 pi eta D)
"""
import json
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from scipy.optimize import curve_fit

# ----------------------------------------------------------------------------- Paramètres
PIXEL_UM_DEFAUT = 0.5      # taille d'un pixel dans l'échantillon (um), si absente du nom du fichier
DT_S_DEFAUT = 0.5          # temps entre deux images (s), si absent du nom du fichier
N_POINTS_MSD = 4           # nombre de délais utilisés dans l'ajustement du MSD
DEMI_FENETRE_PX = 15       # demi-largeur de la fenêtre d'ajustement autour de la particule (pixels)
T_K = 293.15               # température de l'eau (K), 20 degrés C
ETA = 1.002e-3             # viscosité de l'eau (Pa s)
KB = 1.380649e-23          # constante de Boltzmann (J/K)

DOSSIER = Path(__file__).resolve().parent
DOSSIER_FILMS = DOSSIER / "films"
DOSSIER_RESULTATS = DOSSIER / "resultats"


# ----------------------------------------------------------------------------- 1. Lecture
def lire_film(chemin):
    """Retourne un tableau (n_images, hauteur, largeur). Une image couleur est convertie en gris."""
    images = []
    with Image.open(chemin) as film:
        for i in range(getattr(film, "n_frames", 1)):
            film.seek(i)
            a = np.asarray(film, dtype=float)
            images.append(a.mean(axis=2) if a.ndim == 3 else a)
    return np.array(images)


def lire_parametres_du_nom(nom):
    """Cherche la taille de pixel (PixelSize_0.5um), le délai (dt_0.1s) ou l'exposition (exp_0.5s)."""
    pixel = re.search(r"PixelSize_([0-9.]+)um", nom)
    dt = re.search(r"dt_([0-9.]+)s", nom) or re.search(r"exp_([0-9.]+)s", nom)
    pixel_um = float(pixel.group(1)) if pixel else PIXEL_UM_DEFAUT
    dt_s = float(dt.group(1)) if dt else DT_S_DEFAUT
    return pixel_um, dt_s


# ----------------------------------------------------------------------------- 2. Localisation
def gaussienne_2d(coord, amplitude, x0, y0, sigma, fond):
    x, y = coord
    return amplitude * np.exp(-((x - x0) ** 2 + (y - y0) ** 2) / (2 * sigma ** 2)) + fond


def localiser_une_image(image):
    """Position (x, y) en pixels de la particule, par ajustement d'une gaussienne 2D.

    On trouve d'abord le maximum de l'image lissée, puis on ajuste une gaussienne dans une
    fenêtre autour de ce maximum. Retourne (nan, nan) si l'ajustement échoue.
    """
    lisse = gaussian_filter(image, 1.0)
    iy, ix = np.unravel_index(np.argmax(lisse), lisse.shape)
    h = DEMI_FENETRE_PX
    y0, y1 = max(iy - h, 0), min(iy + h + 1, image.shape[0])
    x0, x1 = max(ix - h, 0), min(ix + h + 1, image.shape[1])
    fenetre = image[y0:y1, x0:x1]
    ys, xs = np.indices(fenetre.shape)
    fond0 = np.median(fenetre)
    p0 = [fenetre.max() - fond0, ix - x0, iy - y0, 2.0, fond0]
    bornes = ([0, 0, 0, 0.3, -np.inf], [np.inf, fenetre.shape[1], fenetre.shape[0], fenetre.shape[0], np.inf])
    try:
        p, _ = curve_fit(gaussienne_2d, (xs.ravel(), ys.ravel()), fenetre.ravel(), p0=p0, bounds=bornes, maxfev=2000)
    except (RuntimeError, ValueError):
        return np.nan, np.nan
    return x0 + p[1], y0 + p[2]


def localiser_film(images, pixel_um):
    """Positions (n_images, 2) en um, image par image."""
    positions = np.array([localiser_une_image(img) for img in images])
    return positions * pixel_um


# ----------------------------------------------------------------------------- 3 à 5. MSD, D, rayon
def calculer_msd(positions, n_points):
    """MSD pour les délais de 1 à n_points images : moyenne de |x(t + k dt) - x(t)|^2."""
    msd = []
    for k in range(1, n_points + 1):
        carres = np.sum((positions[k:] - positions[:-k]) ** 2, axis=1)
        carres = carres[np.isfinite(carres)]
        msd.append(carres.mean())
    return np.array(msd)


def ajuster_msd(msd, dt_s):
    """Droite MSD = 4 D t + c (2 dimensions). La pente donne D, l'ordonnée c regroupe le bruit de localisation."""
    t = np.arange(1, len(msd) + 1) * dt_s
    pente, c = np.polyfit(t, msd, 1)
    return pente / 4.0, c, t


def rayon_depuis_D(D_um2_s):
    """Stokes-Einstein : a = kB T / (6 pi eta D). Retourne le rayon en um."""
    return KB * T_K / (6 * np.pi * ETA * D_um2_s * 1e-12) * 1e6


# ----------------------------------------------------------------------------- Programme principal
def analyser(chemin):
    pixel_um, dt_s = lire_parametres_du_nom(chemin.name)
    images = lire_film(chemin)
    positions = localiser_film(images, pixel_um)
    n_ok = int(np.isfinite(positions[:, 0]).sum())
    msd = calculer_msd(positions, min(N_POINTS_MSD, len(images) - 3))
    D, c, t = ajuster_msd(msd, dt_s)
    a = rayon_depuis_D(D) if D > 0 else np.nan

    print(f"\n{chemin.name}")
    print(f"  {len(images)} images, pixel {pixel_um} um, delai {dt_s} s, localisee dans {n_ok} images")
    print(f"  D = {D:.4f} um^2/s, rayon = {a:.3f} um")
    fichier_verite = chemin.with_suffix(".json")
    if fichier_verite.exists():
        v = json.loads(fichier_verite.read_text())
        print(f"  vrai (simulation) : D = {v['D_um2_s']:.4f} um^2/s, rayon = {v['rayon_um']:.3f} um, "
              f"erreur sur le rayon = {100 * (a / v['rayon_um'] - 1):+.1f} %")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.6), constrained_layout=True)
    ax1.plot(positions[:, 0], positions[:, 1], ".-", lw=0.7)
    ax1.set_aspect("equal")
    ax1.set(xlabel="x (um)", ylabel="y (um)", title="Trajectoire localisée")
    ax2.plot(t, msd, "o", label="MSD mesuré")
    ax2.plot(t, 4 * D * t + c, "-", label=f"ajustement : D = {D:.3f} um^2/s")
    ax2.set(xlabel="Délai (s)", ylabel="MSD (um^2)", title=f"Rayon estimé : {a:.2f} um")
    ax2.legend()
    DOSSIER_RESULTATS.mkdir(exist_ok=True)
    fig.savefig(DOSSIER_RESULTATS / (chemin.stem + "_analyse.png"), dpi=150)
    return fig


if __name__ == "__main__":
    cible = Path(sys.argv[1]) if len(sys.argv) > 1 else DOSSIER_FILMS
    films = [cible] if cible.is_file() else sorted(cible.glob("*.tif")) + sorted(cible.glob("*.tiff"))
    if not films:
        sys.exit(f"Aucun film .tif trouvé dans {cible}. Mets les films dans le dossier 'films'.")
    for film in films:
        analyser(film)
    print(f"\nFigures enregistrées dans : {DOSSIER_RESULTATS}")
    plt.show()
