"""Analyse du film TIFF : choix des particules, suivi, MSD, D et rayon (Stokes-Einstein).

L'interface de traitement appelle   analyser_video(video_path, pixel_um, dt_s, config)
et reçoit                           {"trajectories": {...}, "results": {...}}.

Trois façons de choisir les particules (config["mode"]) :
    "zones"            une ou plusieurs zones rectangulaires tracées sur l'image :
                       config["zones"] = [{"image": k, "rect": (x0, y0, x1, y1)}, ...] (pixels).
                       Dans chaque zone, la tache la plus lumineuse est suivie.
    "plus_lumineuse"   la tache la plus lumineuse de l'image config["image_depart"] (0 par défaut).
    "echantillon"      toutes les particules suivies sur au moins 60 % du film, triées automatiquement :
                       intensité >= seuil, isolée (pas de chevauchement), D > 0, pas de saut de trajectoire,
                       puis rejet des valeurs aberrantes de D (écart à la médiane > rejet_sigma écarts absolus médians).

Étapes communes :
    1. détection de toutes les taches de chaque image et suivi par appariement hongrois ;
    2. mouvement collectif (vibration, écoulement) : déplacement médian des particules du champ, soustrait ;
    3. MSD sur N_DELAIS délais et régression MSD = 4 D t + c (c tient compte de l'erreur de localisation) ;
    4. rayon a = kB T / (6 pi eta D) ; le rayon moyen est calculé avec le D moyen des particules retenues.

Incertitude du rayon moyen (statistique) :
    3 particules retenues ou plus : écart-type de la moyenne de D entre les particules ;
    moins : dispersion de D sur 5 blocs de chaque trajectoire, combinée.
    La dispersion entre particules (1,48 x écart absolu médian des rayons individuels) est donnée à part.

Utilisation seule (sans interface) :
    python3 analyse_equipe.py film.tif                       tache la plus lumineuse
    python3 analyse_equipe.py film.tif --zone X0 Y0 X1 Y1    zone rectangulaire (image 0), répétable
    python3 analyse_equipe.py film.tif --echantillon         toutes les particules triées
"""
import argparse
import os
import re
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, maximum_filter
from scipy.optimize import curve_fit, linear_sum_assignment

# ----------------------------------------------------------------------------- Paramètres
T_K = 293.15                 # température de l'eau (K), 20 degrés C
ETA_PA_S = 1.002e-3          # viscosité dynamique de l'eau (Pa s)
KB = 1.380649e-23            # constante de Boltzmann (J/K)
DEMI_FENETRE_PX = 15         # demi-largeur de la fenêtre d'ajustement gaussien
RAYON_RECHERCHE_PX = 10      # on cherche la tache à cette distance (pixels) de la position précédente
MAX_PAS_PX = 8.0             # déplacement maximal entre deux images (au-delà, la particule est perdue)
BORD_PX = 20                 # marge de l'image : une particule plus proche du bord n'est pas suivie
SNR_MIN = 5.0                # contraste minimal (pic - fond) / bruit
N_DELAIS = 4                 # nombre de délais utilisés dans la régression du MSD
N_BLOCS = 5                  # nombre de blocs pour l'incertitude statistique
MIN_REFERENCES = 10          # nombre minimal de particules de référence pour corriger le mouvement collectif
ISOLEMENT_PX = 20.0          # une particule est isolée si aucune autre n'est plus proche que cette distance (pixels)
SEUIL_INTENSITE = 0.4        # échantillon : intensité minimale, en fraction de l'intensité de référence (90e centile)
REJET_SIGMA = 3.0            # échantillon : rejet des D à plus de REJET_SIGMA écarts absolus médians de la médiane (0 = pas de rejet)
SAUT_SIGMA = 8.0             # une trajectoire dont un pas dépasse SAUT_SIGMA fois l'écart-type typique est rejetée
N_AFFICHAGE = 10            # nombre de délais calculés pour le graphique du MSD (l'ajustement utilise les N_DELAIS premiers)
FRACTION_LONGUE = 0.6        # une particule est utilisable si elle est suivie sur cette fraction du film


# ----------------------------------------------------------------------------- Lecture
class Film:
    """Accès image par image à un TIFF multipage (sans tout charger en mémoire)."""

    def __init__(self, chemin):
        self.chemin = str(chemin)
        with Image.open(self.chemin) as f:
            self.n = getattr(f, "n_frames", 1)
        self._f = Image.open(self.chemin)

    def image(self, i):
        self._f.seek(int(i))
        a = np.asarray(self._f, dtype=np.float32)
        return a.mean(axis=2) if a.ndim == 3 else a

    def fermer(self):
        self._f.close()


def parametres_du_nom(nom):
    m = re.search(r"dt_([0-9]+(?:\.[0-9]+)?)s", nom)
    p = re.search(r"PixelSize_([0-9]+(?:\.[0-9]+)?)um", nom)
    return (float(p.group(1)) if p else None), (float(m.group(1)) if m else None)


# ----------------------------------------------------------------------------- Localisation
def gaussienne_2d(coord, amplitude, x0, y0, sigma, fond):
    x, y = coord
    return amplitude * np.exp(-((x - x0) ** 2 + (y - y0) ** 2) / (2 * sigma ** 2)) + fond


def ajuster_gaussienne(image, x, y):
    """Position sous-pixel (x, y) de la tache proche de (x, y) ; None si l'ajustement échoue."""
    h, w = image.shape
    xi, yi = int(round(x)), int(round(y))
    x0, x1 = max(xi - DEMI_FENETRE_PX, 0), min(xi + DEMI_FENETRE_PX + 1, w)
    y0, y1 = max(yi - DEMI_FENETRE_PX, 0), min(yi + DEMI_FENETRE_PX + 1, h)
    fen = image[y0:y1, x0:x1].astype(np.float64)
    if fen.shape[0] < 9 or fen.shape[1] < 9:
        return None
    fond = float(np.median(fen))
    ys, xs = np.indices(fen.shape)
    try:
        p, _ = curve_fit(
            gaussienne_2d, (xs.ravel(), ys.ravel()), fen.ravel(),
            p0=[fen.max() - fond, xi - x0, yi - y0, 4.0, fond],
            bounds=([0, 0, 0, 0.5, -np.inf], [np.inf, fen.shape[1], fen.shape[0], 30, np.inf]), maxfev=1500)
    except (RuntimeError, ValueError):
        return None
    return x0 + p[1], y0 + p[2]


def bruit_et_fond(image):
    fond = float(np.median(image))
    return fond, max(1.4826 * float(np.median(np.abs(image - fond))), 0.5)


def tache_la_plus_lumineuse(image):
    lisse = gaussian_filter(image, 2.0)
    lisse[:BORD_PX], lisse[-BORD_PX:], lisse[:, :BORD_PX], lisse[:, -BORD_PX:] = 0, 0, 0, 0
    y, x = np.unravel_index(np.argmax(lisse), lisse.shape)
    return float(x), float(y)


def pic_proche(image, x, y, rayon):
    """Maximum du signal lissé dans un disque autour de (x, y) ; None s'il n'y a pas de pic net."""
    lisse = gaussian_filter(image, 2.0)
    h, w = image.shape
    xi, yi = int(round(x)), int(round(y))
    x0, x1 = max(xi - rayon, 0), min(xi + rayon + 1, w)
    y0, y1 = max(yi - rayon, 0), min(yi + rayon + 1, h)
    zone = lisse[y0:y1, x0:x1]
    if zone.size == 0:
        return None
    j, i = np.unravel_index(np.argmax(zone), zone.shape)
    fond, bruit = bruit_et_fond(image)
    if (zone[j, i] - fond) / bruit < SNR_MIN:
        return None
    return float(x0 + i), float(y0 + j)


# ----------------------------------------------------------------------------- Suivi
def suivre(film, depart, indices):
    """Positions (index, x, y) de la tache le long des images `indices` à partir de la position `depart`."""
    h, w = film.image(indices[0]).shape
    x, y = depart
    sortie = []
    for k in indices:
        img = film.image(k)
        pic = pic_proche(img, x, y, RAYON_RECHERCHE_PX)
        if pic is None:
            break
        pos = ajuster_gaussienne(img, *pic)
        if pos is None:
            break
        nx, ny = pos
        if np.hypot(nx - x, ny - y) > MAX_PAS_PX and sortie:
            break
        if min(nx, ny, w - nx, h - ny) < BORD_PX:
            break
        x, y = nx, ny
        sortie.append((k, x, y))
    return sortie


# ----------------------------------------------------------------------------- Détection de toutes les taches
def detecter_toutes(image, avec_intensite=False):
    """Positions (x, y) de toutes les taches nettes de l'image (maxima locaux du signal lissé).

    avec_intensite=True : retourne aussi le contraste de chaque tache (pic lissé - fond, en niveaux de gris).
    """
    lisse = gaussian_filter(image, 2.0)
    fond, bruit = bruit_et_fond(image)
    haut = float(lisse.max()) - fond
    seuil = fond + max(10 * bruit, 0.2 * haut, 6.0)
    pics = (lisse == maximum_filter(lisse, size=13)) & (lisse > seuil)
    ys, xs = np.nonzero(pics)
    h, w = image.shape
    pos, inten = [], []
    for x, y in zip(xs, ys):
        if min(x, y, w - 1 - x, h - 1 - y) < 12:
            continue
        fen = np.clip(image[y - 8:y + 9, x - 8:x + 9].astype(np.float64) - fond, 0, None)
        s = fen.sum()
        if s > 0:
            yy, xx = np.indices(fen.shape)
            pos.append((x - 8 + (fen * xx).sum() / s, y - 8 + (fen * yy).sum() / s))
            inten.append(float(lisse[y, x] - fond))
    pos = np.array(pos).reshape(-1, 2)
    return (pos, np.array(inten)) if avec_intensite else pos


def relier(detections, intensites=None, lien_max=MAX_PAS_PX):
    """Pistes {debut, pos, I} par appariement hongrois entre images successives (I = contraste de la tache)."""
    if intensites is None:
        intensites = [np.zeros(len(d)) for d in detections]
    actives, finies = [], []
    for i, (pos, inten) in enumerate(zip(detections, intensites)):
        if actives and len(pos):
            dern = np.array([p["pos"][-1] for p in actives])
            cout = np.hypot(dern[:, None, 0] - pos[None, :, 0], dern[:, None, 1] - pos[None, :, 1])
            cout = np.where(cout > lien_max, 1e6, cout)
            li, co = linear_sum_assignment(cout)
            pris_p, pris_d = set(), set()
            for a, b in zip(li, co):
                if cout[a, b] < 1e6:
                    actives[a]["pos"].append(tuple(pos[b]))
                    actives[a]["I"].append(float(inten[b]))
                    pris_p.add(a)
                    pris_d.add(b)
            nouvelles = [dict(debut=i, pos=[tuple(pos[b])], I=[float(inten[b])])
                         for b in range(len(pos)) if b not in pris_d]
            finies += [p for k, p in enumerate(actives) if k not in pris_p]
            actives = [p for k, p in enumerate(actives) if k in pris_p] + nouvelles
        else:
            finies += actives
            actives = [dict(debut=i, pos=[tuple(p)], I=[float(v)]) for p, v in zip(pos, inten)]
    return finies + actives


# ----------------------------------------------------------------------------- Champ : toutes les particules et mouvement collectif
_CACHE = {}


def calculer_champ(film, progression=None):
    """Détecte et relie toutes les particules du film, estime le mouvement collectif (mis en cache).

    Retourne un dictionnaire : detections, intensites, pistes, longues (suivies sur FRACTION_LONGUE du film),
    cumul (n, 2) = déplacement collectif cumulé en pixels (None si trop peu de particules de référence).
    """
    cle = (film.chemin, os.path.getsize(film.chemin), os.path.getmtime(film.chemin))
    if cle in _CACHE:
        return _CACHE[cle]
    n = film.n
    detections, intensites = [], []
    for i in range(n):
        pos, inten = detecter_toutes(film.image(i), avec_intensite=True)
        detections.append(pos)
        intensites.append(inten)
        if progression and (i % 5 == 0 or i == n - 1):
            progression(int(70 * (i + 1) / n), "Détection des particules")
    if progression:
        progression(72, "Suivi des particules")
    pistes = relier(detections, intensites)
    longues = [p for p in pistes if len(p["pos"]) >= FRACTION_LONGUE * n]
    cumul = None
    if len(longues) >= MIN_REFERENCES:
        pas_f = np.zeros((n, 2))
        for f in range(1, n):
            pas = [np.subtract(p["pos"][f - p["debut"]], p["pos"][f - p["debut"] - 1]) for p in longues
                   if 1 <= f - p["debut"] < len(p["pos"])]
            if len(pas) >= MIN_REFERENCES:
                pas_f[f] = np.median(np.array(pas), axis=0)
        cumul = np.cumsum(pas_f, axis=0)
    champ = dict(n=n, detections=detections, intensites=intensites, pistes=pistes, longues=longues, cumul=cumul)
    _CACHE.clear()
    _CACHE[cle] = champ
    return champ


def intensite_reference(champ):
    """Intensité de référence : 90e centile des intensités médianes des particules suivies sur tout le film."""
    valeurs = [float(np.median(p["I"])) for p in champ["longues"]]
    return float(np.percentile(valeurs, 90)) if valeurs else None


def intensite_trajet(champ, frames, pos):
    """Contraste médian (niveaux de gris) d'une trajectoire, lu sur les taches détectées à moins de 4 pixels."""
    valeurs = []
    for f, (x, y) in zip(frames, pos):
        det = champ["detections"][int(f)]
        if len(det):
            d = np.hypot(det[:, 0] - x, det[:, 1] - y)
            j = int(np.argmin(d))
            if d[j] < 4:
                valeurs.append(champ["intensites"][int(f)][j])
    return float(np.median(valeurs)) if valeurs else None


def distance_au_plus_proche(champ, piste, pas=5):
    """Distance minimale (pixels) entre la piste et une autre tache, sur des images échantillonnées."""
    from scipy.spatial import cKDTree
    dmin = np.inf
    for j in range(0, len(piste["pos"]), pas):
        f = piste["debut"] + j
        det = champ["detections"][f]
        if len(det) < 2:
            continue
        d, _ = cKDTree(det).query(piste["pos"][j], k=2)
        dmin = min(dmin, d[1] if d[0] < 3 else d[0])
    return float(dmin)


# ----------------------------------------------------------------------------- Choix dans une zone
def particule_dans_zone(film, champ, image, rect):
    """Position de départ (x, y) de la tache la plus lumineuse dans le rectangle (x0, y0, x1, y1) de l'image donnée.

    Retourne (position, nombre de taches dans la zone). Lève ValueError s'il n'y en a aucune."""
    x0, y0, x1, y1 = rect
    k = max(0, min(int(image), film.n - 1))
    det, inten = champ["detections"][k], champ["intensites"][k]
    dedans = [(i, j) for j, (i, _) in enumerate(zip(det, inten)) if x0 <= det[j][0] <= x1 and y0 <= det[j][1] <= y1]
    if not dedans:
        raise ValueError("Aucune particule nette dans la zone choisie : tracez le rectangle autour d'une particule "
                         "visible, sur l'image où elle est nette.")
    meilleure = max((j for _, j in dedans), key=lambda j: inten[j])
    return tuple(det[meilleure]), len(dedans)


# ----------------------------------------------------------------------------- Évaluation d'une particule
def evaluer(frames, pos_px, cumul, pixel_um, dt_s):
    """MSD, D, rayon et incertitude d'une trajectoire (images consécutives) ; corrige le mouvement collectif si cumul donné."""
    pos_px = np.asarray(pos_px, dtype=float)
    frames = np.asarray(frames)
    corr = pos_px - cumul[frames] if cumul is not None else pos_px
    um = corr * pixel_um
    delais, valeurs = msd(um, min(N_AFFICHAGE, len(um) - 2))
    D, c = ajuster_msd(delais[:N_DELAIS] * dt_s, valeurs[:N_DELAIS])
    pas = np.hypot(*np.diff(um, axis=0).T)
    sigma_pas = np.median(pas) / 1.1774 if len(pas) else 0.0
    saut = bool(sigma_pas > 0 and pas.max() > SAUT_SIGMA * sigma_pas)
    D_sans = estimer_D(pos_px * pixel_um, dt_s)
    return dict(D=float(D), c=float(c), msd=valeurs, rayon=float(rayon_nm(D)), sD=incertitude_D(um, dt_s),
                saut=saut, D_sans=float(D_sans), msd_um=valeurs)


# ----------------------------------------------------------------------------- MSD, D, rayon
def msd(positions_um, n_delais):
    p = np.asarray(positions_um)
    delais = np.arange(1, n_delais + 1)
    valeurs = np.array([np.mean(np.sum((p[k:] - p[:-k]) ** 2, axis=1)) for k in delais])
    return delais, valeurs


def ajuster_msd(delais_s, valeurs):
    """MSD = 4 D t + c (2 dimensions) : retourne (D, c)."""
    pente, ordonnee = np.polyfit(delais_s, valeurs, 1)
    return pente / 4.0, ordonnee


def rayon_nm(D_um2_s):
    return KB * T_K / (6 * np.pi * ETA_PA_S * D_um2_s * 1e-12) * 1e9 if D_um2_s > 0 else float("nan")


def estimer_D(positions_um, dt_s, n_delais=N_DELAIS):
    delais, valeurs = msd(positions_um, n_delais)
    return ajuster_msd(delais * dt_s, valeurs)[0]


def incertitude_D(positions_um, dt_s, n_delais=N_DELAIS, n_blocs=N_BLOCS):
    """Écart-type de la moyenne de D estimé sur des blocs consécutifs de la trajectoire."""
    p = np.asarray(positions_um)
    taille = len(p) // n_blocs
    if taille < n_delais + 8:
        n_blocs = max(len(p) // (n_delais + 8), 0)
        taille = len(p) // n_blocs if n_blocs else 0
    if n_blocs < 3:
        return float("nan")
    D = [estimer_D(p[b * taille:(b + 1) * taille], dt_s, n_delais) for b in range(n_blocs)]
    return float(np.std(D, ddof=1) / np.sqrt(n_blocs))


# ----------------------------------------------------------------------------- Point d'entrée
def analyser_video(video_path, pixel_um, dt_s, config=None):
    """Contrat de l'interface (voir la docstring du module pour config)."""
    config = dict(config or {})
    mode = config.get("mode")
    if mode is None:
        mode = "zones" if (config.get("zones") or config.get("point")) else "plus_lumineuse"
    progression = config.get("progression") or (lambda p, t: None)
    seuil = float(config.get("seuil_intensite", SEUIL_INTENSITE))
    rejet = float(config.get("rejet_sigma", REJET_SIGMA))
    isolement = float(config.get("isolement_px", ISOLEMENT_PX))
    film = Film(video_path)
    try:
        n = film.n
        champ = calculer_champ(film, progression)
        correction = config.get("corriger_derive", "auto") in ("auto", True)
        cumul = champ["cumul"] if correction else None
        notes = []
        if correction and cumul is None:
            notes.append(f"Mouvement collectif non corrigé : moins de {MIN_REFERENCES} particules de référence "
                         "suivies sur le film.")

        # --- candidats : {id, frames, pos, I, origine}
        candidats = []
        if mode in ("zones", "plus_lumineuse"):
            departs = []
            if mode == "zones":
                zones = config.get("zones")
                if not zones and config.get("point") is not None:
                    x, y = config["point"]
                    zones = [{"image": config.get("image_depart", 0), "rect": (x - 12, y - 12, x + 12, y + 12)}]
                if not zones:
                    raise ValueError("Aucune zone choisie : tracez un rectangle autour d'une particule.")
                for j, z in enumerate(zones, start=1):
                    pos0, nb = particule_dans_zone(film, champ, z["image"], z["rect"])
                    if nb > 1:
                        notes.append(f"Zone {j} : {nb} particules dans la zone, la plus lumineuse est suivie. "
                                     "Resserrez le rectangle autour d'une seule particule.")
                    departs.append((f"zone_{j}", int(z["image"]), pos0))
            else:
                k0 = max(0, min(int(config.get("image_depart", 0)), n - 1))
                departs.append(("plus_lumineuse", k0, tache_la_plus_lumineuse(film.image(k0))))
                notes.append("La tache la plus lumineuse est souvent la plus grosse particule : peu représentative.")
            for idx, (pid, k0, pos0) in enumerate(departs):
                progression(75 + int(20 * idx / len(departs)), f"Suivi : {pid}")
                img = film.image(k0)
                p = ajuster_gaussienne(img, *pos0)
                if p is None:
                    raise ValueError(f"Ajustement gaussien impossible pour {pid} : choisissez une particule plus nette.")
                avant = suivre(film, p, list(range(k0, n)))
                arriere = suivre(film, p, list(range(k0, -1, -1)))[1:]
                trajet = sorted(arriere + avant)
                if len(trajet) < max(N_DELAIS + 2 * N_BLOCS, 20):
                    raise ValueError(f"Trajectoire de {pid} trop courte ({len(trajet)} images) : la particule est perdue. "
                                     "Choisissez une particule plus isolée ou un autre film.")
                candidats.append(dict(id=pid, frames=np.array([t[0] for t in trajet]),
                                      pos=np.array([(t[1], t[2]) for t in trajet]), I=None, origine=mode))
        else:   # echantillon
            if len(champ["longues"]) < MIN_REFERENCES:
                raise ValueError(f"Seulement {len(champ['longues'])} particules suivies sur {int(FRACTION_LONGUE * 100)} % "
                                 "du film : l'analyse de l'échantillon demande un champ avec plusieurs particules.")
            for j, p in enumerate(champ["longues"], start=1):
                m = len(p["pos"])
                candidats.append(dict(id=f"particule_{j}", frames=p["debut"] + np.arange(m), pos=np.array(p["pos"]),
                                      I=float(np.median(p["I"])), origine=mode, piste=p))
        ref = intensite_reference(champ)
        progression(96, "Calcul des rayons")

        # --- évaluation et tri
        for c in candidats:
            e = evaluer(c["frames"], c["pos"], cumul, pixel_um, dt_s)
            c.update(e)
            c["raison"] = ""
            if c["I"] is None:
                c["I"] = intensite_trajet(champ, c["frames"], c["pos"])
            c["I_rel"] = c["I"] / ref if (c["I"] is not None and ref) else None
            c["voisin"] = distance_au_plus_proche(champ, {"debut": int(c["frames"][0]), "pos": [tuple(q) for q in c["pos"]]}
                                                  ) if mode != "echantillon" else distance_au_plus_proche(champ, c["piste"])
            if mode == "echantillon":
                if c["I_rel"] is not None and c["I_rel"] < seuil:
                    c["raison"] = "intensité trop faible (hors focus)"
                elif c["voisin"] < isolement:
                    c["raison"] = "chevauchement (autre particule trop proche)"
            if not c["raison"] and not c["D"] > 0:
                c["raison"] = "D négatif ou nul"
            if not c["raison"] and c["saut"]:
                c["raison"] = "saut dans la trajectoire"
        valides = [c for c in candidats if not c["raison"]]
        if mode == "echantillon" and rejet > 0 and len(valides) >= 5:
            # écart robuste calculé sur log(D) : un D trop petit (rayon énorme) est aussi aberrant qu'un D trop grand
            Ds = np.log([c["D"] for c in valides])
            med = np.median(Ds)
            mad = max(1.4826 * np.median(np.abs(Ds - med)), 1e-12)
            for c in valides:
                if abs(np.log(c["D"]) - med) > rejet * mad:
                    c["raison"] = "valeur aberrante (D trop éloigné de la médiane)"
            valides = [c for c in valides if not c["raison"]]
        if not valides:
            raisons = sorted({c["raison"] for c in candidats})
            raise ValueError("Aucune particule utilisable : " + "; ".join(raisons))

        # --- moyenne sur toutes les particules exploitables du film (mêmes seuils), pour situer le choix de l'utilisateur
        film_entier = None
        if mode != "echantillon":
            try:
                g = analyser_video(video_path, pixel_um, dt_s, dict(config, mode="echantillon", progression=None))["results"]
                film_entier = {k: g[k] for k in ("particles", "radius_nm", "uncertainty_nm", "D_um2_s", "rayon_dispersion_nm",
                                                 "n_suivies", "n_ecartees", "logD_med", "logD_mad")}
            except ValueError:
                film_entier = None
            if film_entier is not None:
                for c in candidats:
                    c["atypique"] = bool(not c["raison"] and np.isfinite(film_entier["logD_mad"]) and
                                         abs(np.log(c["D"]) - film_entier["logD_med"]) > REJET_SIGMA * film_entier["logD_mad"])
                    if c["atypique"]:
                        notes.append(f"{c['id']} : D très éloigné de celui des autres particules du film "
                                     f"(rayon {c['rayon']:.0f} nm contre une médiane de "
                                     f"{rayon_nm(float(np.exp(film_entier['logD_med']))):.0f} nm) : à vérifier, la particule est "
                                     "peut-être collée, mal suivie ou confondue avec une autre.")

        # --- résultat global
        Ds = np.array([c["D"] for c in valides])
        D_moy = float(Ds.mean())
        a = rayon_nm(D_moy)
        if len(valides) >= 3:
            sD = float(np.std(Ds, ddof=1) / np.sqrt(len(Ds)))
        else:
            blocs = [c["sD"] for c in valides]
            sD = float(np.sqrt(np.sum(np.square(blocs))) / len(valides)) if np.all(np.isfinite(blocs)) else float("nan")
        sa = a * sD / D_moy if np.isfinite(sD) and D_moy > 0 else float("nan")
        rayons = np.array([c["rayon"] for c in valides])
        n_aff = min(len(c["msd"]) for c in valides)
        tous_msd = np.array([c["msd"][:n_aff] for c in valides])
        msd_moyen = tous_msd.mean(axis=0)
        msd_erreur = (tous_msd.std(axis=0, ddof=1) / np.sqrt(len(valides))) if len(valides) >= 3 else np.full(n_aff, np.nan)
        delais_s = np.arange(1, n_aff + 1) * dt_s
        D_fit, c0 = ajuster_msd(delais_s[:N_DELAIS], msd_moyen[:N_DELAIS])
        D_sans = float(np.mean([c["D_sans"] for c in valides]))
        if mode == "echantillon":
            rejetees = [c for c in candidats if c["raison"]]
            notes.append(f"{len(valides)} particules utilisées sur {len(candidats)} suivies "
                         f"(seuil d'intensité {seuil * 100:.0f} % de la référence, rejet des valeurs aberrantes à "
                         f"{rejet:g} écarts absolus médians).")
            bilan = {}
            for c in rejetees:
                bilan[c["raison"]] = bilan.get(c["raison"], 0) + 1
            for r, k in sorted(bilan.items()):
                notes.append(f"{k} écartée(s) : {r}.")
        if len(valides) == 1 and np.isfinite(a) and a > 10000:
            notes.append("Rayon supérieur à 10 µm (hors de la plage des microplastiques) : particule probablement "
                         "immobile, collée ou agrégat. Choisissez une autre particule.")
        if len(valides) == 1 and valides[0]["D"] <= 0:
            notes.append("D négatif ou nul.")
        for c in candidats:
            if mode != "echantillon" and c["raison"]:
                notes.append(f"{c['id']} : {c['raison']}.")
        progression(100, "Terminé")
        return {
            "trajectories": {c["id"]: [(int(k), float(x), float(y)) for k, (x, y) in zip(c["frames"], c["pos"])]
                             for c in candidats},
            "results": {
                "particles": len(valides),
                "D_um2_s": D_moy,
                "radius_nm": float(a),
                "uncertainty_nm": float(sa),
                "rayon_dispersion_nm": float(1.4826 * np.median(np.abs(rayons - np.median(rayons)))) if len(rayons) > 1 else float("nan"),
                "rayon_median_particules_nm": float(np.median(rayons)),
                "lag_s": [float(t) for t in delais_s],
                "msd_um2": [float(v) for v in msd_moyen],
                "msd_erreur_um2": [float(v) for v in msd_erreur],
                "n_delais_ajustes": int(min(N_DELAIS, n_aff)),
                "fit_msd_um2": [float(4 * D_fit * t + c0) for t in delais_s],
                "n_images_suivies": int(np.mean([len(c["frames"]) for c in valides])),
                "n_suivies": len(candidats),
                "n_ecartees": len(candidats) - len(valides),
                "mode": mode,
                "film_entier": film_entier,
                "logD_med": float(np.median(np.log(Ds))),
                "logD_mad": float(1.4826 * np.median(np.abs(np.log(Ds) - np.median(np.log(Ds))))) if len(Ds) > 1 else float("nan"),
                "c_um2": float(c0),
                "dt_s": float(dt_s),
                "mode_choix": {"zones": "zone(s) rectangulaire(s)", "plus_lumineuse": "tache la plus lumineuse",
                               "echantillon": "toutes les particules (triées)"}[mode],
                "mouvement_collectif_corrige": cumul is not None,
                "n_references": len(champ["longues"]) if cumul is not None else 0,
                "rayon_sans_correction_nm": float(rayon_nm(D_sans)),
                "erreur_localisation_um": float(np.sqrt(c0 / 4)) if c0 > 0 else 0.0,
                "notes": notes,
                "particules": [
                    {"id": c["id"], "statut": "utilisée" if not c["raison"] else "écartée", "raison": c["raison"],
                     "intensite": c["I"], "intensite_rel": c.get("I_rel"), "n_images": int(len(c["frames"])),
                     "D_um2_s": c["D"], "rayon_nm": c["rayon"],
                     "incertitude_nm": float(c["rayon"] * c["sD"] / c["D"]) if (c["D"] > 0 and np.isfinite(c["sD"])) else float("nan"),
                     "localisation_nm": float(1000 * np.sqrt(c["c"] / 4)) if c["c"] > 0 else float("nan"),
                     "atypique": bool(c.get("atypique", False)),
                     "voisin_px": c["voisin"]} for c in candidats],
            },
        }
    finally:
        film.fermer()


def analyser_echantillon(video_path, pixel_um, dt_s, config=None):
    """Compatibilité : analyse de toutes les particules (mode "echantillon")."""
    return analyser_video(video_path, pixel_um, dt_s, dict(config or {}, mode="echantillon"))


def main():
    p = argparse.ArgumentParser(description="Analyse des particules d'un film TIFF.")
    p.add_argument("film")
    p.add_argument("--zone", nargs=4, type=float, action="append", metavar=("X0", "Y0", "X1", "Y1"),
                   help="zone rectangulaire sur l'image 0 (répétable)")
    p.add_argument("--image", type=int, default=0, help="image où les zones sont tracées")
    p.add_argument("--sans-correction", action="store_true", help="ne pas corriger le mouvement collectif")
    p.add_argument("--echantillon", action="store_true", help="toutes les particules, triées automatiquement")
    p.add_argument("--seuil", type=float, default=SEUIL_INTENSITE, help="seuil d'intensité (fraction de la référence)")
    p.add_argument("--rejet", type=float, default=REJET_SIGMA, help="rejet des aberrantes (écarts absolus médians, 0 = non)")
    a = p.parse_args()
    pixel_um, dt_s = parametres_du_nom(Path(a.film).name)
    if not (pixel_um and dt_s):
        raise SystemExit("Le nom du fichier doit contenir dt_...s et PixelSize_...um.")
    cfg = {"image_depart": a.image, "corriger_derive": False if a.sans_correction else "auto",
           "seuil_intensite": a.seuil, "rejet_sigma": a.rejet}
    if a.echantillon:
        cfg["mode"] = "echantillon"
    elif a.zone:
        cfg["mode"] = "zones"
        cfg["zones"] = [{"image": a.image, "rect": tuple(z)} for z in a.zone]
    sortie = analyser_video(a.film, pixel_um, dt_s, cfg)
    r = sortie["results"]
    print(f"Choix : {r['mode_choix']} | particules retenues : {r['particles']} | images suivies : {r['n_images_suivies']}")
    print(f"D = {r['D_um2_s']:.4f} um2/s | rayon = {r['radius_nm']:.0f} +/- {r['uncertainty_nm']:.0f} nm "
          f"| dispersion entre particules : {r['rayon_dispersion_nm']:.0f} nm | médiane : {r['rayon_median_particules_nm']:.0f} nm")
    print(f"Sans correction du mouvement collectif : rayon = {r['rayon_sans_correction_nm']:.0f} nm")
    for n in r["notes"]:
        print("Note :", n)


if __name__ == "__main__":
    main()
