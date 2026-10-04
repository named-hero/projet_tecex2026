"""
protocole.py : le "contrat" entre traitement.py et affichage.py.

Les deux scripts importent CE fichier, donc ils ne peuvent pas se
désynchroniser sur le format du message.

Format d'un message (un message = un paquet UDP) :

    [ en-tête 22 octets ][ matrice_de_convolution m*n*4 octets ][ notes en texte UTF-8 ]

    en-tête : frame_id (uint32),
              t_envoi (float64, instant d'envoi en secondes, pris automatiquement),
              duree_traitement_ms (float32),
              m (uint16), n (uint16), taille_notes (uint16)
    matrice_de_convolution : m*n float32, ligne par ligne
    notes   : texte "C4,E4" (vide s'il n'y a aucune note)
"""

# struct : convertit des nombres en octets bruts et inversement
import struct
# time : sert à lire l'horloge pour horodater l'envoi (t_envoi)
import time
# numpy : manipulation de la matrice
import numpy as np

# Adresse du récepteur (l'affichage). 127.0.0.1 = "cette machine" :
# le paquet ne sort jamais sur un vrai réseau.
HOTE = "127.0.0.1"
# Numéro de la "boîte aux lettres" : émetteur et récepteur doivent utiliser le même.
PORT = 5005

# Forme de l'en-tête. "<" = little-endian, sans remplissage entre les champs.
#   I = frame_id (uint32, 4 octets)
#   d = t_envoi (float64, 8 octets) : float64 obligatoire, un float32 n'a pas
#       assez de chiffres significatifs pour une horloge
#   f = duree_traitement_ms (float32, 4 octets)
#   H = m, n, taille_notes (uint16, 2 octets chacun)
# Total : 4 + 8 + 4 + 2 + 2 + 2 = 22 octets.
_ENTETE = struct.Struct("<IdfHHH")

# Taille maximale d'un paquet UDP. Une matrice_de_convolution 50x50 float32 = 10 000 octets,
# donc on est très loin de la limite.
TAILLE_MAX_PAQUET = 65507

#------------------- Protocle de communication entre traitement.py et affichage.py -------------------

def encoder(frame_id, duree_traitement_ms, matrice_de_convolution, notes):
    """Transforme les résultats du traitement en octets prêts à envoyer.

    frame_id              : numéro du message (entier croissant)
    duree_traitement_ms   : durée du traitement, en millisecondes (float).
                            À mesurer AVANT d'appeler encoder, pour ne pas
                            compter deux fois le même temps.
    matrice_de_convolution: tableau numpy 2D (m, n), valeurs entre 0 et 1
    notes                 : liste de str (["C4", "E4"]) ou une seule str ("C4")

    L'instant d'envoi (t_envoi) est ajouté automatiquement ici.
    """
    # Conversion de la matrice en float32 et vérification du rangement en mémoire
    # ligne après ligne, sans trou, nécessaire pour que tobytes() donne le bon ordre
    matrice_de_convolution = np.ascontiguousarray(matrice_de_convolution, dtype="<f4")

    # On vérifie que l'on a bien une matrice 2D, puis shape donne le nombre de
    # lignes (m) et de colonnes (n)
    if matrice_de_convolution.ndim != 2:
        raise ValueError("La matrice_de_convolution doit être 2D (m, n)")
    m, n = matrice_de_convolution.shape

    # Si les notes sont une seule str on la met dans une liste (une str vide donne
    # une liste vide), puis on joint les notes par des virgules ("C4,E4") et on
    # convertit en octets. On mesurera sa taille en octets, pas en caractères.
    if isinstance(notes, str):
        notes = [notes] if notes else []
    texte_notes = ",".join(notes).encode("utf-8")

    # On fabrique les 22 octets de l'en-tête à partir des 6 valeurs.
    # frame_id & 0xFFFFFFFF garde seulement 32 bits : si le compteur dépasse
    # 4 milliards, il repart de 0 au lieu de planter.
    # time.perf_counter() est l'instant d'envoi, pris au plus près de l'envoi réel.
    entete = _ENTETE.pack(frame_id & 0xFFFFFFFF, time.perf_counter(),
                          duree_traitement_ms, m, n, len(texte_notes))

    # Le paquet à envoyer est l'en-tête, puis la matrice, puis le texte des notes
    paquet = entete + matrice_de_convolution.tobytes() + texte_notes

    # Garde-fou : on vérifie la taille du paquet pour ne pas dépasser la limite UDP
    if len(paquet) > TAILLE_MAX_PAQUET:
        raise ValueError(f"Paquet trop gros ({len(paquet)} octets)")
    return paquet


def decoder(octets):
    """Décode un paquet reçu en un dictionnaire de valeurs.

    Lève ValueError si le paquet est incomplet ou incohérent.
    """

    # Si le paquet est plus petit que l'en-tête, on ne peut pas le décoder
    if len(octets) < _ENTETE.size:
        raise ValueError("Paquet trop court")

    # Lit les 22 premiers octets (à partir de la position 0) et les redécoupe
    # en 6 valeurs. C'est l'exact inverse de pack.
    frame_id, t_envoi, duree_ms, m, n, taille_notes = _ENTETE.unpack_from(octets, 0)

    # Position de la matrice dans le paquet : elle commence juste après l'en-tête
    # et occupe m * n * 4 octets (4 octets par float32).
    debut_matrice_de_convolution = _ENTETE.size
    fin_matrice_de_convolution = debut_matrice_de_convolution + m * n * 4

    # Le paquet doit avoir exactement la taille annoncée par l'en-tête
    # (détecte un paquet tronqué ou du texte parasite)
    if len(octets) != fin_matrice_de_convolution + taille_notes:
        raise ValueError("Taille du paquet incohérente avec l'en-tête")

    # On découpe la partie matrice, on l'interprète comme une suite de float32, on la remet en m lignes et n colonnes,
    # puis .astype crée une copie modifiable (le résultat de frombuffer est en lecture seule).
    matrice_de_convolution = np.frombuffer(
        octets[debut_matrice_de_convolution:fin_matrice_de_convolution],
        dtype="<f4").reshape(m, n).astype(np.float32)

    # Ce qui reste après la matrice est le texte des notes. Le "if x" retire les
    # chaînes vides (sinon "" donnerait une fausse note vide).
    texte = octets[fin_matrice_de_convolution:].decode("utf-8")
    notes = [x for x in texte.split(",") if x]

    # Résultat : les 5 informations, accessibles par leur nom
    return {
        "frame_id": frame_id,
        "t_envoi": t_envoi,
        "duree_traitement_ms": duree_ms,
        "matrice_de_convolution": matrice_de_convolution,
        "notes": notes,
    }

#------------------- fonction  de communication entre traitement.py et affichage.py -------------------

import socket        # envoi UDP
import subprocess    # lancement de affichage.py (facultatif)
import sys           # retrouve le Python en cours (facultatif)
import time          # pause au lancement de l'affichage (facultatif)
from pathlib import Path   # chemin de affichage.py (facultatif)


# ---------------------------------------------------------------------
# Préparation : exécutée UNE fois, automatiquement, à l'import du fichier
# ---------------------------------------------------------------------
# Socket UDP d'envoi : aucune connexion à établir, on envoie c'est tout.
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# Adresse de l'affichage (même ordinateur, port défini dans protocole.py)
_adresse = (HOTE, PORT)
# Numéro du prochain message ; augmente de 1 à chaque envoi
_frame_id = 0


# ---------------------------------------------------------------------
# À appeler à chaque résultat
# ---------------------------------------------------------------------
def envoyer(matrice, notes, duree_ms):
    """Encode et envoie un résultat à l'affichage. Retourne True si envoyé."""
    #matrice : tableau numpy 2D (m, n), valeurs entre 0 et 1
    #notes : liste de str (["C4", "E4"]) ou une seule str ("C4")
    #duree_ms : durée du traitement, en millisecondes (float). À mesurer AVANT d'appeler envoyer(), pour ne pas compter deux fois le même temps

    # "global" pour faire référence a la variable golable _frame_id, qui est modifiée ici
    global _frame_id

    # Encodage : numéro + instant d'envoi (ajouté ici automatiquement) + durée + matrice + notes, 
    # transformés en octets. Lève ValueError si la matrice  n'est pas 2D ou si le paquet est trop gros. Géré parle fichier protocol !
    paquet = encoder(_frame_id, duree_ms, matrice, notes)

    # Envoi. Une erreur réseau ne doit jamais arrêter le traitement.
    try:
        _sock.sendto(paquet, _adresse)
    except OSError as erreur:
        print("Envoi à l'affichage impossible :", erreur)
        return False

    _frame_id += 1
    return True



# ---------------------------------------------------------------------
# Facultatif : ouvrir l'affichage automatiquement
# ---------------------------------------------------------------------
def lancer_affichage():
    """Ouvre affichage.py dans un processus séparé et le laisse tourner.

    À appeler UNE fois, avant le premier envoi. Retourne le processus
    (on peut faire processus.terminate() à la fin pour fermer la fenêtre).
    """
    # affichage.py est cherché dans le même dossier que ce fichier
    script = Path(__file__).parent / "affichage.py"
    # Popen démarre l'affichage SANS attendre sa fin ; sys.executable = le même.Python que celui du traitement (mêmes bibliothèques installées)
    processus = subprocess.Popen([sys.executable, str(script)])
    # UDP ne prévient pas si personne n'écoute : on laisse à la fenêtre letemps d'ouvrir son socket, sinon les premiers paquets seraient perdus
    time.sleep(2)
    # Si l'affichage s'est déjà arrêté (port occupé, erreur...), on le signale
    if processus.poll() is not None:
        raise RuntimeError("affichage.py s'est arrêté au démarrage : voir l'erreur ci-dessus")
    return processus
