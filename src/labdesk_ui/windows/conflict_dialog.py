"""Structured conflict resolve dialog (V2) — not a general code editor."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
)

from labdesk_ui.utils.helpers import format_error
from labdesk_ui.utils.open_external import open_path


class ConflictDialog(QDialog):
    """List conflicted paths; accept ours/theirs, open external, mark resolved."""

    def __init__(self, repo_path: str, *, parent=None, mode: str = "merge") -> None:
        super().__init__(parent)
        self.repo_path = str(Path(repo_path).resolve())
        self.mode = mode  # merge | rebase
        self.setWindowTitle(f"Resolve conflicts ({self.mode})")
        self.resize(960, 600)

        layout = QVBoxLayout(self)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        split = QHBoxLayout()
        self.paths = QListWidget()
        self.paths.currentItemChanged.connect(self._on_selected)
        split.addWidget(self.paths, stretch=1)

        right = QVBoxLayout()
        self.tabs = QTabWidget()
        mono = QFont("monospace")
        self.preview_work = QTextEdit()
        self.preview_work.setReadOnly(True)
        self.preview_work.setFont(mono)
        self.preview_ours = QTextEdit()
        self.preview_ours.setReadOnly(True)
        self.preview_ours.setFont(mono)
        self.preview_theirs = QTextEdit()
        self.preview_theirs.setReadOnly(True)
        self.preview_theirs.setFont(mono)
        self.tabs.addTab(self.preview_work, "Working tree")
        self.tabs.addTab(self.preview_ours, "Ours")
        self.tabs.addTab(self.preview_theirs, "Theirs")
        right.addWidget(self.tabs, stretch=1)

        actions = QHBoxLayout()
        self.btn_ours = QPushButton("Accept ours")
        self.btn_ours.clicked.connect(self._accept_ours)
        actions.addWidget(self.btn_ours)
        self.btn_theirs = QPushButton("Accept theirs")
        self.btn_theirs.clicked.connect(self._accept_theirs)
        actions.addWidget(self.btn_theirs)
        self.btn_external = QPushButton("Open external")
        self.btn_external.clicked.connect(self._open_external)
        actions.addWidget(self.btn_external)
        self.btn_mark = QPushButton("Mark resolved")
        self.btn_mark.clicked.connect(self._mark_resolved)
        actions.addWidget(self.btn_mark)
        right.addLayout(actions)
        split.addLayout(right, stretch=2)
        layout.addLayout(split, stretch=1)

        buttons = QDialogButtonBox()
        self.btn_continue = buttons.addButton(
            "Continue", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.btn_abort = buttons.addButton(
            "Abort", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.btn_continue.clicked.connect(self._continue)
        self.btn_abort.clicked.connect(self._abort)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._reload()

    def _selected_path(self) -> str | None:
        item = self.paths.currentItem()
        if item is None:
            return None
        return item.text()

    def _set_path_actions_enabled(self, enabled: bool) -> None:
        for btn in (
            self.btn_ours,
            self.btn_theirs,
            self.btn_external,
            self.btn_mark,
        ):
            btn.setEnabled(enabled)

    def _reload(self) -> None:
        import labdesk_core

        self.paths.clear()
        try:
            conflicts = list(labdesk_core.repo_list_conflicts(self.repo_path) or [])
            state = labdesk_core.repo_git_state(self.repo_path)
        except Exception as exc:
            code, msg = format_error(exc)
            self.status.setText(f"[{code}] {msg}")
            self.btn_continue.setEnabled(False)
            self._set_path_actions_enabled(False)
            return
        self.status.setText(
            f"{len(conflicts)} conflicted path(s). Mode: {self.mode}. Repo state: {state}"
        )
        for p in conflicts:
            self.paths.addItem(QListWidgetItem(p))
        # Continue only when nothing remains conflicted (still allow Abort).
        self.btn_continue.setEnabled(len(conflicts) == 0)
        self._set_path_actions_enabled(bool(conflicts))
        if conflicts:
            self.paths.setCurrentRow(0)
        else:
            for view in (self.preview_work, self.preview_ours, self.preview_theirs):
                view.setPlainText(
                    "No conflicts remain. Continue merge/rebase, or Abort."
                )

    def _on_selected(self, current: QListWidgetItem | None, _prev) -> None:
        if current is None:
            return
        rel = current.text()
        try:
            import labdesk_core

            if hasattr(labdesk_core, "repo_conflict_side_text"):
                self.preview_work.setPlainText(
                    labdesk_core.repo_conflict_side_text(self.repo_path, rel, "work")
                )
                self.preview_ours.setPlainText(
                    labdesk_core.repo_conflict_side_text(self.repo_path, rel, "ours")
                )
                self.preview_theirs.setPlainText(
                    labdesk_core.repo_conflict_side_text(self.repo_path, rel, "theirs")
                )
                return
        except Exception as exc:
            # Fall through to working-tree-only preview.
            code, msg = format_error(exc)
            self.preview_ours.setPlainText(f"[{code}] {msg}")
            self.preview_theirs.setPlainText(f"[{code}] {msg}")

        full = Path(self.repo_path) / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
            if len(text) > 200_000:
                text = text[:200_000] + "\n\n… truncated …"
            self.preview_work.setPlainText(text)
        except OSError as exc:
            self.preview_work.setPlainText(f"(could not read {rel}: {exc})")

    def _accept_ours(self) -> None:
        rel = self._selected_path()
        if not rel:
            return
        try:
            import labdesk_core

            labdesk_core.repo_checkout_ours(self.repo_path, rel)
            labdesk_core.repo_mark_resolved(self.repo_path, rel)
            self._reload()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _accept_theirs(self) -> None:
        rel = self._selected_path()
        if not rel:
            return
        try:
            import labdesk_core

            labdesk_core.repo_checkout_theirs(self.repo_path, rel)
            labdesk_core.repo_mark_resolved(self.repo_path, rel)
            self._reload()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _open_external(self) -> None:
        rel = self._selected_path()
        if not rel:
            return
        try:
            open_path(Path(self.repo_path) / rel)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def _mark_resolved(self) -> None:
        rel = self._selected_path()
        if not rel:
            return
        try:
            import labdesk_core

            labdesk_core.repo_mark_resolved(self.repo_path, rel)
            self._reload()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _continue(self) -> None:
        try:
            import labdesk_core

            if self.mode == "rebase":
                msg = labdesk_core.repo_continue_rebase(self.repo_path)
            else:
                msg = labdesk_core.repo_continue_merge(self.repo_path)
            QMessageBox.information(self, "Continue", str(msg))
            self.accept()
        except Exception as exc:
            code, msg = format_error(exc)
            # Another conflict step (rebase): stay open and refresh.
            if code == "LD-GIT-020":
                QMessageBox.warning(
                    self,
                    "More conflicts",
                    f"[{code}] {msg}\n\nResolve the next conflicted path(s).",
                )
                self._reload()
                return
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")
            self._reload()

    def _abort(self) -> None:
        reply = QMessageBox.question(
            self,
            "Abort",
            f"Abort {self.mode} and reset to HEAD?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            import labdesk_core

            if self.mode == "rebase":
                msg = labdesk_core.repo_abort_rebase(self.repo_path)
            else:
                msg = labdesk_core.repo_abort_merge(self.repo_path)
            QMessageBox.information(self, "Abort", str(msg))
            self.accept()
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")
