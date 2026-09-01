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
        except Exception as exc:
            self._report_callback_failure(exc)
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
        except Exception as callback_exc:
            self._report_callback_failure(callback_exc)
        finally:
            self._cleanup(touch_widgets=True)

    def _report_callback_failure(self, exc: BaseException) -> None:
        try:
            from labdesk_ui.utils.crash_report import report_exception

            report_exception(type(exc), exc, exc.__traceback__, kind="async-callback")
        except Exception:
            code, msg = format_error(exc)
            print(f"[{code}] {msg}\n{exc}", file=__import__("sys").stderr)

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


def drain_async_jobs(owner: QObject, *, timeout_ms: int = 2500) -> None:
    """Ask in-flight worker threads to quit and wait briefly (safe shutdown)."""
    handles = list(getattr(owner, "_labdesk_async_handles", None) or [])
    if not handles:
        return
    from shiboken6 import isValid

    for handle in handles:
        thread = handle.get("thread")
        try:
            if thread is not None and isValid(thread) and thread.isRunning():
                thread.quit()
        except Exception:
            pass

    # Pump the event loop a little so queued finished/cleanup can run.
    try:
        from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

        app = QCoreApplication.instance()
        if app is not None:
            loop = QEventLoop()
            QTimer.singleShot(min(200, max(50, timeout_ms // 10)), loop.quit)
            loop.exec()
    except Exception:
        pass

    remaining = max(0, int(timeout_ms))
    for handle in handles:
        thread = handle.get("thread")
        try:
            if thread is None or not isValid(thread) or not thread.isRunning():
                continue
            waited = thread.wait(remaining if remaining > 0 else 1)
            if not waited and remaining > 0:
                # Still running (often blocked in libgit2 I/O) — leave it;
                # further wait won't help and can hang quit.
                remaining = 0
            elif waited and remaining > 0:
                remaining = max(0, remaining - 50)
        except Exception:
            pass
