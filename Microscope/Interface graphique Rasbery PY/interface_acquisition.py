"""Interface d'acquisition du microscope (à lancer sur le Raspberry Pi).

Rôle : régler la caméra, voir l'image en direct avec l'échelle et les conditions d'acquisition, puis enregistrer
un film TIFF (avec un fichier de réglages .json). Aucun traitement n'est fait ici : le rayon se calcule ensuite
sur ordinateur, avec l'interface de traitement (Microscope/Interface graphique pc).

Lancement (depuis ce dossier) :
    python3 interface_acquisition.py                   caméra du Raspberry Pi
    python3 interface_acquisition.py --simulation      essai sans caméra (images fictives, clairement indiquées)

Ce fichier s'ajoute à côté de camera.py et main.py (aperçu avec détection de particule) sans les remplacer. La détection
en direct (gaussienne, taille moyenne) est reprise de camera.py et reste disponible par une case à cocher.

Pendant l'enregistrement, l'aperçu en direct est figé (dernière image affichée) : le Raspberry Pi consacre toute sa
puissance à l'acquisition, ce qui évite de perdre des images. L'aperçu reprend dès que le film est enregistré.

Fichiers produits pour chaque film, dans le dossier choisi :
    <nom>_<numéro>_dt_<dt>s_exp_<exp>s_PixelSize_<pixel>um_Mono_8bit.tif    le film (niveaux de gris, 8 bits)
    <nom>_<numéro>_....json                                                 réglages et instants réels des images
Le nom du .tif contient dt, exposition et taille de pixel : l'interface de traitement les lit automatiquement.
"""
import argparse
import json
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import TypedDict

import cv2
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtCore import QObject, QRect, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QCloseEvent, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)
from scipy.ndimage import gaussian_filter
from scipy.optimize import curve_fit

import acquisition as A          # nom des fichiers, numérotation, écriture du TIFF (validé au laboratoire)

TAILLE = A.TAILLE                # (largeur, hauteur) du mode du capteur
PIXEL_CAMERA_UM = A.PIXEL_CAMERA_UM
FACTEUR_MODE = A.FACTEUR_MODE    # pixels du capteur regroupés par pixel d'image (hypothèse à vérifier)
OBJECTIFS = [
    "4X, NA 0,10", "4X, NA 0,13", "10X, NA 0,25", "10X, NA 0,30", "20X, NA 0,40", "20X, NA 0,45",
    "20X, NA 0,50", "40X, NA 0,65", "40X, NA 0,70", "40X, NA 0,75", "60X, NA 0,85",
]
OBJECTIF_DEFAUT = "20X, NA 0,45"
RAFRAICHISSEMENT_MS = 50         # l'aperçu se rafraîchit environ 20 fois par seconde (ménage le Raspberry Pi)

# Même style que l'interface de traitement (fond sombre, boutons bleus, contours gris clair)
STYLE = """
    QMainWindow, QWidget { background: #171c24; color: #eef3fa; font-size: 13px; }
    QGroupBox { border: 1px solid #3b4656; border-radius: 9px; margin-top: 12px; padding: 12px; font-weight: bold; }
    QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
    QPushButton { background: #2865b5; border: 0; border-radius: 6px; padding: 8px 12px; font-weight: bold; }
    QPushButton:hover { background: #367bda; }
    QPushButton:disabled { background: #3c4653; color: #a6adba; }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QPlainTextEdit {
        background: #26303d; border: 1px solid #485365; border-radius: 5px; padding: 4px; }
    QProgressBar { background: #26303d; border: 1px solid #485365; border-radius: 5px; text-align: center; }
    QProgressBar::chunk { background: #2865b5; border-radius: 4px; }
"""


def grossissement(texte):
    return float(texte.split("X")[0])


def longueur_barre_um(largeur_px, pixel_um, fraction=0.2):
    cible = largeur_px * pixel_um * fraction
    puissance = 10.0 ** np.floor(np.log10(cible))
    return min((m * puissance for m in (1, 2, 5, 10)), key=lambda v: abs(v - cible))


# ----------------------------------------------------------------------------- Détection en direct (option)
class Particle(TypedDict):
    pos: tuple[int, int]
    size: float


def gaussian_2d(
    coordinates: tuple[NDArray[np.float64], NDArray[np.float64]],
    amplitude: float,
    center_x: float,
    center_y: float,
    sigma: float,
    background: float,
) -> NDArray[np.float64]:
    x, y = coordinates
    return amplitude * np.exp(
        -((x - center_x) ** 2 + (y - center_y) ** 2) / (2 * sigma**2)
    ) + background


def update_particles(particles: list[Particle], frame: NDArray[np.uint8]) -> None:
    particles.clear()

    if frame.ndim == 2:
        gray = frame.astype(np.float32)
    elif frame.ndim == 3 and frame.shape[2] == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(np.float32)
    else:
        raise ValueError("L'image caméra doit être en niveaux de gris ou RGB.")

    if not gray.size:
        raise ValueError("L'image caméra est vide.")

    smoothed = gaussian_filter(gray, 1.0)
    peak_y, peak_x = np.unravel_index(np.argmax(smoothed), smoothed.shape)

    half_window = 15
    y_min = max(peak_y - half_window, 0)
    y_max = min(peak_y + half_window + 1, gray.shape[0])
    x_min = max(peak_x - half_window, 0)
    x_max = min(peak_x + half_window + 1, gray.shape[1])
    window = gray[y_min:y_max, x_min:x_max]

    background = float(np.median(window))
    noise = float(np.median(np.abs(window - background)))
    peak = float(smoothed[peak_y, peak_x])
    threshold = background + max(3.0 * 1.4826 * noise, 1.0)
    if peak <= threshold:
        return

    ys, xs = np.indices(window.shape)
    initial = [
        float(window.max() - background),
        float(peak_x - x_min),
        float(peak_y - y_min),
        2.0,
        background,
    ]
    bounds = (
        [0, 0, 0, 0.3, -np.inf],
        [np.inf, window.shape[1], window.shape[0], window.shape[0], np.inf],
    )
    try:
        parameters, _ = curve_fit(
            gaussian_2d,
            (xs.ravel(), ys.ravel()),
            window.ravel(),
            p0=initial,
            bounds=bounds,
            maxfev=2000,
        )
    except (RuntimeError, ValueError):
        return

    center_x = x_min + parameters[1]
    center_y = y_min + parameters[2]
    size = max(1.0, 2 * parameters[3])
    particles.append(Particle(pos=(round(center_x), round(center_y)), size=size))


# ----------------------------------------------------------------------------- Caméras
class CameraPi:
    """Caméra Raspberry Pi (picamera2). Les réglages sont ceux de acquisition.py, validés au laboratoire."""

    nom = "Raspberry Pi HQ"

    def __init__(self, exposition_s, dt_s, gain):
        from picamera2 import Picamera2
        self.cam = Picamera2()
        config = self.cam.create_video_configuration(
            main={"format": "YUV420", "size": TAILLE}, raw={"size": TAILLE}, buffer_count=8,
            controls=self._controles(exposition_s, dt_s, gain))
        self.cam.configure(config)
        self.cam.start()
        time.sleep(1.0)

    @staticmethod
    def _controles(exposition_s, dt_s, gain):
        duree_us = round(dt_s * 1_000_000)
        return {"AeEnable": False, "AwbEnable": False, "ExposureTime": round(exposition_s * 1_000_000),
                "AnalogueGain": gain, "FrameDurationLimits": (duree_us, duree_us),
                "NoiseReductionMode": 0, "Sharpness": 0.0}

    def appliquer(self, exposition_s, dt_s, gain):
        self.cam.set_controls(self._controles(exposition_s, dt_s, gain))

    def lire(self, premier=False):
        """Retourne (image uint8 2D, instant du capteur en ns, exposition réelle en s)."""
        try:
            requete = self.cam.capture_request(flush=True) if premier else self.cam.capture_request()
        except TypeError:
            requete = self.cam.capture_request()
        try:
            image = requete.make_array("main")[:TAILLE[1]].copy()    # les premières lignes = luminance
            md = requete.get_metadata()
        finally:
            requete.release()
        expo = md.get("ExposureTime")
        return image, int(md["SensorTimestamp"]), (expo / 1e6 if expo else None)

    def fermer(self):
        try:
            self.cam.stop()
        finally:
            self.cam.close()


class CameraSimulee:
    """Images fictives pour tester l'interface sans matériel (option --simulation uniquement)."""

    nom = "SIMULATION (aucune caméra)"

    def __init__(self, exposition_s, dt_s, gain):
        self.rng = np.random.default_rng(1)
        self.pos = self.rng.uniform([60, 60], [TAILLE[0] - 60, TAILLE[1] - 60], size=(40, 2))
        self.dt, self.expo = dt_s, exposition_s
        self.t0 = time.perf_counter()
        self.prochain = time.perf_counter()

    def appliquer(self, exposition_s, dt_s, gain):
        self.dt, self.expo = dt_s, exposition_s

    def lire(self, premier=False):
        attente = self.prochain - time.perf_counter()
        if attente > 0:
            time.sleep(attente)
        self.prochain = max(self.prochain + self.dt, time.perf_counter() - self.dt)
        self.pos += self.rng.normal(0, 0.6, self.pos.shape)
        w, h = TAILLE
        yy, xx = np.mgrid[0:h:4, 0:w:4]            # image calculée à basse résolution puis agrandie
        img = np.full(yy.shape, 40.0)
        for x, y in self.pos:
            img += 170 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 5.0 ** 2))
        grand = np.kron(np.clip(img, 0, 255), np.ones((4, 4)))[:h, :w].astype(np.uint8)
        return grand, int((time.perf_counter() - self.t0) * 1e9), self.expo

    def fermer(self):
        pass


# ----------------------------------------------------------------------------- Enregistrement
class EnregistrementWorker(QObject):
    progression = pyqtSignal(int, int)
    termine = pyqtSignal(dict)
    erreur = pyqtSignal(str)

    def __init__(self, camera, p):
        super().__init__()
        self.camera, self.p = camera, p

    @pyqtSlot()
    def run(self):
        try:
            self.termine.emit(self._enregistrer())
        except Exception as exc:                 # affichée à l'utilisateur
            self.erreur.emit(f"{exc}\n\n{traceback.format_exc()[-1500:]}")

    def _enregistrer(self):
        p = self.p
        n = p["n_images"]
        images, instants, expositions = [], [], []
        for i in range(n):
            image, ts, expo = self.camera.lire(premier=(i == 0))
            images.append(image)
            instants.append(ts)
            expositions.append(expo)
            if i % max(1, n // 20) == 0:
                self.progression.emit(i + 1, n)
        self.progression.emit(n, n)
        intervalles = np.diff(np.array(instants)) / 1e9
        manquantes = int(np.sum(intervalles > 1.5 * p["dt_s"]))
        base = p["base"]
        dossier = Path(p["dossier"])
        chemin = dossier / f"{base}.tif"
        A.sauvegarder_film(images, chemin)
        valides = [e for e in expositions if e]
        infos = {
            "date": datetime.now().isoformat(timespec="seconds"), "commentaire": p["commentaire"],
            "fichier": chemin.name, "n_images": n, "taille_px": list(TAILLE),
            "dt_demande_s": p["dt_s"], "dt_reel_median_s": float(np.median(intervalles)),
            "dt_reel_ecart_type_s": float(np.std(intervalles)), "dt_reel_max_s": float(np.max(intervalles)),
            "images_manquantes_estimees": manquantes,
            "exposition_demandee_s": p["exposition_s"],
            "exposition_reelle_s": float(np.median(valides)) if valides else None,
            "gain": p["gain"], "pixel_um": p["pixel_um"], "pixel_calibre": p["pixel_calibre"],
            "objectif": p["objectif"], "profondeur_bits": 8, "camera": p["camera"],
            "instants_images_ns": [int(t) for t in instants],
        }
        (dossier / f"{base}.json").write_text(json.dumps(infos, indent=2, ensure_ascii=False), encoding="utf-8")
        return infos


# ----------------------------------------------------------------------------- Fenêtre
class CameraWindow(QMainWindow):
    def __init__(self, simulation=False):
        super().__init__()
        self.simulation = simulation
        self.camera = None
        self.thread = None
        self.worker = None
        self.fige = False                       # vrai pendant l'enregistrement : l'aperçu reste sur la dernière image
        self.derniere_image = None
        self.particles: list[Particle] = []
        self.fps: float | None = None            # cadence de rafraîchissement de l'aperçu (comme dans la version de Brian)
        self.dernier_instant: float | None = None
        self.n_tailles, self.taille_moy_um, self.somme_ecarts = 0, 0.0, 0.0
        self.setWindowTitle("PHS3910 | Acquisition" + ("  [SIMULATION : aucune caméra]" if simulation else ""))
        self.resize(1250, 800)
        self._construire()
        self.setStyleSheet(STYLE)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rafraichir)
        self._connecter_camera()

    # --- interface
    def _construire(self):
        centre = QWidget()
        self.setCentralWidget(centre)
        ligne = QHBoxLayout(centre)
        gauche = QVBoxLayout()
        ligne.addLayout(gauche, 0)

        boite = QGroupBox("Conditions d'acquisition")
        f = QFormLayout(boite)
        self.objectif = QComboBox()
        self.objectif.addItems(OBJECTIFS)
        self.objectif.setCurrentText(OBJECTIF_DEFAUT)
        self.exposition = QDoubleSpinBox(); self.exposition.setRange(0.05, 5000); self.exposition.setDecimals(2)
        self.exposition.setValue(18.0); self.exposition.setSuffix(" ms")
        self.dt = QDoubleSpinBox(); self.dt.setRange(8.3, 5000); self.dt.setDecimals(2)
        self.dt.setValue(20.0); self.dt.setSuffix(" ms")
        self.cadence = QLabel()
        self.duree = QDoubleSpinBox(); self.duree.setRange(0.1, 600); self.duree.setValue(5.0); self.duree.setSuffix(" s")
        self.gain = QDoubleSpinBox(); self.gain.setRange(1.0, 16.0); self.gain.setValue(1.0); self.gain.setDecimals(2)
        self.pixel = QDoubleSpinBox(); self.pixel.setRange(0.001, 100); self.pixel.setDecimals(4)
        self.pixel.setSuffix(" µm/pixel")
        self.pixel_calibre = QCheckBox("Valeur mesurée avec la règle (verrouillée)")
        self.resume = QLabel()
        self.resume.setWordWrap(True)
        f.addRow("Objectif :", self.objectif)
        f.addRow("Temps d'exposition :", self.exposition)
        f.addRow("Intervalle entre images (Δt) :", self.dt)
        f.addRow("Cadence :", self.cadence)
        f.addRow("Durée du film :", self.duree)
        f.addRow("Gain analogique :", self.gain)
        f.addRow("Échelle :", self.pixel)
        f.addRow(self.pixel_calibre)
        f.addRow(self.resume)
        gauche.addWidget(boite)

        sortie = QGroupBox("Enregistrement")
        g = QFormLayout(sortie)
        self.nom = QLineEdit("film")
        self.dossier = QLineEdit(str(Path(__file__).resolve().parent / "films_acquis"))
        parcourir = QPushButton("Parcourir…")
        parcourir.clicked.connect(self._choisir_dossier)
        rangee = QWidget(); r = QHBoxLayout(rangee); r.setContentsMargins(0, 0, 0, 0)
        r.addWidget(self.dossier); r.addWidget(parcourir)
        self.commentaire = QLineEdit()
        self.commentaire.setPlaceholderText("ex. particule bien centrée, échantillon 2")
        self.fichier = QLabel("")
        self.fichier.setWordWrap(True)
        self.fichier.setStyleSheet("color: #9fb0c6; font-size: 11px; font-weight: normal;")
        g.addRow("Nom du fichier :", self.nom)
        g.addRow(self.fichier)
        g.addRow("Dossier :", rangee)
        g.addRow("Commentaire :", self.commentaire)
        gauche.addWidget(sortie)

        apercu = QGroupBox("Aperçu")
        a = QVBoxLayout(apercu)
        self.centre = QCheckBox("Afficher le centre de l'image (placement)")
        self.detection = QCheckBox("Détecter la particule et estimer sa taille en direct (ralentit le Raspberry Pi)")
        self.detection.setToolTip("Détection de Brian : ajustement d'une gaussienne sur la tache la plus brillante. "
                                  "À éteindre pendant les essais où l'on veut la cadence maximale.")
        self.detection.toggled.connect(self._detection_change)
        self.raz = QPushButton("Remettre à zéro la taille moyenne")
        self.raz.clicked.connect(self._raz_tailles)
        self.raz.setVisible(False)
        a.addWidget(self.centre)
        a.addWidget(self.detection)
        a.addWidget(self.raz)
        gauche.addWidget(apercu)

        self.bouton = QPushButton("●  Lancer l'acquisition")
        self.bouton.setMinimumHeight(46)
        self.bouton.setStyleSheet("font-size: 16px;")
        self.bouton.clicked.connect(self.enregistrer)
        gauche.addWidget(self.bouton)
        self.barre = QProgressBar(); self.barre.setValue(0)
        gauche.addWidget(self.barre)
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setMinimumWidth(400)
        gauche.addWidget(self.etat)
        gauche.addStretch()

        droite = QVBoxLayout()
        ligne.addLayout(droite, 1)
        self.image = QLabel("Connexion de la caméra…")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(640, 480)
        self.image.setStyleSheet("background: #05080b; color: #aab; border: 1px solid #40506a;")
        droite.addWidget(self.image, 1)
        self.info = QLabel("")
        droite.addWidget(self.info)

        for w in (self.exposition, self.dt, self.gain, self.duree, self.pixel):
            w.valueChanged.connect(self._reglages_modifies)
        self.objectif.currentTextChanged.connect(self._objectif_change)
        self.pixel_calibre.toggled.connect(self._objectif_change)
        self.nom.textChanged.connect(self._maj_fichier)
        self.dossier.textChanged.connect(self._maj_fichier)
        self._objectif_change()

    def _choisir_dossier(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier des films", self.dossier.text())
        if d:
            self.dossier.setText(d)

    def _nom_nettoye(self):
        return "".join(c if c.isalnum() or c == "-" else "-" for c in self.nom.text().strip()) or "film"

    def _maj_fichier(self, *_):
        """Montre le nom exact du fichier qui sera créé (le numéro évite d'écraser un film existant)."""
        dossier = Path(self.dossier.text().strip() or ".")
        nom = self._nom_nettoye()
        numero = A.prochain_numero(dossier, nom) if dossier.is_dir() else 1
        base = A.nom_de_base(nom, numero, self.dt.value() / 1000.0, self.exposition.value() / 1000.0,
                             round(self.pixel.value(), 4))
        self.fichier.setText(f"Fichier créé : {base}.tif")

    def _objectif_change(self, *_):
        if not self.pixel_calibre.isChecked():
            self.pixel.blockSignals(True)
            self.pixel.setValue(round(PIXEL_CAMERA_UM * FACTEUR_MODE / grossissement(self.objectif.currentText()), 4))
            self.pixel.blockSignals(False)
        self._reglages_modifies()

    def _reglages_modifies(self, *_):
        dt, expo = self.dt.value(), self.exposition.value()
        self.cadence.setText(f"{1000.0 / dt:.2f} images/s")
        n = max(2, round(self.duree.value() * 1000.0 / dt))
        mo = n * TAILLE[0] * TAILLE[1] / 1e6
        texte = f"{n} images, environ {mo:.0f} Mo."
        invalide = expo > dt
        if invalide:
            texte += "  ⚠ L'exposition doit être inférieure ou égale à Δt."
        if not self.pixel_calibre.isChecked():
            texte += "  Échelle calculée (non vérifiée) : à mesurer avec la règle micrométrique."
        self.resume.setText(texte)
        self.resume.setStyleSheet("color: #ff8a80;" if invalide else "")
        self.bouton.setEnabled(not invalide and self.thread is None and self.camera is not None)
        self._maj_fichier()
        if self.camera is not None and not invalide and self.thread is None:
            try:
                self.camera.appliquer(expo / 1000.0, dt / 1000.0, self.gain.value())
            except Exception as exc:
                self.etat.setText(f"Réglage refusé par la caméra : {exc}")

    # --- caméra
    def _connecter_camera(self):
        classe = CameraSimulee if self.simulation else CameraPi
        try:
            self.camera = classe(self.exposition.value() / 1000.0, self.dt.value() / 1000.0, self.gain.value())
        except Exception as exc:
            self.camera = None
            self.image.setText("Caméra introuvable.\n\n" + str(exc))
            self.etat.setText("Vérifiez la nappe et lancez `rpicam-hello --list-cameras`. "
                              "Fermez tout autre programme qui utilise la caméra.")
            return
        self.etat.setText(f"Caméra prête : {self.camera.nom}.")
        self.bouton.setEnabled(True)
        self._reglages_modifies()
        self.timer.start(RAFRAICHISSEMENT_MS)

    def rafraichir(self):
        if self.camera is None or self.fige:
            return
        try:
            image, _, _ = self.camera.lire()
        except Exception as exc:
            self.timer.stop()
            self.etat.setText(f"Erreur de lecture de la caméra : {exc}")
            QMessageBox.critical(self, "Erreur caméra", f"Impossible de capturer une image : {exc}")
            return
        maintenant = time.perf_counter()
        if self.dernier_instant is not None and maintenant > self.dernier_instant:
            self.fps = 1.0 / (maintenant - self.dernier_instant)
        self.dernier_instant = maintenant
        self.derniere_image = image
        self.afficher(image)

    def afficher(self, image, enregistrement=False):
        h, w = image.shape
        qimage = QImage(image.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        pixmap = QPixmap.fromImage(qimage).scaled(self.image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.FastTransformation)
        if self.detection.isChecked() and not enregistrement:
            self._detecter(image)
        self._surimpression(pixmap, w, enregistrement)
        self.image.setPixmap(pixmap)
        sature = float(np.mean(image >= 255)) * 100
        self.info.setText(f"Valeur maximale : {int(image.max())}/255 | pixels saturés : {sature:.3f} %"
                          + ("   ⚠ SATURATION : diminuez l'exposition ou le gain" if sature > 0.01 else ""))
        self.info.setStyleSheet("color: #ff8a80;" if sature > 0.01 else "")

    # --- détection en direct (option)
    def _detection_change(self, actif):
        self.raz.setVisible(actif)
        self.particles.clear()

    def _raz_tailles(self):
        self.n_tailles, self.taille_moy_um, self.somme_ecarts = 0, 0.0, 0.0

    def _detecter(self, image):
        try:
            update_particles(self.particles, image)
        except ValueError:
            self.particles.clear()
        for part in self.particles:
            taille_um = part["size"] * self.pixel.value()
            self.n_tailles += 1
            delta = taille_um - self.taille_moy_um
            self.taille_moy_um += delta / self.n_tailles
            self.somme_ecarts += delta * (taille_um - self.taille_moy_um)

    def _texte_taille(self):
        if not self.n_tailles:
            return None
        if self.n_tailles > 1:
            incertitude = np.sqrt(self.somme_ecarts / (self.n_tailles - 1) / self.n_tailles)
            return f"Taille moyenne : {self.taille_moy_um:.2f} ± {incertitude:.2f} µm"
        return f"Taille moyenne : {self.taille_moy_um:.2f} µm (n=1)"

    def _surimpression(self, pixmap, largeur_image, enregistrement):
        """Échelle et conditions d'acquisition sur l'image affichée."""
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        police = p.font()
        police.setPixelSize(max(11, pixmap.width() // 55))
        p.setFont(police)
        fm = p.fontMetrics()
        marge = max(10, pixmap.width() // 50)
        echelle_aff = pixmap.width() / largeur_image
        if self.detection.isChecked() and not enregistrement:
            p.setPen(QPen(QColor(255, 60, 60), 2))
            for part in self.particles:
                x, y = part["pos"]
                cote = max(4, round(part["size"] * echelle_aff))
                p.drawRect(QRect(round(x * echelle_aff) - cote // 2, round(y * echelle_aff) - cote // 2, cote, cote))
        lignes = [(f"Objectif : {self.objectif.currentText()}", "white"),
                  (f"Exposition : {self.exposition.value():g} ms", "white"),
                  (f"Cadence : {1000.0 / self.dt.value():.1f} images/s", "white"),
                  ("Profondeur de bit : 8 bits", "white")]
        if self.fps is not None and not enregistrement:
            lignes.append((f"FPS de l'aperçu : {self.fps:.1f}", "white"))
        taille = self._texte_taille() if (self.detection.isChecked() and not enregistrement) else None
        if taille:
            lignes.insert(0, (taille, "#ffa500"))
        haut = marge
        for texte, couleur in lignes:
            p.fillRect(marge - 4, haut, fm.horizontalAdvance(texte) + 8, fm.height() + 2, QColor(0, 0, 0, 150))
            p.setPen(QColor(couleur))
            p.drawText(marge, haut + fm.ascent() + 1, texte)
            haut += fm.height() + 4
        pixel_um = self.pixel.value()
        longueur = longueur_barre_um(largeur_image, pixel_um)
        barre = int(round(longueur / pixel_um * echelle_aff))
        y = pixmap.height() - marge - fm.height()
        x2 = pixmap.width() - marge
        etiquette = (f"{longueur:g} µm   ({pixel_um:.4f} µm/pixel"
                     + ("" if self.pixel_calibre.isChecked() else ", non vérifié") + ")")
        largeur_boite = max(barre, fm.horizontalAdvance(etiquette))
        p.fillRect(x2 - largeur_boite - 6, y - 6, largeur_boite + 12, fm.height() + 20, QColor(0, 0, 0, 150))
        p.setPen(QPen(QColor("white"), 3))
        p.drawLine(x2 - barre, y, x2, y)
        p.setPen(QColor("white"))
        p.drawText(x2 - fm.horizontalAdvance(etiquette), y + fm.height() + 2, etiquette)
        if self.centre.isChecked():
            p.setPen(QPen(QColor(255, 200, 0), 1))
            cx, cy = pixmap.width() // 2, pixmap.height() // 2
            p.drawLine(cx - 15, cy, cx + 15, cy)
            p.drawLine(cx, cy - 15, cx, cy + 15)
        if enregistrement:                      # bandeau : l'image est figée, l'acquisition est en cours
            texte = "ACQUISITION EN COURS : aperçu figé"
            police.setBold(True)
            police.setPixelSize(max(13, pixmap.width() // 38))
            p.setFont(police)
            fm = p.fontMetrics()
            largeur_bandeau = fm.horizontalAdvance(texte) + 30
            x = (pixmap.width() - largeur_bandeau) // 2
            p.fillRect(x, pixmap.height() // 2 - fm.height(), largeur_bandeau, 2 * fm.height(), QColor(200, 40, 40, 215))
            p.setPen(QColor("white"))
            p.drawText(x, pixmap.height() // 2 - fm.height(), largeur_bandeau, 2 * fm.height(),
                       Qt.AlignmentFlag.AlignCenter, texte)
        p.end()

    # --- enregistrement
    def enregistrer(self):
        if self.thread is not None or self.camera is None:
            return
        dossier = Path(self.dossier.text().strip())
        nom = self._nom_nettoye()
        try:
            dossier.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Dossier", f"Impossible d'utiliser ce dossier : {exc}")
            return
        n = max(2, round(self.duree.value() * 1000.0 / self.dt.value()))
        besoin = n * TAILLE[0] * TAILLE[1] * 1.3
        libre = shutil.disk_usage(dossier).free
        if besoin > libre:
            QMessageBox.warning(self, "Espace disque",
                                f"Espace insuffisant : il faut environ {besoin / 1e6:.0f} Mo, "
                                f"il reste {libre / 1e6:.0f} Mo. Libérez de la place (videz aussi la corbeille).")
            return
        numero = A.prochain_numero(dossier, nom)
        pixel_um = round(self.pixel.value(), 4)
        params = dict(n_images=n, dt_s=self.dt.value() / 1000.0, exposition_s=self.exposition.value() / 1000.0,
                      gain=self.gain.value(), pixel_um=pixel_um, pixel_calibre=self.pixel_calibre.isChecked(),
                      objectif=self.objectif.currentText(), dossier=str(dossier),
                      base=A.nom_de_base(nom, numero, self.dt.value() / 1000.0, self.exposition.value() / 1000.0, pixel_um),
                      commentaire=self.commentaire.text().strip(), camera=self.camera.nom)
        # Aperçu figé : on redessine la dernière image avec le bandeau, puis on arrête toute lecture parallèle
        self.fige = True
        self.timer.stop()
        if self.derniere_image is not None:
            self.afficher(self.derniere_image, enregistrement=True)
        else:
            self.image.setText("Acquisition en cours : aperçu figé")
        self.bouton.setEnabled(False)
        self.barre.setValue(0)
        self.etat.setText(f"Acquisition de {n} images (environ {n * self.dt.value() / 1000.0:.1f} s) : "
                          "l'aperçu est figé pour garder toute la puissance du Raspberry Pi.")
        self.thread = QThread(self)
        self.worker = EnregistrementWorker(self.camera, params)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progression.connect(lambda i, n_: self.barre.setValue(int(100 * i / n_)))
        self.worker.termine.connect(self._termine)
        self.worker.erreur.connect(self._erreur)
        self.worker.termine.connect(self.thread.quit)
        self.worker.erreur.connect(self.thread.quit)
        self.thread.finished.connect(self._nettoyer)
        self.thread.start()

    @pyqtSlot(dict)
    def _termine(self, infos):
        texte = (f"Film enregistré : {infos['fichier']}\n"
                 f"Δt réel : {infos['dt_reel_median_s'] * 1000:.1f} ms (demandé {infos['dt_demande_s'] * 1000:.1f} ms), "
                 f"images manquantes : {infos['images_manquantes_estimees']}")
        if infos["images_manquantes_estimees"]:
            texte += "\n⚠ Des images ont été perdues : augmentez Δt ou fermez les autres programmes."
        self.etat.setText(texte + "\nL'aperçu en direct reprend.")
        self.barre.setValue(100)

    @pyqtSlot(str)
    def _erreur(self, message):
        self.etat.setText("Échec de l'enregistrement.")
        QMessageBox.warning(self, "Erreur d'enregistrement", message)

    @pyqtSlot()
    def _nettoyer(self):
        self.worker.deleteLater()
        self.thread.deleteLater()
        self.thread = None
        self.worker = None
        self.fige = False                        # l'aperçu reprend
        self._reglages_modifies()
        self.timer.start(RAFRAICHISSEMENT_MS)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(5000)
        if self.camera is not None:
            self.camera.fermer()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description="Interface d'acquisition du microscope (Raspberry Pi).")
    parser.add_argument("--simulation", action="store_true", help="essai sans caméra (images fictives)")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    fenetre = CameraWindow(simulation=args.simulation)
    fenetre.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
