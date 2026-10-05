"""
lancer.py : ouvre l'affichage PUIS lance le traitement, avec une seule commande.

Ce fichier est un simple "chef d'orchestre" : ni affichage.py ni le traitement
ne le connaissent ni ne dépendent de lui. Chacun reste un programme autonome,
qu'on peut aussi lancer à la main dans son propre terminal.

Usage : python lancer.py [options du traitement]
        ex. python lancer.py --fixe --hz 5     (options transmises telles quelles)
Pour arrêter : Ctrl+C dans le terminal, ou fermer la fenêtre d'affichage.
"""
import subprocess   # lancement des deux programmes comme processus séparés
import sys          # sys.executable = le Python en cours ; sys.argv = les options
import time         # pauses
from pathlib import Path

# Les deux programmes sont cherchés dans le même dossier que ce fichier
DOSSIER = Path(__file__).parent
AFFICHAGE = DOSSIER / "affichage.py"
# Programme de traitement à lancer : test_envoi.py pour les tests, puis
# le fichier de traitement du collègue (il suffit de changer ce nom).
TRAITEMENT = DOSSIER / "AcquisitionEtCorrelation_4signauxparpoint.py"

# Temps laissé à la fenêtre pour ouvrir son socket avant de lancer le traitement
# (UDP perd sans erreur les messages envoyés avant que l'affichage écoute).
DELAI_OUVERTURE_S = 2
# True : la fenêtre se ferme quand le traitement s'arrête.
# False : elle reste ouverte pour regarder le dernier résultat.
FERMER_AFFICHAGE_A_LA_FIN = True


def main():
    # L'affichage est lancé dans son propre "groupe de processus" : ainsi un
    # Ctrl+C tapé dans le terminal n'atteint que le traitement, et la fenêtre
    # est fermée proprement par ce script (sans message d'erreur de Qt).
    if sys.platform == "win32":
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        options = {"start_new_session": True}

    # 1) Ouvre l'affichage, SANS attendre sa fin (Popen), avec le même Python
    affichage = subprocess.Popen([sys.executable, str(AFFICHAGE)], **options)
    time.sleep(DELAI_OUVERTURE_S)

    # Si la fenêtre s'est déjà arrêtée (port 5005 occupé, erreur de code...),
    # inutile de lancer le traitement : son message d'erreur est affiché plus haut.
    if affichage.poll() is not None:
        print("affichage.py s'est arrêté au démarrage : voir l'erreur ci-dessus.")
        return 1

    # 2) Lance le traitement en lui transmettant les options reçues par lancer.py
    traitement = subprocess.Popen([sys.executable, str(TRAITEMENT), *sys.argv[1:]])

    # 3) Surveille les deux : on s'arrête dès que l'un des deux se termine
    try:
        while traitement.poll() is None and affichage.poll() is None:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass   # Ctrl+C : le traitement l'a aussi reçu et s'arrête de lui-même

    # 4) Nettoyage
    if affichage.poll() is not None:
        print("Fenêtre d'affichage fermée : arrêt du traitement.")
    if traitement.poll() is None:
        try:
            traitement.wait(timeout=1)   # lui laisse le temps de finir proprement
        except subprocess.TimeoutExpired:
            traitement.terminate()
    if FERMER_AFFICHAGE_A_LA_FIN and affichage.poll() is None:
        affichage.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
