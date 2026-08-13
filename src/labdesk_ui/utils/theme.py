"""Apply LabDesk theme preference to the running QApplication."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget


def _dark_palette() -> QPalette:
    """Fusion-friendly dark palette with the roles stylesheets actually use.

    A partial palette leaves roles like ``Mid`` / ``Light`` on light-theme
    defaults, so ``color: palette(mid)`` labels and borders stay dark after
    switching to dark mode.
    """
    p = QPalette()
    window = QColor(45, 45, 45)
    base = QColor(30, 30, 30)
    alt = QColor(55, 55, 55)
    text = QColor(220, 220, 220)
    muted = QColor(160, 160, 160)
    button = QColor(55, 55, 55)
    highlight = QColor(42, 130, 218)
    disabled = QColor(110, 110, 110)

    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, alt)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, button)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Highlight, highlight)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(140, 140, 140))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(60, 60, 60))
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Link, QColor(100, 180, 255))
    p.setColor(QPalette.ColorRole.LinkVisited, QColor(180, 140, 255))

    # Used by LabDesk stylesheets (borders + secondary labels).
    p.setColor(QPalette.ColorRole.Light, QColor(70, 70, 70))
    p.setColor(QPalette.ColorRole.Midlight, QColor(60, 60, 60))
    p.setColor(QPalette.ColorRole.Mid, muted)
    p.setColor(QPalette.ColorRole.Dark, QColor(35, 35, 35))
    p.setColor(QPalette.ColorRole.Shadow, QColor(20, 20, 20))

    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(70, 70, 70))
    p.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, disabled
    )
    return p


def _propagate_palette(app: QApplication, palette: QPalette) -> None:
    """Push palette onto existing widgets and refresh stylesheet palette() refs."""
    app.setPalette(palette)
    for widget in app.allWidgets():
        if not isinstance(widget, QWidget):
            continue
        widget.setPalette(palette)
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)
        widget.update()


def apply_theme(theme: str) -> None:
    app = QApplication.instance()
    if app is None:
        return
    name = (theme or "system").strip().lower()
    app.setStyle("Fusion")
    if name == "dark":
        _propagate_palette(app, _dark_palette())
    else:
        # light + system — Fusion standard palette (system follows style defaults)
        _propagate_palette(app, app.style().standardPalette())
