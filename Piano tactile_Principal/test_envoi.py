"""
test_envoi.py : faux "traitement" pour tester l'affichage.

Envoie à intervalle régulier une matrice avec 0, 1 ou 2 taches (les "touchers"),
les notes correspondantes (selon la position horizontale) et une durée bidon.
Le vrai traitement.py de ton collègue le remplacera : il lui suffit d'appeler
protocole.encoder(...) puis sock.sendto(...).

Usage : python test_envoi.py [--hz 2] [--m 20] [--n 30]
"""
import argparse
import socket
import time

import numpy as np

import protocole

NOTES = ["C4", "D4", "E4", "F4"]   # doivent exister dans piano.json


def tache(m, n, cx, cy, sigma=2.5):
    """Tache gaussienne de corrélation centrée en (cx, cy)."""
    yy, xx = np.mgrid[0:m, 0:n]
    return np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hz", type=float, default=2.0, help="messages par seconde")
    parser.add_argument("--m", type=int, default=20, help="lignes")
    parser.add_argument("--n", type=int, default=30, help="colonnes")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    adresse = (protocole.HOTE, protocole.PORT)
    rng = np.random.default_rng()
    frame_id = 0

    print(f"Envoi vers {adresse} à {args.hz} Hz (Ctrl+C pour arrêter)")
    try:
        while True:
            t0 = time.perf_counter()

            matrice = 0.03 * rng.random((args.m, args.n))
            notes = []
            for _ in range(rng.choice([0, 1, 1, 1, 2])):
                cx = rng.uniform(0, args.n)
                cy = rng.uniform(0, args.m)
                matrice += tache(args.m, args.n, cx, cy)
                note = NOTES[min(int(cx / args.n * len(NOTES)), len(NOTES) - 1)]
                if note not in notes:
                    notes.append(note)
            matrice = np.clip(matrice, 0, 1).astype(np.float32)

            duree_ms = (time.perf_counter() - t0) * 1000
            sock.sendto(protocole.encoder(frame_id, duree_ms, matrice, notes),
                        adresse)
            print(f"#{frame_id}  notes={notes}  traitement={duree_ms:.2f} ms")

            frame_id += 1
            time.sleep(1.0 / args.hz)
    except KeyboardInterrupt:
        print("Arrêt.")


if __name__ == "__main__":
    main()
