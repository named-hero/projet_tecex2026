"""
Enregistrementbanque.py

Meme principe que EnregistrementBanqueGrille.py : une LISTE de points numerotes
1, 2, ..., N (pas de coordonnees, pas de matrice). Difference : chaque point
contient NB_SIGNAUX frappes (4 par defaut, a des endroits legerement differents
de la zone du doigt) au lieu d'une seule.

Avantage de la liste : ajouter un point = ajouter un numero. Au lancement, tu peux
charger une banque existante et lui AJOUTER des points (le numero continue : si la
banque a 12 points, le nouveau sera le 13) sans rien re-enregistrer.

Sortie : resultats_banque/BanqueListe_<horodatage>.npz
    labels : (N,)              "1", "2", ...
    banque : (N, K, N_REPONSE) float32   (K signaux par point)
    fs, duree_reponse, marge_avant, k

A la fin : pour chaque point, cohesion interne (ressemblance entre ses propres
signaux) vs pire ressemblance avec un autre point. Un point dont la cohesion est
plus faible que sa ressemblance externe sera souvent confondu : a regrouper avec
l'autre point (comme GROUPES dans l'ancien code) ou a ecarter sur la plaque.

Installation : pip install sounddevice numpy matplotlib
"""

import os
import glob
import time
import numpy as np
import matplotlib.pyplot as plt
import sounddevice as sd

DOSSIER_SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultats_banque")
os.makedirs(DOSSIER_SORTIE, exist_ok=True)

FS = 44100
DTYPE = "float32"
NB_SIGNAUX = 4          # frappes par point
DUREE_TAMPON = 5.0      # s enregistrees par tentative
DUREE_REPONSE = 0.50    # s conservees apres l'impact
MARGE_AVANT = 0.005     # s conservees avant le seuil

SEUIL_FACTEUR = 6.0
DUREE_SILENCE_REF = 0.2
GARDE_INITIALE = 0.15   # s ignorees en debut de tampon (artefact de demarrage du flux)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 4))
plt.show(block=False)


def choisir_peripherique():
    devices = sd.query_devices()
    txt = "Choisir le # du micro/piezo : \n"
    for i, d in enumerate(devices):
        if d["max_input_channels"]:
            txt += f"{i} : {d['name']} \n"
    while True:
        try:
            i = int(input(txt))
            if devices[i]["max_input_channels"] == 0:
                print("  Pas d'entree audio sur ce #."); continue
        except (ValueError, IndexError):
            print("  Entree invalide."); continue
        break
    sd.default.device = [i, sd.default.device[1]]
    print(f"Entree : {devices[i]['name']}\n")


def detecter_impact(signal, fs, duree_silence_ref=DUREE_SILENCE_REF, seuil_facteur=SEUIL_FACTEUR,
                    garde_initiale=GARDE_INITIALE):
    n_silence = int(duree_silence_ref * fs)
    n_garde = int(garde_initiale * fs)
    if n_silence >= len(signal):
        return None
    # seuil base sur le PIC au repos (pas l'ecart-type) : robuste a un biais DC constant
    pic_repos = np.max(np.abs(signal[:n_silence]))
    seuil = seuil_facteur * pic_repos
    depassements = np.where(np.abs(signal[n_garde:]) > seuil)[0]
    if not depassements.size:
        return None
    return depassements[0] + n_garde


def enregistrer_un_signal(titre):
    """Enregistre une frappe, demande confirmation visuelle, renvoie la reponse extraite."""
    n_reponse = int(round(DUREE_REPONSE * FS))
    n_marge = int(round(MARGE_AVANT * FS))

    while True:
        input(f"\n>>> {titre} : Entree puis tape dans les {DUREE_TAMPON:.0f} s.")

        tampon = sd.rec(int(DUREE_TAMPON * FS), samplerate=FS, channels=1, dtype=DTYPE)
        sd.wait()
        tampon = tampon[:, 0]

        idx = detecter_impact(tampon, FS)
        if idx is None:
            print("  Aucun impact detecte. On recommence."); continue

        debut = idx - n_marge
        fin = debut + n_reponse
        if debut < 0 or fin > len(tampon):
            print(f"  Impact trop pres du bord du tampon (detecte a t={idx/FS:.2f} s sur "
                  f"{DUREE_TAMPON:.0f} s). On recommence."); continue

        fenetre = tampon[debut:fin]

        t1, t2 = np.arange(len(tampon)) / FS, np.arange(len(fenetre)) / FS
        ax1.clear(); ax2.clear()
        ax1.plot(t1, tampon)
        ax1.axvline(idx / FS, color="r", linestyle="--")
        ax1.axvspan(debut / FS, fin / FS, color="r", alpha=0.15)
        ax1.set_title(f"{titre} - tampon complet")
        ax2.plot(t2, fenetre)
        ax2.set_title(f"{titre} - reponse conservee ({DUREE_REPONSE:.2f} s)")
        plt.tight_layout()
        plt.draw()
        plt.pause(0.01)

        if input("  Garder ? [Entree = oui, n = recommencer] : ").strip().lower() == "n":
            continue
        return fenetre


def correlation_max_normalisee(a, b):
    a, b = a.astype(np.float64), b.astype(np.float64)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    # FFT : meme resultat que max|np.correlate(a, b, 'full')|, bien plus rapide
    nfft = 1 << int(np.ceil(np.log2(len(a) + len(b) - 1)))
    xc = np.fft.irfft(np.fft.rfft(a, nfft) * np.conj(np.fft.rfft(b, nfft)), nfft)
    return float(np.max(np.abs(xc)) / (na * nb))


def verifier_distinguabilite(banque, labels):
    """Cohesion interne de chaque point vs sa pire ressemblance avec un autre point."""
    n, k, _ = banque.shape

    cohesion = np.full(n, np.nan)
    for p in range(n):
        vals = [correlation_max_normalisee(banque[p, a], banque[p, b])
                for a in range(k) for b in range(a + 1, k)]
        if vals:
            cohesion[p] = np.mean(vals)

    C = np.zeros((n, n))
    for a in range(n):
        for b in range(a, n):
            C[a, b] = C[b, a] = np.mean([correlation_max_normalisee(banque[a, i], banque[b, j])
                                         for i in range(k) for j in range(k)])

    print("\n=== Verification de la banque ===")
    print("  point  cohesion interne   pire ressemblance externe (point)")
    for p in range(n):
        autres = [d for d in range(n) if d != p]
        if autres:
            d_pire = max(autres, key=lambda d: C[p, d])
            marque = "" if cohesion[p] > C[p, d_pire] else "   <-- confusion possible"
            print(f"  {labels[p]:>4s}   {cohesion[p]:.2f}               "
                  f"{C[p, d_pire]:.2f} ({labels[d_pire]}){marque}")
        else:
            print(f"  {labels[p]:>4s}   {cohesion[p]:.2f}")

    plt.figure(figsize=(5.5, 4.5))
    plt.imshow(C, vmin=0, vmax=1, cmap="viridis")
    plt.colorbar(label="Correlation moyenne entre points")
    plt.xticks(range(n), labels); plt.yticks(range(n), labels)
    plt.title("Ressemblance entre les points")
    plt.tight_layout(); plt.show()


def charger_banque_existante():
    """Propose de reprendre une banque existante pour lui ajouter des points."""
    fichiers = sorted(glob.glob(os.path.join(DOSSIER_SORTIE, "BanqueListe_*.npz")))
    if not fichiers:
        return [], []
    rep = input(f"Ajouter des points a la banque la plus recente ({os.path.basename(fichiers[-1])}) ? "
                "[o = oui, Entree = nouvelle banque] : ").strip().lower()
    if rep != "o":
        return [], []
    b = np.load(fichiers[-1])
    if int(b["k"]) != NB_SIGNAUX:
        print(f"  Cette banque a {int(b['k'])} signaux/point, NB_SIGNAUX = {NB_SIGNAUX} : "
              "on repart d'une nouvelle banque.")
        return [], []
    labels = [str(x) for x in b["labels"]]
    banque = [b["banque"][i] for i in range(len(labels))]
    print(f"  {len(labels)} points charges ; le prochain sera le {len(labels) + 1}.")
    return labels, banque


def demander_entier(texte):
    while True:
        try:
            v = int(input(texte))
            if v > 0:
                return v
        except ValueError:
            pass
        print("  Entre un nombre entier positif.")


if __name__ == "__main__":
    choisir_peripherique()
    labels, banque = charger_banque_existante()

    n_nouveaux = demander_entier("Combien de points veux-tu enregistrer (nouveaux) ? ")
    premier = len(labels) + 1

    for num in range(premier, premier + n_nouveaux):
        print(f"\n##### Point {num} : {NB_SIGNAUX} frappes dans la meme zone #####")
        signaux = [enregistrer_un_signal(f"Point {num} - frappe {k + 1}/{NB_SIGNAUX}")
                   for k in range(NB_SIGNAUX)]
        labels.append(str(num))
        banque.append(np.array(signaux))

    banque = np.array(banque, dtype=np.float32)   # (N, K, N_REPONSE)
    horodatage = time.strftime("%Y%m%d_%H%M%S")
    nom_fichier = os.path.join(DOSSIER_SORTIE, f"BanqueListe_{horodatage}.npz")
    np.savez(nom_fichier, labels=np.array(labels), banque=banque, k=NB_SIGNAUX,
             fs=FS, duree_reponse=DUREE_REPONSE, marge_avant=MARGE_AVANT)
    print(f"\nBanque sauvegardee ICI : {os.path.abspath(nom_fichier)}")

    try:
        verifier_distinguabilite(banque, labels)
    except Exception as e:
        print(f"(Verification ignoree : {e}) La banque est deja sauvegardee, ce n'est pas grave.")
