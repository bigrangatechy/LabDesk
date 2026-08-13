"""Regression: background job callbacks must run on the UI thread."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QThread, Qt
from PySide6.QtWidgets import QLabel, QWidget
from shiboken6 import isValid

from labdesk_ui.utils.async_jobs import run_in_background


def _wait_until(pred, *, timeout: float = 3.0, process_events) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        process_events(5)
        if pred():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met before timeout")


def test_async_callback_runs_on_owner_thread(qapp, process_events):
    owner = QWidget()
    owner_thread = QThread.currentThread()
    seen: dict = {}

    def work():
        time.sleep(0.05)
        seen["worker_thread"] = QThread.currentThread()
        return {"ok": True}

    def on_ok(result) -> None:
        seen["callback_thread"] = QThread.currentThread()
        seen["result"] = result

    def on_err(code: str, msg: str, exc: BaseException) -> None:
        seen["error"] = (code, msg)

    run_in_background(owner, work, on_success=on_ok, on_error=on_err)
    _wait_until(lambda: "callback_thread" in seen or "error" in seen, process_events=process_events)

    assert "error" not in seen, seen.get("error")
    assert seen["result"] == {"ok": True}
    # These two fail if someone wires finished → bare callable (worker thread).
    assert seen["callback_thread"] is owner_thread
    assert seen["worker_thread"] is not owner_thread


def test_async_error_path_on_owner_thread(qapp, process_events):
    owner = QObject()
    owner_thread = QThread.currentThread()
    seen: dict = {}

    def work():
        raise RuntimeError("[LD-SYS-001] boom")

    def on_ok(_result) -> None:
        seen["ok"] = True

    def on_err(code: str, msg: str, exc: BaseException) -> None:
        seen["callback_thread"] = QThread.currentThread()
        seen["code"] = code

    run_in_background(owner, work, on_success=on_ok, on_error=on_err)
    _wait_until(lambda: "callback_thread" in seen, process_events=process_events)

    assert "ok" not in seen
    assert seen["callback_thread"] is owner_thread
    assert seen["code"]


def test_async_can_update_qlabel_safely(qapp, process_events):
    """The old bug updated QLabel from the worker thread → SIGSEGV in Qt Gui."""
    host = QWidget()
    label = QLabel("idle", host)
    host.show()
    process_events()

    def work():
        time.sleep(0.05)
        return "done"

    def on_ok(result) -> None:
        label.setText(str(result))

    run_in_background(
        host,
        work,
        on_success=on_ok,
        busy_widgets=[label],
        status=label.setText,
        working_message="Working…",
    )
    _wait_until(lambda: label.text() == "done", process_events=process_events)
    assert label.text() == "done"
    assert label.isEnabled() is True


def test_async_qthread_is_not_child_of_owner(qapp, process_events):
    """Parenting QThread to the owner aborts Qt if the window closes mid-job."""
    host = QWidget()
    gate = {"go": False}
    done = {"yes": False}

    def work():
        deadline = time.time() + 2.0
        while not gate["go"] and time.time() < deadline:
            time.sleep(0.01)
        return 1

    def on_ok(_r) -> None:
        done["yes"] = True

    run_in_background(host, work, on_success=on_ok)
    _wait_until(
        lambda: bool(getattr(host, "_labdesk_async_handles", None)),
        process_events=process_events,
    )
    handles = host._labdesk_async_handles
    assert handles, "expected an in-flight async handle"
    thread = handles[0]["thread"]
    assert isinstance(thread, QThread)
    assert isValid(thread)
    assert thread.isRunning()
    # Regression lock: must stay None (parented thread → abort on owner destroy).
    assert thread.parent() is None

    gate["go"] = True
    _wait_until(lambda: done["yes"], process_events=process_events, timeout=3.0)


def test_async_owner_destroyed_mid_job_does_not_abort(qapp, process_events):
    """Destroying the owner while work runs must not abort the interpreter."""
    host = QWidget()
    host.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    host.show()
    process_events()
    seen = {"n": 0}
    started = {"yes": False}

    def work():
        started["yes"] = True
        time.sleep(0.25)
        return 1

    def on_ok(_r) -> None:
        seen["n"] += 1

    run_in_background(host, work, on_success=on_ok)
    _wait_until(lambda: started["yes"], process_events=process_events, timeout=2.0)

    handles = list(getattr(host, "_labdesk_async_handles", []) or [])
    assert handles, "job should still be in flight"
    thread = handles[0]["thread"]
    assert isValid(thread)
    assert thread.parent() is None

    host.close()
    deadline = time.time() + 2.0
    while time.time() < deadline and isValid(host):
        process_events(10)
        time.sleep(0.01)
    assert not isValid(host)

    time.sleep(0.35)
    process_events(40)
    assert seen["n"] == 0
