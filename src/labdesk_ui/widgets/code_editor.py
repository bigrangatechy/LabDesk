"""From-scratch in-app code editor (Slice I) — PySide6 only, no QScintilla.

Maintainable subset: open/save, undo/redo, find/replace, line numbers,
basic language highlighting, and large/binary file policy.
"""

from __future__ import annotations

from labdesk_ui.i18n import tr

import re
from pathlib import Path
from weakref import WeakValueDictionary

from PySide6.QtCore import QRect, QSize, Qt, QRegularExpression
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.utils.helpers import format_error
from labdesk_ui.utils.open_external import open_path

# Soft: warn but still editable. Hard: open read-only (offer external).
EDITOR_SOFT_MAX_BYTES = 512_000
EDITOR_HARD_MAX_BYTES = 2_000_000
_BINARY_PROBE = 8_192

# Keep one window per absolute path so re-open focuses existing.
_OPEN_EDITORS: WeakValueDictionary[str, "EditorWindow"] = WeakValueDictionary()


def probe_file_for_edit(path: Path) -> dict:
    """Return edit policy for *path* (size, binary, mode).

    Modes: ``editable``, ``readonly``, ``binary``, ``missing``.
    """
    p = Path(path)
    if not p.is_file():
        return {"mode": "missing", "size": 0, "message": "File not found."}
    size = p.stat().st_size
    try:
        head = p.read_bytes()[:_BINARY_PROBE]
    except OSError as exc:
        return {"mode": "missing", "size": size, "message": str(exc)}
    if b"\x00" in head:
        return {
            "mode": "binary",
            "size": size,
            "message": "Binary file — open externally.",
        }
    if size > EDITOR_HARD_MAX_BYTES:
        return {
            "mode": "readonly",
            "size": size,
            "message": (
                f"File is {size:,} bytes (limit {EDITOR_HARD_MAX_BYTES:,}). "
                "Opened read-only; use Open external for full edit."
            ),
        }
    if size > EDITOR_SOFT_MAX_BYTES:
        return {
            "mode": "editable",
            "size": size,
            "message": (
                f"Large file ({size:,} bytes). Editing may be slow."
            ),
            "warn": True,
        }
    return {"mode": "editable", "size": size, "message": ""}


def language_for_path(path: str | Path) -> str:
    """Map file suffix to a highlighter language key."""
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".rs": "rust",
        ".toml": "toml",
        ".md": "markdown",
        ".markdown": "markdown",
        ".json": "json",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".sh": "shell",
        ".bash": "shell",
        ".js": "javascript",
        ".ts": "javascript",
        ".tsx": "javascript",
        ".jsx": "javascript",
        ".c": "c",
        ".h": "c",
        ".cpp": "c",
        ".hpp": "c",
        ".cc": "c",
        ".css": "css",
        ".html": "html",
        ".htm": "html",
        ".xml": "html",
        ".sql": "sql",
    }.get(suffix, "plain")


class _BasicHighlighter(QSyntaxHighlighter):
    """Lightweight keyword / string / comment highlighter (not a full parser)."""

    _LANG: dict[str, dict] = {
        "python": {
            "keywords": (
                "and as assert async await break class continue def del elif else "
                "except False finally for from global if import in is lambda "
                "None nonlocal not or pass raise return True try while with yield"
            ).split(),
            "line_comment": "#",
            "strings": True,
        },
        "rust": {
            "keywords": (
                "as async await break const continue crate dyn else enum extern "
                "false fn for if impl in let loop match mod move mut pub ref "
                "return self Self static struct super trait true type unsafe use "
                "where while"
            ).split(),
            "line_comment": "//",
            "strings": True,
        },
        "javascript": {
            "keywords": (
                "async await break case catch class const continue debugger "
                "default delete do else export extends false finally for from "
                "function if import in instanceof let new null of return static "
                "super switch this throw true try typeof var void while with yield"
            ).split(),
            "line_comment": "//",
            "strings": True,
        },
        "c": {
            "keywords": (
                "auto break case char const continue default do double else enum "
                "extern float for goto if inline int long register return short "
                "signed sizeof static struct switch typedef union unsigned void "
                "volatile while bool true false nullptr"
            ).split(),
            "line_comment": "//",
            "strings": True,
        },
        "shell": {
            "keywords": (
                "if then else elif fi for while do done case esac function in "
                "select until export local return exit"
            ).split(),
            "line_comment": "#",
            "strings": True,
        },
        "sql": {
            "keywords": (
                "select from where join left right inner outer on group by order "
                "asc desc insert into values update set delete create table alter "
                "drop index and or not null as limit offset"
            ).split(),
            "line_comment": "--",
            "strings": True,
        },
        "toml": {
            "keywords": [],
            "line_comment": "#",
            "strings": True,
        },
        "yaml": {
            "keywords": ["true", "false", "null", "yes", "no"],
            "line_comment": "#",
            "strings": True,
        },
        "json": {
            "keywords": ["true", "false", "null"],
            "line_comment": None,
            "strings": True,
        },
        "css": {
            "keywords": [],
            "line_comment": None,
            "strings": True,
        },
        "html": {
            "keywords": [],
            "line_comment": None,
            "strings": True,
        },
        "markdown": {
            "keywords": [],
            "line_comment": None,
            "strings": False,
        },
        "plain": {
            "keywords": [],
            "line_comment": None,
            "strings": False,
        },
    }

    def __init__(self, document, language: str = "plain") -> None:
        super().__init__(document)
        self.set_language(language)

    def set_language(self, language: str) -> None:
        lang = self._LANG.get(language) or self._LANG["plain"]
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor(86, 156, 214))
        kw_fmt.setFontWeight(QFont.Weight.Bold)
        for word in lang["keywords"]:
            self._rules.append(
                (
                    QRegularExpression(rf"\b{re.escape(word)}\b"),
                    kw_fmt,
                )
            )

        if lang.get("strings"):
            str_fmt = QTextCharFormat()
            str_fmt.setForeground(QColor(206, 145, 120))
            self._rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
            self._rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))

        comment = lang.get("line_comment")
        if comment:
            c_fmt = QTextCharFormat()
            c_fmt.setForeground(QColor(106, 153, 85))
            self._rules.append(
                (QRegularExpression(rf"{re.escape(comment)}[^\n]*"), c_fmt)
            )

        if language == "markdown":
            h_fmt = QTextCharFormat()
            h_fmt.setForeground(QColor(86, 156, 214))
            h_fmt.setFontWeight(QFont.Weight.Bold)
            self._rules.append((QRegularExpression(r"^#{1,6}\s.*"), h_fmt))
            code_fmt = QTextCharFormat()
            code_fmt.setForeground(QColor(206, 145, 120))
            self._rules.append((QRegularExpression(r"`[^`]+`"), code_fmt))

        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 — Qt API
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class _LineNumberArea(QWidget):
    def __init__(self, editor: "_CodeEdit") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802
        self._editor.paint_line_numbers(event)


class _CodeEdit(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFont(QFont("monospace"))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self._line_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_area_width(0)
        self._highlight_current_line()

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(max(1, self.blockCount()))))
        return 8 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_area_width(self, _count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width(0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor(40, 40, 40, 40))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor(120, 120, 120))
                painter.drawText(
                    0,
                    top,
                    self._line_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self) -> None:
        if self.isReadOnly():
            self.setExtraSelections([])
            return
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor(255, 255, 180, 40))
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])


class EditorWindow(QMainWindow):
    """Non-modal editor window for a single file path."""

    def __init__(
        self,
        path: str | Path,
        *,
        parent=None,
        read_only: bool = False,
        status_message: str = "",
    ) -> None:
        super().__init__(parent)
        self.path = Path(path).resolve()
        self._dirty = False
        self._loading = True

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(900, 640)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.banner = QLabel(status_message or "")
        self.banner.setWordWrap(True)
        self.banner.setVisible(bool(status_message))
        layout.addWidget(self.banner)

        # Find / replace bar
        find_row = QHBoxLayout()
        find_row.addWidget(QLabel(tr("Find")))
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText(tr("Find…"))
        self.find_edit.returnPressed.connect(lambda: self.find_next(False))
        find_row.addWidget(self.find_edit, stretch=1)
        self.btn_find_next = QPushButton(tr("Next"))
        self.btn_find_next.clicked.connect(lambda: self.find_next(False))
        find_row.addWidget(self.btn_find_next)
        self.btn_find_prev = QPushButton(tr("Prev"))
        self.btn_find_prev.clicked.connect(lambda: self.find_next(True))
        find_row.addWidget(self.btn_find_prev)
        find_row.addWidget(QLabel(tr("Replace")))
        self.replace_edit = QLineEdit()
        find_row.addWidget(self.replace_edit, stretch=1)
        self.btn_replace = QPushButton(tr("Replace"))
        self.btn_replace.clicked.connect(self.replace_one)
        find_row.addWidget(self.btn_replace)
        self.btn_replace_all = QPushButton(tr("Replace all"))
        self.btn_replace_all.clicked.connect(self.replace_all)
        find_row.addWidget(self.btn_replace_all)
        layout.addLayout(find_row)

        self.editor = _CodeEdit()
        layout.addWidget(self.editor, stretch=1)
        self._highlighter = _BasicHighlighter(
            self.editor.document(), language_for_path(self.path)
        )

        tools = QHBoxLayout()
        self.btn_save = QPushButton(tr("Save"))
        self.btn_save.clicked.connect(self.save)
        tools.addWidget(self.btn_save)
        self.btn_external = QPushButton(tr("Open external"))
        self.btn_external.clicked.connect(self._open_external)
        tools.addWidget(self.btn_external)
        self.pos_label = QLabel("")
        tools.addWidget(self.pos_label)
        tools.addStretch(1)
        layout.addLayout(tools)

        self._build_actions()
        self.editor.cursorPositionChanged.connect(self._update_pos)
        self.editor.document().modificationChanged.connect(self._on_modified)

        self._load_file(read_only=read_only)
        self._loading = False
        self._update_title()
        self._update_pos()

    def _build_actions(self) -> None:
        act_save = QAction(tr("Save"), self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self.save)
        self.addAction(act_save)

        act_find = QAction(tr("Find"), self)
        act_find.setShortcut(QKeySequence.StandardKey.Find)
        act_find.triggered.connect(self._focus_find)
        self.addAction(act_find)

        act_close = QAction(tr("Close"), self)
        act_close.setShortcut(QKeySequence.StandardKey.Close)
        act_close.triggered.connect(self.close)
        self.addAction(act_close)

    def _load_file(self, *, read_only: bool) -> None:
        try:
            data = self.path.read_bytes()
        except OSError as exc:
            QMessageBox.warning(self, tr("Open failed"), str(exc))
            self.editor.setPlainText("")
            self.editor.setReadOnly(True)
            self.btn_save.setEnabled(False)
            return
        text = data.decode("utf-8", errors="replace")
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self._dirty = False
        self.editor.setReadOnly(read_only)
        self.btn_save.setEnabled(not read_only)
        self.btn_replace.setEnabled(not read_only)
        self.btn_replace_all.setEnabled(not read_only)

    def _update_title(self) -> None:
        mark = " *" if self._dirty else ""
        mode = " (read-only)" if self.editor.isReadOnly() else ""
        self.setWindowTitle(f"{self.path.name}{mark}{mode} — LabDesk")

    def _on_modified(self, modified: bool) -> None:
        if self._loading:
            return
        self._dirty = bool(modified)
        self._update_title()

    def _update_pos(self) -> None:
        cur = self.editor.textCursor()
        self.pos_label.setText(
            f"Ln {cur.blockNumber() + 1}, Col {cur.positionInBlock() + 1}"
        )

    def _focus_find(self) -> None:
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def find_next(self, backward: bool = False) -> bool:
        needle = self.find_edit.text()
        if not needle:
            return False
        opts = QTextDocument.FindFlag(0)
        if backward:
            opts |= QTextDocument.FindFlag.FindBackward
        found = self.editor.find(needle, opts)
        if not found:
            cursor = self.editor.textCursor()
            if backward:
                cursor.movePosition(QTextCursor.MoveOperation.End)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(needle, opts)
        return bool(found)

    def replace_one(self) -> None:
        if self.editor.isReadOnly():
            return
        needle = self.find_edit.text()
        if not needle:
            return
        cur = self.editor.textCursor()
        if cur.hasSelection() and cur.selectedText() == needle:
            cur.insertText(self.replace_edit.text())
            self.editor.setTextCursor(cur)
        self.find_next(False)

    def replace_all(self) -> None:
        if self.editor.isReadOnly():
            return
        needle = self.find_edit.text()
        if not needle:
            return
        text = self.editor.toPlainText()
        count = text.count(needle)
        if count == 0:
            return
        self.editor.setPlainText(text.replace(needle, self.replace_edit.text()))
        self.banner.setText(f"Replaced {count} occurrence(s).")
        self.banner.setVisible(True)

    def save(self) -> bool:
        if self.editor.isReadOnly():
            return False
        try:
            self.path.write_text(self.editor.toPlainText(), encoding="utf-8")
        except OSError as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")
            return False
        self.editor.document().setModified(False)
        self._dirty = False
        self._update_title()
        self.banner.setText(tr("Saved."))
        self.banner.setVisible(True)
        return True

    def _open_external(self) -> None:
        try:
            if self._dirty:
                reply = QMessageBox.question(
                    self,
                    tr("Unsaved changes"),
                    tr("Save before opening externally?"),
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Save,
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                if reply == QMessageBox.StandardButton.Save and not self.save():
                    return
            open_path(self.path)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._dirty and not self.editor.isReadOnly():
            reply = QMessageBox.question(
                self,
                tr("Unsaved changes"),
                f"Save changes to {self.path.name}?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Save and not self.save():
                event.ignore()
                return
        key = str(self.path)
        if _OPEN_EDITORS.get(key) is self:
            _OPEN_EDITORS.pop(key, None)
        super().closeEvent(event)


def open_code_editor(path: str | Path, *, parent=None) -> EditorWindow | None:
    """Open (or focus) an in-app editor for *path*. Returns None if binary/missing."""
    p = Path(path).resolve()
    key = str(p)
    existing = _OPEN_EDITORS.get(key)
    if existing is not None:
        existing.raise_()
        existing.activateWindow()
        return existing

    info = probe_file_for_edit(p)
    mode = info["mode"]
    if mode == "missing":
        QMessageBox.warning(
            parent,
            tr("Open editor"),
            info.get("message") or tr("File not found."),
        )
        return None
    if mode == "binary":
        reply = QMessageBox.question(
            parent,
            tr("Binary file"),
            f"{p.name} looks binary. Open with the desktop default instead?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                open_path(p)
            except Exception as exc:
                code, msg = format_error(exc)
                QMessageBox.warning(parent, f"Error {code}", f"[{code}] {msg}")
        return None

    read_only = mode == "readonly"
    status = info.get("message") or ""
    if info.get("warn") and status:
        QMessageBox.information(parent, tr("Large file"), status)

    win = EditorWindow(p, parent=parent, read_only=read_only, status_message=status)
    _OPEN_EDITORS[key] = win
    win.show()
    win.raise_()
    win.activateWindow()
    return win
