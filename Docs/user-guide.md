# LabDesk User Guide

**Status:** Living  
**Audience:** People using LabDesk day to day

This guide is also available in the app under **Help → User Guide…**.

---

## 1. What LabDesk is

- Linux desktop client for **self-hosted** GitLab, Gitea, Forgejo, and
  OneDev (not public SaaS forges).
- Local git (commit, branch, diff) plus forge features (project list,
  merge/pull requests, CI / pipeline status).
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
2. Choose **New host** (forge type + base URL + TLS) or **Add account**
   to an existing host, then enter an account label and API **personal
   access token** (or OneDev access token).
   - Pick the correct **Forge** (GitLab / Gitea / Forgejo / OneDev).
   - Prefer **`https://…`**.
   - On a trusted LAN you may use **`http://192.168.x.x:port`** (or
     other private / loopback addresses). Public host names still need
     HTTPS.
3. SaaS hosts (`gitlab.com`, `github.com`, `gitea.com`, `codeberg.org`,
   `code.onedev.io`, …) are rejected.
4. Choose a TLS mode: **Strict** (default), **Allow self-signed**, or
   **Imported CA**. For Imported CA, use **Import CA…** to add a
   PEM/CRT into LabDesk’s `trusted_certs/` folder (used for API and
   git HTTPS). Connect fails with **`LD-NET-010`** if none are
   imported.
5. The PAT is stored in the **system keyring**, not in plain config
   files.

You can connect **several forge hosts** and **several accounts** on the
same machine. Use the host and account selectors in the main window to
switch; the Projects list follows the active account.

**Same server, domain vs LAN:** add both URLs as separate hosts (each
with its own account/PAT). When you switch **Host**, LabDesk retargets
`origin` on local clones that still point at the previous host **and**
whose project path exists under the newly selected account. It also
rewrites cached project clone/web URLs onto the selected host’s Base
URL, so **clone, fetch/pull/push, Open in …, and MR/pipeline links**
all use that host — not only push. Unrelated hosts, SSH remotes, and
accounts without that project are left alone. Some forges’ own clone
URLs stay on the public hostname even when you talk to the LAN address —
LabDesk prefers the selected host’s Base URL instead.

---

## 4. Settings & preferences

- **Settings → Preferences:** clone folder, theme, window layout
  (`classic` / `sidebar`), **Projects list layout** (`table` / `cards`),
  clone/push progress fill colour + alpha, and whether to check for
  Flatpak updates.
- **View** menu: switch Projects / Settings and layout.
- Do **not** put PATs or passwords in config files.
- If startup hangs for a long time, LabDesk may restore the last good
  settings and show an error with a code like **`LD-CFG-010`**.

---

## 5. Projects & cloning

- **Filter projects…** narrows the list by name or namespace path
  (local cache only).
- **Refresh projects** loads your project list from the forge for the
  **active account** (and keeps a local copy for offline browsing).
  It also fills the **pipeline / CI** status icon from each project’s
  default-branch latest run (may take a moment on large lists).
- Choose **Table** or **Cards** in Settings for how projects are shown.
- **Clone** (HTTPS or SSH) into the default clone folder. While cloning
  or pushing, the matching project row/card fills left→right with the
  configured translucent colour.
- **Open local** / **Add existing…** attach an already-cloned folder.
- Double-click a project or use Open local to open a **repo window**.

---

## 6. Daily git work

In the repo window:

- **Changes:** stage / unstage / commit; read-only diffs. The list shows
  **dirty paths only**. Use **Browse files…** for a filtered, scrollable
  tracked-file listing (capped / load-more on large repos). Untracked
  directories (for example `build/` or `node_modules/`) appear as **one**
  entry — **Stage** / **Stage all** still add all files under that
  directory (like `git add <dir>/`). Very large file or diff previews
  are truncated — use **Open in editor** for the full content.
- **Open in editor:** opens the selected file with the desktop default.
- **Branches:** list, switch, create, merge into current. On conflict,
  use the conflict resolve panel (or open files externally).
- **Sync:** header shows ↑ahead / ↓behind / diverged. With fetch-on-focus
  enabled (default), LabDesk fetches when you open or refresh a repo
  window so remote changes are visible. Pull fast-forwards when possible;
  if histories diverged, choose merge or rebase (conflicts → resolve UI).
  Stash is available when the tree is dirty before pull.
- **Compare:** pick two branches (local or `origin/…`), see ahead/behind,
  recent commits, and a read-only tip diff (truncated if huge). When
  online, LabDesk can check whether the other branch exists on the forge.
- **Merge / pull requests:** opened items for this project (tab label
  follows the forge; refresh while online; last list kept for offline
  viewing). **Open in …** opens the selected row in the browser.
- **Fetch / Pull / Push** and ahead/behind vs upstream in the header.
- **Force push…** only after an explicit confirmation.
- After a successful (non-force) push, LabDesk may offer to **create a
  merge or pull request** (wording matches the active forge).

---

## 7. Pipelines / CI

- **Pipelines** (or forge-equivalent) tab: latest run for the **current
  branch**.
- Status chip in the header; **Open in …** opens the run URL in the
  browser.
- Job list shows stage, name, and status. On GitLab, rows marked **▶**
  are waiting for manual start — select one and **Play manual job…**
  (confirm first). Other forges hide Play when unsupported.
- After an online refresh, the last status and jobs are kept so you can
  still see them offline. **Play is disabled offline.**

---

## 8. Working offline

- A banner shows **Working offline** when the forge cannot be reached.
- Still works: local Changes / History / Branches / Compare / commit /
  open editor; last project list; last CI status and opened merge/pull
  requests (if you refreshed earlier).
- Disabled: refreshing projects from the server, clone, pull/push/force
  push, create merge/pull request, play CI jobs, live remote branch
  check.

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
- LAN `http://` forge: the PAT travels in cleartext — trusted networks
  only.

---

## Document history

Living end-user guide. Contributor / build notes live in `dev-guide.md`.
