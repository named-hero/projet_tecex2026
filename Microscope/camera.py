from typing import TypedDict

import cv2
import numpy as np
from picamera2 import Picamera2
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QMainWindow, QMessageBox
from numpy.typing import NDArray


class Particle(TypedDict):
    pos: tuple[int, int]
    size: int


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
