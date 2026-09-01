"""Settings view — only preferences confirmed ready for the UI.

`config.toml` remains the full surface: many keys are config-only until
the feature works and we deliberately expose a control here.
"""

from __future__ import annotations

from labdesk_ui.i18n import tr

from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.plugins import AppContext, register_view
from labdesk_ui.utils.helpers import format_error


def _section(title: str) -> tuple[QGroupBox, QFormLayout]:
    box = QGroupBox(title)
    form = QFormLayout(box)
    return box, form


class SettingsView(QWidget):
    def __init__(self, parent: QWidget, ctx: AppContext) -> None:
        super().__init__(parent)
        self._ctx = ctx

        root = QVBoxLayout(self)
        root.addWidget(QLabel(tr("Settings")))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)

        # --- Appearance ---
        appearance, form = _section(tr("Appearance"))
        self.theme = QComboBox()
        self.theme.addItem(tr("System"), "system")
        self.theme.addItem(tr("Light"), "light")
        self.theme.addItem(tr("Dark"), "dark")
        form.addRow(tr("Theme"), self.theme)

        self.locale = QComboBox()
        from labdesk_ui.i18n import locale_display_choices

        for code, label in locale_display_choices():
            self.locale.addItem(tr(label) if code == "system" else label, code)
        form.addRow(tr("Language"), self.locale)

        self.ui_shell = QComboBox()
        self.ui_shell.addItem(tr("Classic"), "classic")
        self.ui_shell.addItem(tr("Sidebar"), "sidebar")
        form.addRow(tr("Main window layout"), self.ui_shell)
        layout.addWidget(appearance)

        # --- Projects ---
        projects, form = _section(tr("Projects"))
        self.projects_layout = QComboBox()
        self.projects_layout.addItem(tr("Table"), "table")
        self.projects_layout.addItem(tr("Cards"), "cards")
        self.projects_layout.currentIndexChanged.connect(self._on_projects_layout_changed)
        form.addRow(tr("Projects list layout"), self.projects_layout)

        progress_row = QHBoxLayout()
        self.progress_color_btn = QPushButton(tr("Choose…"))
        self.progress_color_btn.clicked.connect(self._pick_progress_color)
        self._progress_color = "#2ecc71"
        progress_row.addWidget(self.progress_color_btn)
        self.progress_alpha = QSpinBox()
        self.progress_alpha.setRange(0, 255)
        self.progress_alpha.setValue(70)
        self.progress_alpha.setToolTip(
            tr("Transparency of the clone/push fill (0 = invisible, 255 = solid)")
        )
        progress_row.addWidget(QLabel(tr("Alpha")))
        progress_row.addWidget(self.progress_alpha)
        progress_row.addStretch(1)
        form.addRow(tr("Clone/push fill colour"), progress_row)
        layout.addWidget(projects)

        # --- Repositories ---
        repos, form = _section(tr("Repositories"))
        clone_row = QHBoxLayout()
        self.clone_dir = QLineEdit()
        self.clone_dir.setPlaceholderText(tr("e.g. ~/Documents/gitlab"))
        clone_row.addWidget(self.clone_dir, stretch=1)
        browse = QPushButton(tr("Browse…"))
        browse.clicked.connect(self._browse_clone_dir)
        clone_row.addWidget(browse)
        form.addRow(tr("Clone into"), clone_row)

        self.fetch_on_focus = QCheckBox(tr("Fetch when the repo window gains focus"))
        self.fetch_on_focus.setToolTip(
            tr("When enabled, opening or focusing a repo window may fetch from the remote.")
        )
        form.addRow(tr("Remote fetch"), self.fetch_on_focus)

        self.history_page_size = QSpinBox()
        self.history_page_size.setRange(10, 5000)
        self.history_page_size.setSingleStep(50)
        self.history_page_size.setValue(200)
        self.history_page_size.setToolTip(
            tr("How many commits to load per page in the History tab (10–5000).")
        )
        form.addRow(tr("History page size"), self.history_page_size)

        self.browse_files_page_size = QSpinBox()
        self.browse_files_page_size.setRange(10, 5000)
        self.browse_files_page_size.setSingleStep(50)
        self.browse_files_page_size.setValue(200)
        self.browse_files_page_size.setToolTip(
            tr("How many tracked files to list per page when browsing (10–5000).")
        )
        form.addRow(tr("Browse files page size"), self.browse_files_page_size)
        layout.addWidget(repos)

        # --- Updates ---
        updates, form = _section(tr("Updates"))
        self.check_updates = QCheckBox(tr("Check LabDesk Flatpak updates on startup"))
        form.addRow(tr("On startup"), self.check_updates)
        self.btn_check_updates = QPushButton(tr("Check for updates now…"))
        self.btn_check_updates.clicked.connect(self._check_updates_now)
        form.addRow("", self.btn_check_updates)
        layout.addWidget(updates)

        # --- Paths (read-only) ---
        paths_box, paths_form = _section(tr("Paths"))
        self.paths = QLabel("")
        self.paths.setWordWrap(True)
        self.paths.setStyleSheet("color: palette(mid); font-size: 11px;")
        paths_form.addRow(self.paths)
        layout.addWidget(paths_box)

        btns = QHBoxLayout()
        save = QPushButton(tr("Save settings"))
        save.clicked.connect(self._save)
        btns.addWidget(save)
        reload_btn = QPushButton(tr("Reload from config"))
        reload_btn.clicked.connect(self._load)
        btns.addWidget(reload_btn)
        btns.addStretch(1)
        layout.addLayout(btns)

        hint = QLabel(
            tr(
                "This screen only shows options that are ready for everyday use. "
                "config.toml holds the full preference surface (including "
                "config-only keys such as active host/account ids). Saving here "
                "updates only the fields above and preserves other keys in the file. "
                "Use Projects, Admin, and Settings in the main navigation to switch views."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)
        layout.addStretch(1)

        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)
        self._refresh_progress_color_btn()

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
            locale = general.get("locale") or "system"
            loc_idx = self.locale.findData(locale)
            self.locale.setCurrentIndex(loc_idx if loc_idx >= 0 else 0)
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
            self.fetch_on_focus.setChecked(bool(general.get("fetch_on_focus", True)))
            self.history_page_size.setValue(int(general.get("history_page_size") or 200))
            self.browse_files_page_size.setValue(int(general.get("browse_files_page_size") or 200))
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
        chosen = QColorDialog.getColor(initial, self, tr("Clone/push fill colour"))
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
            tr("Select clone folder"),
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
                QMessageBox.information(self, tr("Updates"), detail)
            else:
                QMessageBox.information(self, tr("Updates"), detail or "No updates found.")

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_check_updates],
            status=self._ctx.set_detail,
            working_message=tr("Checking for Flatpak updates…"),
        )

    def _save(self) -> None:
        try:
            import labdesk_core

            clone = self.clone_dir.text().strip()
            if not clone:
                QMessageBox.warning(self, tr("Settings"), tr("Clone folder is required."))
                return

            # Snapshot form values first. set_ui_shell → switch_view → on_activated
            # → _load() mid-save would otherwise reset the layout combo from disk
            # (still "table") and then persist that overwrite.
            theme = str(self.theme.currentData() or "system")
            locale = str(self.locale.itemData(self.locale.currentIndex()) or "system")
            shell = str(self.ui_shell.itemData(self.ui_shell.currentIndex()) or "classic")
            layout_choice = str(
                self.projects_layout.itemData(self.projects_layout.currentIndex())
                or "table"
            )
            progress_color = self._progress_color
            progress_alpha = int(self.progress_alpha.value())
            fetch_on_focus = self.fetch_on_focus.isChecked()
            history_page_size = int(self.history_page_size.value())
            browse_files_page_size = int(self.browse_files_page_size.value())
            check_updates = self.check_updates.isChecked()

            labdesk_core.set_default_clone_dir(clone)
            labdesk_core.set_theme(theme)
            from labdesk_ui.utils.theme import apply_theme

            apply_theme(theme)
            if hasattr(labdesk_core, "set_locale"):
                labdesk_core.set_locale(locale)
            from labdesk_ui.i18n import install_translators
            from PySide6.QtWidgets import QApplication

            install_translators(QApplication.instance(), locale)
            labdesk_core.set_ui_shell(shell)
            if hasattr(self._ctx, "set_ui_shell"):
                self._ctx.set_ui_shell(shell, persist=False)
            labdesk_core.set_projects_layout(layout_choice)
            labdesk_core.set_progress_overlay(progress_color, progress_alpha)
            if hasattr(labdesk_core, "set_fetch_on_focus"):
                labdesk_core.set_fetch_on_focus(fetch_on_focus)
            if hasattr(labdesk_core, "set_history_page_size"):
                labdesk_core.set_history_page_size(history_page_size)
            if hasattr(labdesk_core, "set_browse_files_page_size"):
                labdesk_core.set_browse_files_page_size(browse_files_page_size)
            labdesk_core.set_check_for_updates(check_updates)
            projects = None
            if hasattr(self._ctx, "view_widget"):
                projects = self._ctx.view_widget("projects")
            elif hasattr(self._ctx, "_view_widgets"):
                projects = self._ctx._view_widgets.get("projects")
            if projects is not None and hasattr(projects, "apply_prefs"):
                projects.apply_prefs()
            self._ctx.set_detail(tr("Settings saved."))
            self._load()
            QMessageBox.information(
                self,
                tr("Settings"),
                tr("Settings saved to config.toml.")
                + "\n\n"
                + tr("Restart LabDesk to fully refresh all window text."),
            )
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")


def _factory(parent: QWidget, ctx: AppContext) -> QWidget:
    return SettingsView(parent, ctx)


register_view("settings", tr("Settings"), _factory, order=90)
