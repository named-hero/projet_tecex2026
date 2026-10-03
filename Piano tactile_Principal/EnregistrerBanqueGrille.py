"""
EnregistrerBanqueGrille.py

Enregistre une banque de reponses impulsionnelles sur la plaque reelle.
Au lancement, tu donnes le nombre de points a enregistrer. Pour chaque point :
Entree, tape dans la fenetre de temps, le script detecte et garde l'impact.
Les points sont juste numerotes (1, 2, 3, ...) : pas de coordonnees a entrer,
note a cote (papier, photo) ou tu as tape pour le point N si tu veux t'y referer.

A la fin : banque sauvegardee en .npz (labels + reponses), et verification de
la distinguabilite entre points (matrice de correlation), utile pour decider
quels points regrouper en une meme note dans AcquisitionEtCorrelation.py.

Installation : pip install sounddevice numpy matplotlib scipy
"""

import os
import time
import numpy as np
import matplotlib.pyplot as plt
import sounddevice as sd

DOSSIER_SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resultats_banque')
os.makedirs(DOSSIER_SORTIE, exist_ok=True)

FS = 44100
DTYPE = 'float32'
DUREE_TAMPON = 5.0      # s enregistrees par tentative (temps pour reagir + taper)
DUREE_REPONSE = 0.50    # s conservees apres l'impact
MARGE_AVANT = 0.005     # s conservees avant le seuil

SEUIL_FACTEUR = 6.0
DUREE_SILENCE_REF = 0.2
GARDE_INITIALE = 0.15   # s ignorees en debut de tampon avant de chercher un impact (evite
                        # un artefact de demarrage du flux audio pris pour un impact a t=0)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 4))
plt.show(block=False)

def choisir_peripherique():
    devices = sd.query_devices()
    txt = "Choisir le # du micro/piezo : \n"
    for i, d in enumerate(devices):
        if d['max_input_channels']:
            txt += f"{i} : {d['name']} \n"
    while True:
        try:
            i = int(input(txt))
            if devices[i]['max_input_channels'] == 0:
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
    # du signal, qu'un seuil fonde sur l'ecart-type ignorerait.
    pic_repos = np.max(np.abs(signal[:n_silence]))
    seuil = seuil_facteur * pic_repos
    # recherche seulement apres n_garde : evite un artefact de demarrage du flux audio
    depassements = np.where(np.abs(signal[n_garde:]) > seuil)[0]
    if not depassements.size:
        return None
    return depassements[0] + n_garde


def enregistrer_un_point(num):
    """Enregistre un point, demande confirmation visuelle, renvoie la reponse extraite."""
    n_reponse = int(round(DUREE_REPONSE * FS))
    n_marge = int(round(MARGE_AVANT * FS))

    while True:
        input(f"\n>>> Point {num} : Entree puis tape dans les {DUREE_TAMPON:.0f} s.")

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
        ax1.axvline(idx / FS, color='r', linestyle='--')
        ax1.axvspan(debut / FS, fin / FS, color='r', alpha=0.15)
        ax1.set_title(f"Point {num} - tampon complet")
        ax2.plot(t2, fenetre)
        ax2.set_title(f"Point {num} - reponse conservee ({DUREE_REPONSE:.2f} s)")
        plt.tight_layout(); 
        plt.draw()

        if input("  Garder ? [Entree = oui, n = recommencer] : ").strip().lower() == 'n':
            continue

        return fenetre


def correlation_max_normalisee(a, b):
    a, b = a.astype(np.float64), b.astype(np.float64)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return np.max(np.abs(np.correlate(a, b, mode='full'))) / (na * nb)


def verifier_distinguabilite(banque, labels):
    """Matrice de correlation entre tous les points : aide a reperer ceux a regrouper."""
    n = len(labels)
    C = np.array([[correlation_max_normalisee(banque[i], banque[j]) for j in range(n)] for i in range(n)])
    print("\n=== Verification rapide (equivalent eq. 8) ===")
    for i in range(n):
        pire = max(C[i, j] for j in range(n) if j != i) if n > 1 else float('nan')
        print(f"  {labels[i]:4s} : pire ressemblance = {pire:.2f}")
    plt.figure(figsize=(5.5, 4.5))
    plt.imshow(C, vmin=0, vmax=1, cmap='viridis')
    plt.colorbar(label='Correlation max normalisee')
    plt.xticks(range(n), labels); plt.yticks(range(n), labels)
    plt.title('Ressemblance entre les points')
    plt.tight_layout(); plt.show()


if __name__ == '__main__':
    choisir_peripherique()

    while True:
        try:
            n_points = int(input("Combien de points veux-tu enregistrer ? "))
            if n_points > 0:
                break
        except ValueError:
            pass
        print("  Entre un nombre entier positif.")

    labels, banque = [], []
    for num in range(1, n_points + 1):
        fenetre = enregistrer_un_point(num)
        labels.append(str(num))
        banque.append(fenetre)

    banque = np.array(banque)
    horodatage = time.strftime('%Y%m%d_%H%M%S')
    nom_fichier = os.path.join(DOSSIER_SORTIE, f'Banque_{horodatage}.npz')
    np.savez(nom_fichier,
             labels=np.array(labels), banque=banque,
             fs=FS, duree_reponse=DUREE_REPONSE, marge_avant=MARGE_AVANT)
    print(f"\nBanque sauvegardee ICI : {os.path.abspath(nom_fichier)}")
    print("Mets ce chemin dans CHEMIN_BANQUE de AcquisitionEtCorrelation.py.")

    try:
        verifier_distinguabilite(banque, labels)
    except Exception as e:
        print(f"(Verification ignoree : {e}) La banque est deja sauvegardee, ce n'est pas grave.")
