"""Acquisition de films au microscope (Mandat 3). Aucun suivi ni localisation ici :
on enregistre des films, qui seront analysés plus tard avec analyser_films.py.

Utilisation (sur le Raspberry Pi, caméra branchée, dans le dossier Microscope) :
    python3 acquisition.py                         réglages par défaut (voir PARAMETRES)
    python3 acquisition.py --dt 0.05 --exp 0.02 --duree 30 --nom bille2um
    python3 acquisition.py --apercu                affiche d'abord l'image en direct (mise au point)
    python3 acquisition.py --aide                  liste de tous les réglages

Déroulement : le programme règle la caméra, puis attend. Appuie sur Entrée pour enregistrer un film
(ou écris un commentaire, ex. "particule 3, bien centrée", puis Entrée). Tape q pour quitter.

Chaque film donne dans le dossier films_acquis :
    <nom>_<numéro>_dt_<dt>s_exp_<exp>s_PixelSize_<pixel>um_Mono_8bit.tif   le film (images en niveaux de gris)
    <nom>_<numéro>_....json                                                tous les réglages, le commentaire
                                                                           et les instants réels des images
Le nom du .tif contient dt, exposition et taille de pixel : analyser_films.py les lit automatiquement.

A FAIRE AVANT LA SEANCE :
    - Mesurer la taille de pixel dans l'échantillon avec une règle micrométrique et la donner avec --pixel
      (sinon on utilise PIXEL_CAMERA_UM * FACTEUR_MODE / grossissement, FACTEUR_MODE est à vérifier).
    - Vérifier le grossissement et la NA réels de l'objectif (--objectif, --na).
"""
import argparse
import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

# ----------------------------------------------------------------------------- PARAMETRES
DOSSIER_FILMS = Path(__file__).resolve().parent / "films_acquis"
TAILLE = (1332, 990)        # taille des images (largeur, hauteur) : correspond à un mode du capteur IMX477
                            # (autre mode possible : (2028, 1520), champ plus grand mais moins d'images/s)
PIXEL_CAMERA_UM = 1.55      # taille d'un pixel du capteur (um)
FACTEUR_MODE = 2.4          # calé sur la règle graduée : objectif 20X -> 0,186 um/pixel (1,55 x 2,4 / 20)
OBJECTIF_M = 20             # grossissement de l'objectif   TODO : valeur réelle
OBJECTIF_NA = 0.40          # ouverture numérique (objectif 20X)
DT_S = 0.05                 # temps entre deux images (s)
EXPOSITION_S = 0.02         # temps d'exposition (s), doit être <= dt
DUREE_S = 30.0              # durée d'un film (s)
GAIN = 1.0                  # gain analogique, fixe pendant toute la séance
NOM = "film"                # début du nom des fichiers


# ----------------------------------------------------------------------------- Fichiers
def nom_de_base(nom, numero, dt_s, exposition_s, pixel_um):
    return f"{nom}_{numero:02d}_dt_{dt_s:g}s_exp_{exposition_s:g}s_PixelSize_{pixel_um:g}um_Mono_8bit"


def prochain_numero(dossier, nom):
    """Premier numéro libre, pour ne jamais écraser un film existant."""
    deja = [int(m.group(1)) for f in dossier.glob(f"{nom}_*.tif")
            if (m := re.match(rf"{re.escape(nom)}_(\d+)_", f.name))]
    return max(deja, default=0) + 1


def sauvegarder_film(images, chemin):
    """Écrit un .tif multi-images en niveaux de gris (8 bits), sans compression."""
    frames = [Image.fromarray(a) for a in images]
    frames[0].save(chemin, save_all=True, append_images=frames[1:], compression=None)


# ----------------------------------------------------------------------------- Caméra
def configurer_camera(args):
    from picamera2 import Picamera2

    camera = Picamera2()
    duree_image_us = round(args.dt * 1_000_000)
    config = camera.create_video_configuration(
        main={"format": "YUV420", "size": TAILLE},    # on garde la luminance (Y) : image en gris, 8 bits
        raw={"size": TAILLE},                          # impose le mode du capteur
        buffer_count=8,
        controls={
            "AeEnable": False,                         # pas d'exposition automatique
            "AwbEnable": False,                        # pas de balance des blancs
            "ExposureTime": round(args.exp * 1_000_000),
            "AnalogueGain": args.gain,
            "FrameDurationLimits": (duree_image_us, duree_image_us),   # impose dt
            "NoiseReductionMode": 0,                   # pas de débruitage de la caméra
            "Sharpness": 0.0,                          # pas d'accentuation
        },
    )
    camera.configure(config)
    return camera


def enregistrer_film(camera, args, numero, commentaire):
    largeur, hauteur = TAILLE
    n_images = max(2, round(args.duree / args.dt))
    octets = n_images * largeur * hauteur
    libre = shutil.disk_usage(DOSSIER_FILMS).free
    if octets * 1.2 > libre:
        print(f"Pas assez d'espace disque : il faut environ {octets / 1e6:.0f} Mo, il reste {libre / 1e6:.0f} Mo.")
        return None

    print(f"Enregistrement de {n_images} images (environ {n_images * args.dt:.1f} s)...")
    images, instants_ns, expositions_us = [], [], []
    debut = time.perf_counter()
    for i in range(n_images):
        requete = camera.capture_request()
        try:
            image = requete.make_array("main")[:hauteur].copy()     # les `hauteur` premières lignes = luminance
            metadonnees = requete.get_metadata()
        finally:
            requete.release()
        images.append(image)
        instants_ns.append(metadonnees["SensorTimestamp"])
        expositions_us.append(metadonnees.get("ExposureTime"))
        if (i + 1) % max(1, n_images // 10) == 0:
            print(f"  {100 * (i + 1) // n_images} %")
    duree_reelle = time.perf_counter() - debut

    intervalles = np.diff(np.array(instants_ns)) / 1e9
    manquantes = int(np.sum(intervalles > 1.5 * args.dt))
    base = nom_de_base(args.nom, numero, args.dt, args.exp, args.pixel)
    chemin = DOSSIER_FILMS / f"{base}.tif"
    sauvegarder_film(images, chemin)

    infos = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "commentaire": commentaire,
        "fichier": chemin.name,
        "n_images": n_images,
        "taille_px": list(TAILLE),
        "dt_demande_s": args.dt,
        "dt_reel_median_s": float(np.median(intervalles)),
        "dt_reel_ecart_type_s": float(np.std(intervalles)),
        "dt_reel_max_s": float(np.max(intervalles)),
        "images_manquantes_estimees": manquantes,
        "exposition_demandee_s": args.exp,
        "exposition_reelle_s": (float(np.median([e for e in expositions_us if e])) / 1e6
                                if any(expositions_us) else None),
        "gain": args.gain,
        "pixel_um": args.pixel,
        "objectif_M": args.objectif,
        "objectif_NA": args.na,
        "profondeur_bits": 8,
        "duree_totale_s": duree_reelle,
        "instants_images_ns": [int(t) for t in instants_ns],
    }
    (DOSSIER_FILMS / f"{base}.json").write_text(json.dumps(infos, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Film enregistré : {chemin.name}")
    print(f"  dt réel : {infos['dt_reel_median_s'] * 1000:.1f} ms (demandé {args.dt * 1000:.1f} ms), "
          f"images manquantes estimées : {manquantes}")
    if manquantes:
        print("  ATTENTION : des images ont été perdues. Augmente dt ou diminue la taille de l'image.")
    return chemin


# ----------------------------------------------------------------------------- Programme
def lire_arguments():
    p = argparse.ArgumentParser(description="Acquisition de films au microscope (Mandat 3).", add_help=False)
    p.add_argument("--aide", action="help", help="affiche cette aide")
    p.add_argument("--dt", type=float, default=DT_S, help="temps entre deux images (s)")
    p.add_argument("--exp", type=float, default=EXPOSITION_S, help="temps d'exposition (s), <= dt")
    p.add_argument("--duree", type=float, default=DUREE_S, help="durée d'un film (s)")
    p.add_argument("--gain", type=float, default=GAIN, help="gain analogique")
    p.add_argument("--nom", default=NOM, help="début du nom des fichiers (sans espace)")
    p.add_argument("--objectif", type=float, default=OBJECTIF_M, help="grossissement de l'objectif")
    p.add_argument("--na", type=float, default=OBJECTIF_NA, help="ouverture numérique de l'objectif")
    p.add_argument("--pixel", type=float, default=None, help="taille d'un pixel dans l'échantillon (um), mesurée")
    p.add_argument("--apercu", action="store_true", help="affiche l'image en direct (mise au point)")
    args = p.parse_args()
    if args.exp > args.dt:
        p.error("le temps d'exposition doit être inférieur ou égal à dt")
    if args.pixel is None:
        args.pixel = round(PIXEL_CAMERA_UM * FACTEUR_MODE / args.objectif, 4)
        print(f"Taille de pixel non donnée : {args.pixel:g} um (calcul, à vérifier avec --pixel).")
    args.nom = re.sub(r"[^A-Za-z0-9-]", "-", args.nom)    # pas d'espace ni de "_" dans le nom
    return args


def main():
    args = lire_arguments()
    DOSSIER_FILMS.mkdir(exist_ok=True)
    camera = configurer_camera(args)
    if args.apercu:
        try:
            from picamera2 import Preview
            camera.start_preview(Preview.QT)
        except Exception as erreur:
            print(f"Aperçu impossible : {erreur}")
    camera.start()
    time.sleep(1.0)          # laisse les réglages se stabiliser

    print(f"Caméra prête : dt = {args.dt:g} s, exposition = {args.exp:g} s, gain = {args.gain:g}, "
          f"film de {args.duree:g} s, pixel = {args.pixel:g} um.")
    try:
        while True:
            reponse = input("Entrée = enregistrer un film (ou écris un commentaire), q = quitter : ").strip()
            if reponse.lower() == "q":
                break
            numero = prochain_numero(DOSSIER_FILMS, args.nom)
            enregistrer_film(camera, args, numero, reponse)
    finally:
        camera.stop()
        camera.close()


if __name__ == "__main__":
    main()
