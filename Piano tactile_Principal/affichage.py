"""
affichage.py : fenêtre unique avec
  1. la carte de corrélation (image noir/blanc),
  2. le piano superposé à la plaque 2D (zones qui s'illuminent),
  3. les notes reçues,
  4. la latence (traitement + affichage).

Dépendances : pip install PySide6 pyqtgraph numpy
Lancement   : python affichage.py   (puis, dans un autre terminal,
              python test_envoi.py)

Principe : tout est événementiel. Qt surveille le socket UDP ; quand un
paquet arrive, il appelle _lire_datagrammes(). Pas de thread, pas de boucle
d'attente à écrire.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from PyQt6 import QtCore, QtGui, QtNetwork, QtWidgets
import pyqtgraph as pg

import protocole

DOSSIER = Path(__file__).parent
FICHIER_PIANO = DOSSIER / "piano.json"


class FenetrePiano(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Piano tactile - affichage")
        self.resize(1000, 560)

        self.zones = {}              # note -> {"item", "repos", "active"}
        self.notes_actives = set()   # notes actuellement éclairées
        self._notes_inconnues = set()

        self._construire_interface()
        self._charger_piano()
        self._ouvrir_socket()

    # ------------------------------------------------------------------
    # 1) CONSTRUCTION (exécutée une seule fois au démarrage)
    # ------------------------------------------------------------------
    def _construire_interface(self):
        centre = QtWidgets.QWidget()
        self.setCentralWidget(centre)
        layout = QtWidgets.QVBoxLayout(centre)

        # Zone graphique avec deux panneaux côte à côte
        self.vue = pg.GraphicsLayoutWidget()
        layout.addWidget(self.vue, stretch=1)

        # --- Panneau 1 : carte de corrélation ---
        self.plot_corr = self.vue.addPlot(row=0, col=0,
                                          title="Carte de corrélation")
        self.plot_corr.setAspectLocked(True)
        self.plot_corr.invertY(True)          # ligne 0 de la matrice en haut
        self.plot_corr.setMenuEnabled(False)
        self.plot_corr.setMouseEnabled(False, False)
        self.plot_corr.hideButtons()

        self.image_corr = pg.ImageItem()
        # Table de couleurs : valeur 0 -> blanc, valeur 1 -> noir.
        # (= "opacité du noir proportionnelle à la corrélation")
        niveaux = np.linspace(255, 0, 256).astype(np.uint8)
        self.image_corr.setLookupTable(np.stack([niveaux] * 3, axis=1))
        self.image_corr.setLevels((0.0, 1.0))  # échelle FIXE entre 0 et 1
        self.plot_corr.addItem(self.image_corr)
        self.image_corr.setImage(np.zeros((10, 10), dtype=np.float32),
                                 autoLevels=False)

        # --- Panneau 2 : plaque + piano ---
        self.plot_piano = self.vue.addPlot(row=0, col=1,
                                           title="Plaque et piano")
        self.plot_piano.setAspectLocked(True)
        self.plot_piano.invertY(True)         # origine en haut à gauche
        self.plot_piano.setMenuEnabled(False)
        self.plot_piano.setMouseEnabled(False, False)
        self.plot_piano.hideButtons()
        self.plot_piano.hideAxis("left")
        self.plot_piano.hideAxis("bottom")

        # --- Zone de texte en bas : notes et latence ---
        bas = QtWidgets.QHBoxLayout()
        self.label_notes = QtWidgets.QLabel("Notes : -")
        self.label_latence = QtWidgets.QLabel("Latence : -")
        for label in (self.label_notes, self.label_latence):
            label.setStyleSheet("font-size: 20px; padding: 6px;")
            bas.addWidget(label, stretch=1)
        layout.addLayout(bas)

    def _charger_piano(self):
        """Lit piano.json : image de la plaque (facultative) + zones."""
        with open(FICHIER_PIANO, encoding="utf-8") as f:
            config = json.load(f)

        largeur, hauteur = config["largeur"], config["hauteur"]

        # Couche 0 : image de la plaque (si un nom de fichier est donné)
        nom_image = config.get("image", "")
        if nom_image and (DOSSIER / nom_image).exists():
            pixmap = QtGui.QPixmap(str(DOSSIER / nom_image))
            fond = QtWidgets.QGraphicsPixmapItem(pixmap)
            fond.setZValue(0)
            self.plot_piano.addItem(fond)
            # Les coordonnées des zones sont alors en pixels de cette image
            largeur, hauteur = pixmap.width(), pixmap.height()

        # Couche 1 : un polygone opaque par note
        for note, zone in config["zones"].items():
            points = [QtCore.QPointF(x, y) for x, y in zone["points"]]
            item = QtWidgets.QGraphicsPolygonItem(QtGui.QPolygonF(points))
            crayon = QtGui.QPen(QtGui.QColor("#333333"))
            crayon.setWidth(2)
            crayon.setCosmetic(True)  # épaisseur constante, quel que soit le zoom
            item.setPen(crayon)
            item.setZValue(1)

            brosse_repos = QtGui.QBrush(QtGui.QColor(zone["couleur_repos"]))
            brosse_active = QtGui.QBrush(QtGui.QColor(zone["couleur_active"]))
            item.setBrush(brosse_repos)
            self.plot_piano.addItem(item)

            self.zones[note] = {"item": item,
                                "repos": brosse_repos,
                                "active": brosse_active}

        self.plot_piano.setRange(xRange=(0, largeur), yRange=(0, hauteur),
                                 padding=0.02)

    def _ouvrir_socket(self):
        """Ouvre la 'boîte aux lettres' UDP et branche le signal Qt."""
        self.socket = QtNetwork.QUdpSocket(self)
        adresse = QtNetwork.QHostAddress(protocole.HOTE)
        if not self.socket.bind(adresse, protocole.PORT):
            raise RuntimeError(
                f"Impossible d'ouvrir le port {protocole.PORT} "
                f"({self.socket.errorString()}). "
                "Un autre affichage est peut-être déjà lancé.")
        # readyRead = "au moins un paquet est arrivé"
        self.socket.readyRead.connect(self._lire_datagrammes)

    # ------------------------------------------------------------------
    # 2) RÉCEPTION (appelée par Qt à chaque arrivée de paquet)
    # ------------------------------------------------------------------
    def _lire_datagrammes(self):
        t_reception = time.perf_counter()

        # S'il y a plusieurs paquets en attente, on les vide tous et on ne
        # garde que le dernier : "le plus récent gagne", l'affichage ne
        # prend jamais de retard.
        dernier = None
        while self.socket.hasPendingDatagrams():
            dernier = self.socket.receiveDatagram().data()
        if dernier is None:
            return

        try:
            message = protocole.decoder(bytes(dernier))
        except ValueError as erreur:
            print("Message invalide ignoré :", erreur)
            return

        self._mettre_a_jour(message)

        # On force le dessin immédiat pour que le chronomètre mesure le rendu
        # réel (sinon Qt ne dessinerait qu'un peu plus tard).
        self.vue.viewport().repaint()
        duree_affichage_ms = (time.perf_counter() - t_reception) * 1000

        self._afficher_latence(message["duree_traitement_ms"],
                               duree_affichage_ms)

    # ------------------------------------------------------------------
    # 3) MISE À JOUR DES ÉLÉMENTS GRAPHIQUES
    # ------------------------------------------------------------------
    def _mettre_a_jour(self, message):
        # Élément 1 : carte de corrélation (on remplace juste les données)
        self.image_corr.setImage(message["matrice"], autoLevels=False)

        # Élément 2 : zones du piano
        self._eclairer(set(message["notes"]))

        # Élément 3 : texte des notes
        texte = ", ".join(message["notes"]) or "-"
        self.label_notes.setText(f"Notes : {texte}")

    def _eclairer(self, actives):
        """Ne change la couleur que des zones dont l'état a changé."""
        for note in actives - self.notes_actives:
            self._colorier(note, "active")
        for note in self.notes_actives - actives:
            self._colorier(note, "repos")
        self.notes_actives = actives

    def _colorier(self, note, etat):
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
    pg.setConfigOptions(imageAxisOrder="row-major",  # matrice[ligne, colonne]
                        background="w", foreground="k", antialias=True)
    app = QtWidgets.QApplication(sys.argv)
    fenetre = FenetrePiano()
    fenetre.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
