"""
test_envoi.py : faux "traitement" pour tester l'affichage.

Ce fichier ne fait que DEUX choses : fabriquer des données (calcul simulé)
et les envoyer avec com.envoyer(...). Il ne s'occupe pas de l'affichage :
c'est affichage.py, lancé séparément, qui reçoit les données et les montre
en temps réel.

Dans ce fichier, deux types de parties :

    [RÉEL]    = ce que le vrai traitement.py doit reproduire
    [FICTIF]  = sert uniquement à fabriquer de fausses données ; le collègue
                le remplace par son vrai calcul (corrélation + détection de notes)

Squelette du vrai traitement.py (tout le reste de ce fichier est fictif) :

    import time
    import Protocole_et_Communication as com

    while ...:
        t0 = time.perf_counter()
        matrice, notes = ...                      # son calcul à lui
        duree_ms = (time.perf_counter() - t0) * 1000
        com.envoyer(matrice, notes, duree_ms)

Utilisation (deux terminaux) :
    1) python affichage.py      <- d'abord : la fenêtre attend les données
    2) python test_envoi.py     [--hz 2] [--m 20] [--n 30] [--fixe]
       --fixe : envoie toujours la même matrice exemple (voir MATRICE_EXEMPLE)
"""
import argparse   # [FICTIF] lecture des options de la ligne de commande
import time       # [RÉEL]   chronomètre de la durée de traitement

import numpy as np

# [RÉEL] Tout ce qui touche à la communication est dans ce seul fichier :
# format du message et envoi UDP.
import Protocole_et_Communication as com


# =====================================================================
# EXEMPLE DE MATRICE : ce que le vrai traitement doit produire
# =====================================================================
# Matrice m x n (ici 6 lignes x 8 colonnes) de floats entre 0 et 1.
# Chaque cellule = corrélation à cet endroit : 0 = aucune, 1 = maximale.
# La ligne 0 est EN HAUT de la carte affichée.
# Ici : un toucher centré vers la ligne 3, colonne 2 (zone gauche).
# Sert aussi à vérifier l'orientation : si la tache apparaît à droite ou
# en bas, la matrice est transposée ou inversée quelque part.
MATRICE_EXEMPLE = np.array([
    [0.02, 0.03, 0.05, 0.04, 0.02, 0.01, 0.02, 0.01],
    [0.03, 0.10, 0.25, 0.20, 0.06, 0.02, 0.01, 0.02],
    [0.04, 0.30, 0.75, 0.65, 0.18, 0.04, 0.02, 0.01],
    [0.03, 0.28, 0.90, 0.80, 0.22, 0.05, 0.01, 0.02],
    [0.02, 0.12, 0.35, 0.30, 0.09, 0.03, 0.02, 0.01],
    [0.01, 0.03, 0.06, 0.05, 0.03, 0.01, 0.02, 0.01],
], dtype=np.float32)
# Notes correspondant à cet exemple : une liste de str, vide s'il n'y a
# aucune note ; ex. ["C4", "E4"] pour deux notes simultanées.
NOTES_EXEMPLE = ["E4"]

# [FICTIF] notes utilisées pour la simulation aléatoire. Les noms doivent
# exister dans piano.json, lettre pour lettre (ex. "C#4", pas "Db4").
NOTES = ["C4", "D4", "E4", "F4", "G4", "A4", "B4"]


# =====================================================================
# [FICTIF] Fabrication de fausses données
# =====================================================================
def tache(m, n, cx, cy, sigma=2.5):
    """Tache gaussienne de corrélation centrée en (cx, cy)."""
    yy, xx = np.mgrid[0:m, 0:n]
    return np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))


def simuler_traitement(m, n, rng):
    """[FICTIF] Remplacé par le vrai calcul. Retourne (matrice, notes).

    Fond de bruit faible + 0, 1 ou 2 taches ; la note dépend de la position
    horizontale de chaque tache.
    """
    matrice = 0.03 * rng.random((m, n))
    notes = []
    for _ in range(rng.choice([0, 1, 1, 1, 2])):
        cx = rng.uniform(0, n)
        cy = rng.uniform(0, m)
        matrice += tache(m, n, cx, cy)
        note = NOTES[min(int(cx / n * len(NOTES)), len(NOTES) - 1)]
        if note not in notes:
            notes.append(note)
    # Les valeurs doivent rester entre 0 et 1
    return np.clip(matrice, 0, 1).astype(np.float32), notes


# =====================================================================
# Boucle principale : calcul, puis envoi
# =====================================================================
def main():
    # ---- [FICTIF] options de la ligne de commande ----
    parser = argparse.ArgumentParser()
    parser.add_argument("--hz", type=float, default=2.0, help="messages par seconde")
    parser.add_argument("--m", type=int, default=20, help="lignes")
    parser.add_argument("--n", type=int, default=30, help="colonnes")
    parser.add_argument("--fixe", action="store_true",
                        help="envoie toujours MATRICE_EXEMPLE")
    args = parser.parse_args()
    rng = np.random.default_rng()   # [FICTIF] générateur aléatoire

    print(f"Envoi vers {com.HOTE}:{com.PORT} à {args.hz} Hz (Ctrl+C pour arrêter)")
    print("Rappel : affichage.py doit déjà tourner, sinon les messages sont perdus.")
    frame = 0   # [FICTIF] compteur pour le journal console uniquement
    try:
        while True:
            # ---- [RÉEL] début du chronomètre du traitement ----
            t0 = time.perf_counter()

            # ---- [FICTIF] ici le vrai code calcule matrice et notes ----
            if args.fixe:
                matrice, notes = MATRICE_EXEMPLE, NOTES_EXEMPLE
            else:
                matrice, notes = simuler_traitement(args.m, args.n, rng)

            # ---- [RÉEL] fin du chronomètre ----
            # À mesurer AVANT envoyer : la durée de traitement s'arrête quand
            # matrice et notes sont prêtes.
            duree_ms = (time.perf_counter() - t0) * 1000

            # ---- [RÉEL] encodage + envoi : UNE seule ligne ----
            envoye = com.envoyer(matrice, notes, duree_ms)

            # ---- [FICTIF] journal console de l'émetteur ----
            print(f"#{frame}  notes={notes}  traitement={duree_ms:.2f} ms"
                  + ("" if envoye else "  (ENVOI ÉCHOUÉ)"))
            frame += 1

            # ---- [FICTIF] cadence : dans le vrai programme, c'est
            # l'acquisition du capteur qui fixe le rythme, pas un sleep ----
            time.sleep(1.0 / args.hz)
    except KeyboardInterrupt:
        # Ctrl+C : on s'arrête proprement, sans message d'erreur
        print("Arrêt.")


if __name__ == "__main__":
    main()
