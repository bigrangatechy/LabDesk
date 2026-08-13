"""Local repository window — changes, files, history, branches, push/pull."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.utils.helpers import format_error
from labdesk_ui.utils.open_external import open_path, open_url
from labdesk_ui.windows.mr_dialog import MRDialog


def _format_commit_time(epoch: int | float | None) -> str:
    if epoch is None:
        return ""
    try:
        dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc).astimezone()
        return dt.strftime("%H:%M:%S  %d/%m/%Y")
    except (OverflowError, OSError, ValueError):
        return str(epoch)


def _job_is_playable(job: dict) -> bool:
    """GitLab play API accepts jobs waiting in ``status: manual``.

    ``when`` may also be ``manual`` (CI yaml), but status is what the Jobs
    API documents for playable actions — rules-based manual jobs sometimes
    surface mainly via status.
    """
    status = (job.get("status") or "").lower()
    when = (job.get("when") or "").lower()
    return status == "manual" or when == "manual"


def _sort_pipeline_jobs(jobs: list) -> list:
    """Playable/manual first, then stage, then name."""

    def key(job: dict):
        playable = 0 if _job_is_playable(job) else 1
        stage = (job.get("stage") or "").lower()
        name = (job.get("name") or "").lower()
        return (playable, stage, name)

    return sorted(jobs, key=key)


def _format_job_row(job: dict) -> str:
    stage = job.get("stage") or ""
    name = job.get("name") or f"job {job.get('id')}"
    status = job.get("status") or ""
    label = f"{stage} · {name}  [{status}]" if stage else f"{name}  [{status}]"
    if _job_is_playable(job):
        label = f"▶ {label}"
    return label


def _format_mr_row(mr: dict) -> str:
    iid = mr.get("iid")
    title = mr.get("title") or "(no title)"
    state = mr.get("state") or ""
    src = mr.get("source_branch") or "?"
    tgt = mr.get("target_branch") or "?"
    prefix = f"!{iid} " if iid is not None else ""
    return f"{prefix}{title}  [{state}]  {src} → {tgt}"


def _set_colored_diff(widget: QTextEdit, text: str) -> None:
    widget.clear()
    dark = widget.palette().color(QPalette.ColorRole.Window).lightness() < 128
    plus = QColor("#6bcf6b" if dark else "#0a7a0a")
    minus = QColor("#f08080" if dark else "#a10a0a")
    hunk = QColor("#7ec8e3" if dark else "#0a4a8a")
    cursor = widget.textCursor()
    for line in text.splitlines(keepends=True):
        fmt = QTextCharFormat()
        if line.startswith("+") and not line.startswith("+++"):
            fmt.setForeground(plus)
        elif line.startswith("-") and not line.startswith("---"):
            fmt.setForeground(minus)
        elif line.startswith("@@"):
            fmt.setForeground(hunk)
        cursor.setCharFormat(fmt)
        cursor.insertText(line)
    widget.moveCursor(QTextCursor.MoveOperation.Start)


class RepoWindow(QMainWindow):
    def __init__(self, repo_path: str, title: str | None = None, parent=None) -> None:
        # No QWidget parent: owned windows must be true top-levels so the
        # compositor/taskbar lists them (Wayland/Flatpak). Lifetime is held by
        # MainWindow._repo_windows + WA_DeleteOnClose.
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        # Closing a repo must not quit the whole app while main is open.
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.repo_path = str(Path(repo_path).resolve())
        self._network_available = True
        self.setWindowTitle(title or f"LabDesk — {self.repo_path}")
        self.resize(1100, 700)
        try:
            from labdesk_ui.utils.branding import app_icon

            icon = app_icon()
            if not icon.isNull():
                self.setWindowIcon(icon)
        except Exception:
            pass

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        self.header = QLabel(self.repo_path)
        self.header.setWordWrap(True)
        self.header.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.header)

        self.pipeline_chip = QLabel("")
        self.pipeline_chip.setWordWrap(True)
        self.pipeline_chip.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.pipeline_chip)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        row.addWidget(self.btn_refresh)

        self.btn_pull = QPushButton("Pull")
        self.btn_pull.clicked.connect(self._pull)
        row.addWidget(self.btn_pull)

        self.btn_fetch = QPushButton("Fetch")
        self.btn_fetch.clicked.connect(self._fetch)
        row.addWidget(self.btn_fetch)

        self.btn_push = QPushButton("Push")
        self.btn_push.clicked.connect(self._push)
        row.addWidget(self.btn_push)

        self.btn_force = QPushButton("Force push…")
        self.btn_force.clicked.connect(self._force_push)
        row.addWidget(self.btn_force)

        self.btn_mr = QPushButton("Create merge request…")
        self.btn_mr.clicked.connect(self._create_mr)
        row.addWidget(self.btn_mr)

        self.btn_editor = QPushButton("Open in editor")
        self.btn_editor.clicked.connect(self._open_in_editor)
        self.btn_editor.setEnabled(False)
        row.addWidget(self.btn_editor)
        row.addStretch(1)
        layout.addLayout(row)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_changes_tab(), "Changes")
        self.tabs.addTab(self._build_history_tab(), "History")
        self.tabs.addTab(self._build_branches_tab(), "Branches")
        self.tabs.addTab(self._build_compare_tab(), "Compare")
        self.tabs.addTab(self._build_pipelines_tab(), "Pipelines")
        self.tabs.addTab(self._build_mrs_tab(), "Merge requests")
        layout.addWidget(self.tabs, stretch=1)

        self.footer = QLabel("")
        self.footer.setWordWrap(True)
        layout.addWidget(self.footer)

        self._pipeline_project_id: int | None = None
        self._pipeline_web_url: str | None = None
        self._mr_project_id: int | None = None
        self._busy = False

        self.refresh()
        self.set_network_available(True)

    def set_network_available(self, available: bool) -> None:
        self._network_available = available
        if not getattr(self, "_busy", False):
            self.btn_push.setEnabled(available)
            self.btn_force.setEnabled(available)
            self.btn_pull.setEnabled(available)
            self.btn_fetch.setEnabled(available)
            self.btn_mr.setEnabled(available)
            if hasattr(self, "btn_pipeline_refresh"):
                # Refresh stays enabled offline so cached pipeline can load.
                self.btn_pipeline_refresh.setEnabled(True)
                self.btn_pipeline_open.setEnabled(bool(self._pipeline_web_url))
                self.btn_play_job.setEnabled(available)
            if hasattr(self, "btn_mr_refresh"):
                self.btn_mr_refresh.setEnabled(True)
                self.btn_mr_open.setEnabled(False)
        tip = "Working offline — network git actions disabled." if not available else ""
        self.btn_push.setToolTip(tip)
        self.btn_force.setToolTip(tip)
        self.btn_pull.setToolTip(tip)
        self.btn_fetch.setToolTip(tip)
        self.btn_mr.setToolTip(tip)

    def _network_busy_widgets(self) -> list:
        widgets = [
            self.btn_pull,
            self.btn_fetch,
            self.btn_push,
            self.btn_force,
            self.btn_mr,
        ]
        if hasattr(self, "btn_pipeline_refresh"):
            widgets.extend(
                [self.btn_pipeline_refresh, self.btn_pipeline_open, self.btn_play_job]
            )
        if hasattr(self, "btn_mr_refresh"):
            widgets.extend([self.btn_mr_refresh, self.btn_mr_open])
        return widgets

    def _build_compare_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        pick = QHBoxLayout()
        pick.addWidget(QLabel("Base"))
        self.compare_base = QComboBox()
        self.compare_base.setMinimumWidth(160)
        pick.addWidget(self.compare_base, stretch=1)
        pick.addWidget(QLabel("Other"))
        self.compare_other = QComboBox()
        self.compare_other.setMinimumWidth(160)
        pick.addWidget(self.compare_other, stretch=1)
        self.btn_compare = QPushButton("Compare")
        self.btn_compare.clicked.connect(self._run_compare)
        pick.addWidget(self.btn_compare)
        layout.addLayout(pick)

        self.compare_summary = QLabel("Pick two refs and Compare.")
        self.compare_summary.setWordWrap(True)
        layout.addWidget(self.compare_summary)

        split = QSplitter()
        self.compare_commits = QListWidget()
        split.addWidget(self.compare_commits)
        self.compare_diff = QTextEdit()
        self.compare_diff.setReadOnly(True)
        self.compare_diff.setFont(QFont("monospace"))
        self.compare_diff.setPlaceholderText("Tip-to-tip unified diff.")
        split.addWidget(self.compare_diff)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([280, 700])
        layout.addWidget(split, stretch=1)
        return page

    def _build_mrs_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.mr_summary = QLabel("No merge requests loaded yet.")
        self.mr_summary.setWordWrap(True)
        layout.addWidget(self.mr_summary)
        self.mr_list = QListWidget()
        layout.addWidget(self.mr_list, stretch=1)
        row = QHBoxLayout()
        self.btn_mr_refresh = QPushButton("Refresh MRs")
        self.btn_mr_refresh.clicked.connect(self._refresh_mrs)
        row.addWidget(self.btn_mr_refresh)
        self.btn_mr_open = QPushButton("Open in GitLab")
        self.btn_mr_open.clicked.connect(self._open_selected_mr)
        self.btn_mr_open.setEnabled(False)
        row.addWidget(self.btn_mr_open)
        row.addStretch(1)
        layout.addLayout(row)
        self.mr_list.currentItemChanged.connect(self._on_mr_selected)
        return page

    def _build_pipelines_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.pipeline_summary = QLabel("No pipeline loaded yet.")
        self.pipeline_summary.setWordWrap(True)
        layout.addWidget(self.pipeline_summary)
        self.pipeline_jobs = QListWidget()
        layout.addWidget(self.pipeline_jobs, stretch=1)
        row = QHBoxLayout()
        self.btn_pipeline_refresh = QPushButton("Refresh pipeline")
        self.btn_pipeline_refresh.clicked.connect(self._refresh_pipelines)
        row.addWidget(self.btn_pipeline_refresh)
        self.btn_pipeline_open = QPushButton("Open in GitLab")
        self.btn_pipeline_open.clicked.connect(self._open_pipeline)
        self.btn_pipeline_open.setEnabled(False)
        row.addWidget(self.btn_pipeline_open)
        self.btn_play_job = QPushButton("Play manual job…")
        self.btn_play_job.clicked.connect(self._play_selected_job)
        row.addWidget(self.btn_play_job)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def refresh(self) -> None:
        self._refresh_header()
        self._refresh_changes()
        self._refresh_history()
        self._refresh_branches()
        self._refresh_compare_refs()
        self._refresh_pipelines()
        self._refresh_mrs()

    def _build_changes_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        split = QSplitter()

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.files = QListWidget()
        self.files.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.files.currentItemChanged.connect(self._on_file_selected)
        left_layout.addWidget(self.files, stretch=1)

        stage_row = QHBoxLayout()
        self.btn_stage = QPushButton("Stage")
        self.btn_stage.clicked.connect(self._stage_selected)
        stage_row.addWidget(self.btn_stage)
        self.btn_unstage = QPushButton("Unstage")
        self.btn_unstage.clicked.connect(self._unstage_selected)
        stage_row.addWidget(self.btn_unstage)
        self.btn_stage_all = QPushButton("Stage all")
        self.btn_stage_all.clicked.connect(self._stage_all)
        stage_row.addWidget(self.btn_stage_all)
        left_layout.addLayout(stage_row)

        left_layout.addWidget(QLabel("Commit message"))
        self.commit_message = QTextEdit()
        self.commit_message.setPlaceholderText(
            "Summary (required)\n\nOptional longer description…"
        )
        self.commit_message.setFixedHeight(90)
        left_layout.addWidget(self.commit_message)
        self.btn_commit = QPushButton("Commit")
        self.btn_commit.clicked.connect(self._commit)
        left_layout.addWidget(self.btn_commit)

        split.addWidget(left)

        self.diff = QTextEdit()
        self.diff.setReadOnly(True)
        self.diff.setFont(QFont("monospace"))
        self.diff.setPlaceholderText(
            "Select a changed file for a diff, or a tracked file to view."
        )
        split.addWidget(self.diff)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([320, 700])
        layout.addWidget(split)
        return page

    def _build_history_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        split = QSplitter()

        self.commits = QListWidget()
        self.commits.setUniformItemSizes(False)
        self.commits.setWordWrap(True)
        self.commits.currentItemChanged.connect(self._on_commit_selected)
        split.addWidget(self.commits)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.commit_meta = QLabel("")
        self.commit_meta.setWordWrap(True)
        self.commit_meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right_layout.addWidget(self.commit_meta)

        self.commit_diff = QTextEdit()
        self.commit_diff.setReadOnly(True)
        self.commit_diff.setFont(QFont("monospace"))
        self.commit_diff.setPlaceholderText("Select a commit to view its patch.")
        right_layout.addWidget(self.commit_diff, stretch=1)
        split.addWidget(right)

        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([320, 700])
        layout.addWidget(split)
        return page

    def _build_branches_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.branches = QListWidget()
        self.branches.itemDoubleClicked.connect(lambda _i: self._switch_branch())
        layout.addWidget(self.branches, stretch=1)
        row = QHBoxLayout()
        self.btn_switch_branch = QPushButton("Switch")
        self.btn_switch_branch.clicked.connect(self._switch_branch)
        row.addWidget(self.btn_switch_branch)
        self.btn_create_branch = QPushButton("Create…")
        self.btn_create_branch.clicked.connect(self._create_branch)
        row.addWidget(self.btn_create_branch)
        self.btn_merge_branch = QPushButton("Merge into current…")
        self.btn_merge_branch.clicked.connect(self._merge_branch)
        row.addWidget(self.btn_merge_branch)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _refresh_header(self) -> None:
        try:
            import labdesk_core

            branch = labdesk_core.repo_branch(self.repo_path)
            summary = ""
            try:
                summary = labdesk_core.repo_head_summary(self.repo_path)
            except Exception:
                summary = ""
            head_line = f"{self.repo_path}  ({branch})"
            if summary:
                head_line += f"\nHEAD: {summary}"
            sync = ""
            try:
                ab = labdesk_core.repo_ahead_behind(self.repo_path)
                ahead = int(ab.get("ahead") or 0)
                behind = int(ab.get("behind") or 0)
                upstream = ab.get("upstream") or ""
                if upstream:
                    parts = []
                    if ahead:
                        parts.append(f"↑{ahead}")
                    if behind:
                        parts.append(f"↓{behind}")
                    if not parts:
                        parts.append("up to date")
                    sync = f"\nUpstream {upstream}: {' '.join(parts)}"
            except Exception:
                sync = ""
            self.header.setText(head_line + sync)
        except Exception as exc:
            code, msg = format_error(exc)
            self.header.setText(f"[{code}] {msg}")

    def _merge_branch(self) -> None:
        name = self._selected_branch_name()
        if not name:
            QMessageBox.information(
                self, "Merge", "Select a branch to merge into the current branch."
            )
            return
        try:
            import labdesk_core

            current = labdesk_core.repo_branch(self.repo_path)
            if name == current:
                QMessageBox.information(
                    self, "Merge", "Select a different branch than the current one."
                )
                return
            reply = QMessageBox.question(
                self,
                "Merge",
                f"Merge '{name}' into '{current}'?\n\n"
                "Only clean merges are supported. On conflict, LabDesk aborts "
                "and you resolve externally.",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            msg = labdesk_core.repo_merge_branch(self.repo_path, name)
            self.footer.setText(msg)
            self.refresh()
            QMessageBox.information(self, "Merge", msg)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _fetch(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            labdesk_core.repo_fetch(path)
            return True

        def on_ok(_result) -> None:
            self._busy = False
            self.footer.setText("Fetch OK.")
            self._refresh_header()
            QMessageBox.information(self, "Fetch", "Fetched from origin.")

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self._busy = False
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        self._busy = True
        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=self._network_busy_widgets(),
            status=self.footer.setText,
            working_message="Working…",
        )

    def _refresh_branches(self) -> None:
        try:
            import labdesk_core

            data = labdesk_core.repo_list_branches(self.repo_path)
            current = data.get("current") or ""
            self.branches.clear()
            for name in data.get("branches") or []:
                label = f"* {name}" if name == current else f"  {name}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, name)
                self.branches.addItem(item)
                if name == current:
                    self.branches.setCurrentItem(item)
        except Exception as exc:
            code, msg = format_error(exc)
            self.footer.setText(f"[{code}] {msg}")

    def _selected_branch_name(self) -> str | None:
        item = self.branches.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return str(data) if data else None

    def _switch_branch(self) -> None:
        name = self._selected_branch_name()
        if not name:
            QMessageBox.information(self, "Switch branch", "Select a branch.")
            return
        try:
            import labdesk_core

            current = labdesk_core.repo_branch(self.repo_path)
            if name == current:
                return
            labdesk_core.repo_checkout_branch(self.repo_path, name)
            self.footer.setText(f"Switched to {name}.")
            self.refresh()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _create_branch(self) -> None:
        name, ok = QInputDialog.getText(self, "Create branch", "New branch name:")
        if not ok or not name.strip():
            return
        try:
            import labdesk_core

            labdesk_core.repo_create_branch(self.repo_path, name.strip(), True)
            self.footer.setText(f"Created and switched to {name.strip()}.")
            self.refresh()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _selected_file_path(self) -> str | None:
        item = self.files.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get("path"):
            return str(data["path"])
        return None

    def _open_in_editor(self) -> None:
        rel = self._selected_file_path()
        if not rel:
            QMessageBox.information(self, "Open in editor", "Select a file first.")
            return
        abs_path = Path(self.repo_path) / rel
        try:
            open_path(abs_path)
            self.footer.setText(f"Opened {rel} in external application.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _create_mr(self) -> None:
        if not self._network_available:
            QMessageBox.information(
                self,
                "Create merge request",
                "Working offline — cannot create a merge request.",
            )
            return
        try:
            import labdesk_core

            info = labdesk_core.resolve_repo_project(self.repo_path)
            dlg = MRDialog(
                source_branch=info.get("current_branch")
                or labdesk_core.repo_branch(self.repo_path),
                target_branch=info.get("default_branch") or "main",
                project_label=info.get("path_with_namespace") or "",
                parent=self,
            )
            if dlg.exec() != MRDialog.DialogCode.Accepted:
                return
            source, target, title, description = dlg.values()
            if not title:
                QMessageBox.warning(self, "Create merge request", "Title is required.")
                return
            if not source or not target:
                QMessageBox.warning(
                    self,
                    "Create merge request",
                    "Source and target branches are required.",
                )
                return
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")
            return

        from labdesk_ui.utils.async_jobs import run_in_background

        project_id = int(info["project_id"])
        desc = description or None

        def work():
            import labdesk_core

            return labdesk_core.create_merge_request(
                project_id, source, target, title, desc
            )

        def on_ok(mr) -> None:
            self._busy = False
            web = (mr or {}).get("web_url") or ""
            iid = (mr or {}).get("iid")
            self.footer.setText(f"Created !{iid}")
            reply = QMessageBox.information(
                self,
                "Merge request created",
                f"Created !{iid}: {(mr or {}).get('title') or title}\n\nOpen in GitLab?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes and web:
                try:
                    open_url(web)
                except Exception as exc:
                    code, msg = format_error(exc)
                    QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self._busy = False
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        self._busy = True
        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=self._network_busy_widgets(),
            status=self.footer.setText,
            working_message="Creating merge request…",
        )

    def _refresh_changes(self) -> None:
        try:
            import labdesk_core

            branch = labdesk_core.repo_branch(self.repo_path)
            summary = ""
            try:
                summary = labdesk_core.repo_head_summary(self.repo_path)
            except Exception:
                summary = ""

            changes = labdesk_core.repo_status(self.repo_path)
            tracked = labdesk_core.repo_list_files(self.repo_path)

            self.files.clear()
            self.diff.clear()
            self.btn_editor.setEnabled(False)

            if changes:
                staged_only = [
                    e for e in changes if e.get("staged") and not e.get("unstaged")
                ]
                other = [
                    e
                    for e in changes
                    if not (e.get("staged") and not e.get("unstaged"))
                ]
                if staged_only:
                    sep = QListWidgetItem("— Staged —")
                    sep.setFlags(Qt.ItemFlag.NoItemFlags)
                    self.files.addItem(sep)
                    for e in staged_only:
                        self._add_change_item(e)
                if other:
                    sep = QListWidgetItem("— Changes —")
                    sep.setFlags(Qt.ItemFlag.NoItemFlags)
                    self.files.addItem(sep)
                    for e in other:
                        self._add_change_item(e)

            sep = QListWidgetItem(
                "— Working tree clean —" if not changes else "— Tracked files —"
            )
            sep.setFlags(Qt.ItemFlag.NoItemFlags)
            self.files.addItem(sep)

            change_paths = {e.get("path") for e in changes}
            for path in tracked:
                if path in change_paths:
                    continue
                item = QListWidgetItem(f"{'file':10}  {path}")
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    {"kind": "file", "path": path},
                )
                self.files.addItem(item)

            n_changes = len(changes)
            n_files = len(tracked)
            if n_changes == 0:
                self.footer.setText(
                    f"Working tree clean · {n_files} tracked file(s). "
                    "Use the History tab for commits."
                )
                self.diff.setPlainText(
                    "Working tree clean — no local changes.\n\n"
                    "Tracked files are listed on the left; select one to view contents.\n"
                    "Open the History tab for commit history.\n"
                    f"Branch: {branch}"
                    + (f"\nHEAD: {summary}" if summary else "")
                )
                for prefer in ("README.md", "README", "readme.md"):
                    matches = self.files.findItems(
                        f"{'file':10}  {prefer}", Qt.MatchFlag.MatchExactly
                    )
                    if matches:
                        self.files.setCurrentItem(matches[0])
                        break
            else:
                n_staged = sum(1 for e in changes if e.get("staged"))
                self.footer.setText(
                    f"{n_changes} changed path(s) · {n_staged} staged · "
                    f"{n_files} tracked file(s)"
                )
        except Exception as exc:
            code, msg = format_error(exc)
            self.footer.setText(f"[{code}] {msg}")
            self.diff.setPlainText(f"[{code}] {msg}\n\n{exc}")
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _add_change_item(self, e: dict) -> None:
        status = e.get("status") or "?"
        path = e.get("path") or ""
        item = QListWidgetItem(f"{status:12}  {path}")
        item.setData(
            Qt.ItemDataRole.UserRole,
            {
                "kind": "change",
                "path": path,
                "status": status,
                "staged": bool(e.get("staged")),
                "unstaged": bool(e.get("unstaged")),
            },
        )
        self.files.addItem(item)

    def _selected_change_paths(self) -> list[str]:
        paths: list[str] = []
        for item in self.files.selectedItems():
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("kind") == "change" and data.get("path"):
                paths.append(str(data["path"]))
        return paths

    def _stage_selected(self) -> None:
        paths = self._selected_change_paths()
        if not paths:
            QMessageBox.information(self, "Stage", "Select one or more changed files.")
            return
        try:
            import labdesk_core

            n = labdesk_core.repo_stage(self.repo_path, paths)
            self.footer.setText(f"Staged {n} path(s).")
            self._refresh_changes()
            self._refresh_header()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _unstage_selected(self) -> None:
        paths = self._selected_change_paths()
        if not paths:
            QMessageBox.information(self, "Unstage", "Select one or more staged files.")
            return
        try:
            import labdesk_core

            n = labdesk_core.repo_unstage(self.repo_path, paths)
            self.footer.setText(f"Unstaged {n} path(s).")
            self._refresh_changes()
            self._refresh_header()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _stage_all(self) -> None:
        try:
            import labdesk_core

            changes = labdesk_core.repo_status(self.repo_path)
            paths = [e["path"] for e in changes if e.get("path") and e.get("unstaged")]
            if not paths:
                paths = [e["path"] for e in changes if e.get("path")]
            if not paths:
                QMessageBox.information(self, "Stage all", "Nothing to stage.")
                return
            n = labdesk_core.repo_stage(self.repo_path, paths)
            self.footer.setText(f"Staged {n} path(s).")
            self._refresh_changes()
            self._refresh_header()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _commit(self) -> None:
        message = self.commit_message.toPlainText().strip()
        if not message:
            QMessageBox.warning(self, "Commit", "Enter a commit message.")
            return
        try:
            import labdesk_core

            oid = labdesk_core.repo_commit(self.repo_path, message)
            short = oid[:7] if oid else ""
            self.commit_message.clear()
            self.footer.setText(f"Committed {short}.")
            self.refresh()
            QMessageBox.information(self, "Commit", f"Created commit {short}.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _refresh_history(self) -> None:
        try:
            import labdesk_core

            commits = labdesk_core.repo_log(self.repo_path, 200)
            self.commits.clear()
            self.commit_meta.setText("")
            self.commit_diff.clear()

            if not commits:
                self.commits.addItem(QListWidgetItem("(no commits)"))
                self.commit_meta.setText("This repository has no commits yet.")
                return

            for c in commits:
                when = _format_commit_time(c.get("time"))
                summary = (c.get("summary") or "(no subject)").replace("\n", " ")
                short = c.get("short_oid") or ""
                author = c.get("author_name") or ""
                label = f"{short}  {summary}"
                if author or when:
                    label += f"\n    {author}"
                    if when:
                        label += f" · {when}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, c)
                self.commits.addItem(item)

            self.commits.setCurrentRow(0)
            base = self.footer.text().rstrip(" ·")
            hist = f"{len(commits)} commit(s) in History"
            self.footer.setText(f"{base} · {hist}" if base else hist)
        except Exception as exc:
            code, msg = format_error(exc)
            self.commit_meta.setText(f"[{code}] {msg}")
            self.commit_diff.setPlainText(str(exc))

    def _on_file_selected(self, current: QListWidgetItem | None, _prev) -> None:
        if current is None:
            self.btn_editor.setEnabled(False)
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            self.btn_editor.setEnabled(False)
            return
        rel = data.get("path") or ""
        kind = data.get("kind") or "change"
        self.btn_editor.setEnabled(bool(rel))
        if not rel:
            return
        try:
            import labdesk_core

            if kind == "change":
                text = labdesk_core.repo_diff(self.repo_path, rel)
                _set_colored_diff(self.diff, text)
            else:
                text = labdesk_core.repo_show_file(self.repo_path, rel)
                self.diff.setPlainText(text)
                self.diff.moveCursor(QTextCursor.MoveOperation.Start)
        except Exception as exc:
            code, msg = format_error(exc)
            self.diff.setPlainText(f"[{code}] {msg}\n{exc}")

    def _on_commit_selected(self, current: QListWidgetItem | None, _prev) -> None:
        if current is None:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        oid = data.get("oid") or ""
        if not oid:
            return
        try:
            import labdesk_core

            info = labdesk_core.repo_commit_info(self.repo_path, oid)
            when = _format_commit_time(info.get("time"))
            lines = [
                f"{info.get('short_oid')}  {info.get('summary') or '(no subject)'}",
                f"Author: {info.get('author_name')} <{info.get('author_email')}>",
            ]
            if when:
                lines.append(f"Date:   {when}")
            lines.append(f"Full:   {info.get('oid')}")
            body = (info.get("body") or "").strip()
            if body:
                lines.append("")
                lines.append(body)
            self.commit_meta.setText("\n".join(lines))

            patch = labdesk_core.repo_commit_diff(self.repo_path, oid)
            _set_colored_diff(self.commit_diff, patch)
        except Exception as exc:
            code, msg = format_error(exc)
            self.commit_meta.setText(f"[{code}] {msg}")
            self.commit_diff.setPlainText(str(exc))

    def _pull(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            return labdesk_core.repo_pull(path)

        def on_ok(msg) -> None:
            self._busy = False
            self.footer.setText(str(msg))
            self.refresh()
            QMessageBox.information(self, "Pull", str(msg))

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self._busy = False
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        self._busy = True
        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=self._network_busy_widgets(),
            status=self.footer.setText,
            working_message="Working…",
        )

    def _push(self) -> None:
        self._do_push(False)

    def _force_push(self) -> None:
        try:
            import labdesk_core

            branch = labdesk_core.repo_branch(self.repo_path)
        except Exception:
            branch = "current branch"
        reply = QMessageBox.warning(
            self,
            "Force push",
            f"Force push to {branch}? This can overwrite remote history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._do_push(True)

    def _do_push(self, force: bool) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            labdesk_core.repo_push(path, force)
            return True

        def on_ok(_result) -> None:
            self._busy = False
            self.footer.setText("Force push OK." if force else "Push OK.")
            QMessageBox.information(
                self,
                "Push",
                "Force push succeeded." if force else "Push succeeded.",
            )
            self._refresh_history()
            self._refresh_header()
            if not force and self._network_available:
                reply = QMessageBox.question(
                    self,
                    "Create merge request?",
                    "Push succeeded. Create a merge request on GitLab now?",
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._create_mr()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self._busy = False
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        self._busy = True
        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=self._network_busy_widgets(),
            status=self.footer.setText,
            working_message="Working…",
        )

    def _refresh_compare_refs(self) -> None:
        if not hasattr(self, "compare_base"):
            return
        try:
            import labdesk_core

            data = labdesk_core.repo_list_compare_refs(self.repo_path)
            current = data.get("current") or ""
            refs = list(data.get("branches") or [])
            self.compare_base.blockSignals(True)
            self.compare_other.blockSignals(True)
            self.compare_base.clear()
            self.compare_other.clear()
            for name in refs:
                self.compare_base.addItem(name)
                self.compare_other.addItem(name)
            if current:
                idx = self.compare_base.findText(current)
                if idx >= 0:
                    self.compare_base.setCurrentIndex(idx)
                origin = f"origin/{current}"
                oidx = self.compare_other.findText(origin)
                if oidx >= 0:
                    self.compare_other.setCurrentIndex(oidx)
                elif refs:
                    # Prefer a different local than current when no origin tip.
                    for i, name in enumerate(refs):
                        if name != current and not name.startswith("origin/"):
                            self.compare_other.setCurrentIndex(i)
                            break
            self.compare_base.blockSignals(False)
            self.compare_other.blockSignals(False)
        except Exception as exc:
            code, msg = format_error(exc)
            if hasattr(self, "compare_summary"):
                self.compare_summary.setText(f"[{code}] {msg}")

    def _run_compare(self) -> None:
        base = self.compare_base.currentText().strip()
        other = self.compare_other.currentText().strip()
        if not base or not other:
            QMessageBox.information(self, "Compare", "Select base and other refs.")
            return
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path
        online = self._network_available

        def work():
            import labdesk_core

            cmp = labdesk_core.repo_compare_branches(path, base, other)
            remote = None
            if online:
                try:
                    info = labdesk_core.resolve_repo_project(path)
                    pid = int(info["project_id"])
                    # Check the other tip's branch name on GitLab.
                    branch = other.split("/", 1)[-1] if other.startswith("origin/") else other
                    remote = labdesk_core.remote_branch_exists(pid, branch)
                except Exception as exc:
                    remote = {"error": str(exc)}
            return {"compare": cmp, "remote": remote}

        def on_ok(data) -> None:
            cmp = (data or {}).get("compare") or {}
            ahead = int(cmp.get("ahead") or 0)
            behind = int(cmp.get("behind") or 0)
            lines = [
                f"{cmp.get('other_ref')} vs {cmp.get('base_ref')}: "
                f"ahead {ahead}, behind {behind}"
            ]
            remote = (data or {}).get("remote")
            if isinstance(remote, dict):
                if "exists" in remote:
                    exists = remote.get("exists")
                    br = remote.get("branch") or other
                    lines.append(
                        f"Remote branch '{br}': "
                        + ("present on GitLab" if exists else "not found on GitLab")
                    )
                elif remote.get("error"):
                    lines.append(f"Remote check skipped: {remote.get('error')}")
            elif not online:
                lines.append("Remote check skipped (offline).")
            self.compare_summary.setText("\n".join(lines))
            self.compare_commits.clear()
            for c in cmp.get("commits") or []:
                summary = c.get("summary") or ""
                oid = (c.get("oid") or "")[:8]
                author = c.get("author") or ""
                when = _format_commit_time(c.get("time"))
                label = f"{oid}  {summary}"
                if author or when:
                    label += f"\n    {author}  {when}".rstrip()
                self.compare_commits.addItem(QListWidgetItem(label))
            _set_colored_diff(self.compare_diff, cmp.get("diff_text") or "")

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.compare_summary.setText(f"[{code}] {msg}")
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_compare],
            status=self.footer.setText,
            working_message="Comparing…",
        )

    def _apply_mrs_view(self, mrs: list, *, cached: bool = False, fetched_at: str | None = None) -> None:
        self.mr_list.clear()
        for mr in mrs:
            if not isinstance(mr, dict):
                continue
            item = QListWidgetItem(_format_mr_row(mr))
            item.setData(Qt.ItemDataRole.UserRole, mr)
            self.mr_list.addItem(item)
        n = len(mrs)
        meta = f"Opened MRs ({n}"
        if cached:
            meta += ", cached"
        if fetched_at:
            meta += f", fetched_at {fetched_at}"
        meta += ")"
        self.mr_summary.setText(meta)
        self.btn_mr_open.setEnabled(False)

    def _load_cached_mrs(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            info = labdesk_core.resolve_repo_project(path)
            project_id = int(info["project_id"])
            cached = labdesk_core.cached_merge_requests(project_id)
            return {"project_id": project_id, "cached": cached}

        def on_ok(data) -> None:
            self._mr_project_id = (data or {}).get("project_id")
            cached = (data or {}).get("cached")
            if not cached:
                self.mr_summary.setText("Offline — no cached merge requests.")
                self.mr_list.clear()
                return
            self._apply_mrs_view(
                cached.get("merge_requests") or [],
                cached=True,
                fetched_at=cached.get("fetched_at"),
            )

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.mr_summary.setText(f"Offline — could not load MR cache [{code}]: {msg}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_mr_refresh] if hasattr(self, "btn_mr_refresh") else None,
            status=self.footer.setText,
            working_message="Loading cached MRs…",
        )

    def _refresh_mrs(self) -> None:
        if not hasattr(self, "mr_list"):
            return
        if not self._network_available:
            self._load_cached_mrs()
            return
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            info = labdesk_core.resolve_repo_project(path)
            project_id = int(info["project_id"])
            result = labdesk_core.refresh_merge_requests(project_id)
            return {"project_id": project_id, "result": result}

        def on_ok(data) -> None:
            self._mr_project_id = (data or {}).get("project_id")
            result = (data or {}).get("result") or {}
            self._apply_mrs_view(result.get("merge_requests") or [], cached=False)

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            if code.startswith("LD-NET"):
                self.set_network_available(False)
                self._load_cached_mrs()
                return
            self.mr_summary.setText(f"[{code}] {msg}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_mr_refresh] if hasattr(self, "btn_mr_refresh") else None,
            status=self.footer.setText,
            working_message="Loading merge requests…",
        )

    def _on_mr_selected(self, current, _previous) -> None:
        mr = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.btn_mr_open.setEnabled(bool(isinstance(mr, dict) and mr.get("web_url")))

    def _open_selected_mr(self) -> None:
        item = self.mr_list.currentItem()
        if item is None:
            return
        mr = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(mr, dict) or not mr.get("web_url"):
            return
        try:
            open_url(mr["web_url"])
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _apply_pipeline_view(
        self,
        *,
        project_id,
        pipe: dict | None,
        jobs: list,
        branch: str | None = None,
        cached: bool = False,
        fetched_at: str | None = None,
    ) -> None:
        self._pipeline_project_id = project_id
        if not pipe:
            self._pipeline_web_url = None
            self.pipeline_chip.setText(
                "Pipeline: none for current branch"
                if not cached
                else "Pipeline: (offline — no cache)"
            )
            self.pipeline_summary.setText(
                "No pipeline found for the current branch."
                if not cached
                else "Offline — no cached pipeline for this branch."
            )
            self.pipeline_jobs.clear()
            self.btn_pipeline_open.setEnabled(False)
            self.btn_play_job.setEnabled(False)
            return
        status = pipe.get("status") or "unknown"
        self._pipeline_web_url = pipe.get("web_url")
        chip = f"Pipeline: {status}"
        if cached:
            chip = f"Pipeline: {status} (cached)"
        self.pipeline_chip.setText(chip)
        ref = pipe.get("ref") or branch or "—"
        lines = [
            f"#{pipe.get('id')}  {status}  ref={ref}",
            f"Updated: {pipe.get('updated_at') or pipe.get('created_at') or '—'}",
        ]
        if fetched_at:
            lines.append(f"Cached: {fetched_at}")
        self.pipeline_summary.setText("\n".join(lines))
        self.btn_pipeline_open.setEnabled(bool(self._pipeline_web_url))
        self.btn_play_job.setEnabled(self._network_available and not cached)
        self.pipeline_jobs.clear()
        for job in _sort_pipeline_jobs(list(jobs)):
            if not isinstance(job, dict):
                continue
            item = QListWidgetItem(_format_job_row(job))
            item.setData(Qt.ItemDataRole.UserRole, job)
            self.pipeline_jobs.addItem(item)

    def _load_cached_pipelines(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            info = labdesk_core.resolve_repo_project(path)
            project_id = int(info["project_id"])
            branch = info.get("current_branch") or labdesk_core.repo_branch(path)
            cached = labdesk_core.cached_pipeline(project_id, branch)
            return {
                "project_id": project_id,
                "branch": branch,
                "cached": cached,
            }

        def on_ok(data) -> None:
            cached = (data or {}).get("cached")
            if not cached:
                self._apply_pipeline_view(
                    project_id=(data or {}).get("project_id"),
                    pipe=None,
                    jobs=[],
                    branch=(data or {}).get("branch"),
                    cached=True,
                )
                return
            self._apply_pipeline_view(
                project_id=(data or {}).get("project_id"),
                pipe=cached.get("pipeline"),
                jobs=cached.get("jobs") or [],
                branch=(data or {}).get("branch"),
                cached=True,
                fetched_at=cached.get("fetched_at"),
            )

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.pipeline_chip.setText("Pipeline: (offline)")
            self.pipeline_summary.setText(f"Offline — could not load cache [{code}]: {msg}")
            self.btn_play_job.setEnabled(False)

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_pipeline_refresh] if hasattr(self, "btn_pipeline_refresh") else None,
            status=self.footer.setText,
            working_message="Loading cached pipeline…",
        )

    def _refresh_pipelines(self) -> None:
        if not self._network_available:
            self._load_cached_pipelines()
            return
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            info = labdesk_core.resolve_repo_project(path)
            project_id = int(info["project_id"])
            branch = info.get("current_branch") or labdesk_core.repo_branch(path)
            pipe = labdesk_core.latest_pipeline(project_id, branch)
            jobs = []
            if pipe and pipe.get("id") is not None:
                jobs = labdesk_core.list_pipeline_jobs(project_id, int(pipe["id"]))
                labdesk_core.cache_pipeline(project_id, branch, pipe, jobs)
            return {"project_id": project_id, "branch": branch, "pipeline": pipe, "jobs": jobs}

        def on_ok(data) -> None:
            self._apply_pipeline_view(
                project_id=(data or {}).get("project_id"),
                pipe=(data or {}).get("pipeline"),
                jobs=(data or {}).get("jobs") or [],
                branch=(data or {}).get("branch"),
                cached=False,
            )

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            if code.startswith("LD-NET"):
                self.set_network_available(False)
                self._load_cached_pipelines()
                return
            self.pipeline_chip.setText(f"Pipeline: [{code}]")
            self.pipeline_summary.setText(f"[{code}] {msg}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_pipeline_refresh] if hasattr(self, "btn_pipeline_refresh") else None,
            status=self.footer.setText,
            working_message="Loading pipeline…",
        )

    def _open_pipeline(self) -> None:
        if not self._pipeline_web_url:
            return
        try:
            open_url(self._pipeline_web_url)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _play_selected_job(self) -> None:
        if not self._network_available:
            QMessageBox.information(self, "Play job", "Working offline.")
            return
        item = self.pipeline_jobs.currentItem()
        if item is None:
            QMessageBox.information(self, "Play job", "Select a manual job first.")
            return
        job = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(job, dict):
            return
        if not _job_is_playable(job):
            status = job.get("status") or "?"
            when = job.get("when") or "?"
            QMessageBox.information(
                self,
                "Play job",
                "Only jobs waiting for manual start can be played from LabDesk.\n\n"
                f"Selected job status={status}, when={when}.\n"
                "Look for a row marked ▶ (status manual).",
            )
            return
        name = job.get("name") or job.get("id")
        reply = QMessageBox.question(
            self,
            "Play job",
            f"Start manual job '{name}'?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._pipeline_project_id is None:
            QMessageBox.warning(self, "Play job", "Project id unknown; refresh pipeline.")
            return

        from labdesk_ui.utils.async_jobs import run_in_background

        project_id = int(self._pipeline_project_id)
        job_id = int(job["id"])

        def work():
            import labdesk_core

            return labdesk_core.play_job(project_id, job_id)

        def on_ok(result) -> None:
            self.footer.setText(f"Started job {result.get('name') or job_id}")
            self._refresh_pipelines()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=self._network_busy_widgets(),
            status=self.footer.setText,
            working_message="Starting job…",
        )
