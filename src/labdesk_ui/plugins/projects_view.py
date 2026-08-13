"""Projects browser view plugin."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.plugins import AppContext, register_view
from labdesk_ui.utils.helpers import format_error


def filter_projects(projects: list, query: str) -> list:
    """Case-insensitive filter on name / namespace path fields."""
    q = (query or "").strip().lower()
    if not q:
        return list(projects)
    out = []
    for p in projects:
        if not isinstance(p, dict):
            continue
        hay = " ".join(
            str(p.get(k) or "")
            for k in ("name", "name_with_namespace", "path_with_namespace")
        ).lower()
        if q in hay:
            out.append(p)
    return out


class _ProjectsTableModel(QAbstractTableModel):
    _HEADERS = ("Project", "Default branch", "Visibility", "Last activity")
    _KEYS = ("name_with_namespace", "default_branch", "visibility", "last_activity_at")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list = []

    def set_rows(self, rows: list) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        p = self._rows[index.row()]
        key = self._KEYS[index.column()]
        if key == "name_with_namespace":
            return p.get("name_with_namespace") or p.get("name") or ""
        return p.get(key) or ""

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._HEADERS[section]
        return str(section + 1)

    def project_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._rows):
            p = self._rows[row]
            return p if isinstance(p, dict) else None
        return None


class ProjectsView(QWidget):
    def __init__(self, parent: QWidget, ctx: AppContext) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._all_projects: list = []
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(120)
        self._filter_timer.timeout.connect(self._apply_filter)

        layout = QVBoxLayout(self)

        self.projects_meta = QLabel("Projects")
        layout.addWidget(self.projects_meta)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter projects…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._on_filter_text_changed)
        layout.addWidget(self.filter_edit)

        self._model = _ProjectsTableModel(self)
        self.table = QTableView()
        self.table.setModel(self._model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 180)
        self.table.doubleClicked.connect(lambda _idx: self._open_local_repo())
        layout.addWidget(self.table, stretch=1)

        row = QHBoxLayout()
        self.btn_connect = QPushButton("Add host / account…")
        self.btn_connect.clicked.connect(self._ctx.show_connect_dialog)
        row.addWidget(self.btn_connect)

        self.btn_refresh_user = QPushButton("Refresh user")
        self.btn_refresh_user.clicked.connect(self._ctx.refresh_connection_banner)
        row.addWidget(self.btn_refresh_user)

        self.btn_refresh_projects = QPushButton("Refresh projects")
        self.btn_refresh_projects.clicked.connect(self._refresh_projects)
        row.addWidget(self.btn_refresh_projects)

        self.btn_open_local = QPushButton("Open local")
        self.btn_open_local.clicked.connect(self._open_local_repo)
        row.addWidget(self.btn_open_local)

        self.btn_add_existing = QPushButton("Add existing…")
        self.btn_add_existing.clicked.connect(self._add_existing_clone)
        row.addWidget(self.btn_add_existing)

        self.btn_open = QPushButton("Open in browser")
        self.btn_open.clicked.connect(self._open_in_browser)
        row.addWidget(self.btn_open)

        self.btn_clone = QPushButton("Clone")
        self.btn_clone.clicked.connect(lambda: self._clone_with_transport("https"))
        row.addWidget(self.btn_clone)

        self.btn_clone_ssh = QPushButton("Clone (SSH)")
        self.btn_clone_ssh.clicked.connect(lambda: self._clone_with_transport("ssh"))
        row.addWidget(self.btn_clone_ssh)

        layout.addLayout(row)

    def on_activated(self) -> None:
        self._load_cached_projects()
        if hasattr(self._ctx, "is_network_available"):
            self.set_network_available(self._ctx.is_network_available())

    def on_deactivated(self) -> None:
        return

    def set_network_available(self, available: bool) -> None:
        self.btn_refresh_projects.setEnabled(available)
        self.btn_refresh_user.setEnabled(True)  # allow probe to come back online
        self.btn_clone.setEnabled(available)
        self.btn_clone_ssh.setEnabled(available)
        tip = "Working offline — refresh disabled." if not available else ""
        self.btn_refresh_projects.setToolTip(tip)
        self.btn_clone.setToolTip(tip)
        self.btn_clone_ssh.setToolTip(tip)
        if not available:
            text = self.projects_meta.text()
            if "offline" not in text.lower():
                self.projects_meta.setText(f"{text} · offline (cached)")

    def _selected_project(self) -> dict | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return None
        return self._model.project_at(indexes[0].row())

    def _on_filter_text_changed(self, _text: str = "") -> None:
        self._filter_timer.start()

    def _load_cached_projects(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            import labdesk_core

            cfg = labdesk_core.load_config()
            if not (cfg.get("accounts") or cfg.get("instances")):
                return {"projects": [], "empty": True}
            projects = labdesk_core.list_projects()
            # Plain dicts so the UI thread never touches PyO3 objects.
            return {
                "projects": [dict(p) if hasattr(p, "items") else p for p in (projects or [])],
                "empty": False,
            }

        def on_ok(data) -> None:
            if (data or {}).get("empty"):
                self._all_projects = []
                self._model.set_rows([])
                self.projects_meta.setText("Projects (none — connect a host/account)")
                return
            self._all_projects = (data or {}).get("projects") or []
            self._apply_filter()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.projects_meta.setText(f"Projects — [{code}] {msg}")
            self._all_projects = []
            self._model.set_rows([])

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            status=self._ctx.set_detail,
            working_message="Loading projects…",
        )

    def _apply_filter(self, _text: str = "") -> None:
        filtered = filter_projects(self._all_projects, self.filter_edit.text())
        self._model.set_rows(filtered)
        total = len(self._all_projects)
        shown = len(filtered)
        fetched = None
        if self._all_projects:
            fetched = self._all_projects[0].get("fetched_at")
        q = self.filter_edit.text().strip()
        if q:
            meta = f"Projects (showing {shown} of {total}"
        else:
            meta = f"Projects ({total} cached"
        if fetched:
            meta += f", fetched_at {fetched}"
        meta += ")"
        if hasattr(self._ctx, "is_network_available") and not self._ctx.is_network_available():
            if "offline" not in meta.lower():
                meta += " · offline (cached)"
        self.projects_meta.setText(meta)

    def _refresh_projects(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            import labdesk_core

            return labdesk_core.refresh_projects()

        def on_ok(result) -> None:
            count = result.get("count", 0) if isinstance(result, dict) else 0
            self._ctx.set_detail(f"Refreshed {count} projects from API.")
            if hasattr(self._ctx, "set_network_available"):
                self._ctx.set_network_available(True)
            self._load_cached_projects()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self._ctx.set_detail(f"[{code}] {msg} — showing cache if available.")
            self._load_cached_projects()
            if code == "LD-NET-001" or code.startswith("LD-NET"):
                if hasattr(self._ctx, "set_network_available"):
                    self._ctx.set_network_available(False, detail=str(exc))
                return
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_refresh_projects, self.btn_clone, self.btn_clone_ssh],
            status=self._ctx.set_detail,
            working_message="Refreshing projects…",
        )

    def _open_in_browser(self) -> None:
        project = self._selected_project()
        if not project:
            return
        web = project.get("web_url")
        if not web:
            QMessageBox.information(self, "Open", "No web URL for this project.")
            return
        QDesktopServices.openUrl(QUrl(web))

    def _open_local_repo(self) -> None:
        project = self._selected_project()
        if not project:
            QMessageBox.information(self, "Open", "Select a project first.")
            return
        project_id = project.get("project_id")
        if project_id is None:
            return
        try:
            import labdesk_core

            info = labdesk_core.find_local_repo(int(project_id))
            if not info.get("found") or not info.get("exists"):
                reply = QMessageBox.question(
                    self,
                    "Open local",
                    "No registered clone for this project.\n\n"
                    "Add an existing folder now?",
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._add_existing_clone()
                return
            path = info.get("path")
            if info.get("source") == "discovered":
                self._ctx.set_detail(f"Found existing clone at {path}")
            title = project.get("path_with_namespace") or path
            self._ctx.open_repo_window(path, title=f"LabDesk — {title}")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _add_existing_clone(self) -> None:
        project = self._selected_project()
        if not project:
            QMessageBox.information(self, "Add existing", "Select a project first.")
            return
        project_id = project.get("project_id")
        if project_id is None:
            return

        start = ""
        try:
            import labdesk_core

            start = (labdesk_core.get_default_clone_dir().get("expanded") or "")
        except Exception:
            start = ""

        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select existing clone folder",
            start,
            QFileDialog.Option.ShowDirsOnly,
        )
        if not chosen:
            return

        try:
            import labdesk_core

            result = labdesk_core.register_local_repo(int(project_id), chosen)
            path = result.get("path") or chosen
            self._ctx.set_detail(f"Registered existing clone: {path}")
            title = project.get("path_with_namespace") or path
            reply = QMessageBox.question(
                self,
                "Add existing",
                f"Registered:\n{path}\n\nOpen it now?",
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._ctx.open_repo_window(path, title=f"LabDesk — {title}")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _clone_with_transport(self, transport: str) -> None:
        project = self._selected_project()
        if not project:
            QMessageBox.information(self, "Clone", "Select a project first.")
            return
        project_id = project.get("project_id")
        if project_id is None:
            QMessageBox.warning(self, "Clone", "Selected project has no id.")
            return

        name = project.get("path_with_namespace") or project.get("name") or str(project_id)
        reply = QMessageBox.question(
            self,
            "Clone",
            f"Clone {name} via {transport.upper()} into the clone folder?\n"
            "(If a clone already exists there, LabDesk will use it.)",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_clone.setEnabled(False)
        self.btn_clone_ssh.setEnabled(False)
        self._ctx.set_detail(f"Cloning {name} ({transport})…")

        from labdesk_ui.utils.async_jobs import run_in_background

        pid = int(project_id)

        def work():
            import labdesk_core

            return labdesk_core.clone_project(pid, transport)

        def on_ok(result) -> None:
            path = result.get("path") if isinstance(result, dict) else None
            if isinstance(result, dict) and result.get("adopted_existing"):
                self._ctx.set_detail(f"Using existing clone at {path}")
                QMessageBox.information(
                    self,
                    "Existing clone",
                    f"A git repository was already at:\n{path}\n\n"
                    "It has been registered with this project.",
                )
            else:
                self._ctx.set_detail(f"Cloned to {path}")
                QMessageBox.information(self, "Clone", f"Cloned to:\n{path}")

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self._ctx.set_detail(f"[{code}] {msg}")
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_clone, self.btn_clone_ssh, self.btn_refresh_projects],
            status=self._ctx.set_detail,
            working_message=f"Cloning {name} ({transport})…",
        )


def _factory(parent: QWidget, ctx: AppContext) -> QWidget:
    return ProjectsView(parent, ctx)


register_view("projects", "Projects", _factory, order=10)
