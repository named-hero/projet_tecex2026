"""Annotation des images d'une séquence (exigence du test en conditions réelles).

Chaque image de la vidéo remise doit afficher : le temps écoulé depuis le début en unités SI,
l'échelle spatiale en µm/pixel et les conditions d'acquisition (grossissement, temps d'exposition,
fréquence d'acquisition, profondeur de bit). Ce module dessine ces informations et écrit une vidéo AVI.

Utilisation en ligne de commande (PC ou Raspberry Pi) :
    python3 annotation.py film.tif --objectif "20X, NA 0,40"
Les valeurs de Δt, d'exposition et de taille de pixel sont lues dans le nom du fichier
(ex. film_01_dt_0.02s_exp_0.018s_PixelSize_0.186um_Mono_8bit.tif).
"""
import argparse
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def parametres_du_nom(nom):
    """Retourne (dt_s, exposition_s, pixel_um, bits) lus dans le nom du fichier (None si absent)."""
    def lire(motif):
        m = re.search(motif, nom, flags=re.IGNORECASE)
        return float(m.group(1).replace(",", ".")) if m else None
    bits = re.search(r"(\d+)\s*bit", nom, flags=re.IGNORECASE)
    return (lire(r"dt_([0-9]+(?:[.,][0-9]+)?)s"), lire(r"exp_([0-9]+(?:[.,][0-9]+)?)s"),
            lire(r"PixelSize_([0-9]+(?:[.,][0-9]+)?)um"), int(bits.group(1)) if bits else None)


def longueur_barre_um(largeur_px, pixel_um, fraction=0.2):
    """Longueur 'ronde' (1, 2 ou 5 x 10^k µm) la plus proche de fraction x largeur de l'image."""
    cible = largeur_px * pixel_um * fraction
    puissance = 10.0 ** np.floor(np.log10(cible))
    return min((m * puissance for m in (1, 2, 5, 10)), key=lambda v: abs(v - cible))


def _texte(image, texte, origine, echelle, couleur=(255, 255, 255)):
    epaisseur = max(1, int(round(echelle * 2)))
    cv2.putText(image, texte, origine, cv2.FONT_HERSHEY_SIMPLEX, echelle, (0, 0, 0), epaisseur + 2, cv2.LINE_AA)
    cv2.putText(image, texte, origine, cv2.FONT_HERSHEY_SIMPLEX, echelle, couleur, epaisseur, cv2.LINE_AA)


def annoter_image(image, temps_s, pixel_um, dt_s, exposition_s, objectif, bits=8, trace=None):
    """Retourne une image BGR avec temps, échelle, conditions et (facultatif) la trace d'une particule.

    image : tableau 2D (gris) ou 3D ; trace : liste de points (x_px, y_px) à dessiner jusqu'à cette image.
    """
    if image.dtype != np.uint8:
        image = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    sortie = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image.copy()
    h, w = sortie.shape[:2]
    echelle = max(0.5, w / 1400.0)
    marge = int(round(18 * echelle))
    pas = int(round(30 * echelle))
    if trace is not None and len(trace) > 1:
        points = np.round(np.array(trace)).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(sortie, [points], False, (0, 200, 255), 1, cv2.LINE_AA)
    fps = 1.0 / dt_s if dt_s else None
    lignes = [f"t = {temps_s:.3f} s",
              f"Objectif : {objectif}",
              f"Exposition : {exposition_s * 1000:g} ms" if exposition_s else "Exposition : n.d.",
              f"Cadence : {fps:.1f} images/s" if fps else "Cadence : n.d.",
              f"Profondeur de bit : {bits} bits"]
    for k, ligne in enumerate(lignes):
        _texte(sortie, ligne, (marge, marge + pas * (k + 1) - int(8 * echelle)), echelle * 0.9)
    # barre d'échelle en bas à droite
    longueur = longueur_barre_um(w, pixel_um)
    barre_px = int(round(longueur / pixel_um))
    x2, y = w - marge, h - marge - int(28 * echelle)
    x1 = x2 - barre_px
    cv2.line(sortie, (x1, y), (x2, y), (255, 255, 255), max(2, int(3 * echelle)), cv2.LINE_AA)
    etiquette = f"{longueur:g} um"
    (tw, _), _ = cv2.getTextSize(etiquette, cv2.FONT_HERSHEY_SIMPLEX, echelle, max(1, int(2 * echelle)))
    _texte(sortie, etiquette, (x2 - tw, y - int(10 * echelle)), echelle)
    echelle_txt = f"{pixel_um:.4f} um/pixel"
    (tw2, _), _ = cv2.getTextSize(echelle_txt, cv2.FONT_HERSHEY_SIMPLEX, echelle, max(1, int(2 * echelle)))
    _texte(sortie, echelle_txt, (w - marge - tw2, h - marge), echelle)
    return sortie


def lire_images(chemin):
    """Générateur d'images (tableaux 2D) d'un TIFF multipage, une à la fois (mémoire limitée)."""
    with Image.open(chemin) as film:
        for i in range(getattr(film, "n_frames", 1)):
            film.seek(i)
            a = np.asarray(film)
            yield a.mean(axis=2).astype(a.dtype) if a.ndim == 3 else a


def annoter_film(chemin_tif, sortie_avi, pixel_um, dt_s, exposition_s, objectif, bits=8,
                 trace=None, rappel=None):
    """Écrit une vidéo AVI annotée à partir d'un TIFF. La vidéo est lue à min(cadence, 30) images/s ;
    le temps affiché est le temps réel de l'acquisition. rappel(i, n) est appelé pour la progression."""
    chemin_tif = Path(chemin_tif)
    with Image.open(chemin_tif) as film:
        n = getattr(film, "n_frames", 1)
    lecture = min(30.0, 1.0 / dt_s) if dt_s else 25.0
    ecrivain = None
    for i, image in enumerate(lire_images(chemin_tif)):
        cadre = annoter_image(image, i * (dt_s or 0.0), pixel_um, dt_s, exposition_s, objectif, bits,
                              None if trace is None else trace[:i + 1])
        if ecrivain is None:
            h, w = cadre.shape[:2]
            ecrivain = cv2.VideoWriter(str(sortie_avi), cv2.VideoWriter_fourcc(*"MJPG"), lecture, (w, h))
            if not ecrivain.isOpened():
                raise RuntimeError("Impossible de créer la vidéo AVI (codec MJPG indisponible).")
        ecrivain.write(cadre)
        if rappel and (i % 10 == 0 or i == n - 1):
            rappel(i + 1, n)
    if ecrivain is not None:
        ecrivain.release()
    return Path(sortie_avi)


def main():
    p = argparse.ArgumentParser(description="Ajoute temps, échelle et conditions d'acquisition à un film TIFF.")
    p.add_argument("film")
    p.add_argument("--objectif", default="20X, NA 0,40", help="texte affiché, ex. \"20X, NA 0,40\"")
    p.add_argument("--dt", type=float)
    p.add_argument("--exposition", type=float, help="en secondes")
    p.add_argument("--pixel", type=float, help="en um/pixel")
    p.add_argument("--bits", type=int)
    p.add_argument("--sortie")
    a = p.parse_args()
    dt, expo, pixel, bits = parametres_du_nom(Path(a.film).name)
    dt, expo, pixel, bits = a.dt or dt, a.exposition or expo, a.pixel or pixel, a.bits or bits or 8
    if not (dt and pixel):
        sys.exit("Δt et la taille de pixel sont introuvables : donnez --dt et --pixel.")
    sortie = Path(a.sortie) if a.sortie else Path(a.film).with_name(Path(a.film).stem + "_annote.avi")
    annoter_film(a.film, sortie, pixel, dt, expo, a.objectif, bits,
                 rappel=lambda i, n: print(f"\r{i}/{n}", end="", flush=True))
    print(f"\nVidéo annotée : {sortie}")


if __name__ == "__main__":
    main()
