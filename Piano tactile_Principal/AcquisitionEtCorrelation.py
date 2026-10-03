"""
AcquisitionEtCorrelation.py

Ecoute le piezo en continu. Detecte un impact (seuil sur le pic observe au
repos). Identifie le point par correlation avec la banque de reference (.npz),
puis regroupe plusieurs points en une seule note via GROUPES ci-dessous
(certains points se confondent trop a la correlation pour etre des notes
distinctes : plutot que forcer une distinction artificielle, on les traite
comme une meme note).

Prerequis : un .npz genere sur la VRAIE plaque, avec EnregistrerBanqueGrille.py.
"""

import time
import numpy as np
import sounddevice as sd
import os

# --- Parametres ---
CHEMIN_BANQUE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultats_banque", "Banque_20261002_175910.npz")
DEVICE_ENTREE = 1        # index du micro/piezo (C-Media USB Headphone Set, confirme avec RecordMicro.py)
FS = 44100
DTYPE = "float32"
TAILLE_BLOC = 512         # ~11.6 ms/bloc
MARGE_SEUIL = 3.0         # seuil = marge x pic observe au repos (pas l'ecart-type : garantit zero
                          # declenchement pendant la calibration elle-meme)
DUREE_CALIBRATION = 2.0   # s de silence au demarrage
GARDE_INITIALE = 0.15     # s ignorees en debut de calibration (artefact de demarrage du flux audio,
                          # meme precaution que EnregistrerBanqueGrille.py)
REFRACTAIRE = 0.5         # s, anti double-declenchement sur la meme frappe
DUREE_IDENTIFICATION = 0.08  # s utilisees pour la correlation (au lieu des 0.5 s stockees) :
                          # l'essentiel du signal utile retombe sous 5% de son pic en 30-55 ms
                          # (verifie sur la banque), donc inutile d'attendre les 500 ms completes.
                          # Reutilise simplement le debut de chaque reponse deja enregistree.

if DEVICE_ENTREE is not None:
    sd.default.device = (DEVICE_ENTREE, sd.default.device[1])

# --- Banque de reference ---
_b = np.load(CHEMIN_BANQUE)
LABELS, BANQUE_COMPLETE = _b["labels"], _b["banque"]
N_MARGE = int(round(float(_b["marge_avant"]) * FS))
N_REPONSE = min(int(round(DUREE_IDENTIFICATION * FS)), BANQUE_COMPLETE.shape[1])
BANQUE = BANQUE_COMPLETE[:, :N_REPONSE]  # ne garde que le debut de chaque reponse de reference

# --- Regroupement des points en notes ---
# Des points proches ou acoustiquement similaires se confondent a la correlation (ex: 8 est
# toujours identifie comme 24). Plutot que de lutter contre, on les regroupe : une "note" =
# un ou plusieurs points. A completer au fil de l'exploration (teste, note quel point gagne
# systematiquement sur quel autre, ajoute-le au meme groupe).
GROUPES = {
    "note_24": ["24"],             
}
POINT_VERS_NOTE = {point: note for note, points in GROUPES.items() for point in points}


def correlation(a, b):
    # correlation croisee normalisee, max sur tous les decalages
    a, b = a.astype(np.float64), b.astype(np.float64)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return np.max(np.abs(np.correlate(a, b, mode="full"))) / (na * nb)


def identifier_note(fenetre):
    """Trouve le point le plus proche par correlation, renvoie (note, point, score)."""
    scores = [correlation(fenetre, ref) for ref in BANQUE]
    i = int(np.argmax(scores))
    point = str(LABELS[i])
    note = POINT_VERS_NOTE.get(point, point)  # un point hors groupe est sa propre note
    return note, point, scores[i]


def calibrer_seuil():
    print(f"Calibration : ne touchez a rien pendant {DUREE_CALIBRATION:.0f} s...")
    silence = sd.rec(int(DUREE_CALIBRATION * FS), samplerate=FS, channels=1, dtype=DTYPE)
    sd.wait()
    n_garde = int(GARDE_INITIALE * FS)
    silence_utile = np.abs(silence[n_garde:, 0])
    # 99.9e percentile plutot que le max : un max est fragile face a un seul echantillon
    # aberrant (artefact de demarrage, glitch electrique), le percentile l'ignore.
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
                self.t_debut_impact = maintenant  # debut du chrono de latence

        else:  # capture
            self.tampon = np.concatenate([self.tampon, bloc])
            if len(self.tampon) >= N_REPONSE:
                fenetre = self.tampon[:N_REPONSE]
                note, point, score = identifier_note(fenetre)
                pic = float(np.max(np.abs(fenetre)))
                latence_ms = (time.time() - self.t_debut_impact) * 1000
                print(f"Impact -> {note:8s} (point {point}, correlation {score:.2f}, "
                      f"pic {pic:.3f}, latence {latence_ms:.0f} ms)")
                self.derniere_t = time.time()
                self.etat = "attente"
                self.tampon = np.zeros(0, dtype=DTYPE)


def main():
    seuil = calibrer_seuil()
    detecteur = Detecteur(seuil)
    print("Ecoute en continu (Ctrl+C pour arreter)...")
    with sd.InputStream(samplerate=FS, channels=1, dtype=DTYPE,
                         blocksize=TAILLE_BLOC, callback=detecteur.callback):
        while True:
            time.sleep(0.1)


if __name__ == "__main__":
    main()
