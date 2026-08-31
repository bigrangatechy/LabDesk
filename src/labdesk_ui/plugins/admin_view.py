"""Admin view — instance runners/agents + user list (Slice J)."""

from __future__ import annotations

from labdesk_ui.i18n import tr

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.plugins import AppContext, register_view
from labdesk_ui.utils.forge_labels import forge_info, open_in_label
from labdesk_ui.utils.helpers import format_error
from labdesk_ui.utils.open_external import open_url


def _runner_row_text(row: dict) -> str:
    desc = (row.get("description") or row.get("id") or "?").strip()
    bits = [desc]
    if row.get("online") is True:
        bits.append("online")
    elif row.get("online") is False:
        bits.append("offline")
    if row.get("paused") is True or row.get("active") is False:
        bits.append("paused")
    elif row.get("active") is True:
        bits.append("active")
    tags = row.get("tag_list") or []
    if tags:
        bits.append("tags:" + ",".join(str(t) for t in tags[:6]))
    scope = row.get("scope")
    if scope:
        bits.append(str(scope))
    return " — ".join(bits)


def _user_row_text(row: dict) -> str:
    name = row.get("name") or ""
    user = row.get("username") or "?"
    label = f"{user}" if not name else f"{user} ({name})"
    extras = []
    if row.get("is_admin"):
        extras.append("admin")
    if row.get("state"):
        extras.append(str(row["state"]))
    if extras:
        label += " — " + ", ".join(extras)
    return label


class AdminView(QWidget):
    def __init__(self, parent: QWidget, ctx: AppContext) -> None:
        super().__init__(parent)
        self._ctx = ctx

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        back = QPushButton(tr("← Back to Projects"))
        back.clicked.connect(lambda: self._ctx.switch_view("projects"))
        header.addWidget(back)
        self.title = QLabel(tr("Admin"))
        header.addWidget(self.title, stretch=1)
        layout.addLayout(header)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_runners_tab(), tr("Runners"))
        self.tabs.addTab(self._build_users_tab(), tr("Users"))
        layout.addWidget(self.tabs, stretch=1)

    def _build_runners_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.runners = QListWidget()
        self.runners.currentItemChanged.connect(self._on_runner_selected)
        layout.addWidget(self.runners, stretch=1)

        row = QHBoxLayout()
        self.btn_runners_refresh = QPushButton(tr("Refresh"))
        self.btn_runners_refresh.clicked.connect(self._load_runners)
        row.addWidget(self.btn_runners_refresh)
        self.btn_pause = QPushButton(tr("Pause"))
        self.btn_pause.clicked.connect(lambda: self._set_paused(True))
        row.addWidget(self.btn_pause)
        self.btn_enable = QPushButton(tr("Enable"))
        self.btn_enable.clicked.connect(lambda: self._set_paused(False))
        row.addWidget(self.btn_enable)
        self.btn_delete = QPushButton(tr("Delete…"))
        self.btn_delete.clicked.connect(self._delete_runner)
        row.addWidget(self.btn_delete)
        self.btn_open_runner = QPushButton(tr("Open in forge"))
        self.btn_open_runner.clicked.connect(self._open_selected_runner)
        row.addWidget(self.btn_open_runner)
        self.btn_open_runners_admin = QPushButton(tr("Open admin…"))
        self.btn_open_runners_admin.clicked.connect(self._open_runners_admin)
        row.addWidget(self.btn_open_runners_admin)
        row.addStretch(1)
        layout.addLayout(row)
        self._set_runner_actions(False)
        return page

    def _build_users_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.users = QListWidget()
        layout.addWidget(self.users, stretch=1)
        row = QHBoxLayout()
        self.btn_users_refresh = QPushButton(tr("Refresh"))
        self.btn_users_refresh.clicked.connect(self._load_users)
        row.addWidget(self.btn_users_refresh)
        self.btn_open_user = QPushButton(tr("Open user…"))
        self.btn_open_user.clicked.connect(self._open_selected_user)
        self.btn_open_user.setEnabled(False)
        row.addWidget(self.btn_open_user)
        self.btn_open_users_admin = QPushButton(tr("Open admin…"))
        self.btn_open_users_admin.clicked.connect(self._open_users_admin)
        row.addWidget(self.btn_open_users_admin)
        row.addStretch(1)
        layout.addLayout(row)
        self.users.currentItemChanged.connect(
            lambda cur, _prev: self.btn_open_user.setEnabled(
                bool(cur and isinstance(cur.data(Qt.ItemDataRole.UserRole), dict))
            )
        )
        return page

    def on_activated(self) -> None:
        info = forge_info()
        label = info.get("runners_label") or "Runners"
        self.tabs.setTabText(0, str(label))
        self.title.setText(f"Admin — {info.get('display_name') or 'forge'}")
        self.btn_open_runner.setText(open_in_label(info))
        can_pause = bool(info.get("supports_runner_pause"))
        can_delete = bool(info.get("supports_runner_delete"))
        self.btn_pause.setVisible(can_pause)
        self.btn_enable.setVisible(can_pause)
        self.btn_delete.setVisible(can_delete)
        self._load_runners()
        self._load_users()

    def on_deactivated(self) -> None:
        return

    def _set_runner_actions(self, enabled: bool) -> None:
        info = forge_info()
        self.btn_pause.setEnabled(enabled and bool(info.get("supports_runner_pause")))
        self.btn_enable.setEnabled(enabled and bool(info.get("supports_runner_pause")))
        self.btn_delete.setEnabled(enabled and bool(info.get("supports_runner_delete")))
        self.btn_open_runner.setEnabled(enabled)

    def _selected_runner(self) -> dict | None:
        item = self.runners.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _on_runner_selected(self, current, _prev) -> None:
        self._set_runner_actions(
            bool(current and isinstance(current.data(Qt.ItemDataRole.UserRole), dict))
        )

    def _load_runners(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            import labdesk_core

            return list(labdesk_core.list_instance_runners() or [])

        def on_ok(rows: list) -> None:
            self.runners.clear()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item = QListWidgetItem(_runner_row_text(row))
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.runners.addItem(item)
            label = forge_info().get("runners_label") or "Runners"
            self.status.setText(f"{len(rows)} {str(label).lower()} (instance / owned).")
            self._set_runner_actions(False)

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.runners.clear()
            self.status.setText(f"[{code}] {msg}")
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_runners_refresh],
            status=self.status.setText,
            working_message=tr("Loading runners…"),
        )

    def _load_users(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            import labdesk_core

            return list(labdesk_core.list_admin_users() or [])

        def on_ok(rows: list) -> None:
            self.users.clear()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item = QListWidgetItem(_user_row_text(row))
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.users.addItem(item)
            note = f"{len(rows)} user(s)."
            if not rows:
                note += " Admin token may be required."
            # Prefer runners status unless users failed earlier; append lightly.
            cur = self.status.text() or ""
            if "runner" in cur.lower() or "agent" in cur.lower():
                self.status.setText(f"{cur} {note}")
            else:
                self.status.setText(note)

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.users.clear()
            QMessageBox.warning(
                self,
                f"Error {code}",
                f"Users list failed (admin token often required).\n[{code}] {msg}\n\n{exc}",
            )

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_users_refresh],
            status=lambda _t: None,
            working_message="",
        )

    def _set_paused(self, paused: bool) -> None:
        row = self._selected_runner()
        if not row:
            return
        rid = str(row.get("id") or "")
        if not rid:
            return
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            import labdesk_core

            return labdesk_core.set_runner_paused(rid, paused)

        def on_ok(_r) -> None:
            self._load_runners()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_pause, self.btn_enable],
            status=self.status.setText,
            working_message=tr("Updating runner…"),
        )

    def _delete_runner(self) -> None:
        row = self._selected_runner()
        if not row:
            return
        rid = str(row.get("id") or "")
        desc = row.get("description") or rid
        reply = QMessageBox.question(
            self,
            tr("Delete runner?"),
            f"Delete runner '{desc}'?\nThis cannot be undone from LabDesk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            import labdesk_core

            labdesk_core.delete_runner(rid)
            return True

        def on_ok(_r) -> None:
            self._load_runners()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_delete],
            status=self.status.setText,
            working_message=tr("Deleting runner…"),
        )

    def _open_selected_runner(self) -> None:
        row = self._selected_runner()
        url = (row or {}).get("web_url") if row else None
        if not url:
            self._open_runners_admin()
            return
        try:
            open_url(url)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _open_runners_admin(self) -> None:
        try:
            import labdesk_core

            urls = dict(labdesk_core.admin_web_urls() or {})
            url = urls.get("runners")
            if not url:
                raise RuntimeError("No admin runners URL")
            open_url(url)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _open_selected_user(self) -> None:
        item = self.users.currentItem()
        row = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(row, dict):
            return
        url = row.get("web_url")
        if not url:
            self._open_users_admin()
            return
        try:
            open_url(url)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _open_users_admin(self) -> None:
        try:
            import labdesk_core

            urls = dict(labdesk_core.admin_web_urls() or {})
            url = urls.get("users")
            if not url:
                raise RuntimeError("No admin users URL")
            open_url(url)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")


def _factory(parent: QWidget, ctx: AppContext) -> QWidget:
    return AdminView(parent, ctx)


register_view("admin", tr("Admin"), _factory, order=40)
