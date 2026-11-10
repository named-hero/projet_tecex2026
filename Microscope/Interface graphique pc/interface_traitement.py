"""Interface de traitement (PC) : on part d'un film TIFF enregistré avec l'interface d'acquisition du Raspberry Pi.

Onglets :
    Film et sélection   lecteur du film (temps, échelle et conditions sur chaque image), choix des particules :
                        zones rectangulaires tracées à la souris, tache la plus lumineuse, ou toutes les particules
                        triées automatiquement (seuil d'intensité, chevauchements, valeurs aberrantes)
    Résultats           rayon moyen et incertitude, tableau par particule, MSD moyen, rayons par particule
    Taille des taches   cas des particules immobiles (collées à la lame) : le mouvement brownien n'est pas mesurable, le
                        diamètre est estimé par la largeur des taches (calcul de l'optique ou film de référence)
    Vidéo annotée       le film rejoué avec les trajectoires calculées, zoom et déplacement dans l'image, AVI
    Paramètres          conditions d'acquisition (modifiables), échelle µm/pixel, réglages du tri

Base : interface de Keira (main_v6.py, PySide6). Le pilotage de la caméra n'est pas ici : il se fait sur le Raspberry Pi.
Utilisation : python3 interface_traitement.py
"""
import csv
import sys
import traceback
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import QPointF, Qt, QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QProgressDialog,
    QPushButton, QRubberBand, QScrollArea, QSlider, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

import annotation
import analyse_equipe

OBJECTIFS = ["4X, NA 0,10", "4X, NA 0,13", "10X, NA 0,25", "10X, NA 0,30", "20X, NA 0,40", "20X, NA 0,45",
             "20X, NA 0,50", "40X, NA 0,65", "40X, NA 0,70", "40X, NA 0,75", "60X, NA 0,85"]
OBJECTIF_PAR_DEFAUT = "20X, NA 0,40"     # objectif utilisé, modifiable dans Paramètres
MODES = ["Tracer des zones sur l'image (une par particule)",
         "La plus lumineuse (automatique)",
         "Toutes les particules, triées automatiquement (rayon moyen)"]
STYLE = """
    QMainWindow, QWidget { background: #171c24; color: #eef3fa; font-size: 13px; }
    QGroupBox { border: 1px solid #3b4656; border-radius: 9px; margin-top: 12px; padding: 12px; font-weight: bold; }
    QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
    QPushButton { background: #2865b5; border: 0; border-radius: 6px; padding: 8px 12px; font-weight: bold; }
    QPushButton:hover { background: #367bda; }
    QPushButton:disabled { background: #3c4653; color: #a6adba; }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QPlainTextEdit, QTableWidget {
        background: #26303d; border: 1px solid #485365; border-radius: 5px; padding: 4px; }
    QHeaderView::section { background: #2d3a4b; color: #eef3fa; padding: 4px; border: 0; }
    QTabWidget::pane { border: 1px solid #394657; }
    QTabBar::tab { background: #26303d; padding: 12px 22px; }
    QTabBar::tab:selected { background: #2865b5; }
"""


# ----------------------------------------------------------------------------- Film
class LectureFilm:
    """Accès image par image à un TIFF multipage, avec un contraste d'affichage fixe pour tout le film."""

    def __init__(self, chemin):
        self.chemin = str(chemin)
        self._f = Image.open(self.chemin)
        self.n = getattr(self._f, "n_frames", 1)
        self._dernier = (None, None)
        premiere = self.brut(0).astype(np.float32)
        self.lo = float(np.percentile(premiere, 0.5))
        self.hi = max(float(np.percentile(premiere, 99.95)), self.lo + 1.0)

    def brut(self, i):
        i = int(max(0, min(i, self.n - 1)))
        if self._dernier[0] == i:
            return self._dernier[1]
        self._f.seek(i)
        a = np.asarray(self._f)
        a = a.mean(axis=2).astype(a.dtype) if a.ndim == 3 else a
        self._dernier = (i, a)
        return a

    def image8(self, i, contraste=True):
        a = self.brut(i).astype(np.float32)
        if contraste:
            a = (a - self.lo) / (self.hi - self.lo) * 255.0
        elif self.brut(i).dtype != np.uint8:
            a = a / max(float(a.max()), 1.0) * 255.0
        return np.clip(a, 0, 255).astype(np.uint8)

    def fermer(self):
        self._f.close()


# ----------------------------------------------------------------------------- Graphiques
def graduations(bas, haut, n=5):
    """Valeurs rondes (1, 2, 5 x 10^k) entre bas et haut ; retourne (valeurs, pas)."""
    if not haut > bas:
        haut = bas + 1.0
    brut = (haut - bas) / n
    mag = 10 ** np.floor(np.log10(brut))
    pas = 10 * mag
    for m in (1, 2, 5, 10):
        if m * mag >= brut:
            pas = m * mag
            break
    v = np.ceil(bas / pas - 1e-9) * pas
    valeurs = []
    while v <= haut + pas * 1e-9:
        valeurs.append(float(v))
        v += pas
    return valeurs, float(pas)


def etiquette(v, pas):
    dec = max(0, int(-np.floor(np.log10(pas) + 1e-9)))
    return f"{0.0 if abs(v) < pas * 1e-6 else v:.{dec}f}"


def court(pid):
    return pid.replace("particule_", "").replace("zone_", "").replace("plus_lumineuse", "1")


class Graphique(QWidget):
    """Zone de tracé qui se redessine à sa taille : `dessin(painter, largeur, hauteur)` fait le tracé."""

    def __init__(self, vide=""):
        super().__init__()
        self.dessin = None
        self.vide = vide
        self.setMinimumSize(320, 230)

    def definir(self, dessin, vide=None):
        self.dessin = dessin
        if vide is not None:
            self.vide = vide
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0b1119"))
        if self.dessin is not None:
            self.dessin(p, self.width(), self.height())
        else:
            p.setPen(QColor("#8d9bb0"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.vide)
        p.setPen(QPen(QColor("#394657"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.end()


def bloc_texte(p, x, y, lignes):
    """Légende : une ligne par (texte, couleur), sur fond sombre translucide."""
    police = QFont(p.font())
    police.setPointSize(10)
    p.setFont(police)
    largeur = max(p.fontMetrics().horizontalAdvance(t) for t, _ in lignes) + 14
    p.fillRect(int(x), int(y), int(largeur), 17 * len(lignes) + 8, QColor(11, 17, 25, 215))
    for i, (t, c) in enumerate(lignes):
        p.setPen(QColor(c))
        p.drawText(int(x) + 7, int(y) + 4 + 17 * i, int(largeur), 17, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, t)


def avec_legende(bas, haut, h, lignes):
    """Borne haute de l'axe qui laisse sous la légende (en pixels) une zone sans données."""
    f = min((17 * len(lignes) + 16) / max(h - 78.0, 60.0), 0.65)
    return bas, bas + (haut - bas) / (1 - f)


def cadre_axes(p, w, h, titre, xlab, ylab, xlim, ylim, xgrad=None, xetiq=None):
    """Dessine titre, axes gradués, grille et noms des axes. Retourne la fonction (x, y) -> pixels et le rectangle du tracé."""
    g0, g1, g2, g3 = 68, 14, 32, 46        # marges gauche, droite, haut, bas
    x0, y0, x1, y1 = g0, g2, w - g1, h - g3
    police = QFont(p.font())
    police.setPointSize(10)
    p.setFont(police)
    fort = QFont(police)
    fort.setBold(True)
    p.setFont(fort)
    p.setPen(QColor("#eef3fa"))
    p.drawText(x0, 4, x1 - x0, 22, Qt.AlignmentFlag.AlignCenter, titre)
    p.setFont(police)

    def xy(x, y):
        return (x0 + (x - xlim[0]) / (xlim[1] - xlim[0]) * (x1 - x0),
                y1 - (y - ylim[0]) / (ylim[1] - ylim[0]) * (y1 - y0))
    valeurs, pas = graduations(*ylim, 5)
    for v in valeurs:
        _, py = xy(xlim[0], v)
        p.setPen(QPen(QColor("#222c3a"), 1))
        p.drawLine(x0, int(py), x1, int(py))
        p.setPen(QColor("#b9c7d8"))
        p.drawLine(x0 - 4, int(py), x0, int(py))
        p.drawText(0, int(py) - 9, x0 - 8, 18, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, etiquette(v, pas))
    if xgrad is None:
        xgrad, xpas = graduations(*xlim, 5)
        xetiq = [etiquette(v, xpas) for v in xgrad]
    for v, e in zip(xgrad, xetiq):
        px, _ = xy(v, ylim[0])
        p.setPen(QPen(QColor("#222c3a"), 1))
        p.drawLine(int(px), y0, int(px), y1)
        p.setPen(QColor("#b9c7d8"))
        p.drawLine(int(px), y1, int(px), y1 + 4)
        p.drawText(int(px) - 30, y1 + 6, 60, 16, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, e)
    p.setPen(QPen(QColor("#b9c7d8"), 1.5))
    p.drawLine(x0, y0, x0, y1)
    p.drawLine(x0, y1, x1, y1)
    p.setPen(QColor("#eef3fa"))
    p.drawText(x0, h - 20, x1 - x0, 18, Qt.AlignmentFlag.AlignCenter, xlab)
    p.save()
    p.translate(14, (y0 + y1) / 2)
    p.rotate(-90)
    p.drawText(-(y1 - y0) // 2, -8, y1 - y0, 18, Qt.AlignmentFlag.AlignCenter, ylab)
    p.restore()
    p.setClipRect(x0, y0, x1 - x0, y1 - y0 + 1)
    return xy, (x0, y0, x1, y1)


# ----------------------------------------------------------------------------- Lecteur vidéo (image + curseur + lecture)
class ZoneImage(QLabel):
    """Étiquette qui signale la souris (appui, déplacement, relâchement) en coordonnées de l'étiquette."""
    appui = Signal(float, float)
    deplace = Signal(float, float)
    relache = Signal(float, float)
    molette = Signal(int)

    def wheelEvent(self, e):
        self.molette.emit(e.angleDelta().y())

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.appui.emit(e.position().x(), e.position().y())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.deplace.emit(e.position().x(), e.position().y())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.relache.emit(e.position().x(), e.position().y())


class LecteurVideo(QWidget):
    """Image du film + boutons + curseur. `rendre(index)` fournit l'image BGR à afficher."""
    rectangle = Signal(float, float, float, float)     # x0, y0, x1, y1 en pixels de l'image du film
    image_changee = Signal(int)

    def __init__(self, rendre, avec_zoom=False):
        super().__init__()
        self.rendre = rendre
        self.n, self.index, self.dt = 0, 0, 0.05
        self.mode_zone = False
        self.avec_zoom = avec_zoom
        self.zoom = 1.0
        self.centre_libre = None         # centre choisi à la souris (pixels de l'image), None = centre de l'image
        self.centre_courant = None       # centre réellement affiché (renseigné par la fenêtre à chaque rendu)
        self._pan = None
        self._geom = None            # (largeur image, hauteur image, largeur pixmap, hauteur pixmap)
        self._debut = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = ZoneImage("Ouvrez un film pour commencer")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(520, 390)
        self.label.setStyleSheet("background: #05080b; border: 1px solid #40506a;")
        self.label.appui.connect(self._appui)
        self.label.deplace.connect(self._deplace)
        self.label.relache.connect(self._relache)
        self.bande = QRubberBand(QRubberBand.Shape.Rectangle, self.label)
        self.label.molette.connect(self._molette)
        layout.addWidget(self.label, 1)
        if avec_zoom:
            zl = QHBoxLayout()
            zl.addWidget(QLabel("Zoom :"))
            self.s_zoom = QSlider(Qt.Orientation.Horizontal)
            self.s_zoom.setRange(10, 100)
            self.s_zoom.setValue(10)
            self.s_zoom.valueChanged.connect(self._zoom_change)
            zl.addWidget(self.s_zoom, 3)
            self.l_zoom = QLabel("x 1,0")
            self.l_zoom.setMinimumWidth(50)
            zl.addWidget(self.l_zoom)
            b_entier = QPushButton("Image entière")
            b_entier.clicked.connect(self.vue_entiere)
            zl.addWidget(b_entier)
            zl.addWidget(QLabel("Suivre :"))
            self.combo_suivi = QComboBox()
            self.combo_suivi.addItem("Vue libre (glisser pour se déplacer)", None)
            self.combo_suivi.setMinimumWidth(230)
            zl.addWidget(self.combo_suivi, 2)
            layout.addLayout(zl)
        self.curseur = QSlider(Qt.Orientation.Horizontal)
        self.curseur.setRange(0, 0)
        self.curseur.valueChanged.connect(self.aller_a)
        layout.addWidget(self.curseur)
        ligne = QHBoxLayout()
        self.b_lecture = QPushButton("Lecture")
        self.b_pause = QPushButton("Pause")
        self.b_arret = QPushButton("Retour au début")
        self.b_lecture.clicked.connect(self.lecture)
        self.b_pause.clicked.connect(self.pause)
        self.b_arret.clicked.connect(self.arret)
        for b in (self.b_lecture, self.b_pause, self.b_arret):
            ligne.addWidget(b)
        self.info = QLabel("Image : -")
        ligne.addWidget(self.info, 1)
        layout.addLayout(ligne)
        self.minuteur = QTimer(self)
        self.minuteur.timeout.connect(self._suivante)

    def charger(self, n, dt):
        self.pause()
        self.n, self.dt, self.index = n, dt, 0
        self.curseur.blockSignals(True)
        self.curseur.setRange(0, max(n - 1, 0))
        self.curseur.setValue(0)
        self.curseur.blockSignals(False)
        self.afficher()

    def afficher(self):
        if self.n == 0:
            return
        bgr = self.rendre(self.index)
        h, w = bgr.shape[:2]
        qimg = QImage(np.ascontiguousarray(bgr).data, w, h, 3 * w, QImage.Format.Format_BGR888).copy()
        pix = QPixmap.fromImage(qimg).scaled(self.label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
        self._geom = (w, h, pix.width(), pix.height())
        self.label.setPixmap(pix)
        self.info.setText(f"Image {self.index + 1} / {self.n}    t = {self.index * self.dt:.3f} s")

    # --- zoom et déplacement (lecteur de la vidéo annotée)
    def _zoom_change(self, valeur):
        self.zoom = valeur / 10.0
        self.l_zoom.setText(f"x {self.zoom:.1f}".replace(".", ","))
        self.label.setCursor(Qt.CursorShape.OpenHandCursor if self.zoom > 1.0 else Qt.CursorShape.ArrowCursor)
        self.afficher()

    def definir_zoom(self, zoom):
        self.s_zoom.setValue(int(round(min(max(zoom, 1.0), 10.0) * 10)))

    def vue_entiere(self):
        self.centre_libre = None
        self.combo_suivi.blockSignals(True)
        self.combo_suivi.setCurrentIndex(0)
        self.combo_suivi.blockSignals(False)
        self.definir_zoom(1.0)
        self.afficher()

    def _molette(self, delta):
        if self.avec_zoom and self.n:
            self.definir_zoom(self.zoom * (1.15 if delta > 0 else 1 / 1.15))

    def aller_a(self, index):
        self.index = int(index)
        self.afficher()
        self.image_changee.emit(self.index)

    def _suivante(self):
        if self.index >= self.n - 1:
            self.pause()
            return
        self.curseur.setValue(self.index + 1)

    def lecture(self):
        if self.n:
            self.minuteur.start(int(max(1000 * self.dt, 33)))

    def pause(self):
        self.minuteur.stop()

    def arret(self):
        self.pause()
        self.curseur.setValue(0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.n:
            self.afficher()

    # --- rectangle à la souris
    def _vers_image(self, px, py):
        if not self._geom:
            return None
        w, h, pw, ph = self._geom
        ox, oy = (self.label.width() - pw) / 2, (self.label.height() - ph) / 2
        x, y = (px - ox) * w / pw, (py - oy) * h / ph
        return float(min(max(x, 0), w - 1)), float(min(max(y, 0), h - 1))

    def _appui(self, px, py):
        if self.mode_zone and self._geom:
            self._debut = (px, py)
            self.bande.setGeometry(int(px), int(py), 0, 0)
            self.bande.show()
        elif self.avec_zoom and self.zoom > 1.0 and self._geom and self.centre_courant:
            self._pan = (px, py) + tuple(self.centre_courant)
            self.label.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _deplace(self, px, py):
        if self._pan is not None:
            w, h, pw, ph = self._geom
            px0, py0, cx0, cy0 = self._pan
            self.centre_libre = (cx0 - (px - px0) * (w / pw) / self.zoom, cy0 - (py - py0) * (h / ph) / self.zoom)
            self.combo_suivi.blockSignals(True)
            self.combo_suivi.setCurrentIndex(0)
            self.combo_suivi.blockSignals(False)
            self.afficher()
        elif self._debut is not None:
            x0, y0 = self._debut
            self.bande.setGeometry(int(min(x0, px)), int(min(y0, py)), int(abs(px - x0)), int(abs(py - y0)))

    def _relache(self, px, py):
        if self._pan is not None:
            self._pan = None
            self.label.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if self._debut is None:
            return
        x0, y0 = self._debut
        self._debut = None
        self.bande.hide()
        a, b = self._vers_image(x0, y0), self._vers_image(px, py)
        if a and b and abs(b[0] - a[0]) >= 8 and abs(b[1] - a[1]) >= 8:
            self.rectangle.emit(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


# ----------------------------------------------------------------------------- Analyse en arrière-plan
class AnalyseWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progression = Signal(int, str)

    def __init__(self, chemin, pixel_um, dt_s, config, immobiles=False):
        super().__init__()
        self.chemin, self.pixel_um, self.dt_s, self.config, self.immobiles = chemin, pixel_um, dt_s, config, immobiles

    @Slot()
    def run(self):
        try:
            self.config["progression"] = self.progression.emit
            fonction = analyse_equipe.analyser_immobiles if self.immobiles else analyse_equipe.analyser_video
            sortie = fonction(self.chemin, self.pixel_um, self.dt_s, self.config)
            if not isinstance(sortie, dict) or not isinstance(sortie.get("results"), dict):
                raise ValueError("analyser_video doit renvoyer {'results': {...}, 'trajectories': {...}}")
            self.finished.emit(sortie)
        except Exception as exc:
            if isinstance(exc, ValueError):
                self.failed.emit(str(exc))
            else:
                self.failed.emit(traceback.format_exc())


# ----------------------------------------------------------------------------- Fenêtre principale
class MicroscopeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PHS3910 | Traitement : suivi de particules fluorescentes")
        self.resize(1300, 820)
        self.film = None
        self.chemin = None
        self.zones = []                 # [{"image": k, "rect": (x0, y0, x1, y1)}] en pixels de l'image
        self.sortie = None              # dernier résultat de l'analyse
        self.traces = {}                # {id: (images, positions)}
        self.statuts = {}               # {id: "utilisée" / "écartée"}
        self.thread = None
        self.worker = None
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self._onglet_film()
        self._onglet_resultats()
        self._onglet_taille()
        self._onglet_video()
        self._onglet_parametres()
        self.mode_change()
        self.statusBar().showMessage("Prêt : ouvrez un film TIFF enregistré avec l'interface d'acquisition")
        self.setStyleSheet(STYLE)

    # ------------------------------------------------------------------ construction
    def _onglet_film(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        gauche = QVBoxLayout()
        boite = QGroupBox("Film")
        b = QVBoxLayout(boite)
        self.b_ouvrir = QPushButton("Ouvrir un film (TIFF)")
        self.b_ouvrir.clicked.connect(self.ouvrir_film)
        b.addWidget(self.b_ouvrir)
        self.l_fichier = QLabel("Aucun film chargé")
        self.l_fichier.setWordWrap(True)
        b.addWidget(self.l_fichier)
        self.l_infos = QLabel("")
        self.l_infos.setWordWrap(True)
        b.addWidget(self.l_infos)
        self.c_contraste = QCheckBox("Ajuster le contraste (affichage seulement)")
        self.c_contraste.setChecked(True)
        self.c_contraste.toggled.connect(self.rafraichir)
        b.addWidget(self.c_contraste)
        self.b_image = QPushButton("Enregistrer l'image affichée (PNG)")
        self.b_image.clicked.connect(self.enregistrer_image)
        b.addWidget(self.b_image)
        gauche.addWidget(boite)

        choix = QGroupBox("Choix des particules")
        self.g_choix = choix
        c = QVBoxLayout(choix)
        self.mode = QComboBox()
        self.mode.addItems(MODES)
        self.mode.currentIndexChanged.connect(self.mode_change)
        c.addWidget(self.mode)
        self.l_mode = QLabel("")
        self.l_mode.setWordWrap(True)
        c.addWidget(self.l_mode)
        self.liste_zones = QListWidget()
        self.liste_zones.setMaximumHeight(110)
        c.addWidget(self.liste_zones)
        ligne = QHBoxLayout()
        self.b_retirer = QPushButton("Retirer la dernière zone")
        self.b_effacer = QPushButton("Tout effacer")
        self.b_retirer.clicked.connect(self.retirer_zone)
        self.b_effacer.clicked.connect(self.effacer_zones)
        ligne.addWidget(self.b_retirer)
        ligne.addWidget(self.b_effacer)
        c.addLayout(ligne)
        gauche.addWidget(choix)

        self.c_derive = QCheckBox("Corriger le mouvement collectif (dérive commune), recommandé")
        self.c_derive.setChecked(True)
        self.c_derive.setToolTip("Les particules dérivent ensemble (courant, vibrations) en plus du mouvement brownien. "
                                 "La correction retire cette dérive commune. Sans elle, D est surestimé et le rayon sous-estimé.")
        gauche.addWidget(self.c_derive)
        self.c_immobiles = QCheckBox("Particules immobiles (taille par la largeur des taches)")
        self.c_immobiles.setToolTip("Particules collées à la lame : diamètre estimé à partir de la largeur des taches.")
        self.c_immobiles.toggled.connect(self.immobiles_change)
        gauche.addWidget(self.c_immobiles)
        self.box_imm = QGroupBox("Taille des taches")
        fi = QFormLayout(self.box_imm)
        self.i_na = QDoubleSpinBox()
        self.i_na.setRange(0.05, 1.5)
        self.i_na.setDecimals(2)
        self.i_na.setSingleStep(0.05)
        self.i_na.setValue(0.40)
        self.i_na.setToolTip("Ouverture numérique de l'objectif (reprise de Paramètres).")
        self.i_lambda = QDoubleSpinBox()
        self.i_lambda.setRange(380, 900)
        self.i_lambda.setDecimals(0)
        self.i_lambda.setValue(575)
        self.i_lambda.setSuffix(" nm")
        self.i_lambda.setToolTip("Longueur d'onde d'émission des billes (excitation / émission : 535 / 575 nm).")
        fi.addRow("Ouverture numérique (NA) :", self.i_na)
        fi.addRow("Longueur d'onde d'émission :", self.i_lambda)
        self.box_imm.setVisible(False)
        gauche.addWidget(self.box_imm)
        self.b_analyser = QPushButton("Analyser")
        self.b_analyser.clicked.connect(self.lancer_analyse)
        gauche.addWidget(self.b_analyser)
        self.progression = QProgressBar()
        self.progression.setRange(0, 100)
        gauche.addWidget(self.progression)
        self.l_etat = QLabel("")
        self.l_etat.setWordWrap(True)
        gauche.addWidget(self.l_etat)
        gauche.addStretch()
        conteneur = QWidget()
        conteneur.setLayout(gauche)
        defil = QScrollArea()
        defil.setWidgetResizable(True)
        defil.setWidget(conteneur)
        defil.setMinimumWidth(400)
        defil.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(defil, 2)

        self.lecteur = LecteurVideo(lambda i: self.rendre(i, annote=False))
        self.lecteur.rectangle.connect(self.zone_tracee)
        layout.addWidget(self.lecteur, 4)
        self.tabs.addTab(page, "Film et sélection")

    def _onglet_resultats(self):
        page = QWidget()
        racine = QVBoxLayout(page)
        banniere = QFrame()
        banniere.setObjectName("banniere")
        banniere.setStyleSheet("QFrame#banniere { background: #1d2633; border: 1px solid #394657; border-radius: 10px; }")
        b = QVBoxLayout(banniere)
        def panneau(taille):
            titre = QLabel("")
            resume = QLabel("")
            sous = QLabel("")
            for lab, css in ((titre, "font-size: 16px; color: #b9c7d8;"),
                             (resume, f"font-size: {taille}px; font-weight: bold; color: #7fd1ff;"),
                             (sous, "font-size: 12px; color: #8d9bb0;")):
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lab.setWordWrap(True)
                lab.setStyleSheet(css + " background: transparent;")
            return titre, resume, sous
        haut = QHBoxLayout()
        gauche_b, droite_b = QVBoxLayout(), QVBoxLayout()
        self.l_titre, self.l_resume, self.l_sous = panneau(42)
        self.l_titre.setText("Aucun résultat : lancez une analyse")
        for w_ in (self.l_titre, self.l_resume, self.l_sous):
            gauche_b.addWidget(w_)
        self.g_titre, self.g_resume, self.g_sous = panneau(42)
        self.g_resume.setStyleSheet(self.g_resume.styleSheet().replace("#7fd1ff", "#9be58a"))
        for w_ in (self.g_titre, self.g_resume, self.g_sous):
            droite_b.addWidget(w_)
        self.panneau_g = QWidget()
        self.panneau_g.setStyleSheet("background: transparent;")
        self.panneau_g.setLayout(droite_b)
        self.panneau_g.setVisible(False)
        haut.addLayout(gauche_b, 1)
        haut.addWidget(self.panneau_g, 1)
        b.addLayout(haut)
        cartes = QHBoxLayout()
        self.cartes = {}
        for cle, titre in (("D", "Coefficient de diffusion moyen D"), ("disp", "Dispersion entre particules"),
                           ("med", "Rayon médian"), ("brut", "Rayon sans correction du mouvement collectif"),
                           ("ecart", "Particules écartées")):
            carte = QFrame()
            carte.setStyleSheet("QFrame { background: #26303d; border-radius: 8px; }")
            v = QVBoxLayout(carte)
            v.setContentsMargins(10, 6, 10, 6)
            valeur = QLabel("-")
            valeur.setAlignment(Qt.AlignmentFlag.AlignCenter)
            valeur.setStyleSheet("font-size: 19px; font-weight: bold; background: transparent;")
            legende = QLabel(titre)
            legende.setAlignment(Qt.AlignmentFlag.AlignCenter)
            legende.setWordWrap(True)
            legende.setStyleSheet("font-size: 11px; color: #9fb0c6; background: transparent;")
            v.addWidget(valeur)
            v.addWidget(legende)
            cartes.addWidget(carte, 1)
            self.cartes[cle] = (carte, valeur)
        b.addLayout(cartes)
        racine.addWidget(banniere)

        bas = QHBoxLayout()
        gauche = QVBoxLayout()
        self.tableau = QTableWidget(0, 0)
        self.tableau.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tableau.horizontalHeader().setStretchLastSection(True)
        self.tableau.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tableau.verticalHeader().setVisible(False)
        gauche.addWidget(self.tableau, 1)
        self.t_notes = QPlainTextEdit()
        self.t_notes.setReadOnly(True)
        self.t_notes.setMaximumHeight(96)
        gauche.addWidget(self.t_notes)
        self.b_export = QPushButton("Exporter les résultats (CSV)")
        self.b_export.setEnabled(False)
        self.b_export.clicked.connect(self.exporter_resultats)
        gauche.addWidget(self.b_export)
        bas.addLayout(gauche, 5)
        droite = QVBoxLayout()
        self.g_msd = Graphique("MSD : lancez une analyse")
        self.g_rayons = Graphique("Rayons : lancez une analyse")
        droite.addWidget(self.g_msd, 1)
        droite.addWidget(self.g_rayons, 1)
        bas.addLayout(droite, 4)
        racine.addLayout(bas, 1)
        self.tabs.addTab(page, "Résultats")

    def _onglet_video(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        haut = QHBoxLayout()
        self.c_traces = QCheckBox("Afficher les trajectoires")
        self.c_traces.setChecked(True)
        self.c_rejetees = QCheckBox("Afficher aussi les particules écartées (en rouge)")
        self.c_rejetees.setChecked(True)
        for c in (self.c_traces, self.c_rejetees):
            c.toggled.connect(self.rafraichir)
            haut.addWidget(c)
        haut.addStretch()
        self.b_avi = QPushButton("Exporter la vidéo annotée (AVI)")
        self.b_avi.setEnabled(False)
        self.b_avi.clicked.connect(self.exporter_avi)
        haut.addWidget(self.b_avi)
        layout.addLayout(haut)
        self.l_video = QLabel("La vidéo avec les trajectoires apparaît après l'analyse.")
        layout.addWidget(self.l_video)
        self.lecteur2 = LecteurVideo(lambda i: self.rendre(i, annote=True, lecteur=self.lecteur2), avec_zoom=True)
        self.lecteur2.combo_suivi.currentIndexChanged.connect(self.suivi_change)
        layout.addWidget(self.lecteur2, 1)
        self.tabs.addTab(page, "Vidéo annotée")

    def _onglet_parametres(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        cond = QGroupBox("Conditions d'acquisition (affichées sur chaque image)")
        f = QFormLayout(cond)
        self.p_obj = QComboBox()
        self.p_obj.addItems(OBJECTIFS)
        self.p_obj.setCurrentText(OBJECTIF_PAR_DEFAUT)
        self.p_expo = QDoubleSpinBox()
        self.p_expo.setRange(0.001, 100000)
        self.p_expo.setDecimals(3)
        self.p_expo.setValue(20.0)
        self.p_expo.setSuffix(" ms")
        self.p_dt = QDoubleSpinBox()
        self.p_dt.setRange(0.001, 100000)
        self.p_dt.setDecimals(3)
        self.p_dt.setValue(50.0)
        self.p_dt.setSuffix(" ms")
        self.l_cadence = QLabel("")
        self.p_bits = QSpinBox()
        self.p_bits.setRange(1, 32)
        self.p_bits.setValue(8)
        self.p_bits.setSuffix(" bits")
        self.p_pix = QDoubleSpinBox()
        self.p_pix.setRange(0.0001, 1000)
        self.p_pix.setDecimals(4)
        self.p_pix.setValue(0.186)
        self.p_pix.setSuffix(" µm/pixel")
        f.addRow("Objectif :", self.p_obj)
        f.addRow("Temps d'exposition :", self.p_expo)
        f.addRow("Intervalle entre images Δt :", self.p_dt)
        f.addRow("Fréquence d'acquisition :", self.l_cadence)
        f.addRow("Profondeur de bit :", self.p_bits)
        f.addRow("Échelle spatiale :", self.p_pix)
        note = QLabel("Ces valeurs sont lues dans le nom du fichier quand il les contient, sinon ce sont les valeurs les "
                      "plus probables (objectif 20X, NA 0,40, échelle 0,186 µm/pixel mesurée à la règle). Elles sont modifiables. Le rayon varie comme 1/p²: "
                      "une erreur sur l'échelle se retrouve doublée sur le rayon.")
        note.setWordWrap(True)
        f.addRow(note)
        layout.addWidget(cond)
        self.p_obj.currentIndexChanged.connect(self._na_depuis_objectif)
        self._na_depuis_objectif()
        for w in (self.p_obj, self.p_expo, self.p_dt, self.p_bits, self.p_pix):
            (w.currentIndexChanged if isinstance(w, QComboBox) else w.valueChanged).connect(self.parametres_changes)

        tri = QGroupBox("Analyse")
        g = QFormLayout(tri)
        self.p_derive = self.c_derive
        self.p_seuil = QSpinBox()
        self.p_seuil.setRange(0, 100)
        self.p_seuil.setValue(int(analyse_equipe.SEUIL_INTENSITE * 100))
        self.p_seuil.setSuffix(" %")
        self.p_seuil.setToolTip("Les particules moins lumineuses que ce pourcentage de l'intensité de référence "
                                "(90e centile des particules suivies) sont écartées : elles sont hors focus.")
        self.p_rejet = QDoubleSpinBox()
        self.p_rejet.setRange(0, 10)
        self.p_rejet.setDecimals(1)
        self.p_rejet.setValue(analyse_equipe.REJET_SIGMA)
        self.p_rejet.setToolTip("Rejet des valeurs aberrantes de D au-delà de ce nombre d'écarts absolus médians "
                                "(0 = aucun rejet).")
        self.p_iso = QDoubleSpinBox()
        self.p_iso.setRange(5, 200)
        self.p_iso.setDecimals(0)
        self.p_iso.setValue(analyse_equipe.ISOLEMENT_PX)
        self.p_iso.setSuffix(" pixels")
        g.addRow("Seuil d'intensité (mode automatique) :", self.p_seuil)
        g.addRow("Rejet des aberrantes (écarts absolus médians) :", self.p_rejet)
        g.addRow("Distance minimale entre particules :", self.p_iso)
        layout.addWidget(tri)
        layout.addStretch()
        self.tabs.addTab(page, "Paramètres")
        self.parametres_changes()

    # ------------------------------------------------------------------ film
    def ouvrir_film(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Ouvrir un film", "", "Films TIFF (*.tif *.tiff)")
        if chemin:
            self.charger_film(chemin)

    def charger_film(self, chemin):
        try:
            film = LectureFilm(chemin)
        except Exception as exc:
            QMessageBox.warning(self, "Film", f"Impossible d'ouvrir le film : {exc}")
            return
        if self.film is not None:
            self.film.fermer()
        self.film, self.chemin = film, str(chemin)
        nom = Path(chemin).name
        dt, expo, pixel, bits = annotation.parametres_du_nom(nom)
        for w, v in ((self.p_dt, dt and dt * 1000), (self.p_expo, expo and expo * 1000), (self.p_pix, pixel),
                     (self.p_bits, bits)):
            if v:
                w.blockSignals(True)
                w.setValue(v)
                w.blockSignals(False)
        self.parametres_changes(rafraichir=False)
        self.zones, self.sortie, self.traces, self.statuts = [], None, {}, {}
        self.liste_zones.clear()
        self.b_export.setEnabled(False)
        self.b_avi.setEnabled(False)
        self.l_titre.setText("Aucun résultat : lancez une analyse")
        self.l_resume.setText("")
        self.l_sous.setText("")
        self.g_msd.definir(None, "MSD : lancez une analyse")
        self.g_rayons.definir(None, "Rayons : lancez une analyse")
        self.l_fichier.setText(nom)
        manque = [t for t, v in (("Δt", dt), ("exposition", expo), ("échelle", pixel)) if not v]
        self.l_infos.setText(f"{film.n} images, Δt = {self.p_dt.value():g} ms, durée {film.n * self.p_dt.value() / 1000:.1f} s."
                             + (f" Absent du nom du fichier : {', '.join(manque)} (valeurs par défaut, à vérifier)." if manque else ""))
        self.lecteur.charger(film.n, self.p_dt.value() / 1000)
        self.lecteur2.charger(0, 0.05)
        self.lecteur2.vue_entiere()
        self.lecteur2.label.setText("La vidéo avec les trajectoires apparaît après l'analyse.")
        self.progression.setValue(0)
        self.l_etat.setText("")
        self.statusBar().showMessage(f"Film ouvert : {nom}")

    def conditions(self):
        return dict(objectif=self.p_obj.currentText(), expo_s=self.p_expo.value() / 1000, dt_s=self.p_dt.value() / 1000,
                    bits=self.p_bits.value(), pixel_um=self.p_pix.value())

    def parametres_changes(self, *_, rafraichir=True):
        dt = self.p_dt.value() / 1000
        self.l_cadence.setText(f"{1 / dt:.2f} images/s")
        self.p_expo.setStyleSheet("color: #ff8a80;" if self.p_expo.value() > self.p_dt.value() else "")
        if self.film is not None and rafraichir:
            self.lecteur.dt = dt
            self.lecteur2.dt = dt
            self.rafraichir()

    def rafraichir(self, *_):
        if self.film is not None:
            self.lecteur.afficher()
            if self.sortie is not None:
                self.lecteur2.afficher()

    # ------------------------------------------------------------------ rendu d'une image
    def _centre_vue(self, lecteur, index, w, h):
        pid = lecteur.combo_suivi.currentData()
        if pid in self.traces:
            images, pos = self.traces[pid]
            k = int(np.clip(index - images[0], 0, len(images) - 1))
            lo, hi = max(0, k - 10), min(len(images), k + 11)
            return tuple(float(v) for v in pos[lo:hi].mean(axis=0))
        return lecteur.centre_libre or (w / 2.0, h / 2.0)

    def suivi_change(self, *_):
        if self.lecteur2.combo_suivi.currentData() is not None and self.lecteur2.zoom <= 1.0:
            self.lecteur2.definir_zoom(5.0)
        self.lecteur2.afficher()

    def rendre(self, index, annote, lecteur=None):
        c = self.conditions()
        gris = self.film.image8(index, self.c_contraste.isChecked())
        h, w = gris.shape
        vue = (0.0, 0.0, 1.0, 1.0)         # origine x, origine y, échelle x, échelle y (image du film -> image affichée)
        if annote and lecteur is not None and lecteur.zoom > 1.0 + 1e-6:
            cw, ch = max(int(round(w / lecteur.zoom)), 8), max(int(round(h / lecteur.zoom)), 8)
            cx, cy = self._centre_vue(lecteur, index, w, h)
            lecteur.centre_courant = (cx, cy)
            x0 = int(round(min(max(cx - cw / 2.0, 0), w - cw)))
            y0 = int(round(min(max(cy - ch / 2.0, 0), h - ch)))
            gris = cv2.resize(gris[y0:y0 + ch, x0:x0 + cw], (w, h), interpolation=cv2.INTER_CUBIC)
            vue = (float(x0), float(y0), w / cw, h / ch)
        bgr = cv2.cvtColor(gris, cv2.COLOR_GRAY2BGR)
        if annote:
            self._tracer_trajectoires(bgr, index, vue)
        else:
            for j, z in enumerate(self.zones, start=1):
                if z["image"] == index:
                    x0, y0, x1, y1 = (int(round(v)) for v in z["rect"])
                    cv2.rectangle(bgr, (x0, y0), (x1, y1), (0, 255, 255), 2)
                    cv2.putText(bgr, str(j), (x0 + 3, y0 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
        # l'échelle (barre et valeur) suit le zoom : un pixel de l'écran vaut pixel_um / zoom
        return annotation.annoter_image(bgr, index * c["dt_s"], c["pixel_um"] / vue[2], c["dt_s"], c["expo_s"],
                                        c["objectif"], c["bits"])

    def _tracer_trajectoires(self, bgr, index, vue):
        if not self.c_traces.isChecked():
            return
        x0, y0, zx, zy = vue
        ids = list(self.traces)

        def ecran(a):
            return (np.asarray(a, float) - [x0, y0]) * [zx, zy]
        for j, pid in enumerate(ids):
            utilisee = self.statuts.get(pid) == "utilisée"
            if not utilisee and not self.c_rejetees.isChecked():
                continue
            images, pos = self.traces[pid]
            if index < images[0]:
                continue
            m = int(min(index, images[-1]) - images[0] + 1)
            if utilisee:
                teinte = int((j * 37) % 180)
                couleur = tuple(int(v) for v in cv2.cvtColor(np.uint8([[[teinte, 230, 255]]]), cv2.COLOR_HSV2BGR)[0, 0])
                epaisseur = 2
            else:
                couleur, epaisseur = (70, 70, 255), 1
            points = ecran(pos[:m])
            if m > 1:
                cv2.polylines(bgr, [np.round(points * 16).astype(np.int32).reshape(-1, 1, 2)], False, couleur, epaisseur,
                              cv2.LINE_AA, 4)
            if index <= images[-1]:
                cx, cy = points[-1]
                rayon = 9 * np.sqrt(zx)
                cv2.circle(bgr, (int(round(cx * 16)), int(round(cy * 16))), int(round(rayon * 16)), couleur, epaisseur,
                           cv2.LINE_AA, 4)
                if len(ids) <= 12:
                    cv2.putText(bgr, court(pid), (int(cx + rayon + 3), int(cy - rayon + 2)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur, 2, cv2.LINE_AA)

    def enregistrer_image(self):
        if self.film is None:
            return
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer l'image", "image.png", "PNG (*.png)")
        if chemin:
            cv2.imwrite(chemin, self.rendre(self.lecteur.index, annote=False))
            self.statusBar().showMessage("Image enregistrée : " + chemin)

    # ------------------------------------------------------------------ choix des particules
    def mode_change(self, *_):
        m = self.mode.currentIndex()
        self.lecteur.mode_zone = (m == 0)
        for w in (self.liste_zones, self.b_retirer, self.b_effacer):
            w.setVisible(m == 0)
        textes = [
            "Placez le film sur une image où la particule est nette, puis glissez la souris pour tracer un rectangle "
            "autour d'elle. Chaque rectangle ajoute une particule. Une seule particule par rectangle.",
            "La tache la plus lumineuse de la première image. C'est souvent la plus grosse particule, donc peu représentative.",
            "Toutes les particules suivies sur au moins 60 % du film, triées automatiquement : intensité suffisante "
            "(hors focus écartées), pas de chevauchement, trajectoire sans saut, valeurs aberrantes rejetées. "
            "Réglages dans Paramètres.",
        ]
        self.l_mode.setText(textes[m])
        self.lecteur.label.setCursor(Qt.CursorShape.CrossCursor if m == 0 else Qt.CursorShape.ArrowCursor)
        self.rafraichir()

    def zone_tracee(self, x0, y0, x1, y1):
        self.zones.append({"image": self.lecteur.index, "rect": (x0, y0, x1, y1)})
        self.liste_zones.addItem(f"Zone {len(self.zones)} : image {self.lecteur.index + 1}, "
                                 f"{x1 - x0:.0f} x {y1 - y0:.0f} pixels")
        self.rafraichir()

    def retirer_zone(self):
        if self.zones:
            self.zones.pop()
            self.liste_zones.takeItem(self.liste_zones.count() - 1)
            self.rafraichir()

    def effacer_zones(self):
        self.zones.clear()
        self.liste_zones.clear()
        self.rafraichir()

    # ------------------------------------------------------------------ analyse
    def lancer_analyse(self):
        if self.film is None:
            QMessageBox.information(self, "Analyse", "Ouvrez d'abord un film.")
            return
        if self.thread is not None:
            return
        if self.c_immobiles.isChecked():
            config = {"na": self.i_na.value(), "lambda_nm": self.i_lambda.value(),
                      "seuil_intensite": self.p_seuil.value() / 100, "isolement_px": self.p_iso.value(),
                      "rejet_sigma": self.p_rejet.value()}
            self._demarrer_analyse(config, immobiles=True)
            return
        m = self.mode.currentIndex()
        config = {"corriger_derive": "auto" if self.p_derive.isChecked() else False,
                  "seuil_intensite": self.p_seuil.value() / 100, "rejet_sigma": self.p_rejet.value(),
                  "isolement_px": self.p_iso.value()}
        if m == 0:
            if not self.zones:
                QMessageBox.information(self, "Choix des particules",
                                        "Tracez d'abord un rectangle autour d'une particule (glisser la souris sur l'image).")
                return
            config.update(mode="zones", zones=[dict(z) for z in self.zones])
        elif m == 1:
            config.update(mode="plus_lumineuse", image_depart=self.lecteur.index)
        else:
            config.update(mode="echantillon")
        self._demarrer_analyse(config)

    def _demarrer_analyse(self, config, immobiles=False):
        self.b_analyser.setEnabled(False)
        self.progression.setValue(0)
        self.l_etat.setText("Analyse en cours...")
        self.thread = QThread(self)
        self.worker = AnalyseWorker(self.chemin, self.p_pix.value(), self.p_dt.value() / 1000, config, immobiles)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progression.connect(self.progression_analyse)
        self.worker.finished.connect(self.analyse_terminee)
        self.worker.failed.connect(self.analyse_echouee)
        for s in (self.worker.finished, self.worker.failed):
            s.connect(self.thread.quit)
        self.thread.finished.connect(self.nettoyer_analyse)
        self.thread.start()

    @Slot(int, str)
    def progression_analyse(self, pourcent, texte):
        self.progression.setValue(pourcent)
        self.l_etat.setText(texte + "...")

    @Slot(object)
    def analyse_terminee(self, sortie):
        self.sortie = sortie
        r = sortie["results"]
        self.traces, self.statuts = {}, {}
        for pid, pts in sortie["trajectories"].items():
            a = np.array(pts, dtype=float)
            self.traces[pid] = (a[:, 0].astype(int), a[:, 1:3])
        for p in r.get("particules", []):
            self.statuts[p["id"]] = p["statut"]
        if r.get("mode") == "immobiles":
            self.remplir_immobiles(r)
            self.l_etat.setText(f"Terminé : largeur des taches mesurée sur {r['particles']} particule(s).")
        else:
            self.remplir_resultats(r)
            self.l_etat.setText(f"Terminé : {r['particles']} particule(s) utilisée(s).")
        self.progression.setValue(100)
        self.l_video.setText(f"{len(self.traces)} trajectoire(s) calculée(s). Le rouge indique les particules écartées. "
                             "Molette ou curseur : zoom. Glisser : déplacer. \"Suivre\" : centrer sur une particule.")
        c = self.lecteur2.combo_suivi
        c.blockSignals(True)
        c.clear()
        c.addItem("Vue libre (glisser pour se déplacer)", None)
        for pid in self.traces:
            c.addItem(f"Particule {court(pid)}" + (" (écartée)" if self.statuts.get(pid) != "utilisée" else ""), pid)
        c.blockSignals(False)
        self.lecteur2.charger(self.film.n, self.p_dt.value() / 1000)
        self.b_avi.setEnabled(True)
        self.tabs.setCurrentIndex(2 if r.get("mode") == "immobiles" else 1)

    @Slot(str)
    def analyse_echouee(self, message):
        self.l_etat.setText("Analyse impossible.")
        QMessageBox.warning(self, "Analyse", message[-3500:])

    @Slot()
    def nettoyer_analyse(self):
        self.thread.deleteLater()
        self.worker.deleteLater()
        self.thread = None
        self.worker = None
        self.b_analyser.setEnabled(True)

    # ------------------------------------------------------------------ résultats
    RAISONS_COURTES = {"intensité trop faible (hors focus)": "hors focus", "chevauchement (autre particule trop proche)": "chevauchement",
                       "valeur aberrante (D trop éloigné de la médiane)": "valeur aberrante", "saut dans la trajectoire": "saut",
                       "valeur aberrante (largeur trop éloignée de la médiane)": "largeur aberrante",
                       "ajustement impossible (tache saturée ou déformée)": "ajustement impossible",
                       "D négatif ou nul": "D négatif"}

    ORDRE_RAISONS = ["largeur aberrante", "valeur aberrante", "chevauchement", "hors focus"]

    def _trier_lignes(self, lignes):
        """Particules gardées d'abord, puis écartées : largeur aberrante, chevauchement, hors focus, autres."""
        def cle(p):
            if p["statut"] == "utilisée":
                return (0, 0)
            court_ = self.RAISONS_COURTES.get(p["raison"], p["raison"])
            return (1, self.ORDRE_RAISONS.index(court_) if court_ in self.ORDRE_RAISONS else len(self.ORDRE_RAISONS))
        return sorted(lignes, key=cle)          # tri stable : l'ordre des numéros est conservé dans chaque groupe

    @staticmethod
    def _nombre(v, fmt="{:.0f}", unite=""):
        return (fmt.format(v) + unite) if isinstance(v, (int, float)) and np.isfinite(v) else "-"

    def remplir_resultats(self, r):
        a, u = r.get("radius_nm"), r.get("uncertainty_nm")
        n, mode = r["particles"], r.get("mode")
        lignes = r.get("particules", [])
        ecartees = [p for p in lignes if p["statut"] != "utilisée"]
        if mode == "echantillon":
            titre = f"Rayon moyen sur {n} particules"
            sous = (f"{r.get('n_suivies', n)} particules suivies, {len(ecartees)} écartées automatiquement "
                    "(hors focus, chevauchement, valeurs aberrantes)")
        elif mode == "plus_lumineuse":
            titre, sous = "Rayon de la particule la plus lumineuse", ""
        elif n == 1:
            titre, sous = "Rayon de la particule choisie", ""
        else:
            titre, sous = f"Rayon moyen sur {n} particules choisies", ""
        if n > 1:
            sous = (sous + " | " if sous else "") + "incertitude = écart-type de la moyenne de D entre les particules"
        else:
            sous = (sous + " | " if sous else "") + "incertitude statistique estimée sur des blocs de la trajectoire"
        self.l_titre.setText(titre)
        self.l_resume.setText(f"a = {a:.0f} ± {u:.0f} nm" if np.isfinite(u) else f"a = {a:.0f} nm")
        self.l_sous.setText(sous)
        fe = r.get("film_entier")
        self.panneau_g.setVisible(bool(fe))
        if fe:
            self.g_titre.setText(f"Rayon moyen sur les {fe['particles']} particules exploitables du film")
            ug = fe["uncertainty_nm"]
            self.g_resume.setText(f"a = {fe['radius_nm']:.0f} ± {ug:.0f} nm" if np.isfinite(ug) else f"a = {fe['radius_nm']:.0f} nm")
            self.g_sous.setText(f"{fe['n_suivies']} suivies, {fe['n_ecartees']} écartées (seuils d'intensité, chevauchement, "
                                "valeurs aberrantes de l'onglet Paramètres)")
        utilisees = [p for p in lignes if p["statut"] == "utilisée"]
        valeurs = {"D": self._nombre(r.get("D_um2_s"), "{:.4f}", " µm²/s"),
                   "disp": self._nombre(r.get("rayon_dispersion_nm"), "{:.0f}", " nm"),
                   "med": self._nombre(r.get("rayon_median_particules_nm"), "{:.0f}", " nm"),
                   "brut": self._nombre(r.get("rayon_sans_correction_nm"), "{:.0f}", " nm"),
                   "ecart": f"{len(ecartees)} sur {len(lignes)}"}
        for cle, (carte, label) in self.cartes.items():
            label.setText(valeurs[cle])
            carte.setVisible(not ((cle in ("disp", "med") and n < 2) or (cle == "ecart" and not ecartees)
                                  or (cle == "brut" and not r.get("mouvement_collectif_corrige"))))
        notes = [t for t in r.get("notes", []) if not t.startswith("La tache la plus lumineuse")]
        self.t_notes.setPlainText("\n".join(notes))
        self.t_notes.setVisible(bool(notes))
        # tableau : la colonne des raisons n'apparaît que s'il y a des particules écartées
        atyp = [p for p in lignes if p.get("atypique")]
        titres = ["Particule", "Intensité (% réf.)", "D (µm²/s)", "Rayon (nm)", "Incertitude (± nm)"]
        infobulles = ["Numéro de la particule", "Contraste médian de la particule, en % de l'intensité de référence du film",
                      "Coefficient de diffusion (ajustement MSD = 4Dτ + c sur les 4 premiers délais)",
                      "Rayon hydrodynamique a = kB T / (6 π η D)",
                      "Incertitude statistique sur le rayon de cette particule (± nm), estimée sur 5 blocs de sa trajectoire"]
        if ecartees or atyp:
            titres.insert(1, "Remarque" if atyp else "Raison d'écartement")
            infobulles.insert(1, "Raison pour laquelle la particule est exclue de la moyenne" +
                              (". Atypique : gardée, mais D très éloigné de celui du film." if atyp else ""))
        self.tableau.setColumnCount(len(titres))
        self.tableau.setHorizontalHeaderLabels(titres)
        for j, t in enumerate(infobulles):
            self.tableau.horizontalHeaderItem(j).setToolTip(t)
        self.tableau.setRowCount(len(lignes))
        for i, p in enumerate(self._trier_lignes(lignes)):
            iv = p.get("intensite_rel")
            cellules = [f"{court(p['id'])}"]
            if ecartees or atyp:
                if p["statut"] != "utilisée":
                    cellules.append(self.RAISONS_COURTES.get(p["raison"], p["raison"]))
                else:
                    cellules.append("atypique" if p.get("atypique") else "")
            cellules += [f"{iv * 100:.0f}" if iv is not None else "-", self._nombre(p["D_um2_s"], "{:.4f}"),
                         self._nombre(p["rayon_nm"]), self._nombre(p.get("incertitude_nm"), "{:.0f}")]
            for j, v in enumerate(cellules):
                it = QTableWidgetItem(v)
                it.setTextAlignment((Qt.AlignmentFlag.AlignCenter if (j != 1 or not (ecartees or atyp)) else Qt.AlignmentFlag.AlignLeft)
                                    | Qt.AlignmentFlag.AlignVCenter)
                if p["statut"] != "utilisée":
                    it.setForeground(QColor("#ff8a80"))
                elif p.get("atypique"):
                    it.setForeground(QColor("#f3b35b"))
                self.tableau.setItem(i, j, it)
        self.b_export.setEnabled(True)
        self.dessiner_msd(r)
        self.dessiner_rayons(utilisees, a, u, r)

    def dessiner_msd(self, r):
        lag, msd = np.array(r.get("lag_s", []), float), np.array(r.get("msd_um2", []), float)
        if len(lag) < 2:
            self.g_msd.definir(None, "MSD indisponible")
            return
        err = np.array(r.get("msd_erreur_um2", []), float)
        if len(err) != len(lag):
            err = np.full(len(lag), np.nan)
        nfit = int(r.get("n_delais_ajustes", len(lag)))
        fit = np.array(r.get("fit_msd_um2", []), float)
        pente, ordonnee = np.polyfit(lag[:nfit], fit[:nfit], 1)
        xmax = float(lag.max()) * 1.05
        haut = float(max(np.nanmax(msd + np.nan_to_num(err)), pente * xmax + ordonnee))
        ymin = min(0.0, ordonnee * 1.4, float(np.nanmin(msd - np.nan_to_num(err))) * 1.1)
        n = r["particles"]
        avec_err = bool(np.any(np.isfinite(err)))
        lignes = [(f"Ajustement MSD = 4 D τ + c :  D = {pente / 4:.4f} µm²/s ,  c = {ordonnee:.4f} µm²", "#f3b35b"),
                  (f"Δt = {r.get('dt_s', lag[0]) * 1000:g} ms ; ajusté sur τ = {lag[0] * 1000:g} à {lag[nfit - 1] * 1000:g} ms "
                   f"({nfit} délais)", "#cfd8e4"),
                  (f"MSD moyen sur {n} particule{'s' if n > 1 else ''}" + (" ; barres : erreur type entre particules" if avec_err else ""),
                   "#cfd8e4"),
                  ("● points ajustés     ○ points non ajustés", "#cfd8e4")]
        ymax_donnees = haut

        def dessin(p, w, h):
            xy, (x0, y0, x1, y1) = cadre_axes(p, w, h, "Déplacement carré moyen (MSD) en fonction du délai",
                                             "Délai τ (s)", "MSD moyen (µm²)", (0, xmax),
                                             avec_legende(ymin, ymax_donnees * 1.04, h, lignes))
            p.setPen(QPen(QColor("#f3b35b"), 2))
            a, b = xy(0, ordonnee), xy(xmax, pente * xmax + ordonnee)
            p.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
            for i, (t, v) in enumerate(zip(lag, msd)):
                px, py = xy(t, v)
                couleur = QColor("#55bde9") if i < nfit else QColor("#8d9bb0")
                if np.isfinite(err[i]) and err[i] > 0:
                    _, hy = xy(t, v + err[i])
                    _, by = xy(t, v - err[i])
                    p.setPen(QPen(couleur, 1.5))
                    p.drawLine(int(px), int(hy), int(px), int(by))
                    p.drawLine(int(px) - 3, int(hy), int(px) + 3, int(hy))
                    p.drawLine(int(px) - 3, int(by), int(px) + 3, int(by))
                p.setPen(QPen(couleur, 1.5))
                p.setBrush(QBrush(couleur) if i < nfit else QBrush(QColor("#0b1119")))
                p.drawEllipse(int(px) - 4, int(py) - 4, 8, 8)
            p.setClipping(False)
            bloc_texte(p, x0 + 6, y0 + 4, lignes)
        self.g_msd.definir(dessin)

    def dessiner_rayons(self, utilisees, moyenne, incertitude, r):
        rayons = np.array([p["rayon_nm"] for p in utilisees], float)
        if len(rayons) == 0 or not np.all(np.isfinite(rayons)):
            self.g_rayons.definir(None, "Rayons indisponibles")
            return
        u = incertitude if np.isfinite(incertitude) else 0.0
        k = len(rayons)
        fe = r.get("film_entier")
        moy_txt = f"a = {moyenne:.0f} ± {u:.0f} nm" if u else f"a = {moyenne:.0f} nm"
        if k <= 20:
            barres = np.array([p.get("incertitude_nm", np.nan) for p in utilisees], float)
            barres = np.where(np.isfinite(barres), barres, 0.0)
            normal = np.array([not p.get("atypique") for p in utilisees])
            ref_ = normal if normal.any() else np.ones(k, bool)
            bas = float(min((rayons - barres)[ref_].min(), moyenne - u))
            haut = float(max((rayons + barres)[ref_].max(), min(moyenne + u, (rayons + barres)[ref_].max() * 1.5)))
            if fe:
                bas, haut = min(bas, fe["radius_nm"] - fe["uncertainty_nm"]), max(haut, fe["radius_nm"] + fe["uncertainty_nm"])
            etendue = max(haut - bas, 1.0)
            ylim = (max(0.0, bas - 0.08 * etendue), haut + 0.04 * etendue)
            xlim = (0.4, k + 0.6)
            pas_x = 1 if k <= 12 else int(np.ceil(k / 10))
            xgrad = [float(i) for i in range(1, k + 1, pas_x)]
            xetiq = [court(utilisees[int(i) - 1]["id"]) for i in xgrad]
            lignes = [(f"Choisies ({k}) : {moy_txt}  (zone orange : ± incertitude)", "#f3b35b")]
            if fe:
                lignes.append((f"Film ({fe['particles']} exploitables) : a = {fe['radius_nm']:.0f} ± "
                               f"{fe['uncertainty_nm']:.0f} nm  (tirets verts)", "#9be58a"))
            lignes.append(("Points : rayon de chaque particule ; barres : son incertitude", "#cfd8e4"))
            ylim0 = ylim
            hors = [(i, p) for i, p in enumerate(utilisees, start=1) if p.get("atypique") and p["rayon_nm"] > ylim0[1]]
            if any(p.get("atypique") for p in utilisees):
                txt = "Orange : atypique (D éloigné du film)"
                if hors:
                    txt += " ; ▲ hors graphique : " + ", ".join(f"n°{court(p_['id'])} : {p_['rayon_nm']:.0f} nm" for _, p_ in hors)
                lignes.append((txt, "#f3b35b"))

            def dessin(p, w, h):
                xy, (x0, y0, x1, y1) = cadre_axes(p, w, h, "Rayon de chaque particule utilisée", "Particule (numéro)",
                                                 "Rayon (nm)", xlim, avec_legende(*ylim0, h, lignes), xgrad, xetiq)
                gx0, gy1 = xy(xlim[0], moyenne + u)
                gx1, gy2 = xy(xlim[1], moyenne - u)
                p.fillRect(int(gx0), int(gy1), int(gx1 - gx0), max(int(gy2 - gy1), 1), QColor(243, 179, 91, 60))
                _, ym = xy(0, moyenne)
                p.setPen(QPen(QColor("#f3b35b"), 2))
                p.drawLine(x0, int(ym), x1, int(ym))
                if fe:
                    _, yf = xy(0, fe["radius_nm"])
                    p.setPen(QPen(QColor("#9be58a"), 2, Qt.PenStyle.DashLine))
                    p.drawLine(x0, int(yf), x1, int(yf))
                for i, (a, b, part) in enumerate(zip(rayons, barres, utilisees), start=1):
                    couleur = QColor("#f3b35b") if part.get("atypique") else QColor("#55bde9")
                    px, py = xy(i, a)
                    p.setPen(QPen(couleur, 1.5))
                    if b > 0:
                        _, hy = xy(i, a + b)
                        _, by = xy(i, a - b)
                        p.drawLine(int(px), int(hy), int(px), int(by))
                        p.drawLine(int(px) - 4, int(hy), int(px) + 4, int(hy))
                        p.drawLine(int(px) - 4, int(by), int(px) + 4, int(by))
                    p.setBrush(QBrush(couleur))
                    p.drawEllipse(int(px) - 4, int(py) - 4, 8, 8)
                p.setClipping(False)
                bloc_texte(p, x0 + 6, y0 + 4, lignes)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor("#f3b35b")))
                for i, _ in hors:
                    px, _ = xy(i, 0)
                    yt = y0 + 17 * len(lignes) + 12
                    p.drawPolygon([QPointF(px, yt), QPointF(px - 6, yt + 11), QPointF(px + 6, yt + 11)])
        else:
            bins = int(min(15, max(6, np.sqrt(k))))
            bas, haut = (float(v) for v in np.percentile(rayons, [1, 99]))
            marge = max((haut - bas) * 0.08, 1.0)
            xlim = (max(0.0, bas - marge), haut + marge)
            comptes, bords = np.histogram(rayons[(rayons >= xlim[0]) & (rayons <= xlim[1])], bins=bins, range=xlim)
            ylim0 = (0, float(comptes.max()))
            disp = r.get("rayon_dispersion_nm", float("nan"))
            lignes = [(f"Moyenne des {k} particules utilisées : {moy_txt}", "#f3b35b"),
                      ("Zone orange : ± incertitude de la moyenne", "#f3b35b"),
                      (f"Dispersion entre particules : {disp:.0f} nm" if np.isfinite(disp) else "", "#cfd8e4"),
                      (f"Classes de {bords[1] - bords[0]:.0f} nm de large", "#cfd8e4")]
            lignes = [l for l in lignes if l[0]]

            def dessin(p, w, h):
                xy, (x0, y0, x1, y1) = cadre_axes(p, w, h, f"Répartition des rayons ({k} particules utilisées)",
                                                 "Rayon (nm)", "Nombre de particules", xlim, avec_legende(*ylim0, h, lignes))
                for c, b0, b1 in zip(comptes, bords[:-1], bords[1:]):
                    ax, ay = xy(b0, c)
                    bx, by = xy(b1, 0)
                    p.fillRect(int(ax) + 1, int(ay), max(int(bx - ax) - 2, 1), int(by - ay), QColor("#55bde9"))
                gx0, gy1 = xy(moyenne - u, avec_legende(*ylim0, h, lignes)[1])
                gx1, gy2 = xy(moyenne + u, 0)
                p.fillRect(int(gx0), int(gy1), max(int(gx1 - gx0), 2), int(gy2 - gy1), QColor(243, 179, 91, 70))
                mx, _ = xy(moyenne, 0)
                p.setPen(QPen(QColor("#f3b35b"), 2))
                p.drawLine(int(mx), y0, int(mx), y1)
                p.setClipping(False)
                bloc_texte(p, x0 + 6, y0 + 4, lignes)
        self.g_rayons.definir(dessin)

    def exporter_resultats(self):
        if not self.sortie:
            return
        r = self.sortie["results"]
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter les résultats", "resultats.csv", "CSV (*.csv)")
        if not chemin:
            return
        try:
            with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["film", Path(self.chemin).name])
                w.writerow(["choix_des_particules", r.get("mode_choix", "")])
                for k, u in (("radius_nm", "nm"), ("uncertainty_nm", "nm"), ("rayon_dispersion_nm", "nm"),
                             ("rayon_median_particules_nm", "nm"), ("D_um2_s", "um2/s"), ("particles", "nombre"),
                             ("rayon_sans_correction_nm", "nm")):
                    w.writerow([k, r.get(k, ""), u])
                fe = r.get("film_entier")
                if fe:
                    w.writerow(["film_entier_particules_exploitables", fe["particles"], "nombre"])
                    w.writerow(["film_entier_radius_nm", fe["radius_nm"], "nm"])
                    w.writerow(["film_entier_uncertainty_nm", fe["uncertainty_nm"], "nm"])
                w.writerow(["pixel_um", self.p_pix.value(), "um/pixel"])
                w.writerow(["dt_s", self.p_dt.value() / 1000, "s"])
                w.writerow([])
                w.writerow(["particule", "statut", "raison", "intensite_rel", "D_um2_s", "rayon_nm", "incertitude_nm"])
                for p in r.get("particules", []):
                    w.writerow([p["id"], p["statut"], p["raison"], p.get("intensite_rel", ""), p["D_um2_s"], p["rayon_nm"],
                                p.get("incertitude_nm", "")])
                w.writerow([])
                w.writerow(["lag_s", "msd_um2", "erreur_type_um2", "fit_msd_um2"])
                for i, (t, v) in enumerate(zip(r["lag_s"], r["msd_um2"])):
                    w.writerow([t, v, r["msd_erreur_um2"][i] if i < len(r.get("msd_erreur_um2", [])) else "",
                                r["fit_msd_um2"][i] if i < len(r["fit_msd_um2"]) else ""])
            self.statusBar().showMessage("Résultats exportés : " + chemin)
        except OSError as exc:
            QMessageBox.warning(self, "Exportation", str(exc))

    # ------------------------------------------------------------------ particules immobiles : taille des taches
    def _na_depuis_objectif(self, *_):
        try:
            self.i_na.setValue(float(self.p_obj.currentText().split("NA")[1].replace(",", ".")))
        except (IndexError, ValueError):
            pass

    def immobiles_change(self, actif):
        self.box_imm.setVisible(actif)
        self.g_choix.setEnabled(not actif)
        self.c_derive.setEnabled(not actif)
        self.b_analyser.setText("Analyser (taille des taches)" if actif else "Analyser")

    def _onglet_taille(self):
        page = QWidget()
        racine = QVBoxLayout(page)
        banniere = QFrame()
        banniere.setStyleSheet("QFrame { background: #1d2633; border: 1px solid #394657; border-radius: 10px; }")
        b = QHBoxLayout(banniere)

        def panneau(couleur):
            titre, valeur, sous = QLabel(""), QLabel(""), QLabel("")
            for lab, css in ((titre, "font-size: 15px; color: #b9c7d8;"),
                             (valeur, f"font-size: 34px; font-weight: bold; color: {couleur};"),
                             (sous, "font-size: 12px; color: #8d9bb0;")):
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lab.setWordWrap(True)
                lab.setStyleSheet(css + " background: transparent;")
            v = QVBoxLayout()
            for w_ in (titre, valeur, sous):
                v.addWidget(w_)
            return titre, valeur, sous, v
        self.t_titre, self.t_valeur, self.t_sous, vg = panneau("#7fd1ff")
        self.t_titre.setText("Aucun résultat : cochez « Particules immobiles » et lancez une analyse")
        b.addLayout(vg, 1)
        racine.addWidget(banniere)
        cartes = QHBoxLayout()
        self.cartes_i = {}
        for cle, titre in (("sigma", "σ moyen des taches (y)"), ("optique", "σ optique"),
                           ("mouvement", "D apparent"), ("n", "Particules utilisées")):
            carte = QFrame()
            carte.setStyleSheet("QFrame { background: #26303d; border-radius: 8px; }")
            v = QVBoxLayout(carte)
            v.setContentsMargins(10, 6, 10, 6)
            valeur = QLabel("-")
            valeur.setAlignment(Qt.AlignmentFlag.AlignCenter)
            valeur.setStyleSheet("font-size: 19px; font-weight: bold; background: transparent;")
            legende = QLabel(titre)
            legende.setAlignment(Qt.AlignmentFlag.AlignCenter)
            legende.setWordWrap(True)
            legende.setStyleSheet("font-size: 11px; color: #9fb0c6; background: transparent;")
            v.addWidget(valeur)
            v.addWidget(legende)
            cartes.addWidget(carte, 1)
            self.cartes_i[cle] = valeur
        racine.addLayout(cartes)
        bas = QHBoxLayout()
        gauche = QVBoxLayout()
        self.tableau_i = QTableWidget(0, 0)
        self.tableau_i.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tableau_i.horizontalHeader().setStretchLastSection(True)
        self.tableau_i.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tableau_i.verticalHeader().setVisible(False)
        gauche.addWidget(self.tableau_i, 1)
        self.t_notes_i = QPlainTextEdit()
        self.t_notes_i.setReadOnly(True)
        self.t_notes_i.setMaximumHeight(150)
        gauche.addWidget(self.t_notes_i)
        self.b_export_i = QPushButton("Exporter les résultats (CSV)")
        self.b_export_i.setEnabled(False)
        self.b_export_i.clicked.connect(self.exporter_immobiles)
        gauche.addWidget(self.b_export_i)
        bas.addLayout(gauche, 5)
        droite = QVBoxLayout()
        self.g_largeurs = Graphique("Largeurs : lancez une analyse")
        self.g_msd_i = Graphique("MSD résiduel : lancez une analyse")
        droite.addWidget(self.g_largeurs, 1)
        droite.addWidget(self.g_msd_i, 1)
        bas.addLayout(droite, 4)
        racine.addLayout(bas, 1)
        self.tabs.addTab(page, "Taille des taches")

    def remplir_immobiles(self, r):
        d, inc = r["d_calcul_um"], r["d_calcul_inc_um"]
        self.t_titre.setText("Diamètre estimé (calcul de l'optique)")
        if np.isfinite(d):
            self.t_valeur.setText(f"d = {d:.2f} ± {inc:.2f} µm" if np.isfinite(inc) else f"d = {d:.2f} µm")
        else:
            self.t_valeur.setText("non calculable")
        self.t_sous.setText(f"σ² = σ optique² + (d / 4,47)²   |   σ = {r['sigma_y_um'] * 1000:.0f} nm, "
                            f"σ optique = {r['sigma_optique_um'] * 1000:.0f} nm (0,21 λ / NA)")
        n = r["particles"]
        sy, sy_inc = r["sigma_y_um"] * 1000, r["sigma_y_inc_um"] * 1000
        self.cartes_i["sigma"].setText(f"{sy:.0f} ± {sy_inc:.0f} nm" if np.isfinite(sy_inc) else f"{sy:.0f} nm")
        self.cartes_i["optique"].setText(f"{r['sigma_optique_um'] * 1000:.0f} nm")
        D = r.get("D_app_um2_s", float("nan"))
        self.cartes_i["mouvement"].setText(("immobiles : " if r.get("immobile") else "") + (f"D = {D:.4f} µm²/s" if np.isfinite(D) else "-"))
        self.cartes_i["n"].setText(f"{n} sur {r['n_suivies']}")
        notes = list(r.get("notes", []))
        self.t_notes_i.setPlainText("\n".join(notes))
        lignes = r["particules"]
        ecartees = [p for p in lignes if p["statut"] != "utilisée"]
        titres = ["Particule", "Raison d'écartement", "Intensité (% réf.)", "σ y (nm)", "± images (nm)", "σ x (nm)"]
        infobulles = ["Numéro de la particule", "Raison pour laquelle la particule est exclue de la moyenne",
                      "Contraste médian, en % de l'intensité de référence",
                      "Largeur de la tache (y), moyenne sur toutes les images",
                      "Écart-type de la moyenne sur les images",
                      "Largeur selon x (étirée par la vibration)"]
        self.tableau_i.setColumnCount(len(titres))
        self.tableau_i.setHorizontalHeaderLabels(titres)
        for j, t in enumerate(infobulles):
            self.tableau_i.horizontalHeaderItem(j).setToolTip(t)
        self.tableau_i.setRowCount(len(lignes))
        for i, p in enumerate(self._trier_lignes(lignes)):
            iv = p.get("intensite_rel")
            cell = [court(p["id"]), self.RAISONS_COURTES.get(p["raison"], p["raison"]) if p["statut"] != "utilisée" else "",
                    f"{iv * 100:.0f}" if iv is not None else "-", self._nombre(p["sigma_y_um"] * 1000),
                    self._nombre(p["sigma_y_inc_um"] * 1000, "{:.1f}"), self._nombre(p["sigma_x_um"] * 1000)]
            for j, v in enumerate(cell):
                it = QTableWidgetItem(v)
                it.setTextAlignment((Qt.AlignmentFlag.AlignLeft if j == 1 else Qt.AlignmentFlag.AlignCenter) | Qt.AlignmentFlag.AlignVCenter)
                if p["statut"] != "utilisée":
                    it.setForeground(QColor("#ff8a80"))
                self.tableau_i.setItem(i, j, it)
        self.b_export_i.setEnabled(True)
        self.dessiner_largeurs(r)
        self.dessiner_msd_immobiles(r)

    def dessiner_largeurs(self, r):
        util = [p for p in r["particules"] if p["statut"] == "utilisée"]
        vals = np.array([p["sigma_y_um"] * 1000 for p in util], float)
        k = len(vals)
        moy, se = r["sigma_y_um"] * 1000, r["sigma_y_inc_um"] * 1000
        se = se if np.isfinite(se) else 0.0
        marge = max((vals.max() - vals.min()) * 0.15, 20.0)
        xlim = (float(vals.min() - marge), float(vals.max() + marge))
        comptes, bords = np.histogram(vals, bins=int(min(12, max(4, np.sqrt(k)))), range=xlim)
        s_opt = r["sigma_optique_um"] * 1000
        lignes = [(f"Moyenne : {moy:.0f} ± {se:.0f} nm", "#f3b35b"),
                  (f"σ optique : {s_opt:.0f} nm" + ("" if xlim[0] <= s_opt <= xlim[1] else " (hors graphique)"), "#9be58a"),
                  (f"{k} particules", "#cfd8e4")]
        ylim0 = (0.0, float(comptes.max()))

        def dessin(p, w, h):
            xy, (x0, y0, x1, y1) = cadre_axes(p, w, h, f"Largeur des taches (σ, direction y), {k} particules", "σ (nm)",
                                             "Nombre de particules", xlim, avec_legende(*ylim0, h, lignes))
            for c, b0, b1 in zip(comptes, bords[:-1], bords[1:]):
                ax, ay = xy(b0, c)
                bx, by = xy(b1, 0)
                p.fillRect(int(ax) + 1, int(ay), max(int(bx - ax) - 2, 1), int(by - ay), QColor("#55bde9"))
            gx0, _ = xy(moy - se, 0)
            gx1, _ = xy(moy + se, 0)
            p.fillRect(int(gx0), y0, max(int(gx1 - gx0), 2), y1 - y0, QColor(243, 179, 91, 70))
            mx, _ = xy(moy, 0)
            p.setPen(QPen(QColor("#f3b35b"), 2))
            p.drawLine(int(mx), y0, int(mx), y1)
            if xlim[0] <= s_opt <= xlim[1]:
                ox, _ = xy(s_opt, 0)
                p.setPen(QPen(QColor("#9be58a"), 2, Qt.PenStyle.DashLine))
                p.drawLine(int(ox), y0, int(ox), y1)
            p.setClipping(False)
            bloc_texte(p, x0 + 6, y0 + 4, lignes)
        self.g_largeurs.definir(dessin)

    def dessiner_msd_immobiles(self, r):
        lag, msd = np.array(r.get("msd_lag_s", []), float), np.array(r.get("msd_um2", []), float)
        if len(lag) < 3:
            self.g_msd_i.definir(None, "MSD indisponible (trop peu de particules suivies)")
            return
        err = np.array(r.get("msd_erreur_um2", []), float)
        D, c0, deb = r["D_app_um2_s"], r["msd_c_um2"], int(r.get("msd_debut_fit", 0))
        xmax = float(lag.max()) * 1.05
        haut = float(max(np.nanmax(msd + np.nan_to_num(err)), 4 * D * xmax + c0))
        bas = min(0.0, float(np.nanmin(msd - np.nan_to_num(err))) * 1.1)
        a_app = r.get("rayon_app_nm", float("nan"))
        lignes = [(f"MSD = 4 D τ + c :  D = {D:.4f} µm²/s", "#f3b35b"),
                  (f"{int(r['particles'])} particules, vibration retirée", "#cfd8e4")]

        def dessin(p, w, h):
            xy, (x0, y0, x1, y1) = cadre_axes(p, w, h, "Mouvement résiduel : MSD en fonction du délai", "Délai τ (s)",
                                             "MSD moyen (µm²)", (0, xmax), avec_legende(bas, haut * 1.04, h, lignes))
            p.setPen(QPen(QColor("#f3b35b"), 2))
            a, b = xy(0, c0), xy(xmax, 4 * D * xmax + c0)
            p.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
            for i, (t, v) in enumerate(zip(lag, msd)):
                px, py = xy(t, v)
                couleur = QColor("#55bde9") if i >= deb else QColor("#8d9bb0")
                if i < len(err) and np.isfinite(err[i]) and err[i] > 0:
                    _, hy = xy(t, v + err[i])
                    _, by = xy(t, v - err[i])
                    p.setPen(QPen(couleur, 1))
                    p.drawLine(int(px), int(hy), int(px), int(by))
                p.setPen(QPen(couleur, 1.5))
                p.setBrush(QBrush(couleur))
                p.drawEllipse(int(px) - 3, int(py) - 3, 6, 6)
            p.setClipping(False)
            bloc_texte(p, x0 + 6, y0 + 4, lignes)
        self.g_msd_i.definir(dessin)

    def exporter_immobiles(self):
        if not self.sortie or self.sortie["results"].get("mode") != "immobiles":
            return
        r = self.sortie["results"]
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter les résultats", "taille_des_taches.csv", "CSV (*.csv)")
        if not chemin:
            return
        try:
            with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["film", Path(self.chemin).name])
                for k, u in (("particles", "nombre"), ("sigma_y_um", "um"), ("sigma_y_inc_um", "um"), ("sigma_x_um", "um"),
                             ("na", ""), ("lambda_nm", "nm"), ("sigma_optique_um", "um"), ("d_calcul_um", "um"),
                             ("d_calcul_inc_um", "um"), ("D_app_um2_s", "um2/s"), ("rayon_app_nm", "nm")):
                    w.writerow([k, r.get(k, ""), u])
                w.writerow(["pixel_um", r["pixel_um"], "um/pixel"])
                w.writerow([])
                w.writerow(["particule", "statut", "raison", "intensite_rel", "sigma_y_um", "sigma_y_inc_images_um", "sigma_x_um",
                            "images_ajustees", "images_suivies"])
                for p in r["particules"]:
                    w.writerow([p["id"], p["statut"], p["raison"], p.get("intensite_rel", ""), p["sigma_y_um"],
                                p["sigma_y_inc_um"], p["sigma_x_um"], p["n_ajustements"], p["n_images"]])
                w.writerow([])
                w.writerow(["lag_s", "msd_um2", "erreur_type_um2"])
                for t, v, e in zip(r["msd_lag_s"], r["msd_um2"], r["msd_erreur_um2"]):
                    w.writerow([t, v, e])
            self.statusBar().showMessage("Résultats exportés : " + chemin)
        except OSError as exc:
            QMessageBox.warning(self, "Exportation", str(exc))

    # ------------------------------------------------------------------ vidéo annotée
    def exporter_avi(self):
        if self.film is None or self.sortie is None:
            return
        base = Path(self.chemin).with_name(Path(self.chemin).stem + "_annote.avi")
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter la vidéo annotée", str(base), "Vidéo AVI (*.avi)")
        if not chemin:
            return
        dt = self.p_dt.value() / 1000
        dialogue = QProgressDialog("Écriture de la vidéo...", "Annuler", 0, self.film.n, self)
        dialogue.setWindowModality(Qt.WindowModality.WindowModal)
        dialogue.setMinimumDuration(0)
        ecrivain = None
        try:
            for i in range(self.film.n):
                cadre = self.rendre(i, annote=True)
                if ecrivain is None:
                    h, w = cadre.shape[:2]
                    ecrivain = cv2.VideoWriter(chemin, cv2.VideoWriter_fourcc(*"MJPG"), min(30.0, 1 / dt), (w, h))
                    if not ecrivain.isOpened():
                        raise RuntimeError("Codec MJPG indisponible : impossible de créer la vidéo.")
                ecrivain.write(cadre)
                dialogue.setValue(i + 1)
                QApplication.processEvents()
                if dialogue.wasCanceled():
                    break
            self.statusBar().showMessage("Vidéo annotée enregistrée : " + chemin)
        except Exception as exc:
            QMessageBox.warning(self, "Vidéo annotée", str(exc))
        finally:
            if ecrivain is not None:
                ecrivain.release()
            dialogue.close()

    def closeEvent(self, event):
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(3000)
        if self.film is not None:
            self.film.fermer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    fenetre = MicroscopeApp()
    fenetre.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
