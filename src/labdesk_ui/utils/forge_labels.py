"""Forge-aware UI labels from ``labdesk_core.active_forge_info``."""

from __future__ import annotations


def forge_info() -> dict:
    """Return display strings for the active host's forge (safe defaults)."""
    info = {
        "forge": "gitlab",
        "display_name": "GitLab",
        "pull_request_label": "Merge request",
        "pull_request_label_plural": "Merge requests",
        "ci_tab_label": "Pipelines",
        "supports_play_job": True,
        "supports_mr_detail": True,
        "supports_mr_update": True,
        "supports_mr_retarget": True,
        "supports_mr_merge": True,
        "supports_mr_notes": True,
        "supports_draft_mr": True,
        "supports_runners": True,
        "supports_runner_pause": True,
        "supports_runner_delete": True,
        "supports_admin_users": True,
        "runners_label": "Runners",
        "open_in_label": "Open in GitLab",
    }
    try:
        import labdesk_core

        if hasattr(labdesk_core, "active_forge_info"):
            info.update(dict(labdesk_core.active_forge_info() or {}))
    except Exception:
        pass
    return info


def pr_label(info: dict | None = None) -> str:
    return str((info or forge_info()).get("pull_request_label") or "Merge request")


def pr_label_plural(info: dict | None = None) -> str:
    return str(
        (info or forge_info()).get("pull_request_label_plural") or "Merge requests"
    )


def forge_name(info: dict | None = None) -> str:
    return str((info or forge_info()).get("display_name") or "forge")


def open_in_label(info: dict | None = None) -> str:
    data = info or forge_info()
    return str(
        data.get("open_in_label") or f"Open in {data.get('display_name') or 'forge'}"
    )


def ci_tab_label(info: dict | None = None) -> str:
    return str((info or forge_info()).get("ci_tab_label") or "Pipelines")


_FORGE_DISPLAY = {
    "gitlab": "GitLab",
    "gitea": "Gitea",
    "forgejo": "Forgejo",
    "onedev": "OneDev",
}


def instance_label(inst: dict | None) -> str:
    """Combo/list label for a host: ``Name — url`` (forge-aware fallback)."""
    inst = inst or {}
    forge = str(inst.get("forge") or "gitlab").lower()
    fallback = _FORGE_DISPLAY.get(forge) or forge.title() or "Host"
    name = inst.get("name") or fallback
    url = inst.get("base_url") or ""
    return f"{name} — {url}" if url else str(name)
