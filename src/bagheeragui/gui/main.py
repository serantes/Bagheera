#!/usr/bin/env python3
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from .app import BagheeraSearchWindow, PROG_ID


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Bagheera Search GUI")
    app.setDesktopFileName(PROG_ID)

    # Load application icon from local file (theme independent)
    # Assumes icon at src/bagheeragui/gui/assets/bagheeragui.png
    icon_path = os.path.join(
        os.path.dirname(__file__), "..", "assets", "bagheeragui.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Attempt to use system icon theme (default to KDE Breeze)
    if QIcon.themeName() == "":
        QIcon.setThemeName("breeze-dark")

    window = BagheeraSearchWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
