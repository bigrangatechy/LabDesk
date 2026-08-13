"""Regression: background job callbacks must run on the UI thread."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QThread
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
    assert label.isEnabled()


def test_async_owner_destroyed_mid_job_does_not_abort(qapp, process_events):
    """QThread must not be a child of the owner (Qt aborts if destroyed early)."""
    host = QWidget()
    seen = {"n": 0}

    def work():
        time.sleep(0.2)
        return 1

    def on_ok(_r) -> None:
        seen["n"] += 1

    run_in_background(host, work, on_success=on_ok)
    host.close()
    host.deleteLater()
    deadline = time.time() + 1.0
    while time.time() < deadline and isValid(host):
        process_events(10)
        time.sleep(0.01)
    time.sleep(0.3)
    process_events(40)
    # Success = process still alive (no Qt abort). Callback may be skipped.
    assert True

