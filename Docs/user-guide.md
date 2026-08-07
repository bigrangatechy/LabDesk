# LabDesk User Guide

**Status:** Shell (docs stage)  
**Audience:** People using LabDesk day to day  
**Related:** `user-journey.md` (flows), `security-credentials.md` (secrets),
Technical Specification (constraints)

This guide is written so it can later be **embedded in the app** (Help)
without dragging in developer build details. Prefer short how-tos and
screenshots (when available) over architecture.

Filled sections will grow from `Docs/user-journey.md`. Do not duplicate
the full API or SQLite schema here.

---

## 1. What LabDesk is

- Linux desktop client for **self-hosted GitLab** only (not GitLab.com).
- Local git (commit, branch, diff) plus forge features (project list,
  merge requests).
- Distributed as **Flatpak** for releases.

*(Expand from README / product blurb when README is rewritten.)*

---

## 2. Install & update

- Install via Flatpak / Flathub (details TBD).
- Updates: Flatpak remote (`check_for_updates` preference).

---

## 3. First-time setup

- Add instance (URL + API personal access token).
- Why SaaS URLs are rejected.
- TLS / self-signed / imported CA (short, practical).
- Where the token is stored (system keyring — not a file you edit).

→ Journey A in `user-journey.md`.

---

## 4. Projects & cloning

- Browsing projects (membership list).
- Clone with HTTPS (credential helper) or SSH.
- Default clone directory.

→ Journey B.

---

## 5. Daily git work

- Changes, staging, commit.
- Read-only diffs.
- Open files in an **external** editor.
- Branches; clean local merge; conflicts → resolve outside LabDesk.

→ Journey C.

---

## 6. Push, force push & merge requests

- Normal push.
- Force push only with confirmation.
- Creating an MR and opening it in the browser.

→ Journey D.

---

## 7. Working offline

- What still works; what is disabled.
- Stale project list indicators.

→ Journey E.

---

## 8. Troubleshooting

- Auth failures (API PAT vs git credentials vs SSH).
- 2FA and password git auth.
- Certificate errors.
- Cache rebuild (when the app says the cache is corrupt).

---

## 9. Privacy & security (user-facing)

- Short summary of keyring + credential helper.
- Link or pointer: do not paste PATs into chat logs / issues.

---

## Document history

Shell created during documentation-first phase. Body content TBD.
