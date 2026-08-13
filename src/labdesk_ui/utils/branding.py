"""Resolve LabDesk branding assets (window / tray icons)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap

_APP_ID = "com.bigrangatech.LabDesk"
_SIZES = (64, 128, 256, 512)


def _assets_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "assets"


def logo_svg_path() -> Path | None:
    """Mark-only SVG used as the app icon."""
    path = _assets_dir() / "LabDesk-logo.svg"
    return path if path.is_file() else None


def wordmark_svg_path() -> Path | None:
    """Logo + wordmark SVG for About and similar surfaces."""
    path = _assets_dir() / "LabDesk-logo-with-text.svg"
    return path if path.is_file() else None


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
    for svg in (
        logo_svg_path(),
        assets / f"{_APP_ID}.svg",
        Path(f"/app/share/icons/hicolor/scalable/apps/{_APP_ID}.svg"),
    ):
        if svg is not None and Path(svg).is_file():
            icon.addFile(str(svg))
            break
    if icon.isNull():
        icon = QIcon.fromTheme(_APP_ID)
    return icon


def wordmark_pixmap(max_width: int = 320) -> QPixmap | None:
    """Rasterize the wordmark SVG for About; None if unavailable."""
    path = wordmark_svg_path()
    if path is None:
        return None
    pix = QPixmap(str(path))
    if pix.isNull():
        return None
    if pix.width() > max_width:
        pix = pix.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
    return pix
