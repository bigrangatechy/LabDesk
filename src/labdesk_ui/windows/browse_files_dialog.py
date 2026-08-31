"""Opt-in tracked-file browser — virtualized list + filter (Slice B)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, QStringListModel, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
)

from labdesk_ui.utils.helpers import format_error
from labdesk_ui.utils.open_external import open_path

# Default page size; overridden from config when available.
_DEFAULT_BROWSE_PAGE = 200
# Cap text preview fed to QTextEdit (matches core truncation spirit).
_PREVIEW_CHARS = 200_000


class BrowseFilesDialog(QDialog):
    """Browse tracked files without dumping them into the Changes QListWidget."""

    def __init__(self, repo_path: str, *, parent=None, page_size: int | None = None) -> None:
        super().__init__(parent)
        self.repo_path = str(Path(repo_path).resolve())
        self.page_size = int(page_size or _DEFAULT_BROWSE_PAGE)
        if self.page_size < 1:
            self.page_size = _DEFAULT_BROWSE_PAGE
        self.setWindowTitle("Browse tracked files")
        self.resize(900, 560)

        layout = QVBoxLayout(self)
        self.status = QLabel("Loading…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Substring filter (case-insensitive)")
        self.filter_edit.textChanged.connect(self._on_filter)
        filter_row.addWidget(self.filter_edit, stretch=1)
        layout.addLayout(filter_row)

        split = QSplitter()
        self.view = QListView()
        self.view.setUniformItemSizes(True)
        self.model = QStringListModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.view.setModel(self.proxy)
        self.view.selectionModel().currentChanged.connect(self._on_selected)
        split.addWidget(self.view)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFont("monospace"))
        self.preview.setPlaceholderText("Select a file to preview (truncated for large files).")
        split.addWidget(self.preview)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        split.setSizes([320, 580])
        layout.addWidget(split, stretch=1)

        row = QHBoxLayout()
        self.btn_open = QPushButton("Open in editor")
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_external)
        row.addWidget(self.btn_open)
        self.btn_more = QPushButton("Load more…")
        self.btn_more.clicked.connect(self._load_more)
        row.addWidget(self.btn_more)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._offset = 0
        self._all_paths: list[str] = []
        self._truncated = False
        self._load_page(reset=True)

    def _on_filter(self, text: str) -> None:
        self.proxy.setFilterFixedString(text.strip())

    def _current_path(self) -> str | None:
        idx = self.view.currentIndex()
        if not idx.isValid():
            return None
        return self.proxy.data(idx, Qt.ItemDataRole.DisplayRole)

    def _load_page(self, *, reset: bool) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        if reset:
            self._offset = 0
            self._all_paths = []
            self._truncated = False

        path = self.repo_path
        # Request offset+page_size+1 via limit; core returns first N paths only.
        limit = self._offset + self.page_size + 1

        def work():
            import labdesk_core

            return list(labdesk_core.repo_list_files(path, limit) or [])

        def on_ok(paths: list) -> None:
            paths = list(paths or [])
            truncated = len(paths) > self._offset + self.page_size
            chunk = paths[: self._offset + self.page_size]
            self._all_paths = chunk
            self._truncated = truncated
            self.model.setStringList(self._all_paths)
            shown = len(self._all_paths)
            note = f"{shown} tracked path(s)"
            if truncated:
                note += f" (capped; page size {self.page_size})"
            self.status.setText(note)
            self.btn_more.setEnabled(truncated)
            self._offset = shown

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.status.setText(f"[{code}] {msg}")
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_more],
            status=self.status.setText,
            working_message="Loading tracked files…",
        )

    def _load_more(self) -> None:
        self._load_page(reset=False)

    def _on_selected(self, current, _prev) -> None:
        rel = self.proxy.data(current, Qt.ItemDataRole.DisplayRole) if current.isValid() else None
        self.btn_open.setEnabled(bool(rel))
        if not rel:
            self.preview.clear()
            return
        from labdesk_ui.utils.async_jobs import run_in_background

        path = self.repo_path
        file_rel = str(rel)

        def work():
            import labdesk_core

            return labdesk_core.repo_show_file(path, file_rel)

        def on_ok(text) -> None:
            text = str(text or "")
            if len(text) > _PREVIEW_CHARS:
                text = text[:_PREVIEW_CHARS] + "\n\n… truncated …"
            self.preview.setPlainText(text)

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.preview.setPlainText(f"[{code}] {msg}\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[],
            status=lambda _t: None,
            working_message="",
        )

    def _open_external(self) -> None:
        rel = self._current_path()
        if not rel:
            return
        try:
            open_path(Path(self.repo_path) / rel)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")
