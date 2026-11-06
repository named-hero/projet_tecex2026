import sys
import json
import importlib.util
import traceback
import csv
import re
from pathlib import Path

import cv2
import tifffile
import numpy as np
from PySide6.QtCore import Qt, QTimer, QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSlider, QSpinBox, QDoubleSpinBox, QTabWidget,
    QVBoxLayout, QWidget, QCheckBox, QScrollArea, QProgressBar,
)


class AnalyseWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, video_path, pixel_um, dt_s, config):
        super().__init__()
        self.video_path = video_path
        self.pixel_um = pixel_um
        self.dt_s = dt_s
        self.config = config

    @Slot()
    def run(self):
        try:
            from analyse_equipe import analyser_video
            output = analyser_video(self.video_path, self.pixel_um, self.dt_s, self.config)
            if not isinstance(output, dict) or not isinstance(output.get("results"), dict):
                raise ValueError("analyser_video doit renvoyer {'results': {...}, 'trajectories': {...}}")
            self.finished.emit(output)
        except Exception:
            self.failed.emit(traceback.format_exc())


class MicroscopeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PHS3910 | Suivi de particules fluorescentes")
        self.resize(1250, 780)
        self.cap = None
        self.tiff_file = None
        self.tiff_pages = None
        self.tiff_stack = None
        self.tiff_series = None
        self.frame = None
        self.frame_index = 0
        self.frame_count = 0
        self.fps = 30.0
        self.playing = False
        self.centers = []
        self.video_path = None
        self.video_metadata = {}
        # Points d'intégration : aucune trajectoire ni valeur scientifique inventée.
        self.trajectories = {}   # {id_particule: [(index_0_base, x_px, y_px), ...]}
        self.analysis_results = None
        self.analysis_thread = None
        self.analysis_worker = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.build_acquisition_tab()
        self.build_analysis_tab()
        self.build_results_tab()
        self.build_settings_tab()
        self.build_acquisition_controls()
        self.refresh_backend_status()
        self.statusBar().showMessage("Prêt — ouvrez une vidéo pour commencer")
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #171c24; color: #eef3fa; font-size: 13px; }
            QGroupBox { border: 1px solid #3b4656; border-radius: 9px;
                        margin-top: 12px; padding: 12px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QPushButton { background: #2865b5; border: 0; border-radius: 6px;
                          padding: 9px 12px; font-weight: bold; }
            QPushButton:hover { background: #367bda; }
            QPushButton:disabled { background: #3c4653; color: #a6adba; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #26303d;
                border: 1px solid #485365; border-radius: 5px; padding: 6px; }
            QTabWidget::pane { border: 1px solid #394657; }
            QTabBar::tab { background: #26303d; padding: 12px 22px; }
            QTabBar::tab:selected { background: #2865b5; }
        """)

    def build_acquisition_tab(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        left = QVBoxLayout()
        controls = QGroupBox("Lecture et acquisition")
        c = QVBoxLayout(controls)
        self.open_btn = QPushButton("Ouvrir une vidéo")
        self.open_btn.clicked.connect(self.open_video)
        c.addWidget(self.open_btn)
        self.file_label = QLabel("Aucune vidéo chargée")
        self.file_label.setWordWrap(True)
        c.addWidget(self.file_label)
        buttons = QHBoxLayout()
        self.play_btn = QPushButton("▶ Lecture")
        self.pause_btn = QPushButton("⏸ Pause")
        self.stop_btn = QPushButton("■ Arrêt")
        self.play_btn.clicked.connect(self.play_video)
        self.pause_btn.clicked.connect(self.pause_video)
        self.stop_btn.clicked.connect(self.stop_video)
        for b in (self.play_btn, self.pause_btn, self.stop_btn):
            buttons.addWidget(b)
        c.addLayout(buttons)
        self.save_btn = QPushButton("Enregistrer l'image affichée")
        self.save_btn.clicked.connect(self.save_frame)
        c.addWidget(self.save_btn)
        self.info_label = QLabel("Image : —    |    FPS : —")
        c.addWidget(self.info_label)
        left.addWidget(controls)

        metadata_box = QGroupBox("Informations sur la vidéo chargée")
        metadata_layout = QFormLayout(metadata_box)
        self.metadata_labels = {}
        for key, title in (
            ("frames", "Images :"),
            ("duration", "Durée :"),
            ("dt", "Intervalle Δt :"),
            ("acquisition_fps", "Cadence acquisition :"),
            ("exposure", "Exposition vidéo :"),
            ("scale", "Échelle déclarée :"),
            ("objective", "Objectif sélectionné :"),
        ):
            value_label = QLabel("—")
            value_label.setWordWrap(True)
            self.metadata_labels[key] = value_label
            metadata_layout.addRow(title, value_label)
        self.metadata_note = QLabel("Métadonnées lues dans le nom du fichier ; à confirmer avec l'équipe.")
        self.metadata_note.setWordWrap(True)
        metadata_layout.addRow(self.metadata_note)
        left.addWidget(metadata_box)

        camera = QGroupBox("Caméra réelle (connexion ultérieure)")
        cam_layout = QFormLayout(camera)
        self.exposure = QDoubleSpinBox()
        self.exposure.setRange(0.1, 10000)
        self.exposure.setValue(50)
        self.exposure.setSuffix(" ms")
        self.gain = QDoubleSpinBox()
        self.gain.setRange(1, 100)
        self.gain.setValue(1)
        cam_layout.addRow("Exposition :", self.exposure)
        cam_layout.addRow("Gain :", self.gain)
        note = QLabel("Réglages indicatifs : non reliés à la caméra pour le moment.")
        note.setWordWrap(True)
        cam_layout.addRow(note)
        self.camera_box = camera  # Déplacé dans Paramètres : acquisition réelle non connectée.
        self.analyze_btn = QPushButton("Analyser la vidéo — en attente du code de suivi")
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setToolTip("À connecter à la fonction d'analyse de l'équipe.")
        self.analyze_btn.setText("Analyser la vidéo (code équipe requis)")
        self.analyze_btn.clicked.connect(self.start_analysis)
        left.addWidget(self.analyze_btn)
        self.analysis_progress = QProgressBar()
        self.analysis_progress.setRange(0, 100)
        self.analysis_progress.setValue(0)
        left.addWidget(self.analysis_progress)
        self.analysis_status = QLabel("Analyse non disponible : module analyse_equipe.py absent")
        self.analysis_status.setWordWrap(True)
        left.addWidget(self.analysis_status)
        left.addStretch()
        left_container = QWidget()
        left_container.setLayout(left)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_container)
        left_scroll.setMinimumWidth(345)
        layout.addWidget(left_scroll, 2)

        right = QVBoxLayout()
        self.image_label = QLabel("Ouvrez une vidéo pour afficher les particules")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(520, 390)
        self.image_label.setStyleSheet("background: #05080b; border: 1px solid #40506a;")
        right.addWidget(self.image_label, 1)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.seek_frame)
        right.addWidget(self.slider)
        self.scale_label = QLabel("Échelle : non calibrée — renseigner les µm/pixel dans Paramètres")
        right.addWidget(self.scale_label)
        layout.addLayout(right, 3)
        self.tabs.addTab(page, "Acquisition")

    def build_analysis_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Détection des particules fluorescentes")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)
        description = QLabel(
            "Détection exploratoire par seuil d'intensité. Les points repérés sont des "
            "taches lumineuses candidates : ils ne constituent pas encore des trajectoires "
            "ni une localisation sous-pixel validée."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        controls = QGroupBox("Réglages de détection")
        form = QFormLayout(controls)
        self.detect_enabled = QCheckBox("Afficher les centres détectés sur l'image")
        self.detect_enabled.setChecked(True)
        self.detect_enabled.toggled.connect(self.render_frame)
        form.addRow(self.detect_enabled)
        self.threshold = QSpinBox()
        self.threshold.setRange(1, 255)
        self.threshold.setValue(90)
        self.threshold.valueChanged.connect(self.update_detection)
        form.addRow("Seuil (sur 255) :", self.threshold)
        self.min_area = QSpinBox()
        self.min_area.setRange(1, 100000)
        self.min_area.setValue(4)
        self.min_area.valueChanged.connect(self.update_detection)
        form.addRow("Surface minimale (pixels²) :", self.min_area)
        self.max_area = QSpinBox()
        self.max_area.setRange(1, 1000000)
        self.max_area.setValue(1000)
        self.max_area.valueChanged.connect(self.update_detection)
        form.addRow("Surface maximale (pixels²) :", self.max_area)
        layout.addWidget(controls)
        tracking_box = QGroupBox("Trajectoires des particules")
        tracking_layout = QVBoxLayout(tracking_box)
        self.show_tracks = QCheckBox("Afficher les trajectoires sur la vidéo")
        self.show_tracks.setChecked(True)
        self.show_tracks.toggled.connect(self.render_frame)
        tracking_layout.addWidget(self.show_tracks)
        self.tracking_info = QLabel(
            "En attente du code de suivi : les cercles jaunes indiquent seulement "
            "les positions détectées sur une image."
        )
        self.tracking_info.setWordWrap(True)
        tracking_layout.addWidget(self.tracking_info)
        layout.addWidget(tracking_box)
        self.detect_info = QLabel("Ouvrez une vidéo pour commencer la détection.")
        layout.addWidget(self.detect_info)
        self.export_btn = QPushButton("Exporter les positions de cette image (CSV)")
        self.export_btn.clicked.connect(self.export_positions)
        layout.addWidget(self.export_btn)
        note = QLabel(
            "Pour tester : ouvrez une vidéo dans Acquisition, puis revenez ici "
            "pour ajuster le seuil. Les cercles seront visibles sur l'image de l'onglet Acquisition. "
            "Les trajectoires apparaîtront après intégration du code de suivi de l'équipe."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.tabs.addTab(page, "Traitement et suivi")

    def update_detection(self):
        if self.frame is None:
            return
        gray = cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, self.threshold.value(), 255, cv2.THRESH_BINARY)
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        self.centers = []
        for i in range(1, count):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if self.min_area.value() <= area <= self.max_area.value():
                x, y = centroids[i]
                self.centers.append((float(x), float(y), area))
        self.detect_info.setText(
            f"Image {self.frame_index} : {len(self.centers)} tache(s) candidate(s) détectée(s). "
            "Ajustez le seuil pour limiter le bruit et les fausses détections."
        )
        self.render_frame()

    def export_positions(self):
        if self.frame is None:
            QMessageBox.information(self, "Export CSV", "Ouvrez d'abord une vidéo.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les centres détectés", "positions_image.csv", "CSV (*.csv)"
        )
        if not path:
            return
        scale = self.pixel_scale.value() if self.scale_calibrated.isChecked() else None
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["image", "x_px", "y_px", "surface_px2", "x_um", "y_um"])
                for x, y, area in self.centers:
                    writer.writerow([
                        self.frame_index, round(x, 3), round(y, 3), area,
                        round(x * scale, 3) if scale else "",
                        round(y * scale, 3) if scale else "",
                    ])
        except OSError as exc:
            QMessageBox.warning(self, "Erreur", str(exc))
            return
        self.statusBar().showMessage("Positions exportées : " + path)

    def build_results_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Résultats scientifiques — analyse de la vidéo")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)
        note = QLabel(
            "Les résultats seront affichés uniquement après calcul par les algorithmes "
            "de l'équipe. Aucune valeur de démonstration n'est présentée comme une mesure."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.result_state = QLabel("État : en attente d'analyse")
        layout.addWidget(self.result_state)

        summary = QGroupBox("Grandeurs calculées")
        form = QFormLayout(summary)
        self.result_labels = {}
        for key, label in (
            ("particles", "Particules suivies :"),
            ("D", "Coefficient de diffusion D (µm²/s) :"),
            ("radius", "Rayon hydrodynamique moyen (nm) :"),
            ("uncertainty", "Incertitude sur le rayon (nm) :"),
        ):
            val = QLabel("En attente d'analyse")
            self.result_labels[key] = val
            form.addRow(label, val)
        layout.addWidget(summary)

        msd_box = QGroupBox("Déplacement quadratique moyen (MSD)")
        msd_layout = QVBoxLayout(msd_box)
        self.msd_plot = QLabel("Graphique MSD : en attente des données de suivi et de l'ajustement")
        self.msd_plot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msd_plot.setMinimumHeight(210)
        self.msd_plot.setStyleSheet("background: #0b1119; border: 1px solid #394657;")
        msd_layout.addWidget(self.msd_plot)
        self.msd_note = QLabel("Abscisse : décalage temporel Δt (s) | Ordonnée : MSD (µm²)")
        msd_layout.addWidget(self.msd_note)
        layout.addWidget(msd_box)

        self.export_results_btn = QPushButton("Exporter les résultats (CSV)")
        self.export_results_btn.setEnabled(False)
        self.export_results_btn.clicked.connect(self.export_results)
        layout.addWidget(self.export_results_btn)
        layout.addStretch()
        self.tabs.addTab(page, "Résultats")

    def set_trajectories(self, trajectories):
        """Point d'intégration du suivi : {id: [(image_0_base, x_px, y_px), ...]}.

        Appeler cette méthode depuis le code de l'équipe après traitement de la vidéo.
        Les coordonnées doivent être celles des pixels de l'image source.
        """
        if not isinstance(trajectories, dict):
            raise ValueError("Les trajectoires doivent être un dictionnaire {id: points}.")
        validated = {}
        for particle_id, points in trajectories.items():
            validated[str(particle_id)] = [
                (int(t), float(x), float(y)) for t, x, y in points
            ]
        self.trajectories = validated
        self.tracking_info.setText(
            f"{len(validated)} trajectoire(s) reçue(s) du code de suivi. "
            "Les tracés sont superposés dans Acquisition."
            if validated else "Aucune trajectoire reçue du code de suivi."
        )
        self.render_frame()

    def set_analysis_results(self, results):
        """Point d'intégration du calcul scientifique.

        results = {"particles": int, "D_um2_s": float, "radius_nm": float,
                   "uncertainty_nm": float, "lag_s": [...], "msd_um2": [...],
                   "fit_msd_um2": [...] (facultatif)}
        Les unités sont obligatoires ; ne pas transmettre de valeurs fictives.
        """
        if not isinstance(results, dict):
            raise ValueError("Les résultats doivent être un dictionnaire.")
        self.analysis_results = dict(results)
        mapping = {
            "particles": "particles", "D": "D_um2_s",
            "radius": "radius_nm", "uncertainty": "uncertainty_nm",
        }
        for label_key, data_key in mapping.items():
            value = results.get(data_key)
            self.result_labels[label_key].setText(
                f"{value:.5g}" if isinstance(value, (int, float)) else "Non calculé"
            )
        self.result_state.setText("État : résultats transmis par le code d'analyse")
        self.export_results_btn.setEnabled(True)
        self.update_msd_plot()

    def update_msd_plot(self):
        """Dessine les données MSD reçues, sans calculer de modèle physique."""
        data = self.analysis_results or {}
        try:
            lag = np.asarray(data.get("lag_s", []), dtype=float)
            msd = np.asarray(data.get("msd_um2", []), dtype=float)
            if lag.ndim != 1 or msd.ndim != 1 or len(lag) < 2 or len(lag) != len(msd):
                self.msd_plot.setText("MSD non fourni par l'algorithme d'analyse")
                return
            valid = np.isfinite(lag) & np.isfinite(msd)
            lag, msd = lag[valid], msd[valid]
            if len(lag) < 2:
                self.msd_plot.setText("Données MSD insuffisantes")
                return
            fit = np.asarray(data.get("fit_msd_um2", []), dtype=float)
            if len(fit) != len(valid):
                fit = np.array([])
            else:
                fit = fit[valid]
            width, height = 740, 280
            pix = QPixmap(width, height)
            pix.fill(QColor("#0b1119"))
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            x0, y0, x1, y1 = 64, 22, width - 25, height - 42
            all_y = np.concatenate((msd, fit[np.isfinite(fit)])) if len(fit) else msd
            xmin, xmax = float(min(lag)), float(max(lag))
            ymin, ymax = float(min(0, min(all_y))), float(max(all_y))
            if xmax <= xmin: xmax = xmin + 1
            if ymax <= ymin: ymax = ymin + 1
            def xy(x, y):
                return (round(x0 + (x - xmin) / (xmax - xmin) * (x1 - x0)),
                        round(y1 - (y - ymin) / (ymax - ymin) * (y1 - y0)))
            painter.setPen(QPen(QColor("#b9c7d8"), 1))
            painter.drawLine(x0, y0, x0, y1)
            painter.drawLine(x0, y1, x1, y1)
            painter.drawText(x0, height - 12, f"Δt : {xmin:.3g} à {xmax:.3g} s")
            painter.drawText(x0 + 5, y0 + 13, f"MSD : {ymin:.3g} à {ymax:.3g} µm²")
            painter.setPen(QPen(QColor("#55bde9"), 2))
            for i in range(len(lag)):
                px, py = xy(lag[i], msd[i])
                painter.drawEllipse(px - 3, py - 3, 6, 6)
            if len(fit) == len(lag) and np.all(np.isfinite(fit)):
                painter.setPen(QPen(QColor("#f3b35b"), 2))
                order = np.argsort(lag)
                for i, j in zip(order[:-1], order[1:]):
                    painter.drawLine(*xy(lag[i], fit[i]), *xy(lag[j], fit[j]))
            painter.end()
            self.msd_plot.setPixmap(pix)
        except (TypeError, ValueError, OverflowError) as exc:
            self.msd_plot.setText(f"Impossible d'afficher le MSD : {exc}")

    def export_results(self):
        if not self.analysis_results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les résultats", "resultats_analyse.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["parametre", "valeur", "unite"])
                for key, unit in (("particles", "nombre"), ("D_um2_s", "µm²/s"),
                                  ("radius_nm", "nm"), ("uncertainty_nm", "nm")):
                    writer.writerow([key, self.analysis_results.get(key, ""), unit])
                writer.writerow([])
                writer.writerow(["lag_s", "msd_um2", "fit_msd_um2"])
                lag = self.analysis_results.get("lag_s", [])
                msd = self.analysis_results.get("msd_um2", [])
                fit = self.analysis_results.get("fit_msd_um2", [])
                for i, (t, y) in enumerate(zip(lag, msd)):
                    writer.writerow([t, y, fit[i] if i < len(fit) else ""])
            self.statusBar().showMessage("Résultats exportés : " + path)
        except OSError as exc:
            QMessageBox.warning(self, "Erreur d'exportation", str(exc))

    def build_settings_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        box = QGroupBox("Calibration optique")
        form = QFormLayout(box)
        self.objective = QComboBox()
        self.objective.addItems([
            "4X — NA 0,10", "4X — NA 0,13",
            "10X — NA 0,25", "10X — NA 0,30",
            "20X — NA 0,40", "20X — NA 0,45", "20X — NA 0,50",
            "40X — NA 0,65", "40X — NA 0,70", "40X — NA 0,75",
            "60X — NA 0,85",
        ])
        self.pixel_scale = QDoubleSpinBox()
        self.pixel_scale.setRange(0.0001, 1000)
        self.pixel_scale.setDecimals(4)
        self.pixel_scale.setValue(0.5)
        self.pixel_scale.setSuffix(" µm/pixel")
        form.addRow("Objectif :", self.objective)
        self.scale_calibrated = QCheckBox("Calibration vérifiée pour cette vidéo")
        self.scale_calibrated.setChecked(False)
        self.scale_calibrated.toggled.connect(self.render_frame)
        self.pixel_scale.valueChanged.connect(self.render_frame)
        self.objective.currentIndexChanged.connect(self.render_frame)
        self.objective.currentIndexChanged.connect(self.update_video_information)
        form.addRow("Échelle mesurée :", self.pixel_scale)
        form.addRow(self.scale_calibrated)
        note = QLabel("La valeur initiale 0,5 µm/pixel est illustrative. "
                      "Calibrer l'échelle pour chaque configuration réelle.")
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(box)
        layout.addWidget(self.camera_box)
        layout.addStretch()
        self.tabs.addTab(page, "Paramètres")

    @staticmethod
    def parse_video_metadata(filename):
        """Lit les paramètres déclarés dans le nom ; n'invente pas les données absentes."""
        data = {}
        patterns = {
            "dt": r"(?:^|_)dt_([0-9]+(?:[.,][0-9]+)?)s(?:_|\.)",
            "exposure": r"(?:^|_)exp_([0-9]+(?:[.,][0-9]+)?)s(?:_|\.)",
            "scale": r"(?:^|_)PixelSize_([0-9]+(?:[.,][0-9]+)?)um(?:_|\.)",
            "duration": r"(?:^|[-_])([0-9]+(?:[.,][0-9]+)?)s_(?:[0-9]+)_dt_",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, filename, flags=re.IGNORECASE)
            if match:
                value = float(match.group(1).replace(",", "."))
                if value > 0:
                    data[key] = value
        return data

    def update_video_information(self, *_args):
        if not self.video_path:
            return
        data = self.video_metadata
        dt = data.get("dt")
        exposure = data.get("exposure")
        scale = data.get("scale")
        duration = data.get("duration")
        # Le nombre d'images et Δt donnent une durée de N*Δt (convention de séquence).
        if duration is None and dt is not None:
            duration = self.frame_count * dt
        values = {
            "frames": str(self.frame_count),
            "duration": f"≈ {duration:.3f} s" if duration is not None else "Non renseignée",
            "dt": f"{dt:.4f} s" if dt is not None else "Non renseigné",
            "acquisition_fps": f"{1/dt:.1f} images/s (déduite)" if dt else "Inconnue",
            "exposure": f"{1000*exposure:.1f} ms" if exposure is not None else "Non renseignée",
            "scale": f"{scale:.4f} µm/pixel" if scale is not None else "Non renseignée",
            "objective": self.objective.currentText() + " (sélection manuelle)",
        }
        for key, value in values.items():
            self.metadata_labels[key].setText(value)

    def open_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir une vidéo", "",
            "Vidéos et TIFF (*.mp4 *.avi *.mov *.mkv *.tif *.tiff);;Tous les fichiers (*)"
        )
        if not path:
            return
        self.pause_video()
        self.release_source()
        self.frame = None
        self.frame_index = 0
        self.frame_count = 0
        self.video_path = None
        self.tiff_series = None
        self.tiff_pages = None
        self.trajectories = {}
        self.analysis_results = None
        self.tracking_info.setText("En attente du code de suivi des particules.")
        self.result_state.setText("État : en attente d'analyse")
        for label in self.result_labels.values():
            label.setText("En attente d'analyse")
        self.msd_plot.clear()
        self.msd_plot.setText("Graphique MSD : en attente des données")
        self.export_results_btn.setEnabled(False)
        try:
            if path.lower().endswith((".tif", ".tiff")):
                self.tiff_file = tifffile.TiffFile(path)
                series = self.tiff_file.series[0]
                self.tiff_series = series
                shape = series.shape
                axes = series.axes
                # TIFF multipage classique : une page par image.
                # Certains TIFF stockent toute la séquence dans une seule page.
                if len(self.tiff_file.pages) > 1 and len(shape) >= 3:
                    self.tiff_pages = self.tiff_file.pages
                    self.frame_count = len(self.tiff_pages)
                elif len(shape) >= 3 and axes[0] not in "YXS":
                    self.tiff_stack = series.asarray()
                    self.frame_count = self.tiff_stack.shape[0]
                else:
                    self.tiff_pages = self.tiff_file.pages
                    self.frame_count = len(self.tiff_pages)
                self.fps = 10.0  # Vitesse d'affichage, pas cadence expérimentale.
            else:
                self.cap = cv2.VideoCapture(path)
                if not self.cap.isOpened():
                    raise ValueError("Impossible d'ouvrir cette vidéo.")
                self.frame_count = max(0, int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)))
                detected_fps = self.cap.get(cv2.CAP_PROP_FPS)
                self.fps = detected_fps if np.isfinite(detected_fps) and detected_fps > 0 else 30.0
            if self.frame_count < 1:
                raise ValueError("Aucune image trouvée dans le fichier.")
            self.video_path = path
            self.video_metadata = self.parse_video_metadata(Path(path).name)
            if "scale" in self.video_metadata:
                # Valeur déclarée dans le nom, pas calibration indépendante.
                self.pixel_scale.setValue(self.video_metadata["scale"])
                self.scale_calibrated.setChecked(False)
            self.update_video_information()
            self.file_label.setText(Path(path).name)
            self.slider.setRange(0, self.frame_count - 1)
            self.seek_frame(0)
            self.refresh_analysis_status()
            self.statusBar().showMessage("Fichier chargé : " + Path(path).name)
        except Exception as exc:
            self.release_source()
            self.slider.setRange(0, 0)
            self.video_path = None
            self.video_metadata = {}
            self.file_label.setText("Aucune vidéo chargée")
            QMessageBox.warning(self, "Erreur d'ouverture", str(exc))

    def release_source(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        if self.tiff_file is not None:
            self.tiff_file.close()
            self.tiff_file = None
        self.tiff_pages = None
        self.tiff_stack = None
        self.tiff_series = None

    def play_video(self):
        if self.cap is None and self.tiff_file is None:
            QMessageBox.information(self, "Vidéo", "Ouvrez d'abord un fichier.")
            return
        if self.frame_index >= self.frame_count - 1:
            self.seek_frame(0)
        self.playing = True
        self.timer.start(max(1, round(1000 / self.fps)))

    def pause_video(self):
        self.playing = False
        self.timer.stop()

    def stop_video(self):
        self.pause_video()
        if self.cap is not None or self.tiff_file is not None:
            self.seek_frame(0)

    def seek_frame(self, index):
        if self.cap is None and self.tiff_file is None:
            return
        self.frame_index = max(0, min(int(index), self.frame_count - 1))
        self.show_frame(self.frame_index)

    def next_frame(self):
        if self.cap is None and self.tiff_file is None:
            return
        if self.frame_index + 1 >= self.frame_count:
            self.pause_video()
            return
        self.show_frame(self.frame_index + 1)

    def show_frame(self, index):
        try:
            if self.tiff_file is not None:
                if self.tiff_stack is not None:
                    image = self.tiff_stack[index]
                else:
                    image = self.tiff_pages[index].asarray()
                if image.dtype != np.uint8:
                    # Normalisation uniquement pour l'affichage / détection exploratoire.
                    image = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                if image.ndim == 2:
                    frame = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
                elif image.ndim == 3 and image.shape[-1] == 3:
                    frame = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                elif image.ndim == 3 and image.shape[-1] == 4:
                    frame = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
                else:
                    raise ValueError(f"Dimensions TIFF non prises en charge : {image.shape}")
            else:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = self.cap.read()
                if not ok:
                    raise ValueError(f"Impossible de lire l'image {index + 1}.")
            self.frame = frame
            self.frame_index = index
            self.slider.blockSignals(True)
            self.slider.setValue(index)
            self.slider.blockSignals(False)
            if self.tiff_file is not None:
                speed = f"Lecture : {self.fps:.1f} images/s (cadence réelle inconnue)"
            else:
                speed = f"FPS fichier : {self.fps:.2f}"
            self.info_label.setText(f"Image : {index + 1}/{self.frame_count} | {speed}")
            self.update_detection()
        except Exception as exc:
            self.pause_video()
            QMessageBox.warning(self, "Erreur de lecture", str(exc))

    def render_frame(self):
        if self.frame is None:
            return
        # Les superpositions sont faites sur une copie ; l'image source reste intacte.
        display = self.frame.copy()
        h, w = display.shape[:2]
        if self.detect_enabled.isChecked():
            for x, y, _area in self.centers:
                cv2.circle(display, (round(x), round(y)), 7, (0, 220, 255), 1)
                cv2.drawMarker(display, (round(x), round(y)), (0, 220, 255),
                               cv2.MARKER_CROSS, 8, 1)
        
        if self.show_tracks.isChecked() and self.trajectories:
            # Tracés historiques jusqu'à l'image courante ; pas d'association calculée ici.
            for particle_id, points in self.trajectories.items():
                previous = None
                for t, x, y in sorted(points):
                    if t > self.frame_index:
                        break
                    current = (round(x), round(y))
                    if previous is not None:
                        cv2.line(display, previous, current, (220, 140, 60), 1)
                    previous = current

        if self.scale_calibrated.isChecked():
            um_per_px = self.pixel_scale.value()
            self.scale_label.setText(
                f"Échelle : {um_per_px:.4f} µm/pixel | "
                f"Objectif : {self.objective.currentText()}"
            )
        else:
            self.scale_label.setText(
                "Échelle : non calibrée — cocher la calibration dans Paramètres"
            )

        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        
        pixmap = QPixmap.fromImage(image).scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        if self.scale_calibrated.isChecked():
            from PySide6.QtGui import QPainter, QPen, QColor, QFont

            um_per_px = self.pixel_scale.value()
            display_ratio = pixmap.width() / w

            # Longueur réelle choisie pour la barre
            bar_um = 5.0
            bar_px = round((bar_um / um_per_px) * display_ratio)

            if 0 < bar_px < pixmap.width() - 40:
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)

                x2 = pixmap.width() - 25
                x1 = x2 - bar_px
                y = pixmap.height() - 25

                painter.setPen(QPen(QColor("white"), 2))
                painter.drawLine(x1, y, x2, y)
                painter.drawLine(x1, y - 4, x1, y + 4)
                painter.drawLine(x2, y - 4, x2, y + 4)

                font = QFont("Arial", 10)
                painter.setFont(font)
                painter.drawText(x1, y - 9, "5 µm")

                painter.end()

        self.image_label.setPixmap(pixmap)


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "image_label"):
            self.render_frame()

    def save_frame(self):
        if self.frame is None:
            QMessageBox.information(self, "Image", "Aucune image à enregistrer.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer l'image", "particule.png", "Images PNG (*.png);;Images JPEG (*.jpg)"
        )
        if path:
            if cv2.imwrite(path, self.frame):
                self.statusBar().showMessage("Image enregistrée : " + path)
            else:
                QMessageBox.warning(self, "Erreur", "Enregistrement impossible.")

    def build_acquisition_controls(self):
        """Commandes préparées : aucun matériel simulé comme connecté."""
        box = QGroupBox("Acquisition réelle — Raspberry Pi (à connecter)")
        form = QFormLayout(box)
        self.acq_exposure = QDoubleSpinBox()
        self.acq_exposure.setRange(0.1, 10000.0)
        self.acq_exposure.setDecimals(2)
        self.acq_exposure.setValue(18.0)
        self.acq_exposure.setSuffix(" ms")
        self.acq_fps = QDoubleSpinBox()
        self.acq_fps.setRange(0.1, 240.0)
        self.acq_fps.setValue(50.0)
        self.acq_fps.setSuffix(" images/s")
        self.acq_duration = QDoubleSpinBox()
        self.acq_duration.setRange(0.1, 3600)
        self.acq_duration.setValue(5.0)
        self.acq_duration.setSuffix(" s")
        self.acq_count = QLabel()
        self.acq_fps.valueChanged.connect(self.update_acq_count)
        self.acq_duration.valueChanged.connect(self.update_acq_count)
        self.acq_exposure.valueChanged.connect(self.update_acq_count)
        self.acq_directory = QLineEdit(str(Path.home() / "Videos"))
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self.choose_acq_directory)
        directory_row = QWidget()
        directory_layout = QHBoxLayout(directory_row)
        directory_layout.setContentsMargins(0, 0, 0, 0)
        directory_layout.addWidget(self.acq_directory)
        directory_layout.addWidget(browse)
        form.addRow("Exposition :", self.acq_exposure)
        form.addRow("Cadence demandée :", self.acq_fps)
        form.addRow("Durée demandée :", self.acq_duration)
        form.addRow("Images prévues :", self.acq_count)
        form.addRow("Dossier cible :", directory_row)
        form.addRow("Format demandé :", QLabel("TIFF multipage (à valider sur le Pi)"))
        self.acq_status = QLabel("Caméra non connectée — aucun contrôle matériel disponible")
        self.acq_status.setWordWrap(True)
        form.addRow(self.acq_status)
        self.acq_save_config = QPushButton("Exporter les paramètres (JSON)")
        self.acq_save_config.clicked.connect(self.export_acquisition_config)
        form.addRow(self.acq_save_config)
        self.acq_connect = QPushButton("Connecter la caméra")
        self.acq_start = QPushButton("Démarrer l'acquisition")
        self.acq_stop = QPushButton("Arrêter l'acquisition")
        self.acq_connect.clicked.connect(self.connect_camera)
        self.acq_start.clicked.connect(self.start_camera)
        self.acq_stop.clicked.connect(self.stop_camera)
        for button in (self.acq_connect, self.acq_start, self.acq_stop):
            button.setEnabled(False)
            form.addRow(button)
        self.acq_warning = QLabel("Les commandes caméra ne seront activées qu'après intégration et validation d'un module d'acquisition réel.")
        self.acq_warning.setWordWrap(True)
        form.addRow(self.acq_warning)
        self.update_acq_count()
        # Réutilise l'onglet Acquisition, dans une zone défilante.
        acquisition_page = self.tabs.widget(0)
        main_layout = acquisition_page.layout()
        left_layout = main_layout.itemAt(0).widget().widget().layout()
        left_layout.insertWidget(2, box)
        self.refresh_analysis_status()

    def update_acq_count(self, *_):
        n = round(self.acq_fps.value() * self.acq_duration.value())
        interval_ms = 1000.0 / self.acq_fps.value()
        text = str(n) + " (estimation)"
        if self.acq_exposure.value() > interval_ms:
            text += " ⚠ exposition > intervalle entre images"
        self.acq_count.setText(text)

    def choose_acq_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Dossier d'acquisition", self.acq_directory.text())
        if folder:
            self.acq_directory.setText(folder)

    def acquisition_config(self):
        fps = self.acq_fps.value()
        exposure = self.acq_exposure.value()
        if exposure > 1000 / fps:
            raise ValueError("L'exposition dépasse l'intervalle entre deux images. Réduisez l'exposition ou la cadence.")
        if not self.acq_directory.text().strip():
            raise ValueError("Indiquez un dossier cible.")
        return {"exposure_ms": exposure, "fps_requested": fps,
                "duration_s": self.acq_duration.value(),
                "estimated_frames": round(fps * self.acq_duration.value()),
                "output_directory": self.acq_directory.text().strip(),
                "format_requested": "multipage_tiff"}

    def export_acquisition_config(self):
        try:
            config = self.acquisition_config()
            path, _ = QFileDialog.getSaveFileName(self, "Enregistrer les paramètres", "acquisition_config.json", "JSON (*.json)")
            if path:
                Path(path).write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
                self.statusBar().showMessage("Paramètres exportés : " + path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Paramètres invalides", str(exc))

    def refresh_backend_status(self):
        # Intégration matériel volontairement désactivée : pas de fausse connexion.
        self.acq_status.setText("Caméra non connectée — intégration Raspberry Pi à réaliser")

    def connect_camera(self):
        QMessageBox.information(self, "Caméra", "Intégration Raspberry Pi non encore disponible.")

    def start_camera(self):
        QMessageBox.information(self, "Acquisition", "Acquisition réelle non encore disponible.")

    def stop_camera(self):
        QMessageBox.information(self, "Acquisition", "Acquisition réelle non encore disponible.")

    def refresh_analysis_status(self):
        ready = importlib.util.find_spec("analyse_equipe") is not None
        self.analyze_btn.setEnabled(bool(self.video_path) and ready and self.analysis_thread is None)
        if not ready:
            self.analysis_status.setText("En attente du fichier analyse_equipe.py de vos coéquipiers.")
        elif not self.video_path:
            self.analysis_status.setText("Chargez une vidéo pour lancer l'analyse.")
        elif self.analysis_thread is None:
            self.analysis_status.setText("Module d'analyse détecté. Prêt à lancer (résultats à valider).")

    def start_analysis(self):
        if not self.video_path or self.analysis_thread is not None:
            return
        if not self.scale_calibrated.isChecked():
            QMessageBox.warning(self, "Calibration", "Vérifiez et cochez la calibration µm/pixel dans Paramètres avant l'analyse.")
            return
        dt = self.video_metadata.get("dt")
        if not dt:
            QMessageBox.warning(self, "Temps d'acquisition", "Δt est absent du nom du fichier : le module d'analyse nécessite un intervalle temporel connu.")
            return
        self.pause_video()
        self.analysis_thread = QThread(self)
        self.analysis_worker = AnalyseWorker(self.video_path, self.pixel_scale.value(), dt,
                                             {"objective": self.objective.currentText()})
        self.analysis_worker.moveToThread(self.analysis_thread)
        self.analysis_thread.started.connect(self.analysis_worker.run)
        self.analysis_worker.finished.connect(self.analysis_success)
        self.analysis_worker.failed.connect(self.analysis_failure)
        self.analysis_worker.finished.connect(self.analysis_thread.quit)
        self.analysis_worker.failed.connect(self.analysis_thread.quit)
        self.analysis_thread.finished.connect(self.analysis_cleanup)
        self.analysis_thread.finished.connect(self.analysis_worker.deleteLater)
        self.analysis_thread.finished.connect(self.analysis_thread.deleteLater)
        self.analysis_progress.setRange(0, 0)  # activité indéterminée, pas un pourcentage fictif
        self.analysis_status.setText("Analyse en cours…")
        self.analyze_btn.setEnabled(False)
        self.analysis_thread.start()

    @Slot(object)
    def analysis_success(self, output):
        try:
            if output.get("trajectories") is not None:
                self.set_trajectories(output["trajectories"])
            self.set_analysis_results(output["results"])
            self.analysis_status.setText("Analyse terminée — vérifier la validité scientifique des résultats.")
            self.tabs.setCurrentIndex(2)
        except Exception as exc:
            self.analysis_failure(str(exc))

    @Slot(str)
    def analysis_failure(self, details):
        self.analysis_status.setText("Échec de l'analyse. Consultez le message d'erreur.")
        QMessageBox.warning(self, "Erreur d'analyse", details[-4000:])

    @Slot()
    def analysis_cleanup(self):
        self.analysis_thread = None
        self.analysis_worker = None
        self.analysis_progress.setRange(0, 100)
        self.analysis_progress.setValue(100 if self.analysis_results is not None else 0)
        self.refresh_analysis_status()

    def closeEvent(self, event):
        self.timer.stop()
        if self.analysis_thread is not None:
            self.analysis_thread.quit()
            self.analysis_thread.wait(3000)
        self.release_source()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MicroscopeApp()
    window.show()
    sys.exit(app.exec())
