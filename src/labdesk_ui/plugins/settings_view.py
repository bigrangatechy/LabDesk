"""Settings view — only preferences confirmed ready for the UI.

`config.toml` remains the full surface: many keys are config-only until
the feature works and we deliberately expose a control here.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.plugins import AppContext, register_view
from labdesk_ui.utils.helpers import format_error


class SettingsView(QWidget):
    def __init__(self, parent: QWidget, ctx: AppContext) -> None:
        super().__init__(parent)
        self._ctx = ctx

        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        back = QPushButton("← Back to Projects")
        back.clicked.connect(lambda: self._ctx.switch_view("projects"))
        header.addWidget(back)
        header.addWidget(QLabel("Settings"), stretch=1)
        layout.addLayout(header)

        form = QFormLayout()

        clone_row = QHBoxLayout()
        self.clone_dir = QLineEdit()
        self.clone_dir.setPlaceholderText("e.g. ~/Documents/gitlab")
        clone_row.addWidget(self.clone_dir, stretch=1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_clone_dir)
        clone_row.addWidget(browse)
        form.addRow("Clone into", clone_row)

        self.theme = QComboBox()
        self.theme.addItem("System", "system")
        self.theme.addItem("Light", "light")
        self.theme.addItem("Dark", "dark")
        form.addRow("Theme", self.theme)

        self.ui_shell = QComboBox()
        self.ui_shell.addItem("Classic", "classic")
        self.ui_shell.addItem("Sidebar", "sidebar")
        form.addRow("Main window layout", self.ui_shell)

        self.check_updates = QCheckBox("Check LabDesk Flatpak updates on startup")
        form.addRow("Updates", self.check_updates)

        layout.addLayout(form)

        update_row = QHBoxLayout()
        check_now = QPushButton("Check for updates now…")
        check_now.clicked.connect(self._check_updates_now)
        update_row.addWidget(check_now)
        update_row.addStretch(1)
        layout.addLayout(update_row)

        self.paths = QLabel("")
        self.paths.setWordWrap(True)
        self.paths.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(self.paths)

        btns = QHBoxLayout()
        save = QPushButton("Save settings")
        save.clicked.connect(self._save)
        btns.addWidget(save)
        reload_btn = QPushButton("Reload from config")
        reload_btn.clicked.connect(self._load)
        btns.addWidget(reload_btn)
        done = QPushButton("Done")
        done.clicked.connect(lambda: self._ctx.switch_view("projects"))
        btns.addWidget(done)
        btns.addStretch(1)
        layout.addLayout(btns)

        hint = QLabel(
            "This screen only shows options that are ready for everyday use. "
            "config.toml holds the full preference surface (including "
            "config-only keys for testing). Saving here updates only the "
            "fields above and preserves other keys in the file."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)
        layout.addStretch(1)

    def on_activated(self) -> None:
        self._load()

    def on_deactivated(self) -> None:
        return

    def _load(self) -> None:
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            general = cfg.get("general") or {}
            clone = labdesk_core.get_default_clone_dir()
            self.clone_dir.setText(clone.get("expanded") or general.get("default_clone_dir") or "")
            theme = general.get("theme") or "system"
            idx = self.theme.findData(theme)
            self.theme.setCurrentIndex(idx if idx >= 0 else 0)
            shell = general.get("ui_shell") or "classic"
            sidx = self.ui_shell.findData(shell)
            self.ui_shell.setCurrentIndex(sidx if sidx >= 0 else 0)
            self.check_updates.setChecked(bool(general.get("check_for_updates", True)))

            paths = labdesk_core.get_paths()
            self.paths.setText(
                f"Config: {paths.get('config_toml', '')}\n"
                f"Cache: {paths.get('cache_db', '')}"
            )
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _browse_clone_dir(self) -> None:
        start = self.clone_dir.text().strip() or ""
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select clone folder",
            start,
            QFileDialog.Option.ShowDirsOnly,
        )
        if chosen:
            self.clone_dir.setText(chosen)

    def _check_updates_now(self) -> None:
        try:
            from labdesk_ui.utils.flatpak_updates import check_for_labdesk_updates

            result = check_for_labdesk_updates()
            detail = result.get("detail") or ""
            if result.get("available"):
                QMessageBox.information(self, "Updates", detail)
            else:
                QMessageBox.information(self, "Updates", detail or "No updates found.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _save(self) -> None:
        try:
            import labdesk_core

            clone = self.clone_dir.text().strip()
            if not clone:
                QMessageBox.warning(self, "Settings", "Clone folder is required.")
                return
            labdesk_core.set_default_clone_dir(clone)
            theme = self.theme.currentData()
            labdesk_core.set_theme(str(theme))
            from labdesk_ui.utils.theme import apply_theme

            apply_theme(str(theme))
            shell = str(self.ui_shell.currentData() or "classic")
            labdesk_core.set_ui_shell(shell)
            if hasattr(self._ctx, "set_ui_shell"):
                self._ctx.set_ui_shell(shell, persist=False)
            labdesk_core.set_check_for_updates(self.check_updates.isChecked())
            self._ctx.set_detail("Settings saved.")
            self._load()
            QMessageBox.information(self, "Settings", "Settings saved to config.toml.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")


def _factory(parent: QWidget, ctx: AppContext) -> QWidget:
    return SettingsView(parent, ctx)


register_view("settings", "Settings", _factory, order=90)
