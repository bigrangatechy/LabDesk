"""Startup hang watchdog — 45s timeout, known-good revert, relaunch."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

STARTUP_TIMEOUT_SEC = 45
_MARKER_NAME = "startup-recovery.json"
_ready = threading.Event()
_step = "starting"
_watchdog_started = False


def _config_dir() -> Path:
    try:
        import labdesk_core

        paths = labdesk_core.get_paths()
        return Path(paths.get("config_dir") or Path.home() / ".config" / "labdesk")
    except Exception:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "labdesk"
        return Path.home() / ".config" / "labdesk"


def recovery_marker_path() -> Path:
    return _config_dir() / _MARKER_NAME


def consume_recovery_marker() -> dict | None:
    path = recovery_marker_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {"code": "LD-CFG-010", "detail": "Startup recovery marker was unreadable."}
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    if not isinstance(data, dict):
        return {"code": "LD-CFG-010", "detail": str(data)}
    return data


def set_step(step: str) -> None:
    global _step
    _step = step


def mark_ready() -> None:
    _ready.set()


def _write_recovery_marker(*, code: str, detail: str) -> None:
    path = recovery_marker_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"code": code, "detail": detail, "step": _step}),
            encoding="utf-8",
        )
    except OSError:
        pass


def _relaunch() -> None:
    try:
        from PySide6.QtCore import QProcess

        QProcess.startDetached(sys.executable, sys.argv)
    except Exception:
        try:
            os.execv(sys.executable, [sys.executable, *sys.argv])
        except OSError:
            pass


def _on_timeout() -> None:
    detail = f"No ready signal within {STARTUP_TIMEOUT_SEC}s (last step: {_step})."
    code = "LD-CFG-010"
    try:
        import labdesk_core

        labdesk_core.revert_config_to_known_good()
    except Exception as exc:
        text = str(exc)
        if "LD-CFG-011" in text:
            code = "LD-CFG-011"
            detail = f"{detail} No known-good snapshot was available ({exc})."
        else:
            detail = f"{detail} Revert failed: {exc}"
    _write_recovery_marker(code=code, detail=detail)
    _relaunch()
    os._exit(1)


def _watchdog_main() -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if _ready.wait(timeout=0.5):
            return
    if _ready.is_set():
        return
    _on_timeout()


def arm_watchdog() -> None:
    """Start the 45s startup watchdog (once per process)."""
    global _watchdog_started
    if _watchdog_started:
        return
    _watchdog_started = True
    _ready.clear()
    set_step("arm_watchdog")
    t = threading.Thread(target=_watchdog_main, name="labdesk-startup-watchdog", daemon=True)
    t.start()
