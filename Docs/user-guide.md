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

See also the project `README.md`.

---

## 2. Install & update

LabDesk releases are Flatpaks from the self-hosted remote published out
of [`Ranga/flatpaks`](http://git.bigrangatech.com/Ranga/flatpaks.git)
(not required to use Flathub for beta).

### 2.1 Add the remote (once)

Flatpak **system** installs refuse unsigned remotes (`Can't pull from
untrusted non-gpg verified remote`). Prefer the signed `.flatpakrepo`
after CI has published with GPG (see §2.1a). Until then, use a **user**
remote with `--no-gpg-verify`:

```bash
# Temporary unsigned path (user install only)
flatpak remote-delete --user bigrangatech-flatpaks 2>/dev/null || true
flatpak remote-add --if-not-exists --user --no-gpg-verify bigrangatech-flatpaks \
  https://git.bigrangatech.com/Ranga/flatpaks/-/raw/main/labdesk/repo
flatpak install --user bigrangatech-flatpaks com.bigrangatech.LabDesk
```

### 2.1a Signed remote (recommended)

After operators create a signing key (`./scripts/flatpak-gpg-create.sh`)
and set `FLATPAK_GPG_PRIVATE_KEY` in GitLab CI, each publish writes
`labdesk.flatpakrepo` + `bigrangatech-flatpak.gpg` into `Ranga/flatpaks`.

```bash
flatpak remote-delete --user bigrangatech-flatpaks 2>/dev/null || true
# Also remove a broken system remote if you added one earlier:
#   sudo flatpak remote-delete bigrangatech-flatpaks

flatpak remote-add --if-not-exists bigrangatech-flatpaks \
  https://git.bigrangatech.com/Ranga/flatpaks/-/raw/main/labdesk/labdesk.flatpakrepo

flatpak install bigrangatech-flatpaks com.bigrangatech.LabDesk
flatpak run com.bigrangatech.LabDesk
```

Or import the public key explicitly:

```bash
curl -fsSL -o /tmp/bigrangatech-flatpak.gpg \
  https://git.bigrangatech.com/Ranga/flatpaks/-/raw/main/labdesk/bigrangatech-flatpak.gpg
flatpak remote-add --if-not-exists --gpg-import=/tmp/bigrangatech-flatpak.gpg \
  bigrangatech-flatpaks \
  https://git.bigrangatech.com/Ranga/flatpaks/-/raw/main/labdesk/repo
```

Prefer **HTTPS** remotes when TLS is set up for the GitLab host.

### 2.2 Install

```bash
flatpak install bigrangatech-flatpaks com.bigrangatech.LabDesk
flatpak run com.bigrangatech.LabDesk
```

After install, **LabDesk** also appears in the desktop application menu
(start menu). Icons are the PNGs under
`src/labdesk_ui/assets/com.bigrangatech.LabDesk-*.png`.

### 2.3 Update

```bash
flatpak update com.bigrangatech.LabDesk
```

Or update everything from that remote:

```bash
flatpak update --appstream
flatpak update
```

In-app **`check_for_updates`** (Settings and `config.toml`) means “check
this Flatpak remote for a newer LabDesk”, not a custom downloader.
Settings can toggle startup checks and run **Check for updates now**.
Inside the Flatpak sandbox the check uses `flatpak-spawn --host` (needs
`--talk-name=org.freedesktop.Flatpak`). You can always fall back to
`flatpak update` as above. New builds appear only after CI on `labdesk`
has pushed to `Ranga/flatpaks`.

### 2.4 Config paths (Flatpak vs unpackaged)

- Flatpak: under `~/.var/app/com.bigrangatech.LabDesk/`
- Unpackaged / dev: `~/.config/labdesk/`, `~/.local/share/labdesk/`

---

## 2a. Beta smoke checklist

After install or a major update:

1. Launch LabDesk; theme and shell layout load from config.
2. Connect to self-hosted GitLab (PAT in keyring).
3. Refresh projects; **Open local** or **Add existing…** for a clone.
4. Repo window: Changes (stage / commit), History, Branches (create /
   switch / merge), Fetch / Pull / Push, ahead/behind vs upstream,
   Open in editor, Create merge request (when online; offered after push).
   Re-opening the same repo focuses the existing window; **Window** menu
   lists open repos.
5. Confirm offline banner if the instance is unreachable (local git still
   works; push/MR/refresh disabled).
6. Run `flatpak update com.bigrangatech.LabDesk` after a new CI publish
   and confirm the app still launches (PySide6 UI included).

---

## 3. First-time setup

- On first launch with no instances, LabDesk offers **Add / connect**.
- Add instance (URL + API personal access token).
- Why SaaS URLs are rejected.
- TLS / self-signed / imported CA (short, practical).
- Where the token is stored (system keyring — not a file you edit).

→ Journey A in `user-journey.md`.

---

## 3a. Settings & config file

- **`config.toml` is the full preference surface** — as many options as
  practical live there (including ones that are not in the UI yet).
- **Settings → Preferences** shows options confirmed for everyday use:
  clone folder, theme, main window layout (`ui_shell`), and Flatpak
  update checks (`check_for_updates` + Check now).
- Switch main views via the **View** menu; last view is stored as
  `general.active_ui_view` (not a Settings form field).
- Main window **layout** (`classic` / `sidebar`) is also available under
  **View → Classic / Sidebar layout**.
- **Clone into:** folder where new clones go (e.g. `~/Documents/gitlab`).
  Saved as `general.default_clone_dir`.
- Advanced / not-yet-in-UI options: edit `config.toml` directly (paths
  under Flatpak vs XDG — fill when writing this section).
- Changes are saved whether made in the UI or in the file; Settings
  saves preserve keys they do not own.
- If the app **hangs on startup** (no ready signal within **45 seconds**),
  it reverts to the last known-good config, relaunches, and shows
  **`LD-CFG-010`** (or **`LD-CFG-011`** if no snapshot existed).
- Do not put PATs or passwords in the config file.

---

## 4. Projects & cloning

- Browsing projects (membership list).
- Clone with HTTPS (credential helper) or SSH.
- Default clone directory.

→ Journey B.

---

## 5. Daily git work

- **Changes:** stage / unstage / commit; read-only diffs.
- **Open in editor:** opens the selected file with the desktop default
  (`xdg-open` / portal).
- **Branches** tab: list, switch, create, and **merge into current**
  (clean merge only; conflicts abort with **`LD-GIT-020`** — resolve
  externally).
- **Fetch / Pull / Push** and ahead/behind vs upstream in the header.

→ Journey C.

---

## 6. Push, force push & merge requests

- **Fetch / Pull / Push** from the repo toolbar (disabled while offline).
- **Force push…** only after confirming the branch name.
- After a successful (non-force) push, LabDesk offers to **create a merge
  request**.
- **Create merge request…:** title, description, source/target; on
  success, optionally open the MR in the browser.

→ Journey D.

---

## 7. Working offline

- Status banner shows **Working offline** when the API is unreachable
  (`LD-NET-001`).
- Still works: local Changes / History / Branches / commit / open editor.
- Disabled: project refresh from API, clone, pull/push/force push,
  create MR.
- Cached project list may show a staleness / offline hint.

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
