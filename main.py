import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from core.config import config
from ui.main_window import MainWindow
from ui.style import build_palette, sanitize_accent


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Veronica")
    app.setStyle("Fusion")
    accent = sanitize_accent(config.accent_color)
    config.accent_color = accent
    app.setPalette(build_palette(accent))

    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "Ubuntu", "Noto Sans", "Sans Serif"])
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
