"""Apply LabDesk theme preference to the running QApplication."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_theme(theme: str) -> None:
    app = QApplication.instance()
    if app is None:
        return
    name = (theme or "system").strip().lower()
    if name == "dark":
        app.setStyle("Fusion")
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(140, 140, 140))
        app.setPalette(palette)
    elif name == "light":
        app.setStyle("Fusion")
        app.setPalette(app.style().standardPalette())
    else:
        # system — leave desktop/Qt defaults
        app.setStyle("Fusion")
        app.setPalette(app.style().standardPalette())
