import sys
from pathlib import Path
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def _load_embedded_fonts():
    fonts_dir = Path(__file__).resolve().parent / "assets" / "fonts"
    if not fonts_dir.exists():
        return

    for pattern in ("*.ttf", "*.otf", "*.ttc"):
        for font_path in fonts_dir.glob(pattern):
            QFontDatabase.addApplicationFont(str(font_path))


def main():
    app = QApplication(sys.argv)
    _load_embedded_fonts()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
