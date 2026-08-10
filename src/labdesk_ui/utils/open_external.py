"""Open paths / URLs with the desktop default handler (xdg-open / portal)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_path(path: str | Path) -> None:
    """Open a local file or directory. Raises RuntimeError with LD-SYS-010 on failure."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise RuntimeError(f"[LD-SYS-010] Could not open external application.: {p}")
    url = QUrl.fromLocalFile(str(p))
    if not QDesktopServices.openUrl(url):
        raise RuntimeError(f"[LD-SYS-010] Could not open external application.: {p}")


def open_url(url: str) -> None:
    """Open an http(s) or other URL. Raises RuntimeError with LD-SYS-010 on failure."""
    u = QUrl(url)
    if not u.isValid() or not QDesktopServices.openUrl(u):
        raise RuntimeError(f"[LD-SYS-010] Could not open external application.: {url}")
