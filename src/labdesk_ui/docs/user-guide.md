# LabDesk User Guide

**Status:** Living  
**Audience:** People using LabDesk day to day  
**Related:** `user-journey.md` (flows), `security-credentials.md` (secrets),
Technical Specification (constraints)

This guide is also available in the app under **Help → User Guide…**.
It stays end-user focused — no API or SQLite schema detail.

---

## 1. What LabDesk is

- Linux desktop client for **self-hosted GitLab** only (not GitLab.com).
- Local git (commit, branch, diff) plus forge features (project list,
  merge requests, pipeline status).
- Distributed as **Flatpak** for releases.
- **V1 is complete** (connect → git → MR → Flatpak). **Help → About**
  shows the build-date version (`YYYY.MM.DD`).

---

## 2. Install & update

LabDesk releases are Flatpaks from the self-hosted remote published out
of `Ranga/flatpaks` (not required to use Flathub for beta).

### 2.1 Add the remote (once)

Flatpak **system** installs refuse unsigned remotes. Prefer the signed
`.flatpakrepo` after CI has published with GPG (see §2.1a). Until then,
use a **user** remote with `--no-gpg-verify`:

```bash
flatpak remote-delete --user bigrangatech-flatpaks 2>/dev/null || true
flatpak remote-add --if-not-exists --user --no-gpg-verify bigrangatech-flatpaks \
  https://git.bigrangatech.com/Ranga/flatpaks/-/raw/main/labdesk/repo
flatpak install --user bigrangatech-flatpaks com.bigrangatech.LabDesk
```

### 2.1a Signed remote (recommended)

```bash
flatpak remote-delete --user bigrangatech-flatpaks 2>/dev/null || true
flatpak remote-add --if-not-exists bigrangatech-flatpaks \
  https://git.bigrangatech.com/Ranga/flatpaks/-/raw/main/labdesk/labdesk.flatpakrepo
flatpak install bigrangatech-flatpaks com.bigrangatech.LabDesk
flatpak run com.bigrangatech.LabDesk
```

Prefer **HTTPS** remotes when TLS is set up for the GitLab host.

### 2.2 Update

```bash
flatpak update com.bigrangatech.LabDesk
```

In-app **Check for updates** (Settings) uses the same Flatpak remote.
New builds appear only after CI on `labdesk` has published to
`Ranga/flatpaks`.

### 2.3 Config paths

- Flatpak: under `~/.var/app/com.bigrangatech.LabDesk/`
- Unpackaged / dev: `~/.config/labdesk/`, `~/.local/share/labdesk/`

---

## 3. First-time setup

1. On first launch with no instances, LabDesk offers **Add / connect**.
2. Enter a display name, **base URL**, and API **personal access token**.
   - Prefer **`https://…`**.
   - On a LAN you may use **`http://192.168.x.x:port`** (or other
     RFC1918 / loopback hosts). Public DNS names still require HTTPS.
   - Over plain HTTP the API PAT travels in cleartext — trusted LAN only.
3. SaaS hosts (`gitlab.com`, `github.com`, …) are rejected.
4. Choose a TLS mode: **Strict** (default), **Allow self-signed**, or
   Imported CA (uses system trust until full CA import lands).
5. The PAT is stored in the **system keyring**, not in `config.toml`.

---

## 4. Settings & preferences

- **Settings → Preferences:** clone folder, theme, window layout
  (`classic` / `sidebar`), Flatpak update checks.
- **View** menu: switch Projects / Settings and layout.
- Full options live in `config.toml` (including tester-only keys).
  Settings saves preserve keys they do not own.
- Do **not** put PATs or passwords in the config file.
- If startup hangs (~45s), LabDesk reverts to last known-good config and
  shows **`LD-CFG-010`**.

---

## 5. Projects & cloning

- **Refresh projects** loads your membership list from GitLab (cached
  in SQLite for offline browsing).
- **Clone** (HTTPS or SSH) into the default clone folder.
- **Open local** / **Add existing…** attach an already-cloned folder.
- Double-click a project or use Open local to open a **repo window**.

---

## 6. Daily git work

In the repo window:

- **Changes:** stage / unstage / commit; read-only diffs.
- **Open in editor:** opens the selected file with the desktop default.
- **Branches:** list, switch, create, merge into current (clean merge
  only; conflicts → **`LD-GIT-020`**, resolve externally).
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
- Online refresh writes a small cache so offline you can still see the
  last status and jobs. **Play is disabled offline.**

---

## 8. Working offline

- Banner shows **Working offline** when the API is unreachable
  (`LD-NET-001`).
- Still works: local Changes / History / Branches / commit / open editor;
  cached project list; cached pipeline status (if previously fetched).
- Disabled: project refresh from API, clone, pull/push/force push,
  create MR, play CI jobs.

---

## 9. Help in the app

- **Help → User Guide…** — this document.
- **Help → About LabDesk** — version (`YYYY.MM.DD` on Flatpak builds).

---

## 10. Troubleshooting

| Symptom | What to try |
|---------|-------------|
| Auth failed (`LD-AUTH-001`) | Re-enter PAT; check scopes / expiry |
| Keyring error (`LD-AUTH-002`) | Unlock Secret Service / password manager |
| Git auth failed | Credential helper, SSH agent, or PAT-as-password |
| 2FA blocks password git | Use SSH or HTTPS with a PAT |
| Certificate not trusted | Settings TLS mode, or fix host CA |
| Cache corrupt | LabDesk rebuilds `cache.db`; refresh projects |
| Flatpak update missing | Confirm CI published to `Ranga/flatpaks` |

---

## 11. Privacy & security

- API PAT → OS keyring only.
- Git HTTPS passwords → Git credential helper.
- Never paste PATs into chat, issues, or screenshots.
- LAN `http://` GitLab: PAT is cleartext on the wire — trusted networks only.

---

## Document history

Living user guide; also bundled for **Help → User Guide…**.
