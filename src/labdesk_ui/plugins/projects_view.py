"""Projects browser view plugin."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.plugins import AppContext, register_view
from labdesk_ui.utils.helpers import format_error


class ProjectsView(QWidget):
    def __init__(self, parent: QWidget, ctx: AppContext) -> None:
        super().__init__(parent)
        self._ctx = ctx

        layout = QVBoxLayout(self)

        self.projects_meta = QLabel("Projects")
        layout.addWidget(self.projects_meta)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Project", "Default branch", "Visibility", "Last activity"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._open_local_repo)
        layout.addWidget(self.table, stretch=1)

        row = QHBoxLayout()
        self.btn_connect = QPushButton("Add / connect instance…")
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
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _load_cached_projects(self) -> None:
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            if not (cfg.get("instances") or []):
                self.table.setRowCount(0)
                self.projects_meta.setText("Projects (none — connect an instance)")
                return

            projects = labdesk_core.list_projects()
            self._fill_table(projects)
            fetched = projects[0].get("fetched_at") if projects else None
            self.projects_meta.setText(
                f"Projects ({len(projects)} cached"
                + (f", fetched_at {fetched}" if fetched else "")
                + ")"
            )
        except Exception as exc:
            code, msg = format_error(exc)
            self.projects_meta.setText(f"Projects — [{code}] {msg}")
            self.table.setRowCount(0)

    def _fill_table(self, projects: list) -> None:
        self.table.setRowCount(len(projects))
        for row, p in enumerate(projects):
            item = QTableWidgetItem(p.get("name_with_namespace") or p.get("name") or "")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, QTableWidgetItem(p.get("default_branch") or ""))
            self.table.setItem(row, 2, QTableWidgetItem(p.get("visibility") or ""))
            self.table.setItem(row, 3, QTableWidgetItem(p.get("last_activity_at") or ""))

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
