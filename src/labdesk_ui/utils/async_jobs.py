"""Run blocking work off the Qt UI thread; marshal results via queued signals."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot
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


class _ResultBridge(QObject):
    """Lives on the owner (UI) thread so slots never touch widgets off-thread.

    Connecting bare Python callables with QueuedConnection is unreliable in
    PySide — Qt may invoke them on the worker thread, which segfaults in Qt Gui
    (QLabel/QTextDocument). Always route through QObject slots on the UI thread.
    """

    def __init__(
        self,
        owner: QObject,
        on_success: Callable[[Any], None] | None,
        on_error: Callable[[str, str, BaseException], None] | None,
        on_finished: Callable[[], None] | None,
        busy_widgets: list[QWidget],
        handles: list,
        handle: dict,
    ) -> None:
        super().__init__(owner)
        self._on_success = on_success
        self._on_error = on_error
        self._on_finished = on_finished
        self._busy_widgets = busy_widgets
        self._handles = handles
        self._handle = handle
        self._done = False

    def _owner_ok(self) -> bool:
        try:
            from shiboken6 import isValid

            if not isValid(self):
                return False
            parent = self.parent()
            if parent is not None and not isValid(parent):
                return False
            return True
        except Exception:
            return False

    @Slot(object)
    def on_ok(self, result: object) -> None:
        if not self._owner_ok():
            self._cleanup(touch_widgets=False)
            return
        try:
            if self._on_success is not None:
                self._on_success(result)
        finally:
            self._cleanup(touch_widgets=True)

    @Slot(str, str, object)
    def on_err(self, code: str, msg: str, exc: object) -> None:
        if not self._owner_ok():
            self._cleanup(touch_widgets=False)
            return
        try:
            if self._on_error is not None:
                err = exc if isinstance(exc, BaseException) else Exception(str(exc))
                self._on_error(code, msg, err)
        finally:
            self._cleanup(touch_widgets=True)

    def _cleanup(self, *, touch_widgets: bool) -> None:
        if self._done:
            return
        self._done = True
        if touch_widgets and self._owner_ok():
            for w in self._busy_widgets:
                try:
                    from shiboken6 import isValid as _iv

                    if _iv(w):
                        w.setEnabled(True)
                except Exception:
                    pass
            if self._on_finished is not None:
                try:
                    self._on_finished()
                except RuntimeError:
                    pass
        try:
            self._handles.remove(self._handle)
        except ValueError:
            pass
        try:
            from shiboken6 import isValid

            if isValid(self):
                self.deleteLater()
        except Exception:
            pass


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
    via a ``QObject`` bridge (queued auto-connection). Never touch widgets
    from ``fn``.

    The ``QThread`` is **not** parented to ``owner`` — parenting aborts Qt if
    the owner is destroyed while the thread is still running (closing a repo
    window mid-fetch).
    """
    widgets = list(busy_widgets or [])
    for w in widgets:
        w.setEnabled(False)
    if status is not None:
        status(working_message)

    # Unparented: see docstring. Lifetime held via ``handles`` on owner.
    thread = QThread()
    worker = _Worker(fn)
    worker.moveToThread(thread)

    handles = getattr(owner, "_labdesk_async_handles", None)
    if handles is None:
        handles = []
        setattr(owner, "_labdesk_async_handles", handles)
    handle: dict = {"thread": thread, "worker": worker}
    handles.append(handle)

    bridge = _ResultBridge(
        owner,
        on_success,
        on_error,
        on_finished,
        widgets,
        handles,
        handle,
    )
    handle["bridge"] = bridge

    def _quit_thread(*_args) -> None:
        try:
            from shiboken6 import isValid

            if isValid(thread) and thread.isRunning():
                thread.quit()
        except Exception:
            pass

    # If the owner goes away mid-flight, stop the thread (do not wait here).
    owner.destroyed.connect(_quit_thread)

    thread.started.connect(worker.run)
    # Worker lives on ``thread``; bridge on ``owner`` → Auto becomes Queued.
    worker.finished.connect(bridge.on_ok)
    worker.failed.connect(bridge.on_err)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
