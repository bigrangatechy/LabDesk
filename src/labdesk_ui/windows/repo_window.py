"""Local repository window — changes, files, history, push/pull."""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
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


def _format_commit_time(epoch: int | float | None) -> str:
    if epoch is None:
        return ""
    try:
        dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc).astimezone()
        return dt.strftime("%H:%M:%S  %d/%m/%Y")
    except (OverflowError, OSError, ValueError):
        return str(epoch)


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
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle(title or f"LabDesk — {repo_path}")
        self.resize(1100, 700)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        self.header = QLabel(repo_path)
        self.header.setWordWrap(True)
        self.header.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.header)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        row.addWidget(self.btn_refresh)

        self.btn_pull = QPushButton("Pull")
        self.btn_pull.clicked.connect(self._pull)
        row.addWidget(self.btn_pull)

        self.btn_push = QPushButton("Push")
        self.btn_push.clicked.connect(self._push)
        row.addWidget(self.btn_push)

        self.btn_force = QPushButton("Force push…")
        self.btn_force.clicked.connect(self._force_push)
        row.addWidget(self.btn_force)
        row.addStretch(1)
        layout.addLayout(row)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_changes_tab(), "Changes")
        self.tabs.addTab(self._build_history_tab(), "History")
        layout.addWidget(self.tabs, stretch=1)

        self.footer = QLabel("")
        self.footer.setWordWrap(True)
        layout.addWidget(self.footer)

        self.refresh()

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
        self.commit_message.setPlaceholderText("Summary (required)\n\nOptional longer description…")
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

    def refresh(self) -> None:
        self._refresh_header()
        self._refresh_changes()
        self._refresh_history()

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
            self.header.setText(head_line)
        except Exception as exc:
            code, msg = format_error(exc)
            self.header.setText(f"[{code}] {msg}")

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

            if changes:
                staged_only = [
                    e
                    for e in changes
                    if e.get("staged") and not e.get("unstaged")
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
                # Also stage anything that might only show as untracked etc.
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
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        rel = data.get("path") or ""
        kind = data.get("kind") or "change"
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
        try:
            import labdesk_core

            msg = labdesk_core.repo_pull(self.repo_path)
            self.footer.setText(msg)
            self.refresh()
            QMessageBox.information(self, "Pull", msg)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

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
        try:
            import labdesk_core

            labdesk_core.repo_push(self.repo_path, force)
            self.footer.setText("Force push OK." if force else "Push OK.")
            QMessageBox.information(
                self,
                "Push",
                "Force push succeeded." if force else "Push succeeded.",
            )
            self._refresh_history()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")
