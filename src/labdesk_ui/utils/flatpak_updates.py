"""Flatpak update checks for LabDesk (`LD-SYS-021`)."""

from __future__ import annotations

import os
import shutil
import subprocess


APP_ID = "com.bigrangatech.LabDesk"


def is_flatpak() -> bool:
    return os.path.exists("/.flatpak-info") or bool(os.environ.get("FLATPAK_ID"))


def _flatpak_argv(args: list[str]) -> list[str]:
    """Prefer host `flatpak` via flatpak-spawn when running inside the sandbox."""
    if is_flatpak():
        spawn = shutil.which("flatpak-spawn")
        if spawn:
            return [spawn, "--host", "flatpak", *args]
    flatpak = shutil.which("flatpak")
    if not flatpak:
        raise RuntimeError(
            "[LD-SYS-021] Could not check for Flatpak updates.: flatpak CLI not found"
        )
    return [flatpak, *args]


def check_for_labdesk_updates() -> dict:
    """Return {available: bool, detail: str, updates: list[str]}.

    Raises RuntimeError with [LD-SYS-021] on failure.

    Unpackaged / ``./scripts/run-labdesk.sh`` runs are not Flatpak installs:
    skip the host ``flatpak`` CLI there (it can block for minutes and is
    irrelevant to the tree you are smoke-testing).
    """
    if not is_flatpak():
        return {
            "available": False,
            "detail": "Not running as Flatpak — update check skipped.",
            "updates": [],
            "skipped": True,
        }
    try:
        # Refresh appstream metadata (best-effort).
        subprocess.run(
            _flatpak_argv(["update", "--appstream", "-y"]),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        proc = subprocess.run(
            _flatpak_argv(["remote-ls", "--updates", "--columns=application"]),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
            raise RuntimeError(
                f"[LD-SYS-021] Could not check for Flatpak updates.: {err}"
            )
        apps = [
            line.strip()
            for line in (proc.stdout or "").splitlines()
            if line.strip() and not line.startswith("Application")
        ]
        matching = [a for a in apps if APP_ID in a]
        if matching:
            return {
                "available": True,
                "detail": f"Update available for {APP_ID}. Run: flatpak update {APP_ID}",
                "updates": matching,
            }
        return {
            "available": False,
            "detail": f"No Flatpak updates listed for {APP_ID}.",
            "updates": [],
        }
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "[LD-SYS-021] Could not check for Flatpak updates.: timed out"
        ) from exc
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"[LD-SYS-021] Could not check for Flatpak updates.: {exc}"
        ) from exc
