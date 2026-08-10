"""Main window — pluggable views, connection banner, menubar."""

from __future__ import annotations

from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.plugins import ensure_builtin_views, list_views
from labdesk_ui.utils.helpers import format_error
from labdesk_ui.utils.theme import apply_theme
from labdesk_ui.windows.instance_config import InstanceConfigDialog
from labdesk_ui.windows.repo_window import RepoWindow


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LabDesk")
        self.resize(960, 600)
        self._repo_windows: list[RepoWindow] = []
        self._view_widgets: dict[str, QWidget] = {}
        self._active_view_id: str | None = None
        self._view_actions: dict[str, QAction] = {}
        self._nav_buttons: dict[str, QPushButton] = {}

        ensure_builtin_views()

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        self.status = QLabel("Loading…")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status)

        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.detail)

        nav = QHBoxLayout()
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for registered in list_views():
            btn = QPushButton(registered.title)
            btn.setCheckable(True)
            btn.setFlat(False)
            btn.clicked.connect(
                lambda checked=False, vid=registered.id: self.switch_view(vid)
            )
            self._nav_group.addButton(btn)
            nav.addWidget(btn)
            self._nav_buttons[registered.id] = btn
        nav.addStretch(1)
        layout.addLayout(nav)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, stretch=1)

        for registered in list_views():
            widget = registered.factory(self, self)
            self._view_widgets[registered.id] = widget
            self.stack.addWidget(widget)

        self._build_menubar()
        self._apply_saved_theme()
        self.refresh_connection_banner()

        initial = self._saved_active_view() or "projects"
        if initial not in self._view_widgets:
            initial = next(iter(self._view_widgets), "projects")
        self.switch_view(initial, persist=False)

    # --- AppContext API for plugins ---------------------------------

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_detail(self, text: str) -> None:
        self.detail.setText(text)

    def open_repo_window(self, path: str, title: str | None = None) -> None:
        win = RepoWindow(path, title=title or f"LabDesk — {path}", parent=self)
        win.show()
        self._repo_windows.append(win)

    def open_repository_dialog(self) -> None:
        start = ""
        try:
            import labdesk_core

            start = labdesk_core.get_default_clone_dir().get("expanded") or ""
        except Exception:
            start = ""
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Open existing repository",
            start,
            QFileDialog.Option.ShowDirsOnly,
        )
        if not chosen:
            return
        try:
            import labdesk_core

            info = labdesk_core.open_repo_path(chosen)
            path = info.get("path") or chosen
            self.open_repo_window(path, title=f"LabDesk — {path}")
            self.set_detail(f"Opened {path}")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def show_connect_dialog(self) -> None:
        dlg = InstanceConfigDialog(self)
        if dlg.exec() != InstanceConfigDialog.DialogCode.Accepted:
            return
        name, url, pat, ssl_mode = dlg.values()
        try:
            import labdesk_core

            result = labdesk_core.connect_instance(name, url, pat, ssl_mode)
            user = result.get("user") or {}
            count = result.get("project_count", 0)
            QMessageBox.information(
                self,
                "Connected",
                f"Signed in as {user.get('name')} (@{user.get('username')}).\n"
                f"Cached {count} projects.",
            )
            self.refresh_connection_banner()
            projects = self._view_widgets.get("projects")
            if projects is not None and hasattr(projects, "on_activated"):
                projects.on_activated()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def refresh_connection_banner(self) -> None:
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            instances = cfg.get("instances") or []
            if not instances:
                self.status.setText(
                    "No GitLab instance configured yet.\n"
                    "Add a self-hosted instance to get started."
                )
                self.detail.setText("")
                return

            user = labdesk_core.fetch_current_user()
            self.status.setText(
                f"Connected as {user.get('name')} (@{user.get('username')})\n"
                f"Instance: {user.get('instance_name')} — {user.get('base_url')}"
            )
            self.detail.setText("")
        except Exception as exc:
            code, msg = format_error(exc)
            self.status.setText(f"[{code}] {msg}")
            self.detail.setText(str(exc))

    def switch_view(self, view_id: str, *, persist: bool = True) -> None:
        widget = self._view_widgets.get(view_id)
        if widget is None:
            return
        if self._active_view_id and self._active_view_id != view_id:
            old = self._view_widgets.get(self._active_view_id)
            if old is not None and hasattr(old, "on_deactivated"):
                old.on_deactivated()
        self.stack.setCurrentWidget(widget)
        self._active_view_id = view_id
        if hasattr(widget, "on_activated"):
            widget.on_activated()
        action = self._view_actions.get(view_id)
        if action is not None:
            action.setChecked(True)
        nav_btn = self._nav_buttons.get(view_id)
        if nav_btn is not None:
            nav_btn.setChecked(True)
        if persist:
            try:
                import labdesk_core

                labdesk_core.set_active_ui_view(view_id)
            except Exception as exc:
                code, msg = format_error(exc)
                self.detail.setText(f"[{code}] {msg}")

    # --- Menubar ----------------------------------------------------

    def _build_menubar(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        act_connect = QAction("Add / connect instance…", self)
        act_connect.triggered.connect(self.show_connect_dialog)
        file_menu.addAction(act_connect)
        act_open_repo = QAction("Open repository…", self)
        act_open_repo.setShortcut(QKeySequence.StandardKey.Open)
        act_open_repo.triggered.connect(self.open_repository_dialog)
        file_menu.addAction(act_open_repo)
        file_menu.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        view_menu = menu.addMenu("&View")
        group = QActionGroup(self)
        group.setExclusive(True)
        for registered in list_views():
            act = QAction(registered.title, self)
            act.setCheckable(True)
            act.setData(registered.id)
            act.triggered.connect(
                lambda checked=False, vid=registered.id: self.switch_view(vid)
            )
            group.addAction(act)
            view_menu.addAction(act)
            self._view_actions[registered.id] = act

        settings_menu = menu.addMenu("&Settings")
        act_prefs = QAction("&Preferences…", self)
        act_prefs.setShortcut(QKeySequence.StandardKey.Preferences)
        act_prefs.triggered.connect(lambda: self.switch_view("settings"))
        settings_menu.addAction(act_prefs)

        help_menu = menu.addMenu("&Help")
        act_about = QAction("&About LabDesk", self)
        act_about.triggered.connect(self._about)
        help_menu.addAction(act_about)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About LabDesk",
            "LabDesk — desktop client for self-hosted GitLab.\n"
            "Linux / Flatpak · GPLv2+",
        )

    def _saved_active_view(self) -> str | None:
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            general = cfg.get("general") or {}
            view = general.get("active_ui_view")
            return str(view) if view else None
        except Exception:
            return None

    def _apply_saved_theme(self) -> None:
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            general = cfg.get("general") or {}
            apply_theme(str(general.get("theme") or "system"))
        except Exception:
            apply_theme("system")
