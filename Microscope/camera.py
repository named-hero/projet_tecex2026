import time
from typing import TypedDict

import cv2
import numpy as np
from picamera2 import Picamera2
from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QCloseEvent, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QLabel, QMainWindow, QMessageBox
from numpy.typing import NDArray
from scipy.ndimage import gaussian_filter
from scipy.optimize import curve_fit

ECHELLE = 0.5  # micromètres par pixel TODO
EXPOSITION = 0.02  # secondes
PROFONDEUR_BITS = 0  # TODO : configurer la profondeur de bit


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
    particles.append(Particle((round(center_x), round(center_y)), size))


class CameraWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.camera = Picamera2()
        self.camera.configure(
            self.camera.create_preview_configuration(
                main={"format": "RGB888", "size": (640, 480)}
            )
        )
        self.camera.set_controls(
            {"AeEnable": False, "ExposureTime": round(EXPOSITION * 1_000_000)}
        )
        self.camera.start()

        self.particles: list[Particle] = []
        self.size_measurement_count = 0
        self.mean_size_um = 0.0
        self.size_squared_deviation_sum = 0.0
        self.fps: float | None = None
        self.last_frame_time: float | None = None

        self.setWindowTitle("Vue caméra du microscope")
        self.resize(800, 600)

        self.lbl_video = QLabel()
        self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_video.setStyleSheet("background: black;")
        self.setCentralWidget(self.lbl_video)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_image)
        self.timer.start(30)

    def update_image(self) -> None:
        try:
            frame = self.camera.capture_array()
        except Exception as error:
            self.timer.stop()
            QMessageBox.critical(
                self,
                "Erreur caméra",
                f"Impossible de capturer une image : {error}",
            )
            return

        current_time = time.perf_counter()
        if self.last_frame_time is not None:
            frame_interval = current_time - self.last_frame_time
            if frame_interval > 0:
                self.fps = 1.0 / frame_interval
        self.last_frame_time = current_time

        update_particles(self.particles, frame)
        self._record_particle_sizes()
        self.draw_particle(frame)

        height, width = frame.shape[:2]
        image = QImage(
            frame.data,
            width,
            height,
            frame.strides[0],
            QImage.Format.Format_RGB888,
        ).copy()
        pixmap = QPixmap.fromImage(image).scaled(
            self.lbl_video.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.add_particle_size(pixmap)
        self.add_acquisition_info(pixmap)
        self.add_camera_info(pixmap)
        self.draw_scale_bar(pixmap, width)
        self.lbl_video.setPixmap(pixmap)

    def draw_particle(self, frame: NDArray[np.uint8]) -> None:
        for particle in self.particles:
            x, y = particle["pos"]
            size = max(1, round(particle["size"]))
            top_left = (x - size // 2, y - size // 2)
            bottom_right = (top_left[0] + size - 1, top_left[1] + size - 1)
            cv2.rectangle(frame, top_left, bottom_right, (255, 0, 0), 2)

    def _record_particle_sizes(self) -> None:
        for particle in self.particles:
            size_um = particle["size"] * ECHELLE
            self.size_measurement_count += 1
            delta = size_um - self.mean_size_um
            self.mean_size_um += delta / self.size_measurement_count
            self.size_squared_deviation_sum += delta * (
                size_um - self.mean_size_um
            )

    def add_particle_size(self, pixmap: QPixmap) -> None:
        if not self.size_measurement_count:
            return

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setPixelSize(max(10, round(pixmap.width() / 60)))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        margin = max(12, round(pixmap.width() / 50))

        if self.size_measurement_count > 1:
            sample_variance = self.size_squared_deviation_sum / (
                self.size_measurement_count - 1
            )
            uncertainty_um = np.sqrt(
                sample_variance / self.size_measurement_count
            )
            size_text = (
                f"Taille moyenne : {self.mean_size_um:.2f} "
                f"± {uncertainty_um:.2f} µm"
            )
        else:
            size_text = f"Taille moyenne : {self.mean_size_um:.2f} µm (n=1)"

        text_width = metrics.horizontalAdvance(size_text)
        text_height = metrics.height()
        text_x = margin
        text_y = margin
        painter.fillRect(
            QRect(
                text_x - 8,
                text_y - 4,
                text_width + 16,
                text_height + 8,
            ),
            QColor(0, 0, 0, 150),
        )
        painter.setPen(QColor(255, 165, 0))
        painter.drawText(text_x, text_y + metrics.ascent(), size_text)
        painter.end()

    def add_acquisition_info(self, pixmap: QPixmap) -> None:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setPixelSize(max(10, round(pixmap.width() / 60)))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        margin = max(12, round(pixmap.width() / 50))

        lines = [
            f"Profondeur de bit : {PROFONDEUR_BITS} bits",
        ]
        line_height = metrics.height()
        top = (
            margin + line_height + 8
            if self.size_measurement_count
            else margin
        )
        text_width = max(metrics.horizontalAdvance(line) for line in lines)
        painter.fillRect(
            QRect(
                margin - 8,
                top - 4,
                text_width + 16,
                line_height * len(lines) + 8,
            ),
            QColor(0, 0, 0, 150),
        )
        painter.setPen(QColor(255, 255, 255))
        for index, line in enumerate(lines):
            painter.drawText(
                margin,
                top + index * line_height + metrics.ascent(),
                line,
            )
        painter.end()

    def add_camera_info(self, pixmap: QPixmap) -> None:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setPixelSize(max(10, round(pixmap.width() / 75)))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        margin = max(12, round(pixmap.width() / 50))

        exposure_text = f"Temps d'exposition : {EXPOSITION:g} s"
        fps_text = f"FPS : {self.fps:.1f}" if self.fps is not None else "FPS : --"
        lines = ["Objectif : X20 de NA 0.45", exposure_text, fps_text] #TODO : remplacer l'objectif par la valeur réelle
        text_width = max(metrics.horizontalAdvance(line) for line in lines)
        line_height = metrics.height()
        box_left = pixmap.width() - margin - text_width - 16
        box_top = margin - 4
        painter.fillRect(
            QRect(
                box_left,
                box_top,
                text_width + 16,
                line_height * len(lines) + 12,
            ),
            QColor(0, 0, 0, 150),
        )
        painter.setPen(QColor(255, 255, 255))
        for index, line in enumerate(lines):
            painter.drawText(
                box_left + 8,
                margin + index * line_height + metrics.ascent(),
                line,
            )
        painter.end()

    def draw_scale_bar(self, pixmap: QPixmap, frame_width: int) -> None:
        if not np.isfinite(ECHELLE) or ECHELLE <= 0:
            raise ValueError("ECHELLE doit être une valeur positive en µm/pixel.")

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = painter.font()
        font.setPixelSize(max(12, round(pixmap.width() / 45)))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        margin = max(12, round(pixmap.width() / 50))

        target_um = frame_width * ECHELLE * 0.2
        exponent = round(np.log10(target_um))
        scale_um = 10.0**exponent
        if scale_um / ECHELLE > frame_width * 0.4:
            scale_um /= 10
        scale_pixels = max(
            1, round(scale_um / ECHELLE * pixmap.width() / frame_width)
        )
        scale_text = f"{scale_um:g} µm"
        text_width = metrics.horizontalAdvance(scale_text)
        line_y = pixmap.height() - margin
        line_end_x = pixmap.width() - margin
        line_start_x = line_end_x - scale_pixels
        text_x = line_end_x - text_width
        text_baseline = line_y - max(6, metrics.height() // 3)
        background_left = min(line_start_x, text_x) - 8
        background_top = text_baseline - metrics.ascent() - 4
        background_right = line_end_x + 8
        painter.fillRect(
            QRect(
                background_left,
                background_top,
                background_right - background_left,
                line_y - background_top + 8,
            ),
            QColor(0, 0, 0, 150),
        )
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(text_x, text_baseline, scale_text)
        line_width = max(2, round(pixmap.width() / 400))
        painter.setPen(QPen(QColor(255, 255, 255), line_width))
        painter.drawLine(line_start_x, line_y, line_end_x, line_y)
        painter.end()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.camera.stop()
        self.camera.close()
        event.accept()
