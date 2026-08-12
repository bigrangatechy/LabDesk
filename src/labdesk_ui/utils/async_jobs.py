"""Run blocking work off the Qt UI thread; marshal results via queued signals."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import QWidget

from labdesk_ui.utils.helpers import format_error


class _Worker(QObject):
    finished = Signal(object)
    failed = Signal(str, str, object)  # code, message, exc

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self._fn())
        except Exception as exc:
            code, msg = format_error(exc)
            self.failed.emit(code, msg, exc)


def run_in_background(
    owner: QObject,
    fn: Callable[[], Any],
    *,
    on_success: Callable[[Any], None] | None = None,
    on_error: Callable[[str, str, BaseException], None] | None = None,
    on_finished: Callable[[], None] | None = None,
    busy_widgets: list[QWidget] | None = None,
    status: Callable[[str], None] | None = None,
    working_message: str = "Working…",
) -> None:
    """
    Start ``fn`` on a worker thread. Callbacks run on the owner's thread
    (queued connections). Never touch widgets from ``fn``.
    """
    widgets = list(busy_widgets or [])
    for w in widgets:
        w.setEnabled(False)
    if status is not None:
        status(working_message)

    thread = QThread(owner)
    worker = _Worker(fn)
    worker.moveToThread(thread)

    # Keep refs so GC does not collect mid-flight.
    handles = getattr(owner, "_labdesk_async_handles", None)
    if handles is None:
        handles = []
        setattr(owner, "_labdesk_async_handles", handles)
    handle = {"thread": thread, "worker": worker}
    handles.append(handle)

    def _cleanup() -> None:
        for w in widgets:
            w.setEnabled(True)
        if on_finished is not None:
            on_finished()
        try:
            handles.remove(handle)
        except ValueError:
            pass

    def _ok(result: object) -> None:
        try:
            if on_success is not None:
                on_success(result)
        finally:
            _cleanup()

    def _err(code: str, msg: str, exc: object) -> None:
        try:
            if on_error is not None:
                on_error(code, msg, exc if isinstance(exc, BaseException) else Exception(str(exc)))
        finally:
            _cleanup()

    thread.started.connect(worker.run)
    worker.finished.connect(_ok, Qt.ConnectionType.QueuedConnection)
    worker.failed.connect(_err, Qt.ConnectionType.QueuedConnection)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
