"""
protocole.py : le "contrat" entre traitement.py et affichage.py.

Les deux scripts importent CE fichier, donc ils ne peuvent pas se
désynchroniser sur le format du message.

Format d'un message (un message = un paquet UDP) :

    [ en-tête 14 octets ][ matrice m*n*4 octets ][ notes en texte UTF-8 ]

    en-tête : frame_id (uint32), duree_traitement_ms (float32),
              m (uint16), n (uint16), taille_notes (uint16)
    matrice : m*n float32, ligne par ligne
    notes   : texte "C4,E4" (vide s'il n'y a aucune note)
"""
import struct

import numpy as np

# Adresse du récepteur (l'affichage). 127.0.0.1 = "cette machine" :
# le paquet ne sort jamais sur un vrai réseau.
HOTE = "127.0.0.1"
PORT = 5005

# "<" = little-endian, sans remplissage : l'en-tête fait exactement 14 octets.
_ENTETE = struct.Struct("<IfHHH")

# Taille maximale d'un paquet UDP. Une matrice 50x50 float32 = 10 000 octets,
# donc on est très loin de la limite.
TAILLE_MAX_PAQUET = 65507


def encoder(frame_id, duree_traitement_ms, matrice, notes):
    """Transforme les résultats du traitement en octets prêts à envoyer.

    frame_id            : numéro du message (entier croissant)
    duree_traitement_ms : durée du traitement, en millisecondes (float)
    matrice             : tableau numpy 2D (m, n), valeurs entre 0 et 1
    notes               : liste de str (["C4", "E4"]) ou une seule str ("C4")
    """
    matrice = np.ascontiguousarray(matrice, dtype="<f4")
    if matrice.ndim != 2:
        raise ValueError("La matrice doit être 2D (m, n)")
    m, n = matrice.shape

    if isinstance(notes, str):
        notes = [notes] if notes else []
    texte_notes = ",".join(notes).encode("utf-8")

    entete = _ENTETE.pack(frame_id & 0xFFFFFFFF, duree_traitement_ms,
                          m, n, len(texte_notes))
    paquet = entete + matrice.tobytes() + texte_notes

    if len(paquet) > TAILLE_MAX_PAQUET:
        raise ValueError(f"Paquet trop gros ({len(paquet)} octets)")
    return paquet


def decoder(octets):
    """Inverse de encoder. Retourne un dictionnaire.

    Lève ValueError si le paquet est incomplet ou incohérent.
    """
    if len(octets) < _ENTETE.size:
        raise ValueError("Paquet trop court")

    frame_id, duree_ms, m, n, taille_notes = _ENTETE.unpack_from(octets, 0)
    debut_matrice = _ENTETE.size
    fin_matrice = debut_matrice + m * n * 4

    if len(octets) != fin_matrice + taille_notes:
        raise ValueError("Taille du paquet incohérente avec l'en-tête")

    matrice = np.frombuffer(octets[debut_matrice:fin_matrice],
                            dtype="<f4").reshape(m, n).astype(np.float32)
    texte = octets[fin_matrice:].decode("utf-8")
    notes = [x for x in texte.split(",") if x]

    return {
        "frame_id": frame_id,
        "duree_traitement_ms": duree_ms,
        "matrice": matrice,
        "notes": notes,
    }
