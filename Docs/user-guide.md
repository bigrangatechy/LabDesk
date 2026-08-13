# LabDesk User Guide

**Status:** Living  
**Audience:** People using LabDesk day to day

This guide is also available in the app under **Help → User Guide…**.

---

## 1. What LabDesk is

- Linux desktop client for **self-hosted GitLab** only (not GitLab.com).
- Local git (commit, branch, diff) plus forge features (project list,
  merge requests, pipeline status).
- Distributed as a **Flatpak**.
- **Help → About** shows the version (`YYYY.MM.DD` on Flatpak builds;
  `dev` when run unpackaged) and whether you are on Flatpak.

---

## 2. Install & update

### 2.1 Install

Add the LabDesk Flatpak remote once, then install:

```bash
flatpak remote-add --if-not-exists bigrangatech-flatpaks \
  https://git.bigrangatech.com/Ranga/flatpaks/-/raw/main/labdesk/labdesk.flatpakrepo
flatpak install bigrangatech-flatpaks com.bigrangatech.LabDesk
flatpak run com.bigrangatech.LabDesk
```

After that, LabDesk appears in your desktop app store (for example
**Discover** on KDE) like other Flatpaks.

If an older **unsigned** test remote is still listed, remove it once
(`flatpak remote-delete --user bigrangatech-flatpaks`) and run the
commands above again.

### 2.2 Update

Updates are normal Flatpak updates. Your app store (Discover, GNOME
Software, …) will offer them when a new build is available. You can also
update from a terminal:

```bash
flatpak update com.bigrangatech.LabDesk
```

Optional: Settings → **Check for updates** does the same check inside
LabDesk.

### 2.3 Where LabDesk stores data

Under Flatpak, LabDesk keeps its files under:

`~/.var/app/com.bigrangatech.LabDesk/`

---

## 3. First-time setup

1. On first launch with no hosts, LabDesk offers **Add / connect**.
2. Choose **New host** (base URL + TLS) or **Add account** to an
   existing host, then enter an account label and API **personal access
   token**.
   - Prefer **`https://…`**.
   - On a trusted LAN you may use **`http://192.168.x.x:port`** (or
     other private / loopback addresses). Public host names still need
     HTTPS.
3. SaaS hosts (`gitlab.com`, `github.com`, …) are rejected.
4. Choose a TLS mode: **Strict** (default), **Allow self-signed**, or
   Imported CA.
5. The PAT is stored in the **system keyring**, not in plain config
   files.

You can connect **several GitLab machines** and **several accounts** on
the same machine. Use the host and account selectors in the main window
to switch; the Projects list follows the active account.

---

## 4. Settings & preferences

- **Settings → Preferences:** clone folder, theme, window layout
  (`classic` / `sidebar`), and whether to check for Flatpak updates.
- **View** menu: switch Projects / Settings and layout.
- Do **not** put PATs or passwords in config files.
- If startup hangs for a long time, LabDesk may restore the last good
  settings and show an error with a code like **`LD-CFG-010`**.

---

## 5. Projects & cloning

- **Filter projects…** narrows the list by name or namespace path
  (local cache only).
- **Refresh projects** loads your project list from GitLab for the
  **active account** (and keeps a local copy for offline browsing).
  It also fills the **pipeline** status icon from each project’s
  default-branch latest pipeline (may take a moment on large lists).
- **Clone** (HTTPS or SSH) into the default clone folder.
- **Open local** / **Add existing…** attach an already-cloned folder.
- Double-click a project or use Open local to open a **repo window**.

---

## 6. Daily git work

In the repo window:

- **Changes:** stage / unstage / commit; read-only diffs.
- **Open in editor:** opens the selected file with the desktop default.
- **Branches:** list, switch, create, merge into current (clean merges
  only; if there are conflicts, resolve them outside LabDesk).
- **Compare:** pick two branches (local or `origin/…`), see ahead/behind,
  recent commits, and a read-only tip diff. When online, LabDesk can
  check whether the other branch exists on GitLab.
- **Merge requests:** opened MRs for this project (refresh while online;
  last list kept for offline viewing). **Open in GitLab** for the
  selected row.
- **Fetch / Pull / Push** and ahead/behind vs upstream in the header.
- **Force push…** only after an explicit confirmation.
- After a successful (non-force) push, LabDesk may offer to **create a
  merge request**.

---

## 7. Pipelines

- **Pipelines** tab: latest pipeline for the **current branch**.
- Status chip in the header; **Open in GitLab** opens the pipeline URL.
- Job list shows stage, name, and status. Rows marked **▶** are waiting
  for manual start — select one and **Play manual job…** (confirm first).
- After an online refresh, the last status and jobs are kept so you can
  still see them offline. **Play is disabled offline.**

---

## 8. Working offline

- A banner shows **Working offline** when GitLab cannot be reached.
- Still works: local Changes / History / Branches / Compare / commit /
  open editor; last project list; last pipeline status and opened MRs
  (if you refreshed earlier).
- Disabled: refreshing projects from the server, clone, pull/push/force
  push, create MR, play CI jobs, live remote branch check.

---

## 9. Help in the app

- **Help → User Guide…** — this document.
- **Help → About LabDesk** — version.

---

## 10. Troubleshooting

| Symptom | What to try |
|---------|-------------|
| Auth failed (`LD-AUTH-001`) | Re-enter PAT; check scopes / expiry |
| Keyring error (`LD-AUTH-002`) | Unlock your password manager / Secret Service |
| Git auth failed | SSH agent, credential helper, or HTTPS with a PAT |
| 2FA blocks password git | Use SSH or HTTPS with a PAT |
| Certificate not trusted | Change TLS mode in Settings, or fix the host CA |
| Projects list looks stale | Refresh projects while online |
| No update in Discover | Run `flatpak update`, or wait for the next published build |

---

## 11. Privacy & security

- API PAT → OS keyring only.
- Git HTTPS passwords → Git credential helper.
- Never paste PATs into chat, issues, or screenshots.
- LAN `http://` GitLab: the PAT travels in cleartext — trusted networks
  only.

---

## Document history

Living end-user guide. Contributor / build notes live in `dev-guide.md`.
