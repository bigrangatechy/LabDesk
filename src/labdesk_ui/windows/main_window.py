"""Main window — pluggable views, classic/sidebar shells, menubar."""

from __future__ import annotations

from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.plugins import ensure_builtin_views, list_views
from labdesk_ui.utils.helpers import format_error
from labdesk_ui.utils.theme import apply_theme
from labdesk_ui.windows.instance_config import InstanceConfigDialog
from labdesk_ui.windows.repo_window import RepoWindow

_SHELL_STYLE = """
QMainWindow {
    background: palette(window);
}
QLabel#LabDeskTitle {
    font-size: 18px;
    font-weight: 600;
    padding: 2px 0 6px 0;
}
QLabel#LabDeskStatus {
    padding: 4px 0;
}
QLabel#LabDeskDetail {
    color: palette(mid);
    padding-bottom: 6px;
}
QPushButton.NavButton {
    padding: 8px 14px;
    text-align: left;
    border: 1px solid palette(mid);
    border-radius: 4px;
    background: palette(button);
}
QPushButton.NavButton:checked {
    background: palette(highlight);
    color: palette(highlighted-text);
    border-color: palette(highlight);
}
QFrame#SideRail {
    border-right: 1px solid palette(mid);
    padding-right: 8px;
    min-width: 140px;
    max-width: 200px;
}
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LabDesk")
        self.resize(1000, 640)
        self.setStyleSheet(_SHELL_STYLE)
        self._repo_windows: list[RepoWindow] = []
        self._view_widgets: dict[str, QWidget] = {}
        self._active_view_id: str | None = None
        self._view_actions: dict[str, QAction] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._shell = "classic"

        ensure_builtin_views()

        root = QWidget()
        self.setCentralWidget(root)
        self._root_layout = QVBoxLayout(root)
        self._root_layout.setContentsMargins(14, 12, 14, 12)
        self._root_layout.setSpacing(8)

        title = QLabel("LabDesk")
        title.setObjectName("LabDeskTitle")
        self._root_layout.addWidget(title)

        self.status = QLabel("Loading…")
        self.status.setObjectName("LabDeskStatus")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._root_layout.addWidget(self.status)

        self.detail = QLabel("")
        self.detail.setObjectName("LabDeskDetail")
        self.detail.setWordWrap(True)
        self._root_layout.addWidget(self.detail)

        self._body = QWidget()
        self._body_layout = QHBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(12)
        self._root_layout.addWidget(self._body, stretch=1)

        self._nav_host = QWidget()
        self._nav_layout = QVBoxLayout(self._nav_host)
        self._nav_layout.setContentsMargins(0, 0, 0, 0)
        self._nav_layout.setSpacing(6)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for registered in list_views():
            btn = QPushButton(registered.title)
            btn.setCheckable(True)
            btn.setProperty("class", "NavButton")
            btn.setStyleSheet("")  # use QSS class via polish
            btn.setObjectName("NavButton")
            btn.setProperty("cssClass", "NavButton")
            btn.setFlat(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda checked=False, vid=registered.id: self.switch_view(vid)
            )
            self._nav_group.addButton(btn)
            self._nav_buttons[registered.id] = btn

        self.stack = QStackedWidget()
        for registered in list_views():
            widget = registered.factory(self, self)
            self._view_widgets[registered.id] = widget
            self.stack.addWidget(widget)

        self._apply_shell(self._saved_ui_shell(), rebuild_nav=True)

        self._build_menubar()
        self._apply_saved_theme()
        self.refresh_connection_banner()

        initial = self._saved_active_view() or "projects"
        if initial not in self._view_widgets:
            initial = next(iter(self._view_widgets), "projects")
        self.switch_view(initial, persist=False)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _apply_shell(self, shell: str, *, rebuild_nav: bool = False) -> None:
        name = (shell or "classic").strip().lower()
        if name not in ("classic", "sidebar"):
            name = "classic"
        self._shell = name
        self._clear_layout(self._body_layout)
        self._clear_layout(self._nav_layout)

        for btn in self._nav_buttons.values():
            btn.setParent(None)
            # Qt StyleSheet class selector for QPushButton.NavButton needs
            # the class property set via setProperty + polish — use objectName.
            btn.setObjectName("NavBtn")
            btn.setStyleSheet(
                "QPushButton#NavBtn { padding: 8px 14px; text-align: left; "
                "border: 1px solid palette(mid); border-radius: 4px; }"
                "QPushButton#NavBtn:checked { background: palette(highlight); "
                "color: palette(highlighted-text); border-color: palette(highlight); }"
            )

        if name == "sidebar":
            rail = QFrame()
            rail.setObjectName("SideRail")
            rail_layout = QVBoxLayout(rail)
            rail_layout.setContentsMargins(0, 0, 8, 0)
            rail_layout.setSpacing(6)
            rail_label = QLabel("Views")
            f = QFont()
            f.setBold(True)
            rail_label.setFont(f)
            rail_layout.addWidget(rail_label)
            for registered in list_views():
                btn = self._nav_buttons[registered.id]
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                rail_layout.addWidget(btn)
            rail_layout.addStretch(1)
            self._body_layout.addWidget(rail)
            self._body_layout.addWidget(self.stack, stretch=1)
        else:
            # classic — horizontal nav above content, stacked vertically in body
            classic_col = QVBoxLayout()
            classic_col.setContentsMargins(0, 0, 0, 0)
            classic_col.setSpacing(8)
            nav_row = QHBoxLayout()
            nav_row.setSpacing(8)
            for registered in list_views():
                btn = self._nav_buttons[registered.id]
                btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                nav_row.addWidget(btn)
            nav_row.addStretch(1)
            classic_col.addLayout(nav_row)
            classic_col.addWidget(self.stack, stretch=1)
            wrap = QWidget()
            wrap.setLayout(classic_col)
            self._body_layout.addWidget(wrap, stretch=1)

        _ = rebuild_nav

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

    def set_ui_shell(self, shell: str, *, persist: bool = True) -> None:
        self._apply_shell(shell, rebuild_nav=True)
        act = self._shell_actions.get(self._shell)
        if act is not None:
            act.setChecked(True)
        if self._active_view_id:
            self.switch_view(self._active_view_id, persist=False)
        if persist:
            try:
                import labdesk_core

                labdesk_core.set_ui_shell(self._shell)
                self.set_detail(f"UI shell: {self._shell}")
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

        view_menu.addSeparator()
        shell_group = QActionGroup(self)
        shell_group.setExclusive(True)
        self._shell_actions: dict[str, QAction] = {}
        for shell_id, label in (("classic", "Classic layout"), ("sidebar", "Sidebar layout")):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(self._shell == shell_id)
            act.triggered.connect(
                lambda checked=False, s=shell_id: self.set_ui_shell(s)
            )
            shell_group.addAction(act)
            view_menu.addAction(act)
            self._shell_actions[shell_id] = act
        self._shell_group = shell_group

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
            "Linux / Flatpak · GPLv2+\n"
            "Updates: Flatpak remote from Ranga/flatpaks",
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

    def _saved_ui_shell(self) -> str:
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            general = cfg.get("general") or {}
            return str(general.get("ui_shell") or "classic")
        except Exception:
            return "classic"

    def _apply_saved_theme(self) -> None:
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            general = cfg.get("general") or {}
            apply_theme(str(general.get("theme") or "system"))
        except Exception:
            apply_theme("system")
