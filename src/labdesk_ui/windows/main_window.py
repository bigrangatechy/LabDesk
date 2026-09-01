"""Main window — pluggable views, classic/sidebar shells, menubar."""

from __future__ import annotations

from labdesk_ui.i18n import tr

from pathlib import Path

from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QFont, QKeySequence
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.plugins import ensure_builtin_views, list_views
from labdesk_ui.utils.forge_labels import instance_label, pr_label
from labdesk_ui.utils.helpers import format_error
from labdesk_ui.utils.theme import apply_theme
from labdesk_ui.windows.instance_config import InstanceConfigDialog
from labdesk_ui.windows.repo_window import RepoWindow

_SHELL_STYLE = """
QMainWindow {
    background: palette(window);
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
        self.setWindowTitle(tr("LabDesk"))
        self.resize(1000, 640)
        self.setStyleSheet(_SHELL_STYLE)
        self._repo_windows: list[RepoWindow] = []
        self._view_widgets: dict[str, QWidget] = {}
        self._active_view_id: str | None = None
        self._view_actions: dict[str, QAction] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._shell = "classic"
        self._online = True
        self._startup_recovery: dict | None = None

        ensure_builtin_views()

        root = QWidget()
        self.setCentralWidget(root)
        self._root_layout = QVBoxLayout(root)
        self._root_layout.setContentsMargins(14, 12, 14, 12)
        self._root_layout.setSpacing(8)

        self.status = QLabel(tr("Loading…"))
        self.status.setObjectName("LabDeskStatus")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._root_layout.addWidget(self.status)

        switch_row = QHBoxLayout()
        switch_row.addWidget(QLabel(tr("Host")))
        self.combo_instance = QComboBox()
        self.combo_instance.setMinimumWidth(180)
        self.combo_instance.currentIndexChanged.connect(self._on_instance_combo)
        switch_row.addWidget(self.combo_instance, stretch=1)
        switch_row.addWidget(QLabel(tr("Account")))
        self.combo_account = QComboBox()
        self.combo_account.setMinimumWidth(140)
        self.combo_account.currentIndexChanged.connect(self._on_account_combo)
        switch_row.addWidget(self.combo_account, stretch=1)
        self._root_layout.addLayout(switch_row)
        self._switching = False

        self.detail = QLabel("")
        self.detail.setObjectName("LabDeskDetail")
        self.detail.setWordWrap(True)
        self._root_layout.addWidget(self.detail)

        self._body = QWidget()
        self._body_layout = QHBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(12)
        self._root_layout.addWidget(self._body, stretch=1)

        # Permanent hosts — never deleteLater these (shell switch only reparents).
        self._nav_host = QFrame()
        self._nav_host.setObjectName("NavHost")
        self._nav_host.setFrameShape(QFrame.Shape.NoFrame)
        self._column = QWidget()
        self._column_layout = QVBoxLayout(self._column)
        self._column_layout.setContentsMargins(0, 0, 0, 0)
        self._column_layout.setSpacing(8)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._rebuild_nav_buttons()

        self.stack = QStackedWidget()
        for registered in list_views():
            widget = registered.factory(self, self)
            self._view_widgets[registered.id] = widget
            self.stack.addWidget(widget)

        self._apply_shell(self._saved_ui_shell())

        self._build_menubar()
        self._apply_saved_theme()
        self.refresh_connection_banner()

        initial = self._saved_active_view() or "projects"
        if initial not in self._view_widgets:
            initial = next(iter(self._view_widgets), "projects")
        self.switch_view(initial, persist=False)

    def _permanent_widgets(self) -> set[QWidget]:
        return {self.stack, self._nav_host, self._column}

    def _park_widget(self, w: QWidget) -> None:
        """Keep a permanent host alive without covering the central widget.

        Parenting leftovers to ``QMainWindow`` itself makes them float over the
        central widget and eat all mouse/keyboard input (sidebar shell used to
        leave ``_column`` stuck like that).
        """
        w.hide()
        w.setParent(self._body)

    def _take_layout_widgets(self, layout) -> None:
        """Detach all items from a layout without deleting permanent widgets."""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is None:
                child = item.layout()
                if child is not None:
                    self._take_layout_widgets(child)
                continue
            if w in self._permanent_widgets():
                self._park_widget(w)
            else:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_nav_buttons(self) -> None:
        for btn in list(self._nav_buttons.values()):
            self._nav_group.removeButton(btn)
            btn.setParent(None)
            btn.deleteLater()
        self._nav_buttons.clear()

        for registered in list_views():
            btn = QPushButton(registered.title)
            btn.setCheckable(True)
            btn.setObjectName("NavBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton#NavBtn { padding: 8px 14px; text-align: left; "
                "border: 1px solid palette(mid); border-radius: 4px; }"
                "QPushButton#NavBtn:checked { background: palette(highlight); "
                "color: palette(highlighted-text); border-color: palette(highlight); }"
            )
            btn.clicked.connect(
                lambda checked=False, vid=registered.id: self.switch_view(vid)
            )
            self._nav_group.addButton(btn)
            self._nav_buttons[registered.id] = btn

    def _set_nav_orientation(self, *, vertical: bool) -> None:
        # Replace layout safely: move the old one onto a throwaway widget.
        old = self._nav_host.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget()
                if w is not None:
                    # Drop labels / old buttons — never parent them to QMainWindow.
                    w.setParent(None)
                    w.deleteLater()
            holder = QWidget()
            holder.setLayout(old)
            holder.deleteLater()

        if vertical:
            layout = QVBoxLayout(self._nav_host)
            layout.setContentsMargins(0, 0, 8, 0)
            layout.setSpacing(6)
            label = QLabel(tr("Views"))
            f = QFont()
            f.setBold(True)
            label.setFont(f)
            layout.addWidget(label)
            for registered in list_views():
                btn = self._nav_buttons[registered.id]
                btn.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
                layout.addWidget(btn)
            layout.addStretch(1)
            self._nav_host.setObjectName("SideRail")
            self._nav_host.setMinimumWidth(140)
            self._nav_host.setMaximumWidth(200)
        else:
            layout = QHBoxLayout(self._nav_host)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            for registered in list_views():
                btn = self._nav_buttons[registered.id]
                btn.setSizePolicy(
                    QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
                )
                layout.addWidget(btn)
            layout.addStretch(1)
            self._nav_host.setObjectName("NavHost")
            self._nav_host.setMinimumWidth(0)
            self._nav_host.setMaximumWidth(16777215)

    def _apply_shell(self, shell: str) -> None:
        name = (shell or "classic").strip().lower()
        if name not in ("classic", "sidebar"):
            name = "classic"
        self._shell = name

        # Detach permanent hosts before rearranging — never destroy them.
        self._take_layout_widgets(self._body_layout)
        self._take_layout_widgets(self._column_layout)
        self._park_widget(self.stack)
        self._park_widget(self._nav_host)
        self._park_widget(self._column)

        self._rebuild_nav_buttons()
        self._set_nav_orientation(vertical=(name == "sidebar"))

        if name == "sidebar":
            # Classic column host stays parked/hidden so it cannot overlay clicks.
            self._body_layout.addWidget(self._nav_host)
            self._body_layout.addWidget(self.stack, stretch=1)
            self._nav_host.show()
            self.stack.show()
        else:
            self._column_layout.addWidget(self._nav_host)
            self._column_layout.addWidget(self.stack, stretch=1)
            self._body_layout.addWidget(self._column, stretch=1)
            self._column.show()
            self._nav_host.show()
            self.stack.show()

    # --- AppContext API for plugins ---------------------------------

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_detail(self, text: str) -> None:
        self.detail.setText(text)

    def open_repo_window(self, path: str, title: str | None = None) -> None:
        try:
            resolved = str(Path(path).resolve())
        except OSError:
            resolved = path
        self._prune_repo_windows_silent()
        for win in list(self._repo_windows):
            if not self._repo_window_alive(win):
                continue
            try:
                same = win.repo_path == resolved
            except RuntimeError:
                continue
            if not same:
                continue
            # Only reuse a still-visible window. After Close, WA_DeleteOnClose
            # leaves a Python wrapper whose repo_path still works but C++ is
            # gone/dying — raising that shows "Internal C++ object already deleted".
            try:
                visible = win.isVisible()
            except RuntimeError:
                visible = False
            if visible:
                self._focus_repo_window(win)
                try:
                    import labdesk_core

                    if hasattr(labdesk_core, "touch_local_repo_opened"):
                        labdesk_core.touch_local_repo_opened(resolved)
                except Exception:
                    pass
                self._rebuild_recent_repos_menu()
                return
            try:
                self._repo_windows.remove(win)
            except ValueError:
                pass
            break
        win = RepoWindow(resolved, title=title or f"LabDesk — {resolved}", parent=None)
        win.set_network_available(self._online)
        win.destroyed.connect(self._prune_repo_windows)
        self._repo_windows.append(win)
        try:
            import labdesk_core

            if hasattr(labdesk_core, "touch_local_repo_opened"):
                labdesk_core.touch_local_repo_opened(resolved)
        except Exception:
            pass
        win.show()
        win.raise_()
        win.activateWindow()
        self._rebuild_window_menu()
        self._rebuild_recent_repos_menu()

    @staticmethod
    def _repo_window_alive(win: RepoWindow) -> bool:
        try:
            from shiboken6 import isValid

            return bool(isValid(win))
        except Exception:
            try:
                _ = win.objectName()
                return True
            except RuntimeError:
                return False

    def _find_repo_window(self, resolved_path: str) -> RepoWindow | None:
        self._prune_repo_windows_silent()
        for win in self._repo_windows:
            if not self._repo_window_alive(win):
                continue
            try:
                if win.repo_path == resolved_path and win.isVisible():
                    return win
            except RuntimeError:
                continue
        return None

    def _prune_repo_windows(self, *_args) -> None:
        alive: list[RepoWindow] = []
        for win in self._repo_windows:
            if self._repo_window_alive(win):
                alive.append(win)
        self._repo_windows = alive
        self._rebuild_window_menu()

    def _focus_repo_window(self, win: RepoWindow) -> None:
        if not self._repo_window_alive(win):
            self._prune_repo_windows()
            return
        try:
            win.raise_()
            win.activateWindow()
            win.showNormal()
        except RuntimeError:
            self._prune_repo_windows()

    def _rebuild_window_menu(self) -> None:
        menu = getattr(self, "_window_menu", None)
        if menu is None:
            return
        menu.clear()
        act_main = QAction(tr("Main window"), self)
        act_main.triggered.connect(self._focus_main_window)
        menu.addAction(act_main)
        self._prune_repo_windows_silent()
        if not self._repo_windows:
            return
        menu.addSeparator()
        for win in self._repo_windows:
            if not self._repo_window_alive(win):
                continue
            try:
                if not win.isVisible():
                    continue
                label = win.windowTitle() or win.repo_path
                act = QAction(label, self)
                act.triggered.connect(
                    lambda checked=False, w=win: self._focus_repo_window(w)
                )
                menu.addAction(act)
            except RuntimeError:
                continue

    def _prune_repo_windows_silent(self) -> None:
        self._repo_windows = [
            win for win in self._repo_windows if self._repo_window_alive(win)
        ]

    def _focus_main_window(self) -> None:
        self.raise_()
        self.activateWindow()
        self.showNormal()

    def closeEvent(self, event: QCloseEvent) -> None:
        # Closing the main window closes owned repo windows (WA_DeleteOnClose).
        from labdesk_ui.utils.async_jobs import drain_async_jobs

        for win in list(self._repo_windows):
            if not self._repo_window_alive(win):
                continue
            try:
                drain_async_jobs(win, timeout_ms=1500)
                win.close()
            except RuntimeError:
                continue
        self._repo_windows.clear()
        for view in list(self._view_widgets.values()):
            try:
                drain_async_jobs(view, timeout_ms=500)
            except Exception:
                pass
        drain_async_jobs(self, timeout_ms=500)
        super().closeEvent(event)

    def is_network_available(self) -> bool:
        return self._online

    def set_network_available(self, available: bool, *, detail: str | None = None) -> None:
        self._online = available
        projects = self._view_widgets.get("projects")
        if projects is not None and hasattr(projects, "set_network_available"):
            projects.set_network_available(available)
        self._prune_repo_windows_silent()
        for win in self._repo_windows:
            if not self._repo_window_alive(win):
                continue
            try:
                win.set_network_available(available)
            except RuntimeError:
                continue
        self._prune_repo_windows()
        if not available and detail:
            self.detail.setText(detail)

    def open_repository_dialog(self) -> None:
        start = ""
        try:
            import labdesk_core

            start = labdesk_core.get_default_clone_dir().get("expanded") or ""
        except Exception:
            start = ""
        chosen = QFileDialog.getExistingDirectory(
            self,
            tr("Open existing repository"),
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

    def show_connect_dialog(self, *, mode: str | None = None) -> None:
        dlg = InstanceConfigDialog(self, mode=mode)
        if dlg.exec() != InstanceConfigDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        try:
            import labdesk_core

            if vals.get("mode") == InstanceConfigDialog.MODE_ADD_ACCOUNT:
                result = labdesk_core.add_account(
                    vals["instance_id"],
                    vals["account_name"],
                    vals["pat"],
                )
            else:
                result = labdesk_core.connect_account(
                    vals["host_name"],
                    vals["account_name"],
                    vals["base_url"],
                    vals["pat"],
                    vals["ssl_mode"],
                    vals.get("forge") or "gitlab",
                )
            user = result.get("user") or {}
            count = result.get("project_count", 0)
            QMessageBox.information(
                self,
                tr("Connected"),
                f"Signed in as {user.get('name')} (@{user.get('username')}).\n"
                f"Cached {count} projects.",
            )
            self.refresh_account_switchers()
            self.refresh_connection_banner()
            projects = self._view_widgets.get("projects")
            if projects is not None and hasattr(projects, "on_activated"):
                projects.on_activated()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def refresh_account_switchers(self) -> None:
        if not hasattr(self, "combo_instance"):
            return
        self._switching = True
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            general = cfg.get("general") or {}
            active_iid = general.get("active_instance_id")
            active_aid = general.get("active_account_id")
            instances = cfg.get("instances") or []
            accounts = cfg.get("accounts") or []

            self.combo_instance.blockSignals(True)
            self.combo_instance.clear()
            for inst in instances:
                label = instance_label(inst)
                self.combo_instance.addItem(label, inst.get("id"))
            if active_iid:
                idx = self.combo_instance.findData(active_iid)
                if idx >= 0:
                    self.combo_instance.setCurrentIndex(idx)
            self.combo_instance.blockSignals(False)

            self._fill_account_combo(accounts, active_iid, active_aid)
        except Exception:
            self.combo_instance.clear()
            self.combo_account.clear()
        finally:
            self._switching = False

    def _fill_account_combo(
        self, accounts: list, instance_id: str | None, active_aid: str | None
    ) -> None:
        self.combo_account.blockSignals(True)
        self.combo_account.clear()
        for acc in accounts:
            if instance_id and acc.get("instance_id") != instance_id:
                continue
            uname = acc.get("username")
            label = acc.get("name") or "Account"
            if uname:
                label = f"{label} (@{uname})"
            self.combo_account.addItem(label, acc.get("id"))
        if active_aid:
            idx = self.combo_account.findData(active_aid)
            if idx >= 0:
                self.combo_account.setCurrentIndex(idx)
        self.combo_account.blockSignals(False)

    def _on_instance_combo(self, _index: int = 0) -> None:
        if self._switching:
            return
        iid = self.combo_instance.currentData()
        if not iid:
            return
        try:
            import labdesk_core

            accounts = labdesk_core.list_accounts(iid) or []
            if not accounts:
                self.combo_account.clear()
                return
            # Prefer keeping current account if it belongs to this host.
            current = self.combo_account.currentData()
            pick = next((a for a in accounts if a.get("id") == current), accounts[0])
            self._switching = True
            self._fill_account_combo(accounts, iid, pick.get("id"))
            self._switching = False
            result = labdesk_core.set_active_account(pick["id"])
            self._after_account_switch(result)
        except Exception as exc:
            code, msg = format_error(exc)
            self.set_detail(f"[{code}] {msg}")

    def _on_account_combo(self, _index: int = 0) -> None:
        if self._switching:
            return
        aid = self.combo_account.currentData()
        if not aid:
            return
        try:
            import labdesk_core

            result = labdesk_core.set_active_account(aid)
            self._after_account_switch(result)
        except Exception as exc:
            code, msg = format_error(exc)
            self.set_detail(f"[{code}] {msg}")

    def _after_account_switch(self, result) -> None:
        self.refresh_connection_banner()
        projects = self._view_widgets.get("projects")
        if projects is not None and hasattr(projects, "on_activated"):
            projects.on_activated()
        retargeted = 0
        base_url = ""
        if isinstance(result, dict):
            try:
                retargeted = int(result.get("retargeted") or 0)
            except (TypeError, ValueError):
                retargeted = 0
            base_url = str(result.get("base_url") or "")
        if retargeted:
            host = base_url or "the selected host"
            self.set_detail(
                f"Switched host. Updated origin on {retargeted} local "
                f"clone(s) to use {host}."
            )
            self._prune_repo_windows_silent()
            for win in list(self._repo_windows):
                if self._repo_window_alive(win) and hasattr(win, "refresh"):
                    try:
                        win.refresh()
                    except Exception:
                        pass
        elif base_url:
            self.set_detail(f"Active host: {base_url}")

    def refresh_connection_banner(self) -> None:
        self.refresh_account_switchers()
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            accounts = cfg.get("accounts") or []
            if not accounts:
                self.status.setText(
                    tr("No forge account configured yet.\n"
                    "Add a self-hosted host and account to get started.")
                )
                self.detail.setText("")
                self.set_network_available(True)
                return
        except Exception as exc:
            code, msg = format_error(exc)
            self.status.setText(f"[{code}] {msg}")
            self.detail.setText(str(exc))
            return

        from labdesk_ui.utils.async_jobs import run_in_background

        self.set_detail("Working…")

        def work():
            import labdesk_core

            return labdesk_core.fetch_current_user()

        def on_ok(user) -> None:
            acc = user.get("account_name") or ""
            self.status.setText(
                f"Connected as {user.get('name')} (@{user.get('username')})"
                + (f" — {acc}" if acc else "")
                + f"\nHost: {user.get('instance_name')} — {user.get('base_url')}"
            )
            self.detail.setText("")
            self.set_network_available(True)

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            if code == "LD-NET-001":
                kind = pr_label()
                self.status.setText(
                    f"Working offline — [{code}] {msg}\n"
                    f"Local git still works; push / {kind.lower()} / "
                    "project refresh are disabled."
                )
                self.detail.setText(str(exc))
                self.set_network_available(False, detail=str(exc))
            else:
                self.status.setText(f"[{code}] {msg}")
                self.detail.setText(str(exc))
                if code.startswith("LD-NET"):
                    self.set_network_available(False, detail=str(exc))
                else:
                    self.set_network_available(True)

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            status=self.set_detail,
        )

    def show_startup_recovery_if_needed(self) -> None:
        info = self._startup_recovery
        if not info:
            return
        self._startup_recovery = None
        code = info.get("code") or "LD-CFG-010"
        detail = info.get("detail") or ""
        QMessageBox.warning(
            self,
            f"Startup recovery ({code})",
            f"[{code}] Startup hung; config was reset to last known good.\n\n"
            f"{detail}".strip(),
        )

    def prompt_first_run_if_needed(self) -> None:
        """Offer Add/connect when no accounts exist yet."""
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            if cfg.get("accounts") or cfg.get("instances"):
                return
        except Exception:
            return
        reply = QMessageBox.question(
            self,
            tr("Welcome to LabDesk"),
            tr("No forge account is configured yet.\n\n"
            "Add a self-hosted host and account to get started?"),
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.show_connect_dialog()

    def check_updates_on_startup_if_enabled(self) -> None:
        """Quiet Flatpak update check when general.check_for_updates is true.

        Must not run ``flatpak`` on the UI thread — ``update --appstream`` can
        block for minutes and freezes the whole shell (Projects is the default
        view, so it looks like the projects list is hung).
        """
        try:
            import labdesk_core

            cfg = labdesk_core.load_config()
            general = cfg.get("general") or {}
            if not bool(general.get("check_for_updates", True)):
                return
        except Exception as exc:
            code, msg = format_error(exc)
            if code == "LD-SYS-021":
                self.set_detail(f"[{code}] {msg}")
            return

        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            from labdesk_ui.utils.flatpak_updates import check_for_labdesk_updates

            return check_for_labdesk_updates()

        def on_ok(result) -> None:
            if not result or not result.get("available"):
                return
            self.set_detail(str(result.get("detail") or "Update available."))
            QMessageBox.information(
                self,
                tr("Update available"),
                str(result.get("detail") or "A LabDesk Flatpak update is available."),
            )

        def on_err(code: str, msg: str, _exc: BaseException) -> None:
            # Non-fatal: leave a detail line; Settings can retry.
            if code == "LD-SYS-021":
                self.set_detail(f"[{code}] {msg}")

        run_in_background(self, work, on_success=on_ok, on_error=on_err)


    def view_widget(self, view_id: str) -> QWidget | None:
        return self._view_widgets.get(view_id)

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
        self._apply_shell(shell)
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

        file_menu = menu.addMenu(tr("&File"))
        act_connect = QAction(tr("Add host / account…"), self)
        act_connect.triggered.connect(self.show_connect_dialog)
        file_menu.addAction(act_connect)
        act_add_account = QAction(tr("Add account to host…"), self)
        act_add_account.triggered.connect(
            lambda: self.show_connect_dialog(mode=InstanceConfigDialog.MODE_ADD_ACCOUNT)
        )
        file_menu.addAction(act_add_account)
        act_open_repo = QAction(tr("Open repository…"), self)
        act_open_repo.setShortcut(QKeySequence.StandardKey.Open)
        act_open_repo.triggered.connect(self.open_repository_dialog)
        file_menu.addAction(act_open_repo)
        self._recent_repos_menu = QMenu(tr("Recent repositories"), self)
        file_menu.addMenu(self._recent_repos_menu)
        self._rebuild_recent_repos_menu()
        file_menu.addSeparator()
        act_quit = QAction(tr("&Quit"), self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        view_menu = menu.addMenu(tr("&View"))
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
        for shell_id, label in (
            ("classic", tr("Classic layout")),
            ("sidebar", tr("Sidebar layout")),
        ):
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

        self._window_menu = menu.addMenu(tr("&Window"))
        self._rebuild_window_menu()

        settings_menu = menu.addMenu(tr("&Settings"))
        act_prefs = QAction(tr("&Preferences…"), self)
        act_prefs.setShortcut(QKeySequence.StandardKey.Preferences)
        act_prefs.triggered.connect(lambda: self.switch_view("settings"))
        settings_menu.addAction(act_prefs)

        help_menu = menu.addMenu(tr("&Help"))
        act_guide = QAction(tr("&User Guide…"), self)
        act_guide.triggered.connect(self._user_guide)
        help_menu.addAction(act_guide)
        act_about = QAction(tr("&About LabDesk"), self)
        act_about.triggered.connect(self._about)
        help_menu.addAction(act_about)

    def _rebuild_recent_repos_menu(self) -> None:
        menu = getattr(self, "_recent_repos_menu", None)
        if menu is None:
            return
        menu.clear()
        rows: list = []
        try:
            import labdesk_core

            if hasattr(labdesk_core, "list_recent_repos"):
                rows = list(labdesk_core.list_recent_repos(12) or [])
        except Exception:
            rows = []
        if not rows:
            empty = QAction(tr("(no recent repositories)"), self)
            empty.setEnabled(False)
            menu.addAction(empty)
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            path = (row.get("path") or "").strip()
            if not path:
                continue
            label = Path(path).name or path
            act = QAction(label, self)
            act.setToolTip(path)
            act.triggered.connect(
                lambda checked=False, p=path: self.open_repo_window(
                    p, title=f"LabDesk — {Path(p).name}"
                )
            )
            menu.addAction(act)

    def _user_guide(self) -> None:
        from labdesk_ui.windows.help_dialog import UserGuideDialog

        dlg = UserGuideDialog(self)
        dlg.exec()

    def _about(self) -> None:
        from labdesk_ui.utils.branding import app_icon, wordmark_pixmap
        from labdesk_ui.utils.flatpak_updates import is_flatpak
        from labdesk_ui.version import APP_VERSION

        core_ver = ""
        try:
            import labdesk_core

            core_ver = getattr(labdesk_core, "__version__", "") or ""
        except Exception:
            core_ver = ""
        core_line = f"\nlabdesk_core {core_ver}" if core_ver else ""
        pack = "Flatpak" if is_flatpak() else "unpackaged (dev)"
        text = (
            f"LabDesk {APP_VERSION} ({pack})\n"
            "Desktop client for self-hosted GitLab, Gitea, Forgejo, and OneDev.\n"
            f"Linux · GPLv2+{core_line}\n"
            "Updates: Flatpak remote from Ranga/flatpaks"
        )
        box = QMessageBox(self)
        box.setWindowTitle(tr("About LabDesk"))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(text)
        icon = app_icon()
        if not icon.isNull():
            box.setWindowIcon(icon)
            box.setIconPixmap(icon.pixmap(64, 64))
        wordmark = wordmark_pixmap(280)
        if wordmark is not None and not wordmark.isNull():
            # Prefer wordmark as the dialog graphic when available.
            box.setIconPixmap(wordmark)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

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
