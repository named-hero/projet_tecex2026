import sys
from PyQt6.QtWidgets import QApplication
import PyQt6.QtCore as QtCore
import camera

def main():
    app = QApplication(sys.argv)
    main_window = camera.CameraWindow()
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()