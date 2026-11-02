from typing import TypedDict

import cv2
import numpy as np
from picamera2 import Picamera2
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QMainWindow, QMessageBox
from numpy.typing import NDArray
from scipy.ndimage import gaussian_filter
from scipy.optimize import curve_fit


class Particle(TypedDict):
    pos: tuple[int, int]
    size: int


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
    size = max(1, round(2 * parameters[3]))
    particles.append(
        {
            "pos": (round(center_x), round(center_y)),
            "size": size,
        }
    )


def draw_particle_rectangles(
    frame: NDArray[np.uint8], particles: list[Particle]
) -> None:
    for particle in particles:
        x, y = particle["pos"]
        size = particle["size"]
        top_left = (x - size // 2, y - size // 2)
        bottom_right = (top_left[0] + size - 1, top_left[1] + size - 1)
        cv2.rectangle(frame, top_left, bottom_right, (255, 0, 0), 2)


class CameraWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.camera = Picamera2()
        self.camera.configure(
            self.camera.create_preview_configuration(
                main={"format": "RGB888", "size": (640, 480)}
            )
        )
        self.camera.start()

        self.particles: list[Particle] = []

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
                self, "Erreur caméra", f"Impossible de capturer une image : {error}"
            )
            return

        update_particles(self.particles, frame)
        draw_particle_rectangles(frame, self.particles)

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
        self.lbl_video.setPixmap(pixmap)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.camera.stop()
        self.camera.close()
        event.accept()
