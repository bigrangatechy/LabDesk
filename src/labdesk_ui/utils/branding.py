"""Resolve LabDesk branding assets (window / tray icons)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

_APP_ID = "com.bigrangatech.LabDesk"
_SIZES = (64, 128, 256, 512)


def _assets_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "assets"


def app_icon() -> QIcon:
    icon = QIcon()
    assets = _assets_dir()
    for sz in _SIZES:
        path = assets / f"{_APP_ID}-{sz}x{sz}.png"
        if path.is_file():
            icon.addFile(str(path), QSize(sz, sz))
    # Flatpak hicolor install (theme lookup / fallback).
    for sz in _SIZES:
        path = Path(f"/app/share/icons/hicolor/{sz}x{sz}/apps/{_APP_ID}.png")
        if path.is_file():
            icon.addFile(str(path), QSize(sz, sz))
    svg = assets / f"{_APP_ID}.svg"
    if svg.is_file():
        icon.addFile(str(svg))
    if icon.isNull():
        icon = QIcon.fromTheme(_APP_ID)
    return icon
