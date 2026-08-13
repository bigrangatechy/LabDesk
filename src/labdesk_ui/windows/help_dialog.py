"""In-app User Guide (Help → User Guide…)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout


def resolve_user_guide_path() -> Path | None:
    """Locate bundled ``user-guide.md`` (packaged, repo checkout, Flatpak share)."""
    here = Path(__file__).resolve()
    candidates = [
        # Packaged with labdesk_ui (dev install + Flatpak /app/lib/labdesk/…)
        here.parent.parent / "docs" / "user-guide.md",
        # Repo checkout: Docs/ next to src/
        here.parents[3] / "Docs" / "user-guide.md",
        # Flatpak share path (explicit install)
        Path("/app/share/labdesk/user-guide.md"),
    ]
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def load_user_guide_markdown() -> str:
    path = resolve_user_guide_path()
    if path is None:
        return (
            "# User Guide unavailable\n\n"
            "Could not find `user-guide.md`. Reinstall LabDesk or open "
            "`Docs/user-guide.md` from the source tree."
        )
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"# User Guide unavailable\n\nFailed to read `{path}`:\n\n{exc}"


class UserGuideDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("LabDesk User Guide")
        self.resize(720, 560)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(load_user_guide_markdown())
        layout.addWidget(browser, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        layout.addWidget(buttons)
