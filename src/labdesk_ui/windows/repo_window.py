"""Local repository window — changes, files, history, branches, push/pull."""

from __future__ import annotations

from labdesk_ui.i18n import tr

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QAbstractListModel, QModelIndex, QStringListModel
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
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

from labdesk_ui.utils.forge_labels import (
    ci_tab_label,
    forge_info,
    forge_name,
    open_in_label,
    pr_label,
    pr_label_plural,
)
from labdesk_ui.utils.helpers import format_error
from labdesk_ui.utils.open_external import open_path, open_url
from labdesk_ui.widgets.diff_view import DiffView, colorize_unified
from labdesk_ui.windows.browse_files_dialog import BrowseFilesDialog
from labdesk_ui.windows.conflict_dialog import ConflictDialog
from labdesk_ui.windows.mr_detail_dialog import MRDetailDialog
from labdesk_ui.windows.mr_dialog import MRDialog

# Hard cap for Changes-tab dirty rows (core also stops recursing untracked dirs).
# Tracked browse uses config `browse_files_page_size` (default 200) in a dialog.
_TRACKED_LIST_CAP = 200
# Cap for dirty/untracked status rows (core also stops recursing untracked dirs).
_CHANGES_LIST_CAP = 500
_DEFAULT_HISTORY_PAGE = 200


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


def _ref_to_branch_name(ref: str) -> str:
    """Strip a leading ``origin/`` remote prefix; keep nested branch names."""
    ref = (ref or "").strip()
    if ref.startswith("origin/"):
        return ref[len("origin/") :]
    return ref


def _set_colored_diff(widget, text: str) -> None:
    if hasattr(widget, "set_diff"):
        widget.set_diff(text)
        return
    colorize_unified(widget, text)


def _diff_looks_truncated(text: str) -> bool:
    return "… (diff truncated)" in text or "(diff truncated)" in text


def _populate_diff_file_list(widget: QListWidget, files: list) -> None:
    widget.clear()
    for f in files or []:
        if isinstance(f, dict):
            path = f.get("path") or ""
            binary = bool(f.get("binary"))
        else:
            path = str(f)
            binary = False
        if not path:
            continue
        label = f"{path}  [binary]" if binary else path
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, {"path": path, "binary": binary})
        widget.addItem(item)


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
        self.pipeline_chip.hide()
        layout.addWidget(self.pipeline_chip)

        self.sync_banner = QLabel("")
        self.sync_banner.setWordWrap(True)
        self.sync_banner.setStyleSheet("padding: 4px;")
        self.sync_banner.hide()
        layout.addWidget(self.sync_banner)

        self.notify_chip = QLabel("")
        self.notify_chip.setWordWrap(True)
        self.notify_chip.hide()
        layout.addWidget(self.notify_chip)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton(tr("Refresh"))
        self.btn_refresh.clicked.connect(self.refresh)
        row.addWidget(self.btn_refresh)

        self.btn_pull = QPushButton(tr("Pull"))
        self.btn_pull.clicked.connect(self._pull)
        row.addWidget(self.btn_pull)

        self.btn_fetch = QPushButton(tr("Fetch"))
        self.btn_fetch.clicked.connect(self._fetch)
        row.addWidget(self.btn_fetch)

        self.btn_push = QPushButton(tr("Push"))
        self.btn_push.clicked.connect(self._push)
        row.addWidget(self.btn_push)

        self.btn_force = QPushButton(tr("Force push…"))
        self.btn_force.clicked.connect(self._force_push)
        row.addWidget(self.btn_force)

        self.btn_stash = QPushButton(tr("Stash…"))
        self.btn_stash.clicked.connect(self._stash)
        row.addWidget(self.btn_stash)
        self.btn_stash_pop = QPushButton(tr("Pop stash…"))
        self.btn_stash_pop.clicked.connect(self._stash_pop)
        row.addWidget(self.btn_stash_pop)
        self.btn_rebase = QPushButton(tr("Rebase onto upstream…"))
        self.btn_rebase.clicked.connect(self._rebase_upstream)
        row.addWidget(self.btn_rebase)
        self.btn_conflicts = QPushButton(tr("Resolve conflicts…"))
        self.btn_conflicts.clicked.connect(self._open_conflicts)
        row.addWidget(self.btn_conflicts)

        self.btn_mr = QPushButton(tr("Create merge request…"))
        self.btn_mr.clicked.connect(self._create_mr)
        row.addWidget(self.btn_mr)

        self.btn_editor = QPushButton(tr("Edit in LabDesk"))
        self.btn_editor.clicked.connect(self._open_in_editor)
        self.btn_editor.setEnabled(False)
        row.addWidget(self.btn_editor)
        self.btn_external = QPushButton(tr("Open external…"))
        self.btn_external.clicked.connect(self._open_external)
        self.btn_external.setEnabled(False)
        row.addWidget(self.btn_external)
        row.addStretch(1)
        layout.addLayout(row)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_changes_tab(), tr("Changes"))
        self.tabs.addTab(self._build_history_tab(), tr("History"))
        self.tabs.addTab(self._build_branches_tab(), tr("Branches"))
        self.tabs.addTab(self._build_compare_tab(), tr("Compare"))
        self.tabs.addTab(self._build_git_tab(), tr("Git"))
        self._pipelines_tab_index = self.tabs.addTab(
            self._build_pipelines_tab(), tr("Pipelines")
        )
        self._runners_tab_index = self.tabs.addTab(
            self._build_runners_tab(), tr("Runners")
        )
        self._mrs_tab_index = self.tabs.addTab(
            self._build_mrs_tab(), tr("Merge requests")
        )
        layout.addWidget(self.tabs, stretch=1)

        self.footer = QLabel("")
        self.footer.setWordWrap(True)
        layout.addWidget(self.footer)

        self._pipeline_project_id: int | None = None
        self._pipeline_web_url: str | None = None
        self._mr_project_id: int | None = None
        self._busy = False
        self._apply_forge_labels()

        # Defer initial load so the window can paint before scanning a large tree.
        self.footer.setText(tr("Loading repository…"))
        QTimer.singleShot(0, self.refresh)
        self.set_network_available(True)
        self._history_offset = 0
        self._history_page = _DEFAULT_HISTORY_PAGE
        self._browse_page = _TRACKED_LIST_CAP
        self._load_list_page_sizes()
        self._last_mr_updated: str | None = None
        self._setup_shortcuts()

    def _load_list_page_sizes(self) -> None:
        """Config-first knobs for history / browse page sizes (Slice B)."""
        try:
            import labdesk_core

            general = (labdesk_core.load_config() or {}).get("general") or {}
            hist = int(general.get("history_page_size") or _DEFAULT_HISTORY_PAGE)
            browse = int(general.get("browse_files_page_size") or _TRACKED_LIST_CAP)
            if hist > 0:
                self._history_page = hist
            if browse > 0:
                self._browse_page = browse
        except Exception:
            pass

    def _apply_forge_labels(self) -> None:
        """Rename MR/CI tabs and buttons for the active forge."""
        info = forge_info()
        self._forge_info = info
        plural = pr_label_plural(info)
        singular = pr_label(info)
        ci = ci_tab_label(info)
        open_lbl = open_in_label(info)
        try:
            self.tabs.setTabText(self._pipelines_tab_index, ci)
            self.tabs.setTabText(self._mrs_tab_index, plural)
            if hasattr(self, "_runners_tab_index"):
                self.tabs.setTabText(
                    self._runners_tab_index, str(info.get("runners_label") or "Runners")
                )
        except Exception:
            pass
        if hasattr(self, "btn_mr_open"):
            self.btn_mr_open.setText(open_lbl)
        if hasattr(self, "btn_pipeline_open"):
            self.btn_pipeline_open.setText(open_lbl)
        if hasattr(self, "btn_runner_open"):
            self.btn_runner_open.setText(open_lbl)
        can_pause = bool(info.get("supports_runner_pause"))
        can_delete = bool(info.get("supports_runner_delete"))
        if hasattr(self, "btn_runner_pause"):
            self.btn_runner_pause.setVisible(can_pause)
            self.btn_runner_enable.setVisible(can_pause)
            self.btn_runner_delete.setVisible(can_delete)
        if hasattr(self, "btn_job_play"):
            playable = bool(info.get("supports_play_job", True))
            self.btn_job_play.setVisible(playable)
        if hasattr(self, "btn_mr"):
            self.btn_mr.setText(f"Create {singular.lower()}…")
        if hasattr(self, "mr_summary") and "No " in (self.mr_summary.text() or ""):
            self.mr_summary.setText(f"No {plural.lower()} loaded yet.")

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
        tip = tr("Working offline — network git actions disabled.") if not available else ""
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
        if hasattr(self, "btn_mr_refresh"):
            widgets.extend([self.btn_mr_refresh, self.btn_mr_open])
        if hasattr(self, "btn_sub_update"):
            widgets.extend(
                [
                    self.btn_sub_refresh,
                    self.btn_sub_init,
                    self.btn_sub_update,
                    self.btn_sub_sync,
                    self.btn_lfs_refresh,
                    self.btn_lfs_pull,
                ]
            )
        return widgets

    def _build_git_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel(tr("Submodules")))
        self.submodules_summary = QLabel(tr("No submodules loaded yet."))
        self.submodules_summary.setWordWrap(True)
        layout.addWidget(self.submodules_summary)
        self.submodules_list = QListWidget()
        self.submodules_list.currentItemChanged.connect(self._on_submodule_selected)
        layout.addWidget(self.submodules_list, stretch=1)
        sub_row = QHBoxLayout()
        self.btn_sub_refresh = QPushButton(tr("Refresh"))
        self.btn_sub_refresh.clicked.connect(self._refresh_git_ext)
        sub_row.addWidget(self.btn_sub_refresh)
        self.btn_sub_init = QPushButton(tr("Init"))
        self.btn_sub_init.clicked.connect(self._submodule_init)
        sub_row.addWidget(self.btn_sub_init)
        self.btn_sub_update = QPushButton(tr("Update…"))
        self.btn_sub_update.clicked.connect(self._submodule_update)
        sub_row.addWidget(self.btn_sub_update)
        self.btn_sub_sync = QPushButton(tr("Sync"))
        self.btn_sub_sync.clicked.connect(self._submodule_sync)
        sub_row.addWidget(self.btn_sub_sync)
        sub_row.addStretch(1)
        layout.addLayout(sub_row)

        layout.addWidget(QLabel(tr("Git LFS")))
        self.lfs_summary = QLabel(tr("LFS status not loaded yet."))
        self.lfs_summary.setWordWrap(True)
        layout.addWidget(self.lfs_summary)
        lfs_row = QHBoxLayout()
        self.btn_lfs_refresh = QPushButton(tr("Refresh"))
        self.btn_lfs_refresh.clicked.connect(self._refresh_git_ext)
        lfs_row.addWidget(self.btn_lfs_refresh)
        self.btn_lfs_pull = QPushButton(tr("Pull LFS objects…"))
        self.btn_lfs_pull.clicked.connect(self._lfs_pull)
        lfs_row.addWidget(self.btn_lfs_pull)
        lfs_row.addStretch(1)
        layout.addLayout(lfs_row)
        self._set_submodule_actions(False)
        return page

    def _build_compare_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        pick = QHBoxLayout()
        pick.addWidget(QLabel(tr("Base")))
        self.compare_base = QComboBox()
        self.compare_base.setMinimumWidth(160)
        pick.addWidget(self.compare_base, stretch=1)
        pick.addWidget(QLabel(tr("Other")))
        self.compare_other = QComboBox()
        self.compare_other.setMinimumWidth(160)
        pick.addWidget(self.compare_other, stretch=1)
        self.btn_compare = QPushButton(tr("Compare"))
        self.btn_compare.clicked.connect(self._run_compare)
        pick.addWidget(self.btn_compare)
        self.btn_compare_mr = QPushButton(tr("Create MR/PR from compare…"))
        self.btn_compare_mr.clicked.connect(self._create_mr_from_compare)
        self.btn_compare_mr.setEnabled(False)
        self.btn_compare_mr.setToolTip(
            tr("Run Compare when the other ref is ahead of the base, then create.")
        )
        pick.addWidget(self.btn_compare_mr)
        layout.addLayout(pick)

        self.compare_summary = QLabel(tr("Pick two refs and Compare."))
        self.compare_summary.setWordWrap(True)
        layout.addWidget(self.compare_summary)
        self._compare_ahead = 0
        self._compare_base_ref = ""
        self._compare_other_ref = ""
        self._compare_selected_path: str | None = None

        split = QSplitter()
        self.compare_commits = QListWidget()
        split.addWidget(self.compare_commits)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.compare_files = QListWidget()
        self.compare_files.setMaximumHeight(140)
        self.compare_files.currentItemChanged.connect(self._on_compare_file_selected)
        right_layout.addWidget(QLabel(tr("Changed files")))
        right_layout.addWidget(self.compare_files)
        self.compare_diff = DiffView(placeholder=tr("Tip-to-tip unified or side-by-side diff."))
        right_layout.addWidget(self.compare_diff, stretch=1)
        diff_row = QHBoxLayout()
        self.compare_trunc_hint = QLabel("")
        self.compare_trunc_hint.setWordWrap(True)
        diff_row.addWidget(self.compare_trunc_hint, stretch=1)
        self.btn_compare_open = QPushButton(tr("Open external…"))
        self.btn_compare_open.clicked.connect(self._open_compare_file_external)
        self.btn_compare_open.setEnabled(False)
        diff_row.addWidget(self.btn_compare_open)
        right_layout.addLayout(diff_row)
        split.addWidget(right)

        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([280, 700])
        layout.addWidget(split, stretch=1)
        return page

    def _build_mrs_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.mr_summary = QLabel(tr("No merge requests loaded yet."))
        self.mr_summary.setWordWrap(True)
        layout.addWidget(self.mr_summary)
        self.mr_list = QListWidget()
        layout.addWidget(self.mr_list, stretch=1)
        row = QHBoxLayout()
        self.btn_mr_refresh = QPushButton(tr("Refresh"))
        self.btn_mr_refresh.clicked.connect(self._refresh_mrs)
        row.addWidget(self.btn_mr_refresh)
        self.btn_mr_open = QPushButton(tr("Open in GitLab"))
        self.btn_mr_open.clicked.connect(self._open_selected_mr)
        self.btn_mr_open.setEnabled(False)
        row.addWidget(self.btn_mr_open)
        self.btn_mr_detail = QPushButton(tr("Details…"))
        self.btn_mr_detail.clicked.connect(self._open_mr_detail)
        self.btn_mr_detail.setEnabled(False)
        row.addWidget(self.btn_mr_detail)
        row.addStretch(1)
        layout.addLayout(row)
        self.mr_list.currentItemChanged.connect(self._on_mr_selected)
        self.mr_list.itemDoubleClicked.connect(lambda _item: self._open_mr_detail())
        return page

    def _build_pipelines_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.pipeline_summary = QLabel(tr("No pipeline loaded yet."))
        self.pipeline_summary.setWordWrap(True)
        layout.addWidget(self.pipeline_summary)
        self.pipeline_jobs = QListWidget()
        layout.addWidget(self.pipeline_jobs, stretch=1)
        row = QHBoxLayout()
        self.btn_pipeline_refresh = QPushButton(tr("Refresh"))
        self.btn_pipeline_refresh.clicked.connect(self._refresh_pipelines)
        row.addWidget(self.btn_pipeline_refresh)
        self.btn_pipeline_open = QPushButton(tr("Open in GitLab"))
        self.btn_pipeline_open.clicked.connect(self._open_pipeline)
        self.btn_pipeline_open.setEnabled(False)
        row.addWidget(self.btn_pipeline_open)
        self.btn_play_job = QPushButton(tr("Play manual job…"))
        self.btn_play_job.clicked.connect(self._play_selected_job)
        row.addWidget(self.btn_play_job)
        self.btn_job_log = QPushButton(tr("Job log…"))
        self.btn_job_log.clicked.connect(self._open_selected_job_log)
        self.btn_job_log.setEnabled(False)
        self.btn_job_log.setToolTip(
            tr("Open the selected job in the forge (log tail in-app deferred).")
        )
        row.addWidget(self.btn_job_log)
        row.addStretch(1)
        layout.addLayout(row)
        self.pipeline_jobs.currentItemChanged.connect(self._on_pipeline_job_selected)
        return page

    def _build_runners_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.runners_summary = QLabel(tr("No project runners loaded yet."))
        self.runners_summary.setWordWrap(True)
        layout.addWidget(self.runners_summary)
        self.project_runners = QListWidget()
        self.project_runners.currentItemChanged.connect(self._on_project_runner_selected)
        layout.addWidget(self.project_runners, stretch=1)
        row = QHBoxLayout()
        self.btn_runners_refresh = QPushButton(tr("Refresh"))
        self.btn_runners_refresh.clicked.connect(self._refresh_project_runners)
        row.addWidget(self.btn_runners_refresh)
        self.btn_runner_pause = QPushButton(tr("Pause"))
        self.btn_runner_pause.clicked.connect(lambda: self._set_project_runner_paused(True))
        row.addWidget(self.btn_runner_pause)
        self.btn_runner_enable = QPushButton(tr("Enable"))
        self.btn_runner_enable.clicked.connect(
            lambda: self._set_project_runner_paused(False)
        )
        row.addWidget(self.btn_runner_enable)
        self.btn_runner_delete = QPushButton(tr("Delete…"))
        self.btn_runner_delete.clicked.connect(self._delete_project_runner)
        row.addWidget(self.btn_runner_delete)
        self.btn_runner_open = QPushButton(tr("Open in forge"))
        self.btn_runner_open.clicked.connect(self._open_project_runner)
        row.addWidget(self.btn_runner_open)
        row.addStretch(1)
        layout.addLayout(row)
        self._set_project_runner_actions(False)
        return page

    def refresh(self) -> None:
        """Reload local git panels (async) plus online pipeline/MR panels."""
        self._maybe_fetch_on_focus(force=False)
        self._history_offset = 0
        self._refresh_local_async()
        self._refresh_pipelines()
        self._refresh_project_runners()
        self._refresh_mrs()
        self._refresh_git_ext()

    def _refresh_local_async(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path
        hist_limit = int(getattr(self, "_history_page", _DEFAULT_HISTORY_PAGE)) + int(
            getattr(self, "_history_offset", 0)
        )

        def work():
            import labdesk_core

            branch = labdesk_core.repo_branch(path)
            summary = ""
            try:
                summary = labdesk_core.repo_head_summary(path)
            except Exception:
                summary = ""
            sync = {}
            try:
                sync = dict(labdesk_core.repo_ahead_behind(path) or {})
            except Exception:
                sync = {}
            git_state = ""
            try:
                git_state = labdesk_core.repo_git_state(path)
            except Exception:
                git_state = ""
            conflicts = []
            try:
                conflicts = list(labdesk_core.repo_list_conflicts(path) or [])
            except Exception:
                conflicts = []
            changes_raw = [
                dict(e) if hasattr(e, "items") else e
                for e in (labdesk_core.repo_status(path) or [])
            ]
            changes_truncated = len(changes_raw) > _CHANGES_LIST_CAP
            changes = changes_raw[:_CHANGES_LIST_CAP]
            # Slice B: Changes is dirty-only; tracked browse is a separate dialog.
            commits = [
                dict(c) if hasattr(c, "items") else c
                for c in (labdesk_core.repo_log(path, hist_limit) or [])
            ]
            branches = dict(labdesk_core.repo_list_branches(path) or {})
            return {
                "branch": branch,
                "summary": summary,
                "sync": sync,
                "git_state": git_state,
                "conflicts": conflicts,
                "changes": changes,
                "changes_truncated": changes_truncated,
                "commits": commits,
                "branches": branches,
            }

        def on_ok(data) -> None:
            self._apply_local_refresh(data or {})

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.footer.setText(f"[{code}] {msg}")
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_refresh],
            status=self.footer.setText,
            working_message=tr("Loading repository…"),
        )

    def _apply_local_refresh(self, data: dict) -> None:
        branch = data.get("branch") or ""
        summary = data.get("summary") or ""
        sync = data.get("sync") or {}
        head_line = f"{self.repo_path}  ({branch})"
        if summary:
            head_line += f"\nHEAD: {summary}"
        ahead = behind = 0
        upstream = ""
        try:
            ahead = int(sync.get("ahead") or 0)
            behind = int(sync.get("behind") or 0)
            upstream = sync.get("upstream") or ""
            if upstream:
                parts = []
                if ahead:
                    parts.append(f"↑{ahead}")
                if behind:
                    parts.append(f"↓{behind}")
                if ahead and behind:
                    parts.append("diverged")
                if not parts:
                    parts.append("up to date")
                head_line += f"\nUpstream {upstream}: {' '.join(parts)}"
        except Exception:
            pass
        self.header.setText(head_line)
        self._update_sync_banner(ahead, behind, upstream, data.get("conflicts") or [])

        conflicts = data.get("conflicts") or []
        if conflicts and hasattr(self, "btn_conflicts"):
            self.btn_conflicts.setEnabled(True)
            self.btn_conflicts.setText(f"Resolve conflicts… ({len(conflicts)})")
        elif hasattr(self, "btn_conflicts"):
            state = str(data.get("git_state") or "")
            mid = "Merge" in state or "Rebase" in state
            self.btn_conflicts.setEnabled(bool(mid))
            self.btn_conflicts.setText(tr("Resolve conflicts…"))

        self._populate_changes(
            branch=branch,
            summary=summary,
            changes=data.get("changes") or [],
            changes_truncated=bool(data.get("changes_truncated")),
        )
        self._populate_history(data.get("commits") or [])
        self._populate_branches(data.get("branches") or {})
        try:
            self._refresh_compare_refs()
        except Exception:
            pass

    def _set_status_chip(self, widget: QLabel | None, text: str) -> None:
        """Show a header chip only when it has something useful to say."""
        if widget is None:
            return
        cleaned = (text or "").strip()
        widget.setText(cleaned)
        if hasattr(widget, "setVisible"):
            widget.setVisible(bool(cleaned))

    def _update_sync_banner(
        self, ahead: int, behind: int, upstream: str, conflicts: list
    ) -> None:
        if not hasattr(self, "sync_banner"):
            return
        if conflicts:
            self._set_status_chip(
                self.sync_banner,
                f"Conflicts in progress ({len(conflicts)} path(s)) — "
                "Resolve conflicts… or open an external editor.",
            )
            return
        if not upstream:
            self._set_status_chip(
                self.sync_banner,
                tr("No upstream set — push then Set upstream, or fetch after tracking exists."),
            )
            return
        if ahead and behind:
            self._set_status_chip(
                self.sync_banner,
                f"Diverged from {upstream}: ↑{ahead} ↓{behind}. "
                "Pull offers merge/rebase; Compare shows tip-to-tip diff.",
            )
        elif behind:
            self._set_status_chip(
                self.sync_banner,
                f"Behind {upstream} by {behind} — Pull to update, or Fetch then Compare.",
            )
        elif ahead:
            self._set_status_chip(
                self.sync_banner,
                f"Ahead of {upstream} by {ahead} — Push, or create an MR/PR.",
            )
        else:
            # Header already shows upstream when in sync — hide redundant banner.
            self._set_status_chip(self.sync_banner, "")

    def _populate_changes(
        self,
        *,
        branch: str,
        summary: str,
        changes: list,
        changes_truncated: bool = False,
        tracked: list | None = None,
        tracked_truncated: bool = False,
        browse: bool = False,
    ) -> None:
        # tracked/browse kept for test back-compat; Slice B ignores them (dirty-only).
        _ = (tracked, tracked_truncated, browse)
        self.files.clear()
        self.diff.clear()
        self.btn_editor.setEnabled(False)
        if hasattr(self, "btn_external"):
            self.btn_external.setEnabled(False)

        if changes:
            staged_only = [
                e for e in changes if e.get("staged") and not e.get("unstaged")
            ]
            other = [
                e for e in changes if not (e.get("staged") and not e.get("unstaged"))
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
            if changes_truncated:
                more = QListWidgetItem(
                    f"— …and more changes (showing first {_CHANGES_LIST_CAP}) —"
                )
                more.setFlags(Qt.ItemFlag.NoItemFlags)
                self.files.addItem(more)
        else:
            tip = QListWidgetItem(
                "— Working tree clean (Browse files… for tracked paths) —"
            )
            tip.setFlags(Qt.ItemFlag.NoItemFlags)
            self.files.addItem(tip)

        n_changes = len(changes)
        if n_changes == 0:
            bits = [tr("Working tree clean")]
            if branch:
                bits.append(f"branch {branch}")
            if summary:
                bits.append(summary)
            self.footer.setText(" · ".join(bits))
        else:
            n_staged = sum(1 for e in changes if e.get("staged"))
            self.footer.setText(
                f"{n_changes} changed path(s) · {n_staged} staged"
                + (
                    f" · changes list capped at {_CHANGES_LIST_CAP}"
                    if changes_truncated
                    else ""
                )
            )

    def _populate_history(self, commits: list) -> None:
        self.commits.clear()
        self.commit_meta.setText("")
        self.commit_diff.clear()
        if not commits:
            self.commits.addItem(QListWidgetItem(tr("(no commits)")))
            self.commit_meta.setText(tr("This repository has no commits yet."))
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

    def _populate_branches(self, data: dict) -> None:
        current = data.get("current") or ""
        self.branches.clear()
        names = list(data.get("branches") or [])
        if not names:
            tip = QListWidgetItem(tr("(no branches)"))
            tip.setFlags(Qt.ItemFlag.NoItemFlags)
            self.branches.addItem(tip)
            return
        for name in names:
            label = f"* {name}" if name == current else f"  {name}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.branches.addItem(item)
            if name == current:
                self.branches.setCurrentItem(item)

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
        self.btn_stage = QPushButton(tr("Stage"))
        self.btn_stage.clicked.connect(self._stage_selected)
        stage_row.addWidget(self.btn_stage)
        self.btn_unstage = QPushButton(tr("Unstage"))
        self.btn_unstage.clicked.connect(self._unstage_selected)
        stage_row.addWidget(self.btn_unstage)
        self.btn_stage_all = QPushButton(tr("Stage all"))
        self.btn_stage_all.clicked.connect(self._stage_all)
        stage_row.addWidget(self.btn_stage_all)
        self.btn_discard = QPushButton(tr("Discard…"))
        self.btn_discard.clicked.connect(self._discard_selected)
        stage_row.addWidget(self.btn_discard)
        self.btn_browse_files = QPushButton(tr("Browse files…"))
        self.btn_browse_files.clicked.connect(self._toggle_browse_files)
        stage_row.addWidget(self.btn_browse_files)
        left_layout.addLayout(stage_row)

        left_layout.addWidget(QLabel(tr("Commit message")))
        self.commit_message = QTextEdit()
        self.commit_message.setPlaceholderText(
            tr("Summary (required)\n\nOptional longer description…")
        )
        self.commit_message.setFixedHeight(90)
        left_layout.addWidget(self.commit_message)
        self.btn_commit = QPushButton(tr("Commit"))
        self.btn_commit.clicked.connect(self._commit)
        left_layout.addWidget(self.btn_commit)

        split.addWidget(left)

        self.diff = DiffView(
            placeholder=tr("Select a changed file for a diff, or a tracked file to view.")
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

        self.commit_diff = DiffView(placeholder=tr("Select a commit to view its patch."))
        right_layout.addWidget(self.commit_diff, stretch=1)

        self.commit_files = QListWidget()
        self.commit_files.setMaximumHeight(140)
        self.commit_files.currentItemChanged.connect(self._on_commit_file_selected)
        right_layout.addWidget(QLabel(tr("Changed files")))
        right_layout.addWidget(self.commit_files)
        hist_diff_row = QHBoxLayout()
        self.commit_trunc_hint = QLabel("")
        self.commit_trunc_hint.setWordWrap(True)
        hist_diff_row.addWidget(self.commit_trunc_hint, stretch=1)
        self.btn_commit_open = QPushButton(tr("Open external…"))
        self.btn_commit_open.clicked.connect(self._open_commit_file_external)
        self.btn_commit_open.setEnabled(False)
        hist_diff_row.addWidget(self.btn_commit_open)
        right_layout.addLayout(hist_diff_row)
        split.addWidget(right)

        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([320, 700])
        layout.addWidget(split)
        hist_row = QHBoxLayout()
        self.btn_history_more = QPushButton(tr("Load more…"))
        self.btn_history_more.clicked.connect(self._load_more_history)
        hist_row.addWidget(self.btn_history_more)
        hist_row.addStretch(1)
        layout.addLayout(hist_row)
        return page

    def _build_branches_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.branches = QListWidget()
        self.branches.itemDoubleClicked.connect(lambda _i: self._switch_branch())
        layout.addWidget(self.branches, stretch=1)
        row = QHBoxLayout()
        self.btn_switch_branch = QPushButton(tr("Switch"))
        self.btn_switch_branch.clicked.connect(self._switch_branch)
        row.addWidget(self.btn_switch_branch)
        self.btn_create_branch = QPushButton(tr("Create…"))
        self.btn_create_branch.clicked.connect(self._create_branch)
        row.addWidget(self.btn_create_branch)
        self.btn_merge_branch = QPushButton(tr("Merge into current…"))
        self.btn_merge_branch.clicked.connect(self._merge_branch)
        row.addWidget(self.btn_merge_branch)
        self.btn_delete_branch = QPushButton(tr("Delete…"))
        self.btn_delete_branch.clicked.connect(self._delete_branch)
        row.addWidget(self.btn_delete_branch)
        self.btn_set_upstream = QPushButton(tr("Set upstream"))
        self.btn_set_upstream.clicked.connect(self._set_upstream)
        row.addWidget(self.btn_set_upstream)
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
                self, tr("Merge"), tr("Select a branch to merge into the current branch.")
            )
            return
        try:
            import labdesk_core

            current = labdesk_core.repo_branch(self.repo_path)
            if name == current:
                QMessageBox.information(
                    self, tr("Merge"), tr("Select a different branch than the current one.")
                )
                return
            reply = QMessageBox.question(
                self,
                tr("Merge"),
                f"Merge '{name}' into '{current}'?\n\n"
                "On conflict, LabDesk leaves the merge in progress so you can "
                "resolve in LabDesk or externally.",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            msg = labdesk_core.repo_merge_branch(self.repo_path, name)
            self.footer.setText(msg)
            self.refresh()
            QMessageBox.information(self, tr("Merge"), msg)
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
            self.footer.setText(tr("Fetch OK."))
            self._refresh_header()
            QMessageBox.information(self, tr("Fetch"), tr("Fetched from origin."))

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
            working_message=tr("Working…"),
        )

    def _refresh_branches(self) -> None:
        self._refresh_local_async()

    def _selected_branch_name(self) -> str | None:
        item = self.branches.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return str(data) if data else None

    def _switch_branch(self) -> None:
        name = self._selected_branch_name()
        if not name:
            QMessageBox.information(self, tr("Switch branch"), tr("Select a branch."))
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
            QMessageBox.information(self, tr("Edit in LabDesk"), tr("Select a file first."))
            return
        from labdesk_ui.widgets.code_editor import open_code_editor

        abs_path = Path(self.repo_path) / rel
        win = open_code_editor(abs_path, parent=self)
        if win is not None:
            self.footer.setText(f"Editing {rel} in LabDesk.")

    def _open_external(self) -> None:
        rel = self._selected_file_path()
        if not rel:
            QMessageBox.information(self, tr("Open external"), tr("Select a file first."))
            return
        abs_path = Path(self.repo_path) / rel
        try:
            open_path(abs_path)
            self.footer.setText(f"Opened {rel} in external application.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _create_mr(self) -> None:
        info = getattr(self, "_forge_info", None) or forge_info()
        kind = pr_label(info)
        create_title = f"Create {kind.lower()}"
        if not self._network_available:
            QMessageBox.information(
                self,
                create_title,
                f"Working offline — cannot create a {kind.lower()}.",
            )
            return
        try:
            import labdesk_core

            project = labdesk_core.resolve_repo_project(self.repo_path)
            dlg = MRDialog(
                source_branch=project.get("current_branch")
                or labdesk_core.repo_branch(self.repo_path),
                target_branch=project.get("default_branch") or "main",
                project_label=project.get("path_with_namespace") or "",
                parent=self,
                kind_label=kind,
            )
            if dlg.exec() != MRDialog.DialogCode.Accepted:
                return
            source, target, title, description, draft = dlg.values()
            if not title:
                QMessageBox.warning(self, create_title, tr("Title is required."))
                return
            if not source or not target:
                QMessageBox.warning(
                    self,
                    create_title,
                    tr("Source and target branches are required."),
                )
                return
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")
            return

        from labdesk_ui.utils.async_jobs import run_in_background

        project_id = int(project["project_id"])
        desc = description or None

        def work():
            import labdesk_core

            return labdesk_core.create_merge_request(
                project_id, source, target, title, desc, draft
            )

        def on_ok(mr) -> None:
            self._busy = False
            web = (mr or {}).get("web_url") or ""
            iid = (mr or {}).get("iid")
            self.footer.setText(f"Created !{iid}")
            self._refresh_mrs()
            reply = QMessageBox.question(
                self,
                f"{kind} created",
                f"Created !{iid}: {(mr or {}).get('title') or title}\n\n"
                f"Open details in LabDesk?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes and iid is not None:
                dlg = MRDetailDialog(
                    project_id=project_id,
                    mr_iid=int(iid),
                    parent=self,
                    kind_label=kind,
                )
                dlg.exec()
                self._refresh_mrs()
            elif web:
                open_reply = QMessageBox.question(
                    self,
                    open_in_label(info),
                    f"{open_in_label(info)}?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if open_reply == QMessageBox.StandardButton.Yes:
                    try:
                        open_url(web)
                    except Exception as exc:
                        code, msg = format_error(exc)
                        QMessageBox.warning(
                            self, f"Error {code}", f"[{code}] {msg}"
                        )

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
            working_message=f"Creating {kind.lower()}…",
        )

    def _refresh_changes(self) -> None:
        self._refresh_local_async()

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
            QMessageBox.information(self, tr("Stage"), tr("Select one or more changed files."))
            return
        try:
            import labdesk_core

            n = labdesk_core.repo_stage(self.repo_path, paths)
            self.footer.setText(f"Staged {n} path(s).")
            self._refresh_local_async()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _unstage_selected(self) -> None:
        paths = self._selected_change_paths()
        if not paths:
            QMessageBox.information(self, tr("Unstage"), tr("Select one or more staged files."))
            return
        try:
            import labdesk_core

            n = labdesk_core.repo_unstage(self.repo_path, paths)
            self.footer.setText(f"Unstaged {n} path(s).")
            self._refresh_local_async()
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
                QMessageBox.information(self, tr("Stage all"), tr("Nothing to stage."))
                return
            n = labdesk_core.repo_stage(self.repo_path, paths)
            self.footer.setText(f"Staged {n} path(s).")
            self._refresh_local_async()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _commit(self) -> None:
        message = self.commit_message.toPlainText().strip()
        if not message:
            QMessageBox.warning(self, tr("Commit"), tr("Enter a commit message."))
            return
        try:
            import labdesk_core

            oid = labdesk_core.repo_commit(self.repo_path, message)
            short = oid[:7] if oid else ""
            self.commit_message.clear()
            self.footer.setText(f"Committed {short}.")
            self.refresh()
            QMessageBox.information(self, tr("Commit"), f"Created commit {short}.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _refresh_history(self) -> None:
        self._refresh_local_async()

    def _on_file_selected(self, current: QListWidgetItem | None, _prev) -> None:
        if current is None:
            self.btn_editor.setEnabled(False)
            if hasattr(self, "btn_external"):
                self.btn_external.setEnabled(False)
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            self.btn_editor.setEnabled(False)
            if hasattr(self, "btn_external"):
                self.btn_external.setEnabled(False)
            return
        rel = data.get("path") or ""
        kind = data.get("kind") or "change"
        can_open = bool(rel)
        self.btn_editor.setEnabled(can_open)
        if hasattr(self, "btn_external"):
            self.btn_external.setEnabled(can_open)
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

            if hasattr(self, "commit_files"):
                try:
                    files = list(labdesk_core.repo_commit_files(self.repo_path, oid) or [])
                    _populate_diff_file_list(self.commit_files, files)
                except Exception:
                    self.commit_files.clear()

            self._commit_selected_oid = oid
            self._commit_selected_path = None
            patch = labdesk_core.repo_commit_diff(self.repo_path, oid)
            _set_colored_diff(self.commit_diff, patch)
            if hasattr(self, "commit_trunc_hint"):
                if _diff_looks_truncated(patch):
                    self.commit_trunc_hint.setText(
                        tr("Diff truncated — select a file and Open external for the full content.")
                    )
                else:
                    self.commit_trunc_hint.setText("")
            if hasattr(self, "btn_commit_open"):
                self.btn_commit_open.setEnabled(False)
        except Exception as exc:
            code, msg = format_error(exc)
            self.commit_meta.setText(f"[{code}] {msg}")
            self.commit_diff.setPlainText(str(exc))

    def _confirm_stash_include_untracked(self, title: str, body: str) -> bool | None:
        """Yes = stash with untracked; No = tracked/staged only; Cancel = abort.

        Returns True/False for include_untracked, or None if cancelled.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(body)
        box.setInformativeText(
            tr("Yes = include untracked files\n"
            "No = tracked and staged changes only\n"
            "Cancel = do nothing")
        )
        yes = box.addButton(tr("Yes (with untracked)"), QMessageBox.ButtonRole.YesRole)
        no = box.addButton(tr("No (tracked only)"), QMessageBox.ButtonRole.NoRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(yes)
        box.exec()
        clicked = box.clickedButton()
        if clicked is yes:
            return True
        if clicked is no:
            return False
        return None

    def _pull(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path
        did_stash = False

        # Safer pull when dirty: offer stash first (still allow pull without).
        try:
            import labdesk_core

            dirty = list(labdesk_core.repo_status(path) or [])
        except Exception:
            dirty = []
        if dirty:
            reply = QMessageBox.question(
                self,
                tr("Pull with local changes"),
                tr("Working tree is dirty. Stash before pull?\n\n"
                "Yes = stash then pull\n"
                "No = pull without stashing\n"
                "Cancel = abort"),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                include = self._confirm_stash_include_untracked(
                    "Stash before pull",
                    "Include untracked files in the stash?",
                )
                if include is None:
                    return
                try:
                    import labdesk_core

                    labdesk_core.repo_stash_save(path, include)
                    did_stash = True
                except Exception as exc:
                    code, msg = format_error(exc)
                    QMessageBox.critical(
                        self, f"Error {code}", f"[{code}] {msg}\n\n{exc}"
                    )
                    return

        def work():
            import labdesk_core

            return labdesk_core.repo_pull(path)

        def on_ok(msg) -> None:
            self._busy = False
            self.footer.setText(str(msg))
            self.refresh()
            QMessageBox.information(self, tr("Pull"), str(msg))
            if did_stash:
                pop = QMessageBox.question(
                    self,
                    tr("Apply stash?"),
                    tr("Pull succeeded. Apply (pop) the stash you just created?"),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if pop == QMessageBox.StandardButton.Yes:
                    self._stash_pop(confirm=False)

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self._busy = False
            if code == "LD-GIT-024":
                choice = QMessageBox.question(
                    self,
                    tr("Histories diverged"),
                    f"[{code}] {msg}\n\nMerge upstream now?\n"
                    "(No = offer rebase; Cancel = abort)",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes,
                )
                if choice == QMessageBox.StandardButton.Yes:
                    self._merge_upstream()
                elif choice == QMessageBox.StandardButton.No:
                    self._rebase_upstream()
                return
            if code == "LD-GIT-020":
                reply = QMessageBox.question(
                    self,
                    tr("Conflicts"),
                    f"[{code}] {msg}\n\nOpen conflict resolver?",
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._open_conflicts()
                return
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        self._busy = True
        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=self._network_busy_widgets(),
            status=self.footer.setText,
            working_message=tr("Working…"),
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
            tr("Force push"),
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
                tr("Push"),
                "Force push succeeded." if force else "Push succeeded.",
            )
            self._refresh_local_async()
            if not force:
                self._maybe_offer_set_upstream()
            if not force and self._network_available:
                info = getattr(self, "_forge_info", None) or forge_info()
                kind = pr_label(info)
                reply = QMessageBox.question(
                    self,
                    f"Create {kind.lower()}?",
                    f"Push succeeded. Create a {kind.lower()} on "
                    f"{forge_name(info)} now?",
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
            working_message=tr("Working…"),
        )

    def _maybe_offer_set_upstream(self) -> None:
        try:
            import labdesk_core

            sync = dict(labdesk_core.repo_ahead_behind(self.repo_path) or {})
            if sync.get("upstream"):
                return
            branch = labdesk_core.repo_branch(self.repo_path)
        except Exception:
            return
        reply = QMessageBox.question(
            self,
            tr("Set upstream?"),
            f"No upstream tracking branch for '{branch}'.\n"
            f"Set upstream to origin/{branch}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._set_upstream()

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
            QMessageBox.information(self, tr("Compare"), tr("Select base and other refs."))
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
                    # Check the other tip's branch name on the forge.
                    branch = _ref_to_branch_name(other)
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
                    host = forge_name(getattr(self, "_forge_info", None))
                    lines.append(
                        f"Remote branch '{br}': "
                        + (
                            f"present on {host}"
                            if exists
                            else f"not found on {host}"
                        )
                    )
                elif remote.get("error"):
                    lines.append(f"Remote check skipped: {remote.get('error')}")
            elif not online:
                lines.append("Remote check skipped (offline).")
            self.compare_summary.setText("\n".join(lines))
            self._compare_ahead = ahead
            self._compare_base_ref = base
            self._compare_other_ref = other
            self._compare_selected_path = None
            if hasattr(self, "btn_compare_mr"):
                self.btn_compare_mr.setEnabled(
                    ahead > 0 and bool(self._network_available)
                )
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
            if hasattr(self, "compare_files"):
                _populate_diff_file_list(self.compare_files, cmp.get("files") or [])
            patch = cmp.get("diff_text") or ""
            _set_colored_diff(self.compare_diff, patch)
            if hasattr(self, "compare_trunc_hint"):
                if _diff_looks_truncated(patch):
                    self.compare_trunc_hint.setText(
                        tr("Diff truncated — select a file and Open external for the full content.")
                    )
                else:
                    self.compare_trunc_hint.setText("")
            if hasattr(self, "btn_compare_open"):
                self.btn_compare_open.setEnabled(False)

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
            working_message=tr("Comparing…"),
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
        plural = pr_label_plural(getattr(self, "_forge_info", None))
        if n == 0:
            meta = tr("No open {plural}.").format(plural=plural.lower())
        else:
            meta = f"{n} open {plural.lower()}"
        if cached:
            meta += " (cached)"
        if fetched_at:
            meta += f", fetched_at {fetched_at}"
        self.mr_summary.setText(meta)
        self.btn_mr_open.setEnabled(False)
        if hasattr(self, "btn_mr_detail"):
            self.btn_mr_detail.setEnabled(False)
        self._last_mrs_for_notify = list(mrs)
        self._update_notify_chip(mrs, getattr(self, "_last_pipe_for_notify", None))

    def _load_cached_mrs(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            info = labdesk_core.resolve_repo_project(path)
            project_id = int(info["project_id"])
            cached = labdesk_core.cached_merge_requests(project_id)
            return {"project_id": project_id, "cached": cached}

        plural = pr_label_plural(getattr(self, "_forge_info", None)).lower()

        def on_ok(data) -> None:
            self._mr_project_id = (data or {}).get("project_id")
            cached = (data or {}).get("cached")
            if not cached:
                self.mr_summary.setText(f"Offline — no cached {plural}.")
                self.mr_list.clear()
                return
            self._apply_mrs_view(
                cached.get("merge_requests") or [],
                cached=True,
                fetched_at=cached.get("fetched_at"),
            )

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.mr_summary.setText(
                f"Offline — could not load {plural} cache [{code}]: {msg}"
            )

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_mr_refresh] if hasattr(self, "btn_mr_refresh") else None,
            status=self.footer.setText,
            working_message=f"Loading cached {plural}…",
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
            working_message=(
                f"Loading {pr_label_plural(getattr(self, '_forge_info', None)).lower()}…"
            ),
        )

    def _on_mr_selected(self, current, _previous) -> None:
        mr = current.data(Qt.ItemDataRole.UserRole) if current else None
        ok = isinstance(mr, dict)
        self.btn_mr_open.setEnabled(bool(ok and mr.get("web_url")))
        if hasattr(self, "btn_mr_detail"):
            info = getattr(self, "_forge_info", None) or forge_info()
            self.btn_mr_detail.setEnabled(
                bool(
                    ok
                    and mr.get("iid") is not None
                    and info.get("supports_mr_detail", True)
                    and self._network_available
                )
            )

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
            # Detail lives on the Pipelines tab; keep header chrome quiet when idle.
            self._set_status_chip(self.pipeline_chip, "")
            self.pipeline_summary.setText(
                tr("No pipeline for the current branch.")
                if not cached
                else tr("Offline — no cached pipeline for this branch.")
            )
            self.pipeline_jobs.clear()
            self.btn_pipeline_open.setEnabled(False)
            self.btn_play_job.setEnabled(False)
            if hasattr(self, "btn_job_log"):
                self.btn_job_log.setEnabled(False)
            self._last_pipe_for_notify = None
            self._update_notify_chip(
                getattr(self, "_last_mrs_for_notify", []) or [], None
            )
            return
        status = pipe.get("status") or "unknown"
        self._pipeline_web_url = pipe.get("web_url")
        chip = f"Pipeline: {status}"
        if cached:
            chip = f"Pipeline: {status} (cached)"
        self._set_status_chip(self.pipeline_chip, chip)
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
        self._last_pipe_for_notify = pipe
        self._update_notify_chip(
            getattr(self, "_last_mrs_for_notify", []) or [], pipe
        )
        if hasattr(self, "btn_job_log"):
            self.btn_job_log.setEnabled(False)

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
            self._set_status_chip(self.pipeline_chip, tr("Pipeline: (offline)"))
            self.pipeline_summary.setText(f"Offline — could not load cache [{code}]: {msg}")
            self.btn_play_job.setEnabled(False)

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_pipeline_refresh] if hasattr(self, "btn_pipeline_refresh") else None,
            status=self.footer.setText,
            working_message=tr("Loading cached pipeline…"),
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
            self._set_status_chip(self.pipeline_chip, f"Pipeline: [{code}]")
            self.pipeline_summary.setText(f"[{code}] {msg}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_pipeline_refresh] if hasattr(self, "btn_pipeline_refresh") else None,
            status=self.footer.setText,
            working_message=tr("Loading pipeline…"),
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
            QMessageBox.information(self, tr("Play job"), tr("Working offline."))
            return
        item = self.pipeline_jobs.currentItem()
        if item is None:
            QMessageBox.information(self, tr("Play job"), tr("Select a manual job first."))
            return
        job = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(job, dict):
            return
        if not _job_is_playable(job):
            status = job.get("status") or "?"
            when = job.get("when") or "?"
            QMessageBox.information(
                self,
                tr("Play job"),
                "Only jobs waiting for manual start can be played from LabDesk.\n\n"
                f"Selected job status={status}, when={when}.\n"
                "Look for a row marked ▶ (status manual).",
            )
            return
        name = job.get("name") or job.get("id")
        reply = QMessageBox.question(
            self,
            tr("Play job"),
            f"Start manual job '{name}'?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._pipeline_project_id is None:
            QMessageBox.warning(self, tr("Play job"), tr("Project id unknown; refresh pipeline."))
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
            working_message=tr("Starting job…"),
        )

    def changeEvent(self, event) -> None:
        from PySide6.QtCore import QEvent

        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowActivate:
            self._maybe_fetch_on_focus(force=False)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._stage_selected)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._commit)
        QShortcut(QKeySequence("Ctrl+Shift+F"), self, activated=self._fetch)
        QShortcut(QKeySequence("Ctrl+Shift+L"), self, activated=self._pull)
        QShortcut(QKeySequence("Ctrl+Shift+P"), self, activated=self._push)
        if hasattr(self, "btn_stage"):
            self.btn_stage.setToolTip(tr("Stage selected paths (Ctrl+S)"))
        if hasattr(self, "btn_commit"):
            self.btn_commit.setToolTip(tr("Commit staged changes (Ctrl+Return)"))
        if hasattr(self, "btn_fetch"):
            self.btn_fetch.setToolTip(tr("Fetch (Ctrl+Shift+F)"))
        if hasattr(self, "btn_pull"):
            self.btn_pull.setToolTip(tr("Pull (Ctrl+Shift+L)"))
        if hasattr(self, "btn_push"):
            self.btn_push.setToolTip(tr("Push (Ctrl+Shift+P)"))

    def _config_fetch_on_focus(self) -> bool:
        try:
            import labdesk_core

            cfg = labdesk_core.load_config() or {}
            general = cfg.get("general") or {}
            return bool(general.get("fetch_on_focus", True))
        except Exception:
            return True

    def _maybe_fetch_on_focus(self, *, force: bool) -> None:
        if not self._network_available:
            return
        if not force and not self._config_fetch_on_focus():
            return
        if getattr(self, "_busy", False):
            return
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            labdesk_core.repo_fetch(path)
            return True

        def on_ok(_r) -> None:
            try:
                self._refresh_header()
            except Exception:
                pass

        def on_err(_c, _m, _e) -> None:
            pass

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[],
            status=lambda _t: None,
            working_message="",
        )

    def _toggle_browse_files(self) -> None:
        """Open virtualized tracked-file browser (does not fill Changes list)."""
        page = int(getattr(self, "_browse_page", _TRACKED_LIST_CAP) or _TRACKED_LIST_CAP)
        dlg = BrowseFilesDialog(self.repo_path, parent=self, page_size=page)
        dlg.exec()

    def _load_more_history(self) -> None:
        page = int(getattr(self, "_history_page", 200))
        self._history_offset = int(getattr(self, "_history_offset", 0)) + page
        self._refresh_local_async()

    def _discard_selected(self) -> None:
        paths = self._selected_change_paths()
        if not paths:
            QMessageBox.information(self, tr("Discard"), tr("Select a changed path."))
            return
        reply = QMessageBox.warning(
            self,
            tr("Discard"),
            f"Discard local changes for {len(paths)} path(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            import labdesk_core

            for p in paths:
                labdesk_core.repo_discard_path(self.repo_path, p)
            self._refresh_local_async()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _stash(self) -> None:
        include = self._confirm_stash_include_untracked(
            "Stash",
            "Stash local changes?",
        )
        if include is None:
            return
        try:
            import labdesk_core

            msg = labdesk_core.repo_stash_save(self.repo_path, include)
            self.footer.setText(str(msg))
            self.refresh()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _stash_pop(self, confirm: bool = True) -> None:
        if confirm:
            reply = QMessageBox.question(
                self,
                tr("Pop stash"),
                tr("Apply and remove the latest stash?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            import labdesk_core

            msg = labdesk_core.repo_stash_pop(self.repo_path)
            self.footer.setText(str(msg))
            self.refresh()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _merge_upstream(self) -> None:
        try:
            import labdesk_core

            msg = labdesk_core.repo_merge_upstream(self.repo_path)
            self.footer.setText(str(msg))
            self.refresh()
            QMessageBox.information(self, tr("Merge"), str(msg))
        except Exception as exc:
            code, msg = format_error(exc)
            if code == "LD-GIT-020":
                self._open_conflicts(mode="merge")
                return
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _rebase_upstream(self) -> None:
        reply = QMessageBox.question(
            self,
            tr("Rebase"),
            tr("Rebase current branch onto upstream?"),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            import labdesk_core

            msg = labdesk_core.repo_rebase_upstream(self.repo_path)
            self.footer.setText(str(msg))
            self.refresh()
            QMessageBox.information(self, tr("Rebase"), str(msg))
        except Exception as exc:
            code, msg = format_error(exc)
            if code == "LD-GIT-020":
                self._open_conflicts(mode="rebase")
                return
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _open_conflicts(self, mode: str | None = None) -> None:
        resolved_mode = mode or "merge"
        try:
            import labdesk_core

            state = labdesk_core.repo_git_state(self.repo_path)
            if "Rebase" in str(state):
                resolved_mode = "rebase"
        except Exception:
            pass
        dlg = ConflictDialog(self.repo_path, parent=self, mode=resolved_mode)
        dlg.exec()
        self.refresh()

    def _delete_branch(self) -> None:
        name = self._selected_branch_name()
        if not name:
            QMessageBox.information(self, tr("Delete branch"), tr("Select a local branch."))
            return
        reply = QMessageBox.warning(
            self,
            tr("Delete branch"),
            f"Delete local branch '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            import labdesk_core

            labdesk_core.repo_delete_local_branch(self.repo_path, name)
            self.refresh()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _set_upstream(self) -> None:
        try:
            import labdesk_core

            branch = labdesk_core.repo_branch(self.repo_path)
            labdesk_core.repo_set_upstream(self.repo_path, branch)
            self.footer.setText(f"Upstream set to origin/{branch}")
            self._refresh_header()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _create_mr_from_compare(self) -> None:
        other = self.compare_other.currentText().strip()
        base = self.compare_base.currentText().strip()
        if not other or not base:
            QMessageBox.information(
                self, tr("Create from compare"), tr("Pick base and other refs first.")
            )
            return
        if not self._network_available:
            QMessageBox.information(
                self,
                tr("Create from compare"),
                tr("Working offline — cannot create on the forge."),
            )
            return
        ahead = int(getattr(self, "_compare_ahead", 0) or 0)
        if ahead <= 0:
            QMessageBox.information(
                self,
                tr("Create from compare"),
                tr("Run Compare first when the other ref is ahead of the base."),
            )
            return
        source = _ref_to_branch_name(other)
        target = _ref_to_branch_name(base)
        try:
            import labdesk_core

            project = labdesk_core.resolve_repo_project(self.repo_path)
            info = getattr(self, "_forge_info", None) or forge_info()
            kind = pr_label(info)
            dlg = MRDialog(
                source_branch=source,
                target_branch=target,
                project_label=project.get("path_with_namespace") or "",
                parent=self,
                kind_label=kind,
                title_prefill=f"{source} into {target}",
            )
            if dlg.exec() != MRDialog.DialogCode.Accepted:
                return
            src, tgt, title, description, draft = dlg.values()
            if not title:
                QMessageBox.warning(self, f"Create {kind.lower()}", tr("Title is required."))
                return
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")
            return

        from labdesk_ui.utils.async_jobs import run_in_background

        project_id = int(project["project_id"])
        desc = description or None

        def work():
            import labdesk_core

            return labdesk_core.create_merge_request(
                project_id, src, tgt, title, desc, draft
            )

        def on_ok(mr) -> None:
            self._busy = False
            iid = (mr or {}).get("iid")
            self.footer.setText(f"Created !{iid}")
            self._refresh_mrs()
            if iid is not None:
                reply = QMessageBox.question(
                    self,
                    f"{kind} created",
                    f"Created !{iid}. Open details in LabDesk?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    detail = MRDetailDialog(
                        project_id=project_id,
                        mr_iid=int(iid),
                        parent=self,
                        kind_label=kind,
                    )
                    detail.exec()
                    self._refresh_mrs()

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
            working_message=f"Creating {kind.lower()}…",
        )

    def _open_mr_detail(self) -> None:
        info = getattr(self, "_forge_info", None) or forge_info()
        if not info.get("supports_mr_detail", True):
            QMessageBox.information(
                self,
                tr("Details"),
                f"{info.get('display_name') or 'This forge'} does not expose "
                "MR/PR detail to LabDesk.",
            )
            return
        if not self._network_available:
            QMessageBox.information(
                self,
                tr("Details"),
                tr("Working offline — open the forge in a browser, or reconnect."),
            )
            return
        item = self.mr_list.currentItem()
        if item is None:
            return
        mr = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(mr, dict) or mr.get("iid") is None:
            return
        project_id = self._mr_project_id
        if not project_id:
            try:
                import labdesk_core

                project_id = int(
                    labdesk_core.resolve_repo_project(self.repo_path)["project_id"]
                )
            except Exception as exc:
                code, msg = format_error(exc)
                QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")
                return
        dlg = MRDetailDialog(
            project_id=int(project_id),
            mr_iid=int(mr["iid"]),
            parent=self,
            kind_label=pr_label(info),
        )
        dlg.exec()
        self._refresh_mrs()

    def _on_commit_file_selected(self, current: QListWidgetItem | None, _prev) -> None:
        if current is None:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        path = data.get("path") or ""
        if not path:
            return
        oid = getattr(self, "_commit_selected_oid", None) or ""
        self._commit_selected_path = path
        if hasattr(self, "btn_commit_open"):
            self.btn_commit_open.setEnabled(True)
        self.footer.setText(f"Commit file: {path}")
        if not oid:
            return
        try:
            import labdesk_core

            if hasattr(labdesk_core, "repo_commit_diff_path"):
                patch = labdesk_core.repo_commit_diff_path(self.repo_path, oid, path)
            else:
                patch = labdesk_core.repo_commit_diff(self.repo_path, oid)
            _set_colored_diff(self.commit_diff, patch)
            if hasattr(self, "commit_trunc_hint"):
                if data.get("binary") or patch.startswith("(binary"):
                    self.commit_trunc_hint.setText(
                        tr("Binary file — use Open external to view outside LabDesk.")
                    )
                elif _diff_looks_truncated(patch):
                    self.commit_trunc_hint.setText(
                        tr("Diff truncated — Open external for the full file.")
                    )
                else:
                    self.commit_trunc_hint.setText("")
        except Exception as exc:
            code, msg = format_error(exc)
            self.commit_diff.setPlainText(f"[{code}] {msg}\n{exc}")

    def _open_commit_file_external(self) -> None:
        path = getattr(self, "_commit_selected_path", None)
        if not path:
            QMessageBox.information(
                self, tr("Open external"), tr("Select a changed file first.")
            )
            return
        full = Path(self.repo_path) / path
        if not full.exists():
            QMessageBox.information(
                self,
                tr("Open external"),
                f"{path} is not in the working tree (deleted or not checked out).",
            )
            return
        try:
            open_path(full)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _on_compare_file_selected(self, current: QListWidgetItem | None, _prev) -> None:
        if current is None:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        path = data.get("path") or ""
        if not path:
            return
        self._compare_selected_path = path
        if hasattr(self, "btn_compare_open"):
            self.btn_compare_open.setEnabled(True)
        base = getattr(self, "_compare_base_ref", "") or ""
        other = getattr(self, "_compare_other_ref", "") or ""
        if not base or not other:
            return
        try:
            import labdesk_core

            if hasattr(labdesk_core, "repo_compare_diff_path"):
                patch = labdesk_core.repo_compare_diff_path(
                    self.repo_path, base, other, path
                )
            else:
                return
            _set_colored_diff(self.compare_diff, patch)
            if hasattr(self, "compare_trunc_hint"):
                if data.get("binary") or patch.startswith("(binary"):
                    self.compare_trunc_hint.setText(
                        tr("Binary file — use Open external to view outside LabDesk.")
                    )
                elif _diff_looks_truncated(patch):
                    self.compare_trunc_hint.setText(
                        tr("Diff truncated — Open external for the full file.")
                    )
                else:
                    self.compare_trunc_hint.setText("")
        except Exception as exc:
            code, msg = format_error(exc)
            self.compare_diff.setPlainText(f"[{code}] {msg}\n{exc}")

    def _open_compare_file_external(self) -> None:
        path = getattr(self, "_compare_selected_path", None)
        if not path:
            QMessageBox.information(
                self, tr("Open external"), tr("Select a changed file first.")
            )
            return
        full = Path(self.repo_path) / path
        if not full.exists():
            QMessageBox.information(
                self,
                tr("Open external"),
                f"{path} is not in the working tree (deleted or not checked out).",
            )
            return
        try:
            open_path(full)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _on_pipeline_job_selected(self, current, _previous) -> None:
        job = current.data(Qt.ItemDataRole.UserRole) if current else None
        ok = isinstance(job, dict)
        if hasattr(self, "btn_job_log"):
            self.btn_job_log.setEnabled(
                bool(ok and (job.get("web_url") or self._pipeline_web_url))
            )

    def _open_selected_job_log(self) -> None:
        """Slice H stub: open job (or pipeline) in the forge — no in-app log tail yet."""
        item = self.pipeline_jobs.currentItem() if hasattr(self, "pipeline_jobs") else None
        job = item.data(Qt.ItemDataRole.UserRole) if item else None
        url = None
        if isinstance(job, dict):
            url = job.get("web_url") or None
        if not url:
            url = getattr(self, "_pipeline_web_url", None)
        if not url:
            QMessageBox.information(
                self,
                tr("Job log"),
                tr("No job URL available. Use Open in … on the pipeline, or refresh online."),
            )
            return
        try:
            open_url(url)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _set_project_runner_actions(self, enabled: bool) -> None:
        info = getattr(self, "_forge_info", None) or forge_info()
        can_pause = bool(info.get("supports_runner_pause"))
        can_delete = bool(info.get("supports_runner_delete"))
        if hasattr(self, "btn_runner_pause"):
            self.btn_runner_pause.setEnabled(enabled and can_pause)
            self.btn_runner_enable.setEnabled(enabled and can_pause)
            self.btn_runner_delete.setEnabled(enabled and can_delete)
            self.btn_runner_open.setEnabled(enabled)

    def _on_project_runner_selected(self, current, _prev) -> None:
        ok = bool(current and isinstance(current.data(Qt.ItemDataRole.UserRole), dict))
        self._set_project_runner_actions(ok)

    def _selected_project_runner(self) -> dict | None:
        item = (
            self.project_runners.currentItem()
            if hasattr(self, "project_runners")
            else None
        )
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _refresh_project_runners(self) -> None:
        if not hasattr(self, "project_runners"):
            return
        if not self._network_available:
            self.runners_summary.setText(tr("Offline — cannot load project runners."))
            return
        from labdesk_ui.utils.async_jobs import run_in_background
        from labdesk_ui.plugins.admin_view import _runner_row_text

        path = self.repo_path

        def work():
            import labdesk_core

            project = labdesk_core.resolve_repo_project(path) or {}
            pid = project.get("project_id") or project.get("id")
            if pid is None:
                return {"error": "no_project", "rows": []}
            hint = project.get("path_with_namespace")
            rows = list(labdesk_core.list_project_runners(int(pid), hint) or [])
            return {"error": None, "rows": rows, "project_id": int(pid)}

        def on_ok(data) -> None:
            data = data or {}
            self.project_runners.clear()
            if data.get("error") == "no_project":
                self.runners_summary.setText(
                    tr("No forge project linked — clone/open from Projects to manage runners.")
                )
                return
            rows = list(data.get("rows") or [])
            self._runner_project_id = data.get("project_id")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item = QListWidgetItem(_runner_row_text(row))
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.project_runners.addItem(item)
            label = (getattr(self, "_forge_info", None) or forge_info()).get(
                "runners_label"
            ) or "Runners"
            if rows:
                self.runners_summary.setText(
                    f"{len(rows)} project {str(label).lower()}."
                )
            else:
                self.runners_summary.setText(
                    tr("No project {label}.").format(label=str(label).lower())
                )
            self._set_project_runner_actions(False)

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.project_runners.clear()
            self.runners_summary.setText(f"[{code}] {msg}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_runners_refresh]
            if hasattr(self, "btn_runners_refresh")
            else [],
            status=lambda t: self.runners_summary.setText(t),
            working_message=tr("Loading project runners…"),
        )

    def _set_project_runner_paused(self, paused: bool) -> None:
        row = self._selected_project_runner()
        if not row:
            return
        rid = str(row.get("id") or "")
        pid = getattr(self, "_runner_project_id", None)
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            import labdesk_core

            return labdesk_core.set_runner_paused(rid, paused, pid)

        def on_ok(_r) -> None:
            self._refresh_project_runners()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_runner_pause, self.btn_runner_enable],
            status=lambda t: self.runners_summary.setText(t),
            working_message=tr("Updating runner…"),
        )

    def _delete_project_runner(self) -> None:
        row = self._selected_project_runner()
        if not row:
            return
        rid = str(row.get("id") or "")
        desc = row.get("description") or rid
        reply = QMessageBox.question(
            self,
            tr("Delete runner?"),
            f"Delete runner '{desc}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        pid = getattr(self, "_runner_project_id", None)
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            import labdesk_core

            labdesk_core.delete_runner(rid, pid)
            return True

        def on_ok(_r) -> None:
            self._refresh_project_runners()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_runner_delete],
            status=lambda t: self.runners_summary.setText(t),
            working_message=tr("Deleting runner…"),
        )

    def _open_project_runner(self) -> None:
        row = self._selected_project_runner()
        url = (row or {}).get("web_url") if row else None
        if not url:
            QMessageBox.information(
                self,
                tr("Runners"),
                tr("No runner URL — use Admin → Open admin for the instance list."),
            )
            return
        try:
            open_url(url)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _update_notify_chip(self, mrs: list, pipe: dict | None) -> None:
        if not hasattr(self, "notify_chip"):
            return
        notes: list[str] = []
        status = ((pipe or {}).get("status") or "").lower()
        if status in {"failed", "canceled", "cancelled"}:
            notes.append(f"Pipeline {status} on {(pipe or {}).get('ref') or 'branch'}")
        newest = None
        for mr in mrs:
            u = (mr or {}).get("updated_at")
            if u and (newest is None or u > newest):
                newest = u
        if newest and getattr(self, "_last_mr_updated", None) and newest > self._last_mr_updated:
            notes.append("MR/PR list updated since last view")
        if newest:
            self._last_mr_updated = newest
        self._set_status_chip(self.notify_chip, " · ".join(notes))

    def _set_submodule_actions(self, has_selection: bool) -> None:
        # Init / Update / Sync work on selection when present, else all.
        for btn in (
            getattr(self, "btn_sub_init", None),
            getattr(self, "btn_sub_update", None),
            getattr(self, "btn_sub_sync", None),
        ):
            if btn is not None:
                btn.setEnabled(True)
        _ = has_selection  # selection only changes the target scope

    def _on_submodule_selected(self, current, _prev) -> None:
        ok = bool(current and isinstance(current.data(Qt.ItemDataRole.UserRole), dict))
        self._set_submodule_actions(ok)

    def _selected_submodule(self) -> dict | None:
        item = (
            self.submodules_list.currentItem()
            if hasattr(self, "submodules_list")
            else None
        )
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _submodule_target(self) -> str | None:
        row = self._selected_submodule()
        if not row:
            return None
        return str(row.get("name") or row.get("path") or "") or None

    @staticmethod
    def _format_submodule_row(row: dict) -> str:
        path = row.get("path") or row.get("name") or "?"
        status = row.get("status_summary") or "?"
        oid = row.get("workdir_id") or row.get("index_id") or row.get("head_id") or "—"
        flags = []
        if not row.get("initialized"):
            flags.append("uninit")
        if row.get("dirty"):
            flags.append("dirty")
        flag_s = f" [{', '.join(flags)}]" if flags else ""
        return f"{path}  {oid}  ({status}){flag_s}"

    def _refresh_git_ext(self) -> None:
        if not hasattr(self, "submodules_list"):
            return
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            subs = [
                dict(s) if hasattr(s, "items") else s
                for s in (labdesk_core.repo_list_submodules(path) or [])
            ]
            lfs = dict(labdesk_core.repo_lfs_status(path) or {})
            return {"submodules": subs, "lfs": lfs}

        def on_ok(data) -> None:
            data = data or {}
            self.submodules_list.clear()
            rows = list(data.get("submodules") or [])
            for row in rows:
                item = QListWidgetItem(self._format_submodule_row(row))
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.submodules_list.addItem(item)
            if not rows:
                self.submodules_summary.setText(tr("No submodules in this repository."))
            else:
                dirty = sum(1 for r in rows if r.get("dirty"))
                uninit = sum(1 for r in rows if not r.get("initialized"))
                self.submodules_summary.setText(
                    tr("{n} submodule(s) — {u} uninitialized, {d} dirty.").format(
                        n=len(rows), u=uninit, d=dirty
                    )
                )
            lfs = dict(data.get("lfs") or {})
            ver = lfs.get("version") or ""
            summary = lfs.get("summary") or ""
            bits = []
            if lfs.get("available"):
                bits.append(ver or tr("git-lfs available"))
            else:
                bits.append(tr("git-lfs not available on host"))
            if lfs.get("mentions_lfs"):
                bits.append(tr("repo references LFS"))
            head = " · ".join(bits)
            self.lfs_summary.setText(f"{head}\n{summary}".strip())
            self.btn_lfs_pull.setEnabled(bool(lfs.get("available")))
            if not lfs.get("available"):
                self.btn_lfs_pull.setToolTip(
                    tr("git-lfs was not found. The Flatpak build bundles it; "
                    "unpackaged installs need git-lfs on PATH.")
                )
            else:
                self.btn_lfs_pull.setToolTip("")

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.submodules_summary.setText(f"[{code}] {msg}")
            self.lfs_summary.setText(f"[{code}] {msg}\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[
                self.btn_sub_refresh,
                self.btn_lfs_refresh,
            ],
            status=lambda t: self.submodules_summary.setText(t),
            working_message=tr("Loading submodules / LFS…"),
        )

    def _submodule_init(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path
        target = self._submodule_target()

        def work():
            import labdesk_core

            return labdesk_core.repo_submodule_init(path, target)

        def on_ok(n) -> None:
            QMessageBox.information(
                self, tr("Submodules"), tr("Initialized {n} submodule(s).").format(n=n)
            )
            self._refresh_git_ext()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=self._network_busy_widgets(),
            status=lambda t: self.submodules_summary.setText(t),
            working_message=tr("Initializing submodules…"),
        )

    def _submodule_update(self) -> None:
        target = self._submodule_target()
        scope = tr("selected submodule") if target else tr("all submodules")
        reply = QMessageBox.question(
            self,
            tr("Update submodules?"),
            tr("Fetch and check out {scope}? This may use the network.").format(scope=scope),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            return labdesk_core.repo_submodule_update(path, target)

        def on_ok(n) -> None:
            QMessageBox.information(
                self, tr("Submodules"), tr("Updated {n} submodule(s).").format(n=n)
            )
            self._refresh_git_ext()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=self._network_busy_widgets(),
            status=lambda t: self.submodules_summary.setText(t),
            working_message=tr("Updating submodules…"),
        )

    def _submodule_sync(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path
        target = self._submodule_target()

        def work():
            import labdesk_core

            return labdesk_core.repo_submodule_sync(path, target)

        def on_ok(n) -> None:
            QMessageBox.information(
                self, tr("Submodules"), tr("Synced {n} submodule(s).").format(n=n)
            )
            self._refresh_git_ext()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_sub_sync],
            status=lambda t: self.submodules_summary.setText(t),
            working_message=tr("Syncing submodule URLs…"),
        )

    def _lfs_pull(self) -> None:
        reply = QMessageBox.question(
            self,
            tr("Pull LFS objects?"),
            tr("Run git lfs pull for this repository?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path

        def work():
            import labdesk_core

            return labdesk_core.repo_lfs_pull(path)

        def on_ok(msg) -> None:
            QMessageBox.information(self, tr("Git LFS"), str(msg or tr("LFS pull completed.")))
            self._refresh_git_ext()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=self._network_busy_widgets(),
            status=lambda t: self.lfs_summary.setText(t),
            working_message=tr("Pulling LFS objects…"),
        )

