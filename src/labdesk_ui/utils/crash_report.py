"""Unexpected-error reporting — log + dialog with traceback (LD-SYS-001)."""

from __future__ import annotations

import faulthandler
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextEdit,
    QVBoxLayout,
)

from labdesk_ui.i18n import tr

_INSTALLED = False
_LOG_FH = None  # keep faulthandler file handle alive


def logs_dir() -> Path:
    try:
        import labdesk_core

        paths = labdesk_core.get_paths() or {}
        data = paths.get("data_dir")
        if data:
            d = Path(data) / "logs"
            d.mkdir(parents=True, exist_ok=True)
            return d
    except Exception:
        pass
    d = Path.home() / ".local" / "share" / "labdesk" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def latest_crash_log_path() -> Path:
    return logs_dir() / "last-crash.log"


def write_crash_log(kind: str, text: str) -> Path:
    path = latest_crash_log_path()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = f"=== LabDesk {kind} {stamp} ===\n{text.rstrip()}\n"
    try:
        path.write_text(body, encoding="utf-8")
    except OSError:
        pass
    try:
        dated = logs_dir() / f"crash-{stamp.replace(':', '')}.log"
        dated.write_text(body, encoding="utf-8")
    except OSError:
        pass
    return path


def format_exception_report(
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb,
) -> str:
    if exc_type is None or exc is None:
        return "Unknown failure (no exception info)."
    return "".join(traceback.format_exception(exc_type, exc, tb))


def show_crash_dialog(report: str, *, log_path: Path | None = None) -> None:
    """Best-effort modal with Details. Safe if QApplication is not ready."""
    try:
        if QApplication.instance() is None:
            return

        dlg = QDialog()
        dlg.setWindowTitle(tr("LabDesk — unexpected error"))
        dlg.resize(640, 420)
        layout = QVBoxLayout(dlg)
        summary = QLabel(
            tr(
                "Something went wrong (LD-SYS-001).\n\n"
                "LabDesk hit an unexpected Python error. Details are below "
                "and were written to a log file — copy them when reporting a bug."
            )
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        if log_path is not None:
            path_lbl = QLabel(tr("Log: {path}").format(path=str(log_path)))
            path_lbl.setWordWrap(True)
            path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(path_lbl)
        details = QTextEdit()
        details.setReadOnly(True)
        details.setPlainText(report)
        layout.addWidget(details, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(dlg.accept)
        layout.addWidget(buttons)
        dlg.exec()
    except Exception:
        print(report, file=sys.stderr)


def report_exception(
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb,
    *,
    kind: str = "exception",
    show_dialog: bool = True,
) -> Path:
    report = format_exception_report(exc_type, exc, tb)
    path = write_crash_log(kind, report)
    print(report, file=sys.stderr)
    if show_dialog:
        show_crash_dialog(report, log_path=path)
    return path


def _excepthook(exc_type, exc, tb) -> None:
    report_exception(exc_type, exc, tb, kind="uncaught")


def _threading_excepthook(args) -> None:
    report_exception(
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
        kind="thread-exception",
    )


def install_crash_reporting() -> None:
    """Install process-wide hooks once (call after QApplication exists for dialogs)."""
    global _INSTALLED, _LOG_FH
    if _INSTALLED:
        return
    _INSTALLED = True

    sys.excepthook = _excepthook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _threading_excepthook  # type: ignore[assignment]

    try:
        fault_path = logs_dir() / "faulthandler.log"
        _LOG_FH = open(fault_path, "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(file=_LOG_FH, all_threads=True)
    except Exception:
        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass
