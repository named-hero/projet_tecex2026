"""
AcquisitionEtCorrelation.py

Ecoute le piezo en continu. Detecte un impact (seuil sur le pic observe au
repos). Identifie le point par correlation avec la banque de reference (.npz),
puis regroupe plusieurs points en une seule note via GROUPES ci-dessous.

Banque : liste de points 1..N avec K signaux par point (Enregistrementbanque.py,
fichier BanqueListe_*.npz, banque de forme (N, K, duree)). L'ancien format a un
seul signal par point (N, duree) est aussi accepte (K = 1).

Deux algorithmes de decision au choix (ALGO_ACTIF) :
  "max"     : score d'un point = meilleure des K correlations. Le point au score
              le plus eleve gagne (equivaut a l'ancien code quand K = 1).
  "hybride" : on commence par "max". Si les deux meilleurs points ont des scores
              a moins de SEUIL_DELTA_C l'un de l'autre, on departage avec la
              MOYENNE des K correlations de chaque point.
"""

import os
import glob
import time
import numpy as np
import sounddevice as sd
from Protocole_et_Communication import envoyer

# --- Parametres ---
DOSSIER_BANQUE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultats_banque")
CHEMIN_BANQUE = None      # None = fichier .npz le plus recent du dossier resultats_banque ;
                          # sinon un chemin, ex. os.path.join(DOSSIER_BANQUE, "Banque_12 points.npz")
DEVICE_ENTREE = 1         # index du micro/piezo (C-Media USB Headphone Set)
FS = 44100
DTYPE = "float32"
TAILLE_BLOC = 512         # ~11.6 ms/bloc
MARGE_SEUIL = 3.0         # seuil = marge x pic observe au repos
DUREE_CALIBRATION = 2.0   # s de silence au demarrage
GARDE_INITIALE = 0.15     # s ignorees en debut de calibration (artefact de demarrage du flux)
REFRACTAIRE = 0.5         # s, anti double-declenchement sur la meme frappe
DUREE_IDENTIFICATION = 0.08  # s utilisees pour la correlation (debut de chaque reference)

# --- Choix de l'algorithme ---
ALGO_ACTIF = "hybride"    # "max" ou "hybride"
SEUIL_DELTA_C = 0.05      # algo hybride : ecart de score en dessous duquel deux points sont
                          # consideres comme ex aequo. Valeur ESTIMEE (pas encore mesuree) : les
                          # points de la banque de test se ressemblent a 0.88-0.94, donc des
                          # ecarts de l'ordre de 0.05 sont deja ambigus. A ajuster avec
                          # AFFICHER_DIAGNOSTIC (voir l'ecart "/2e" des erreurs).
AFFICHER_DIAGNOSTIC = True  # affiche point, score et ecart avec le 2e a chaque frappe

# Forme de la carte envoyee a l'affichage (lignes, colonnes). None = 2 lignes et
# juste assez de colonnes pour les N points ; les cases en trop restent a 0.
FORME_CARTE = None

if DEVICE_ENTREE is not None:
    sd.default.device = (DEVICE_ENTREE, sd.default.device[1])


# --- Banque de reference ---
def trouver_banque():
    if CHEMIN_BANQUE:
        return CHEMIN_BANQUE
    fichiers = glob.glob(os.path.join(DOSSIER_BANQUE, "*.npz"))
    if not fichiers:
        raise FileNotFoundError(f"Aucun .npz dans {DOSSIER_BANQUE}. Lance Enregistrementbanque.py.")
    return max(fichiers, key=os.path.getmtime)


_chemin = trouver_banque()
_b = np.load(_chemin)
LABELS = [str(x) for x in _b["labels"]]
_banque = _b["banque"]
if _banque.ndim == 2:                       # ancien format : un signal par point
    _banque = _banque[:, None, :]
N_POINTS, K = _banque.shape[:2]
N_MARGE = int(round(float(_b["marge_avant"]) * FS))
N_REPONSE = min(int(round(DUREE_IDENTIFICATION * FS)), _banque.shape[2])

# Pour la correlation de toutes les references d'un coup, on precalcule une seule fois
# leur FFT et leur norme (le resultat est le meme que np.correlate, mais plus rapide).
_REFS = _banque[:, :, :N_REPONSE].reshape(N_POINTS * K, N_REPONSE).astype(np.float64)
_NORMES = np.linalg.norm(_REFS, axis=1)
_NORMES[_NORMES == 0] = np.inf              # reference nulle -> correlation 0
_NFFT = 1 << int(np.ceil(np.log2(2 * N_REPONSE - 1)))
_F_REFS = np.fft.rfft(_REFS, _NFFT, axis=1)

if FORME_CARTE is None:
    FORME_CARTE = (2, int(np.ceil(N_POINTS / 2)))
if FORME_CARTE[0] * FORME_CARTE[1] < N_POINTS:
    raise ValueError(f"FORME_CARTE {FORME_CARTE} trop petite pour {N_POINTS} points")
print(f"Banque : {os.path.basename(_chemin)}  ({N_POINTS} points x {K} signaux)")

# --- Regroupement des points en notes ---
# Une "note" = un ou plusieurs points (numeros de la banque, en texte).
GROUPES = {
    "C4": ["1"],
    "D4": ["2"],
    "E4": ["3"],
    "F4": ["4"],
    "G4": ["5"],
    "A4": ["6"],
    "B4": ["7"],
    "C#4": ["8"],
    "D#4": ["9"],
    "F#4": ["10"],
    "G#4": ["11"],
    "A#4": ["12"],
}
POINT_VERS_NOTE = {point: note for note, points in GROUPES.items() for point in points}


# --- Correlation ---
def correlations(fenetre):
    """Correlation max normalisee de la fenetre avec chaque reference -> tableau (N_POINTS, K)."""
    f = fenetre.astype(np.float64)
    nf = np.linalg.norm(f)
    if nf == 0:
        return np.zeros((N_POINTS, K))
    F = np.fft.rfft(f, _NFFT)
    xc = np.fft.irfft(F[None, :] * np.conj(_F_REFS), _NFFT, axis=1)
    c = np.max(np.abs(xc), axis=1) / (nf * _NORMES)
    return np.clip(c, 0.0, 1.0).reshape(N_POINTS, K)


# --- Algorithmes de decision : C (N_POINTS, K) -> score par point (N_POINTS,) ---
def algo_max(C):
    return C.max(axis=1)


def algo_hybride(C):
    scores_max = C.max(axis=1)
    if scores_max.size >= 2:
        deux_meilleurs = np.sort(scores_max)[-2:]
        if deux_meilleurs[1] - deux_meilleurs[0] < SEUIL_DELTA_C:
            return C.mean(axis=1)           # ex aequo : on departage avec la moyenne
    return scores_max


ALGOS = {"max": algo_max, "hybride": algo_hybride}


def identifier_note(fenetre):
    """Trouve le point gagnant, renvoie (note, point, score, ecart_avec_2e, scores_par_point)."""
    scores = ALGOS[ALGO_ACTIF](correlations(fenetre))
    i = int(np.argmax(scores))
    point = LABELS[i]
    note = POINT_VERS_NOTE.get(point, point)   # un point hors groupe est sa propre note
    ecart = float(scores[i] - np.partition(scores, -2)[-2]) if scores.size > 1 else float("nan")
    return note, point, float(scores[i]), ecart, scores


def carte_pour_affichage(scores):
    """Met les scores des points dans une matrice (lignes, colonnes), complete par des 0."""
    plat = np.zeros(FORME_CARTE[0] * FORME_CARTE[1], dtype=np.float32)
    plat[:len(scores)] = scores
    return plat.reshape(FORME_CARTE)


def calibrer_seuil():
    print(f"Calibration : ne touchez a rien pendant {DUREE_CALIBRATION:.0f} s...")
    silence = sd.rec(int(DUREE_CALIBRATION * FS), samplerate=FS, channels=1, dtype=DTYPE)
    sd.wait()
    n_garde = int(GARDE_INITIALE * FS)
    silence_utile = np.abs(silence[n_garde:, 0])
    # 99.9e percentile plutot que le max : ignore un echantillon aberrant isole
    pic_repos = float(np.percentile(silence_utile, 99.9))
    seuil = MARGE_SEUIL * pic_repos
    print(f"Pic au repos : {pic_repos:.5f}  ->  seuil : {seuil:.5f}")
    return seuil


class Detecteur:
    """Machine a etats : attente -> capture -> identification -> attente."""

    def __init__(self, seuil):
        self.seuil = seuil
        self.etat = "attente"
        self.tampon = np.zeros(0, dtype=DTYPE)
        self.derniere_t = -np.inf
        self.t_debut_impact = None  # pour mesurer la latence

    def callback(self, indata, frames, t_info, status):
        if status:
            print(status)
        bloc = indata[:, 0]
        maintenant = time.time()

        if self.etat == "attente":
            if maintenant - self.derniere_t < REFRACTAIRE:
                return
            depassements = np.where(np.abs(bloc) > self.seuil)[0]
            if depassements.size:
                debut = max(0, depassements[0] - N_MARGE)
                self.tampon = bloc[debut:].copy()
                self.etat = "capture"
                self.t_debut_impact = maintenant

        else:  # capture
            self.tampon = np.concatenate([self.tampon, bloc])
            if len(self.tampon) >= N_REPONSE:
                fenetre = self.tampon[:N_REPONSE]
                note, point, score, ecart, scores = identifier_note(fenetre)
                latence_ms = (time.time() - self.t_debut_impact) * 1000

                envoyer(carte_pour_affichage(scores), note, latence_ms)
                if AFFICHER_DIAGNOSTIC:
                    print(f"point {point}  note {note}  score {score:.2f}  "
                          f"ecart/2e {ecart:.3f}  [{ALGO_ACTIF}]  {latence_ms:.0f} ms")
                self.derniere_t = time.time()
                self.etat = "attente"
                self.tampon = np.zeros(0, dtype=DTYPE)


def main():
    seuil = calibrer_seuil()
    detecteur = Detecteur(seuil)
    print(f"Algorithme : {ALGO_ACTIF}   (SEUIL_DELTA_C = {SEUIL_DELTA_C})")
    print("Ecoute en continu (Ctrl+C pour arreter)...")
    with sd.InputStream(samplerate=FS, channels=1, dtype=DTYPE,
                        blocksize=TAILLE_BLOC, callback=detecteur.callback):
        while True:
            time.sleep(0.1)


if __name__ == "__main__":
    main()
