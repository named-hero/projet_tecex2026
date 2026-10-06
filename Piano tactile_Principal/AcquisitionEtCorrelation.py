"""
AcquisitionEtCorrelation.py

Traitement pour la plaque a 40 points : 12 notes, chacune faite de 2 points (barres verticales).
Principe : (piezo -> detection d'impact -> correlation avec une
banque de references -> note -> envoyer() vers l'affichage), avec :

  - Banque : resultats_banque/Banque_enrichie.npz (600 references, ~15 par point : frappes
    d'intensites variees). Un point = la MEILLEURE correlation parmi ses references.
  - Notes : chaque note regroupe 2 points (GROUPES ci-dessous). Les 16 points sans note
    (zones mortes) sont RETIRES des candidats : une frappe dessus joue la note du point le plus
    ressemblant.
  - Detection : seuil = 3 x pic au repos, puis reconnaissance seulement si la plaque est revenue au
    calme (0.3 s) et si la frappe est franche (filtres PIC_MIN / NETTETE_MAX). Sans cela, la
    vibration residuelle et le bruit declenchaient de fausses notes (~49 % des declenchements).
    Consequence : deux frappes doivent etre separees d'au moins ~0.5 s.

Usage : python3 AcquisitionEtCorrelation.py        (ou, avec l'affichage : python3 lancer.py)
Ctrl+C pour arreter.
"""

import os
import queue
import time

import numpy as np
import sounddevice as sd

from Protocole_et_Communication import envoyer

DOSSIER = os.path.dirname(os.path.abspath(__file__))

# --- Parametres ---
CHEMIN_BANQUE = os.path.join(DOSSIER, "resultats_banque", "Banque_enrichie.npz")
DEVICE_ENTREE = 1         # C-Media USB Headphone Set (meme index que le reste du projet)
FS = 44100
DTYPE = "float32"
TAILLE_BLOC = 512         # ~11.6 ms/bloc
MARGE_SEUIL = 3.0         # seuil = 3 x pic observe au repos
DUREE_CALIBRATION = 2.0   # s de silence au demarrage
GARDE_INITIALE = 0.15     # s ignorees en debut de calibration
REFRACTAIRE = 0.5         # s minimum entre deux frappes
CALME_REQUIS = 0.3        # s sous le seuil avant de rearmer la detection
PIC_MIN = 0.10            # pic minimal d'une frappe valide (sous 0.10 : 95 % d'erreurs mesurees)
NETTETE_MAX = 0.3         # (1re ms de la fenetre) / pic au-dela duquel il n'y a pas d'attaque nette

# --- Disposition des notes : note -> numeros de points (photo de la plaque) ---
# Les noms de notes doivent exister dans l'affichage (N1 = C4, N2 = C#4, ... N12 = B4) et dans notes/.
# Pour changer quelle note est jouee par quelle zone, ne modifier QUE les noms a gauche.
GROUPES = {
    "C4":  [1, 5],      # N1  (meme numerotation N1..N12 que l'affichage)
    "C#4": [2, 6],      # N2
    "D4":  [3, 8],      # N3
    "D#4": [11, 18],    # N4
    "E4":  [14, 21],    # N5
    "F4":  [15, 22],    # N6
    "F#4": [17, 23],    # N7
    "G4":  [20, 26],    # N8
    "G#4": [28, 34],    # N9
    "A4":  [32, 39],    # N10
    "A#4": [30, 37],    # N11
    "B4":  [33, 40],    # N12
}
N_POINTS = 40
NOTE_DE = {p: note for note, pts in GROUPES.items() for p in pts}      # point (1..40) -> note
POINTS_MORTS = [p for p in range(1, N_POINTS + 1) if p not in NOTE_DE]  # sans note : jamais retenus


# --- Plaque : grille des points et orientation de la carte de correlation ---
# Grille lue sur la photo : {numero de point: colonne (1..7)} pour chaque ligne (0..6). Trous et
# piezo n'ont pas de point.
LIGNES_GRILLE = [
    {1: 2, 2: 3, 3: 5},
    {4: 1, 5: 2, 6: 3, 7: 4, 8: 5, 9: 6},
    {10: 2, 11: 3, 12: 4, 13: 5, 14: 6, 15: 7},
    {16: 1, 17: 2, 18: 3, 19: 4, 20: 5, 21: 6, 22: 7},
    {23: 2, 24: 3, 25: 4, 26: 5, 27: 6, 28: 7},
    {29: 2, 30: 3, 31: 4, 32: 5, 33: 6, 34: 7},
    {35: 1, 36: 2, 37: 3, 38: 4, 39: 5, 40: 6},
]
TROUS = [(0, 4), (2, 1), (5, 1)]    # (ligne, colonne) des 3 trous de la plaque
PIEZO = (4, 1)                      # (ligne, colonne) du piezo
# L'affichage montre la plaque en miroir puis tournee de 90 degres vers la droite (piezo en haut,
# touches horizontales). Case (ligne, colonne) de la grille -> case (L, C) de la carte envoyee.
def cellule(ligne, colonne):
    return colonne - 1, 6 - ligne
CASE_DE = {p: cellule(r, c) for r, l in enumerate(LIGNES_GRILLE) for p, c in l.items()}
FORME_CARTE = (7, 7)


def carte_de_correlation(S):
    """Matrice 7 x 7 envoyee a l'affichage : score de chaque point a sa place (plaque tournee), 0 ailleurs."""
    m = np.zeros(FORME_CARTE, dtype=np.float32)
    for p, (i, j) in CASE_DE.items():
        m[i, j] = S[p - 1]
    return m



class Identificateur:
    """Banque de references pretraitee (FFT) + score de chaque point pour une frappe."""

    def __init__(self, chemin):
        d = np.load(chemin)
        refs = d["refs"].astype(np.float64)
        self.labels = d["labels"].astype(int)             # numero de point (1..40) de chaque reference
        self.n_marge = int(round(float(d["marge_avant"]) * FS))
        self.n_ech = refs.shape[1]
        normes = np.linalg.norm(refs, axis=1)
        normes[normes == 0] = np.inf
        self.normes = normes
        self.nfft = 1 << int(np.ceil(np.log2(2 * self.n_ech - 1)))
        self.F = np.fft.rfft(refs, self.nfft, axis=1)
        self.candidats = np.array([p in NOTE_DE for p in range(1, N_POINTS + 1)])

    def scores(self, fenetre):
        """Score (0..1) de chacun des 40 points = meilleure correlation max normalisee de ses references."""
        f = np.asarray(fenetre, dtype=np.float64)[:self.n_ech]
        nf = np.linalg.norm(f)
        S = np.zeros(N_POINTS)
        if nf == 0:
            return S
        xc = np.fft.irfft(np.fft.rfft(f, self.nfft)[None, :] * np.conj(self.F), self.nfft, axis=1)
        c = np.clip(np.max(np.abs(xc), axis=1) / (nf * self.normes), 0.0, 1.0)
        np.maximum.at(S, self.labels - 1, c)
        return S

    def identifier(self, fenetre):
        """Renvoie (note, point 1..40, scores des 40 points). Les zones mortes ne sont jamais retenues."""
        S = self.scores(fenetre)
        point = int(np.argmax(np.where(self.candidats, S, -np.inf))) + 1
        return NOTE_DE[point], point, S


class Detecteur:
    """Detection d'impact avec rearmement apres retour au calme.
    Les frappes capturees (fenetre de n_ech echantillons, instant de detection) arrivent dans la file."""

    def __init__(self, seuil, n_ech, n_marge, file):
        self.seuil, self.n_ech, self.n_marge, self.file = seuil, n_ech, n_marge, file
        self.mode = "attente"
        self.tampon = np.zeros(0, dtype=DTYPE)
        self.t0 = 0.0
        self.calme = 0.0            # s consecutives sous le seuil
        self.derniere = -np.inf

    def traiter(self, bloc, maintenant):
        if self.mode == "attente":
            depasse = np.abs(bloc) > self.seuil
            if not depasse.any():
                self.calme += len(bloc) / FS
                return
            if self.calme < CALME_REQUIS or maintenant - self.derniere < REFRACTAIRE:
                self.calme = 0.0     # vibration residuelle ou bruit : on attend le calme
                return
            dep = np.where(depasse)[0]
            debut = max(0, dep[0] - self.n_marge)
            self.tampon = bloc[debut:].copy()
            self.mode = "capture"
            self.t0 = maintenant
        else:
            self.tampon = np.concatenate([self.tampon, bloc])
            if len(self.tampon) >= self.n_ech:
                self.file.put((self.tampon[:self.n_ech].copy(), self.t0))
                self.derniere = maintenant
                self.mode = "attente"
                self.calme = 0.0
                self.tampon = np.zeros(0, dtype=DTYPE)


def raison_rejet(fenetre):
    """None si la frappe est valide, sinon la raison pour laquelle elle est ignoree."""
    pic = float(np.max(np.abs(fenetre)))
    if pic < PIC_MIN:
        return f"pic trop faible ({pic:.3f} < {PIC_MIN})"
    debut = float(np.max(np.abs(fenetre[:int(0.001 * FS)])))
    if debut / pic > NETTETE_MAX:
        return "pas d'attaque nette (vibration residuelle ou bruit)"
    return None


def calibrer_seuil():
    print(f"Calibration : ne touchez a rien pendant {DUREE_CALIBRATION:.0f} s...")
    silence = sd.rec(int(DUREE_CALIBRATION * FS), samplerate=FS, channels=1, dtype=DTYPE)
    sd.wait()
    pic_repos = float(np.percentile(np.abs(silence[int(GARDE_INITIALE * FS):, 0]), 99.9))
    seuil = MARGE_SEUIL * pic_repos
    print(f"Pic au repos : {pic_repos:.5f}  ->  seuil : {seuil:.5f}")
    return seuil


def main():
    if not os.path.exists(CHEMIN_BANQUE):
        raise SystemExit(f"Banque introuvable : {CHEMIN_BANQUE}\n"
                         "Elle se genere avec Caracterisation/ConstruireBanque.py")
    ident = Identificateur(CHEMIN_BANQUE)
    print(f"Banque : {os.path.basename(CHEMIN_BANQUE)} ({len(ident.labels)} references, "
          f"{ident.n_ech / FS:.2f} s chacune). Zones mortes retirees : {POINTS_MORTS}")

    if DEVICE_ENTREE is not None:
        sd.default.device = (DEVICE_ENTREE, sd.default.device[1])
    seuil = calibrer_seuil()

    file = queue.Queue()
    det = Detecteur(seuil, ident.n_ech, ident.n_marge, file)

    def callback(indata, frames, t_info, status):
        if status:
            print(status)
        det.traiter(indata[:, 0], time.time())

    print("Ecoute en continu (Ctrl+C pour arreter)...")
    with sd.InputStream(samplerate=FS, channels=1, dtype=DTYPE, blocksize=TAILLE_BLOC, callback=callback):
        try:
            while True:
                try:
                    fenetre, t0 = file.get(timeout=0.2)
                except queue.Empty:
                    continue
                raison = raison_rejet(fenetre)
                if raison:
                    print(f"    (declenchement ignore : {raison})")
                    continue
                note, point, S = ident.identifier(fenetre)
                latence_ms = (time.time() - t0) * 1000
                envoyer(carte_de_correlation(S), note, latence_ms)
                print(f">>> {note:<3s} (point {point:>2d}, score {S[point - 1]:.2f})   {latence_ms:.0f} ms")
        except KeyboardInterrupt:
            print("\nArret.")


if __name__ == "__main__":
    main()
