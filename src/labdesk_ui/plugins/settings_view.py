"""Settings view — only preferences confirmed ready for the UI.

`config.toml` remains the full surface: many keys are config-only until
the feature works and we deliberately expose a control here.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
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

        self.projects_layout = QComboBox()
        self.projects_layout.addItem("Table", "table")
        self.projects_layout.addItem("Cards", "cards")
        self.projects_layout.currentIndexChanged.connect(self._on_projects_layout_changed)
        form.addRow("Projects list layout", self.projects_layout)

        progress_row = QHBoxLayout()
        self.progress_color_btn = QPushButton("Choose…")
        self.progress_color_btn.clicked.connect(self._pick_progress_color)
        self._progress_color = "#2ecc71"
        progress_row.addWidget(self.progress_color_btn)
        self.progress_alpha = QSpinBox()
        self.progress_alpha.setRange(0, 255)
        self.progress_alpha.setValue(70)
        self.progress_alpha.setToolTip("Transparency of the clone/push fill (0 = invisible, 255 = solid)")
        progress_row.addWidget(QLabel("Alpha"))
        progress_row.addWidget(self.progress_alpha)
        progress_row.addStretch(1)
        form.addRow("Clone/push fill colour", progress_row)

        self.check_updates = QCheckBox("Check LabDesk Flatpak updates on startup")
        form.addRow("Updates", self.check_updates)

        layout.addLayout(form)
        self._refresh_progress_color_btn()

        update_row = QHBoxLayout()
        self.btn_check_updates = QPushButton("Check for updates now…")
        self.btn_check_updates.clicked.connect(self._check_updates_now)
        update_row.addWidget(self.btn_check_updates)
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
            layout = general.get("projects_layout") or "table"
            lidx = self.projects_layout.findData(layout)
            self.projects_layout.blockSignals(True)
            self.projects_layout.setCurrentIndex(lidx if lidx >= 0 else 0)
            self.projects_layout.blockSignals(False)
            self._progress_color = str(general.get("progress_overlay_color") or "#2ecc71")
            self.progress_alpha.setValue(int(general.get("progress_overlay_alpha") or 70))
            self._refresh_progress_color_btn()
            self.check_updates.setChecked(bool(general.get("check_for_updates", True)))

            paths = labdesk_core.get_paths()
            self.paths.setText(
                f"Config: {paths.get('config_toml', '')}\n"
                f"Cache: {paths.get('cache_db', '')}"
            )
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _refresh_progress_color_btn(self) -> None:
        self.progress_color_btn.setText(self._progress_color)
        self.progress_color_btn.setStyleSheet(
            f"background-color: {self._progress_color}; padding: 4px 12px;"
        )

    def _pick_progress_color(self) -> None:
        from PySide6.QtGui import QColor

        initial = QColor(self._progress_color)
        chosen = QColorDialog.getColor(initial, self, "Clone/push fill colour")
        if chosen.isValid():
            self._progress_color = chosen.name()
            self._refresh_progress_color_btn()

    def _apply_projects_layout_now(self) -> None:
        """Persist + apply Projects table/cards immediately (does not require Save)."""
        import labdesk_core

        layout_choice = self.projects_layout.itemData(self.projects_layout.currentIndex())
        labdesk_core.set_projects_layout(str(layout_choice or "table"))
        projects = None
        if hasattr(self._ctx, "view_widget"):
            projects = self._ctx.view_widget("projects")
        elif hasattr(self._ctx, "_view_widgets"):
            projects = self._ctx._view_widgets.get("projects")
        if projects is not None and hasattr(projects, "apply_prefs"):
            projects.apply_prefs()

    def _on_projects_layout_changed(self, _index: int = 0) -> None:
        try:
            self._apply_projects_layout_now()
            self._ctx.set_detail("Projects list layout updated.")
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
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            from labdesk_ui.utils.flatpak_updates import check_for_labdesk_updates

            return check_for_labdesk_updates()

        def on_ok(result) -> None:
            detail = (result or {}).get("detail") or ""
            if (result or {}).get("available"):
                QMessageBox.information(self, "Updates", detail)
            else:
                QMessageBox.information(self, "Updates", detail or "No updates found.")

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_check_updates],
            status=self._ctx.set_detail,
            working_message="Checking for Flatpak updates…",
        )

    def _save(self) -> None:
        try:
            import labdesk_core

            clone = self.clone_dir.text().strip()
            if not clone:
                QMessageBox.warning(self, "Settings", "Clone folder is required.")
                return

            # Snapshot form values first. set_ui_shell → switch_view → on_activated
            # → _load() mid-save would otherwise reset the layout combo from disk
            # (still "table") and then persist that overwrite.
            theme = str(self.theme.currentData() or "system")
            shell = str(self.ui_shell.itemData(self.ui_shell.currentIndex()) or "classic")
            layout_choice = str(
                self.projects_layout.itemData(self.projects_layout.currentIndex())
                or "table"
            )
            progress_color = self._progress_color
            progress_alpha = int(self.progress_alpha.value())
            check_updates = self.check_updates.isChecked()

            labdesk_core.set_default_clone_dir(clone)
            labdesk_core.set_theme(theme)
            from labdesk_ui.utils.theme import apply_theme

            apply_theme(theme)
            labdesk_core.set_ui_shell(shell)
            if hasattr(self._ctx, "set_ui_shell"):
                self._ctx.set_ui_shell(shell, persist=False)
            labdesk_core.set_projects_layout(layout_choice)
            labdesk_core.set_progress_overlay(progress_color, progress_alpha)
            labdesk_core.set_check_for_updates(check_updates)
            projects = None
            if hasattr(self._ctx, "view_widget"):
                projects = self._ctx.view_widget("projects")
            elif hasattr(self._ctx, "_view_widgets"):
                projects = self._ctx._view_widgets.get("projects")
            if projects is not None and hasattr(projects, "apply_prefs"):
                projects.apply_prefs()
            self._ctx.set_detail("Settings saved.")
            self._load()
            QMessageBox.information(self, "Settings", "Settings saved to config.toml.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")


def _factory(parent: QWidget, ctx: AppContext) -> QWidget:
    return SettingsView(parent, ctx)


register_view("settings", "Settings", _factory, order=90)
