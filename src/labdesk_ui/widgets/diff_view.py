"""Side-by-side + unified diff viewer (Slice K) — Qt only, no QScintilla."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class AlignedLine:
    """One visual row in a side-by-side pane."""

    text: str
    kind: str  # context | delete | insert | meta | empty


def parse_unified_to_sides(unified: str) -> tuple[list[AlignedLine], list[AlignedLine]]:
    """Align old/new sides from a unified diff (best-effort, hunk-aware)."""
    left: list[AlignedLine] = []
    right: list[AlignedLine] = []
    if not unified:
        return left, right

    pending_dels: list[str] = []

    def flush_dels() -> None:
        nonlocal pending_dels
        for d in pending_dels:
            left.append(AlignedLine(d, "delete"))
            right.append(AlignedLine("", "empty"))
        pending_dels = []

    for raw in unified.splitlines():
        if raw.startswith("diff ") or raw.startswith("index ") or raw.startswith("--- ") or raw.startswith("+++ "):
            flush_dels()
            left.append(AlignedLine(raw, "meta"))
            right.append(AlignedLine(raw, "meta"))
            continue
        if raw.startswith("@@"):
            flush_dels()
            left.append(AlignedLine(raw, "meta"))
            right.append(AlignedLine(raw, "meta"))
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            body = raw[1:]
            if pending_dels:
                left.append(AlignedLine(pending_dels.pop(0), "delete"))
                right.append(AlignedLine(body, "insert"))
            else:
                left.append(AlignedLine("", "empty"))
                right.append(AlignedLine(body, "insert"))
            continue
        if raw.startswith("-") and not raw.startswith("---"):
            pending_dels.append(raw[1:])
            continue
        # context (leading space or bare)
        flush_dels()
        body = raw[1:] if raw.startswith(" ") else raw
        left.append(AlignedLine(body, "context"))
        right.append(AlignedLine(body, "context"))

    flush_dels()
    return left, right


def _palette_colors(widget: QWidget) -> tuple[QColor, QColor, QColor, QColor]:
    dark = widget.palette().color(QPalette.ColorRole.Window).lightness() < 128
    plus = QColor("#6bcf6b" if dark else "#0a7a0a")
    minus = QColor("#f08080" if dark else "#a10a0a")
    hunk = QColor("#7ec8e3" if dark else "#0a4a8a")
    empty = QColor("#555555" if dark else "#bbbbbb")
    return plus, minus, hunk, empty


def colorize_unified(edit: QTextEdit, text: str) -> None:
    edit.clear()
    plus, minus, hunk, _empty = _palette_colors(edit)
    cursor = edit.textCursor()
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
    edit.moveCursor(QTextCursor.MoveOperation.Start)


def colorize_side(edit: QPlainTextEdit, lines: list[AlignedLine]) -> None:
    edit.clear()
    plus, minus, hunk, empty = _palette_colors(edit)
    cursor = edit.textCursor()
    for row in lines:
        fmt = QTextCharFormat()
        if row.kind == "insert":
            fmt.setForeground(plus)
            prefix = "+ "
        elif row.kind == "delete":
            fmt.setForeground(minus)
            prefix = "- "
        elif row.kind == "meta":
            fmt.setForeground(hunk)
            prefix = ""
        elif row.kind == "empty":
            fmt.setForeground(empty)
            prefix = "  "
        else:
            prefix = "  "
        cursor.setCharFormat(fmt)
        cursor.insertText(prefix + row.text + "\n")
    edit.moveCursor(QTextCursor.MoveOperation.Start)


class DiffView(QWidget):
    """Unified / side-by-side toggle for read-only diffs."""

    MODE_UNIFIED = 0
    MODE_SIDE = 1

    def __init__(self, parent=None, *, placeholder: str = "") -> None:
        super().__init__(parent)
        self._text = ""
        self._mode = self.MODE_UNIFIED

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        self.btn_unified = QPushButton("Unified")
        self.btn_unified.setCheckable(True)
        self.btn_unified.setChecked(True)
        self.btn_unified.clicked.connect(lambda: self.set_mode(self.MODE_UNIFIED))
        bar.addWidget(self.btn_unified)
        self.btn_side = QPushButton("Side by side")
        self.btn_side.setCheckable(True)
        self.btn_side.clicked.connect(lambda: self.set_mode(self.MODE_SIDE))
        bar.addWidget(self.btn_side)
        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        bar.addWidget(self.hint, stretch=1)
        layout.addLayout(bar)

        self.stack = QStackedWidget()
        self.unified = QTextEdit()
        self.unified.setReadOnly(True)
        self.unified.setFont(QFont("monospace"))
        if placeholder:
            self.unified.setPlaceholderText(placeholder)
        self.stack.addWidget(self.unified)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        self.left = QPlainTextEdit()
        self.right = QPlainTextEdit()
        for pane, title in ((self.left, "Old (−)"), (self.right, "New (+)")):
            pane.setReadOnly(True)
            pane.setFont(QFont("monospace"))
            pane.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            pane.setPlaceholderText(title)
        split.addWidget(self.left)
        split.addWidget(self.right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        side_layout.addWidget(split)
        self.stack.addWidget(side)
        layout.addWidget(self.stack, stretch=1)

        self.left.verticalScrollBar().valueChanged.connect(self._sync_from_left)
        self.right.verticalScrollBar().valueChanged.connect(self._sync_from_right)
        self._syncing = False

    def set_mode(self, mode: int) -> None:
        self._mode = mode
        self.btn_unified.setChecked(mode == self.MODE_UNIFIED)
        self.btn_side.setChecked(mode == self.MODE_SIDE)
        self.stack.setCurrentIndex(mode)
        self._render()

    def clear(self) -> None:
        self._text = ""
        self.unified.clear()
        self.left.clear()
        self.right.clear()

    def set_diff(self, text: str) -> None:
        self._text = text or ""
        self._render()

    def set_plain_text(self, text: str) -> None:
        """Show non-diff text (errors) in both modes."""
        self._text = text or ""
        self.unified.setPlainText(self._text)
        self.left.setPlainText(self._text)
        self.right.clear()
        self.hint.setText("")

    # Compatibility with older QTextEdit call sites
    def setPlainText(self, text: str) -> None:  # noqa: N802
        self.set_plain_text(text)

    def moveCursor(self, *_args, **_kwargs) -> None:  # noqa: N802
        self.unified.moveCursor(QTextCursor.MoveOperation.Start)

    def _render(self) -> None:
        text = self._text
        if not text:
            self.unified.clear()
            self.left.clear()
            self.right.clear()
            return
        colorize_unified(self.unified, text)
        left, right = parse_unified_to_sides(text)
        colorize_side(self.left, left)
        colorize_side(self.right, right)
        if self._mode == self.MODE_SIDE:
            self.hint.setText(f"{len(left)} aligned row(s)")
        else:
            self.hint.setText("")

    def _sync_from_left(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.right.verticalScrollBar().setValue(value)
        self._syncing = False

    def _sync_from_right(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.left.verticalScrollBar().setValue(value)
        self._syncing = False
