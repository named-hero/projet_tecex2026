"""
affichage.py : fenêtre unique avec
  1. la carte de corrélation (image noir/blanc, m lignes x n colonnes),
  2. le piano superposé à la plaque 2D (zones qui s'illuminent + sons),
  3. les notes reçues,
  4. la latence (traitement + affichage).

Dépendances : pip install PySide6 pyqtgraph numpy
Lancement   : python affichage.py   (puis, dans un autre terminal,
              python test_envoi.py)

Principe : tout est événementiel. Qt surveille le socket UDP ; quand un
paquet arrive, il appelle _lire_datagrammes(). Pas de thread, pas de boucle
d'attente à écrire.
"""

# json : lecture de piano.json ; sys : arguments et sortie du programme ;
# time : chronomètre pour mesurer la durée d'affichage
import json, sys, time
# Path : manipulation de chemins de fichiers
from pathlib import Path
# numpy : tableaux (matrice, table de couleurs)
import numpy as np
from PyQt6 import QtCore, QtGui, QtNetwork, QtWidgets, QtMultimedia
import pyqtgraph as pg

# Notre fichier commun : décodage des messages, adresse et port
import Protocole_et_Communication as protocole

# Le programme retrouve piano.json et le dossier notes dans le même dossier
# que lui, quel que soit le dossier depuis lequel on le lance.
DOSSIER = Path(__file__).parent
FICHIER_PIANO = DOSSIER / "piano.json"
DOSSIER_NOTES = DOSSIER / "notes"


class FenetrePiano(QtWidgets.QMainWindow):
    def __init__(self):
        # Initialise la partie "fenêtre" héritée de QMainWindow
        super().__init__()
        self.setWindowTitle("Piano tactile - affichage")
        self.resize(1000, 560)

        self.zones = {}              # note -> {"item", "repos", "active"}
        self.sons = {}               # note -> QSoundEffect
        self.notes_actives = set()   # notes actuellement éclairées
        self._notes_inconnues = set()  # notes reçues absentes de piano.json
        self._forme = None           # (m, n) de la matrice affichée

        # Ordre important : le décor doit exister avant d'y ajouter les
        # polygones, et le socket est ouvert en dernier, une fois tout prêt
        # à recevoir.
        self._construire_interface()
        self._charger_piano()
        self._charger_sons()
        self._ouvrir_socket()

    # ------------------------------------------------------------------
    # 1) CONSTRUCTION (exécutée une seule fois au démarrage)
    # ------------------------------------------------------------------
    def _construire_interface(self):
        # Un QMainWindow a besoin d'un widget central ; le layout vertical
        # empile les graphiques (en haut) puis les textes (en bas).
        centre = QtWidgets.QWidget()
        self.setCentralWidget(centre)
        layout = QtWidgets.QVBoxLayout(centre)

        # Zone graphique avec deux panneaux côte à côte
        self.vue = pg.GraphicsLayoutWidget()
        layout.addWidget(self.vue, stretch=1)  # prend tout l'espace libre

        # --- Panneau 1 : carte de corrélation ---
        self.plot_corr = self.vue.addPlot(row=0, col=0, title="Carte de corrélation")
        self.plot_corr.setAspectLocked(True)  # cellules carrées
        self.plot_corr.invertY(True)          # ligne 0 de la matrice en haut
        # On désactive menu, zoom et bouton "A" pour qu'on ne déforme pas la vue
        self.plot_corr.setMenuEnabled(False)
        self.plot_corr.setMouseEnabled(False, False)
        self.plot_corr.hideButtons()

        # Repères sur les 4 côtés, avec leurs chiffres. Haut/droite sont liés
        # à la même vue que bas/gauche : mêmes graduations, même sens.
        for cote in ("top", "bottom", "left", "right"):
            self.plot_corr.showAxis(cote)
            self.plot_corr.getAxis(cote).setStyle(showValues=True)
        self.plot_corr.setLabel("bottom", "Colonnes")
        self.plot_corr.setLabel("left", "Lignes")

        self.image_corr = pg.ImageItem()
        # Table de couleurs : valeur 0 -> blanc, valeur 1 -> noir.
        niveaux = np.linspace(255, 0, 256).astype(np.uint8)
        self.image_corr.setLookupTable(np.stack([niveaux] * 3, axis=1))
        self.image_corr.setLevels((0.0, 1.0))  # échelle FIXE entre 0 et 1
        self.plot_corr.addItem(self.image_corr)
        # Image initiale (zéros = blanc) en attendant le premier paquet
        self.image_corr.setImage(np.zeros((10, 10), dtype=np.float32),
                                 autoLevels=False)
        self._cadrer_carte(10, 10)

        # --- Panneau 2 : plaque + piano ---
        self.plot_piano = self.vue.addPlot(row=0, col=1, title="Plaque et piano")
        self.plot_piano.setAspectLocked(True)
        self.plot_piano.invertY(True)         # origine en haut à gauche
        self.plot_piano.setMenuEnabled(False)
        self.plot_piano.setMouseEnabled(False, False)
        self.plot_piano.hideButtons()
        self.plot_piano.hideAxis("left")      # pas de graduations sur le piano
        self.plot_piano.hideAxis("bottom")

        # --- Zone de texte en bas : notes et latence ---
        bas = QtWidgets.QHBoxLayout()         # range les textes côte à côte
        self.label_notes = QtWidgets.QLabel("Notes : -")
        self.label_latence = QtWidgets.QLabel("Latence : -")
        for label in (self.label_notes, self.label_latence):
            label.setStyleSheet("font-size: 20px; padding: 6px;")
            bas.addWidget(label, stretch=1)
        layout.addLayout(bas)

    def _cadrer_carte(self, m, n):
        """Adapte la vue à une matrice de m lignes et n colonnes.

        La taille est fixe pour un lancement : cette méthode ne s'exécute
        qu'une fois, à la réception du premier paquet.
        """
        self._forme = (m, n)
        # La vue montre exactement n cellules en largeur et m en hauteur
        self.plot_corr.setRange(xRange=(0, n), yRange=(0, m), padding=0)
        # Graduations aux bords des cellules : environ 10 chiffres par axe,
        # un petit trait par cellule
        for cote, taille in (("bottom", n), ("top", n), ("left", m), ("right", m)):
            pas = max(1, round(taille / 10))
            self.plot_corr.getAxis(cote).setTickSpacing(major=pas, minor=1)
        self.plot_corr.setTitle(f"Carte de corrélation ({m} lignes × {n} colonnes)")

    def _charger_piano(self):
        """Lit piano.json : image de la plaque (facultative) + zones."""
        with open(FICHIER_PIANO, encoding="utf-8") as f:
            config = json.load(f)
            echelle = config.get("echelle", 1.0)
            dx, dy = config.get("decalage", [0, 0])
            x0, y0 = dx, dy
        largeur, hauteur = config["largeur"] * echelle, config["hauteur"] * echelle

        # Couche 0 : image de la plaque (si un nom de fichier est donné
        # ET que le fichier existe)
        nom_image = config.get("image", "")
        if nom_image and (DOSSIER / nom_image).exists():
            pixmap = QtGui.QPixmap(str(DOSSIER / nom_image))
            pixmap = pixmap.transformed(QtGui.QTransform().scale(-1, 1))
            fond = QtWidgets.QGraphicsPixmapItem(pixmap)
            fond.setZValue(0)                 # z = 0 : tout au fond
            self.plot_piano.addItem(fond)
            # Les coordonnées des zones sont alors en pixels de cette image
            x0, y0 = 0, 0
            largeur, hauteur = pixmap.width(), pixmap.height()
            print(f"Image de la plaque : {largeur} x {hauteur} pixels")
        # Couche 1 et plus : un polygone opaque par note
        for note, zone in config["zones"].items():
            points = [QtCore.QPointF(x * echelle + dx, y * echelle + dy) for x, y in zone["points"]]
            item = QtWidgets.QGraphicsPolygonItem(QtGui.QPolygonF(points))

            crayon = QtGui.QPen(QtGui.QColor("#333333"))
            crayon.setWidth(2)
            crayon.setCosmetic(True)  # épaisseur constante, quel que soit le zoom
            item.setPen(crayon)
            # Hauteur de dessin : champ "z" du JSON (1 par défaut)
            item.setZValue(zone.get("z", 1))

            # Deux brosses créées UNE fois ; changer d'état = échanger de brosse
            brosse_repos = QtGui.QBrush(QtGui.QColor(zone["couleur_repos"]))
            brosse_active = QtGui.QBrush(QtGui.QColor(zone["couleur_active"]))
            item.setBrush(brosse_repos)
            self.plot_piano.addItem(item)

            self.zones[note] = {"item": item,
                                "repos": brosse_repos,
                                "active": brosse_active}

        # Cadre la vue sur toute la zone du piano (2 % de marge)
        self.plot_piano.setRange(xRange=(x0, x0 + largeur), yRange=(y0, y0 + hauteur), padding=0.02)

    def _nom_fichier(self, note):
        """C4 -> 'c4' ; C#4 -> 'c-4' (le # est remplacé par un tiret)."""
        return note.replace("#", "-").lower()

    def _charger_sons(self):
        """Charge un son par note de piano.json, une seule fois (pas de latence ensuite)."""
        # Index des fichiers du dossier "notes" : nom sans extension, en minuscules
        fichiers = {}
        if DOSSIER_NOTES.exists():
            for f in DOSSIER_NOTES.iterdir():
                if f.suffix.lower() == ".wav":
                    fichiers[f.stem.lower()] = f
        else:
            print(f"Dossier de sons introuvable : {DOSSIER_NOTES}")
        for note in self.zones:
            chemin = fichiers.get(self._nom_fichier(note))
            if chemin is None:
                print(f"Son introuvable pour {note} (attendu : notes/{self._nom_fichier(note)}.wav)")
                continue
            son = QtMultimedia.QSoundEffect(self)
            son.setSource(QtCore.QUrl.fromLocalFile(str(chemin)))
            son.setVolume(1.0)
            self.sons[note] = son

    def _ouvrir_socket(self):
        """Ouvre la 'boîte aux lettres' UDP et branche le signal Qt."""
        self.socket = QtNetwork.QUdpSocket(self)
        adresse = QtNetwork.QHostAddress(protocole.HOTE)
        # bind réserve le port ; il échoue si le port est déjà pris
        if not self.socket.bind(adresse, protocole.PORT):
            raise RuntimeError(
                f"Impossible d'ouvrir le port {protocole.PORT} "
                f"({self.socket.errorString()}). "
                "Un autre affichage est peut-être déjà lancé.")
        self.socket.readyRead.connect(self._lire_datagrammes)

    # ------------------------------------------------------------------
    # 2) RÉCEPTION (appelée par Qt à chaque arrivée de paquet)
    # ------------------------------------------------------------------
    def _lire_datagrammes(self):
        # Plusieurs paquets en attente : on garde le dernier ("le plus récent gagne")
        dernier = None
        while self.socket.hasPendingDatagrams():
            dernier = self.socket.receiveDatagram().data()
        if dernier is None:
            return

        # Un paquet invalide (tronqué, parasite) est ignoré sans planter
        try:
            message = protocole.decoder(bytes(dernier))
        except ValueError as erreur:
            print("Message invalide ignoré :", erreur)
            return

        self._mettre_a_jour(message)

        # Dessin immédiat pour que le chronomètre mesure le rendu réel
        self.vue.viewport().repaint()

        # Durée d'affichage = de t_envoi à maintenant
        duree_affichage_ms = (time.perf_counter() - message["t_envoi"]) * 1000
        self._afficher_latence(message["duree_traitement_ms"],
                               duree_affichage_ms)

    # ------------------------------------------------------------------
    # 3) MISE À JOUR DES ÉLÉMENTS GRAPHIQUES
    # ------------------------------------------------------------------
    def _mettre_a_jour(self, message):
        # Élément 1 : carte de corrélation (échelle fixe 0 à 1)
        matrice = message["matrice_de_convolution"]
        self.image_corr.setImage(matrice, autoLevels=False)
        # Premier paquet (ou changement de taille) : on recadre sur m x n
        if matrice.shape != self._forme:
            self._cadrer_carte(*matrice.shape)

        # Élément 2 : zones du piano + sons
        self._eclairer(set(message["notes"]))

        # Élément 3 : texte des notes ("-" si la liste est vide)
        texte = ", ".join(message["notes"]) or "-"
        self.label_notes.setText(f"Notes : {texte}")

    def _eclairer(self, actives):
        """Ne change la couleur (et le son) que des notes dont l'état a changé."""
        # Notes nouvellement pressées : on les allume et on joue le son
        for note in actives:
            self._colorier(note, "active")
            son = self.sons.get(note)
            if son is not None:
                son.play()
        # Notes relâchées : on les remet au repos et on coupe le son
        for note in self.notes_actives - actives:
            self._colorier(note, "repos")
            son = self.sons.get(note)
            if son is not None:
                son.stop()
        self.notes_actives = actives

    def _colorier(self, note, etat):
        """etat vaut "active" ou "repos" (clés du dictionnaire self.zones)."""
        zone = self.zones.get(note)
        if zone is None:
            if note not in self._notes_inconnues:   # on ne prévient qu'une fois
                self._notes_inconnues.add(note)
                print(f"Note '{note}' absente de piano.json : ignorée")
            return
        zone["item"].setBrush(zone[etat])

    # Élément 4 : latence = traitement (mesuré par le collègue) + affichage
    def _afficher_latence(self, traitement_ms, affichage_ms):
        total = traitement_ms + affichage_ms
        self.label_latence.setText(
            f"Latence : {total:.1f} ms   "
            f"(traitement {traitement_ms:.1f} + affichage {affichage_ms:.1f})")


def main():
    pg.setConfigOptions(imageAxisOrder="row-major", background="w",
                        foreground="k", antialias=True)
    # QApplication : objet unique qui gère tout Qt, à créer avant toute fenêtre
    app = QtWidgets.QApplication(sys.argv)
    fenetre = FenetrePiano()
    fenetre.show()
    sys.exit(app.exec())


# main() ne s'exécute que si on lance ce fichier directement (pas s'il est importé)
if __name__ == "__main__":
    main()
