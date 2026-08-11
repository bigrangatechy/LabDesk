"""Resolve LabDesk branding assets (window / tray icons)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon


def _asset_candidates() -> list[Path]:
    here = Path(__file__).resolve().parent
    ui_root = here.parent  # labdesk_ui/
    name = "com.bigrangatech.LabDesk"
    return [
        ui_root / "assets" / f"{name}.svg",
        ui_root / "assets" / f"{name}.png",
        Path(f"/app/share/icons/hicolor/scalable/apps/{name}.svg"),
        Path(f"/app/share/icons/hicolor/256x256/apps/{name}.png"),
        Path(f"/app/share/icons/hicolor/128x128/apps/{name}.png"),
    ]


def app_icon() -> QIcon:
    icon = QIcon()
    for path in _asset_candidates():
        if path.is_file():
            icon.addFile(str(path))
            break
    if icon.isNull():
        # Theme name used by the Flatpak .desktop file.
        icon = QIcon.fromTheme("com.bigrangatech.LabDesk")
    return icon
