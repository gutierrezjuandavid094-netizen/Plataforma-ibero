"""Punto de entrada de Campus Flow."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from src.ui.main_window import Ventana
from src.version import __version__


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Campus Flow")
    app.setApplicationDisplayName("Campus Flow")
    app.setApplicationVersion(__version__)
    icon = resource_path("src/assets/campus-flow.svg" if hasattr(sys, "_MEIPASS") else "assets/campus-flow.svg")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = Ventana()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
