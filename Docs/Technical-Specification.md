# Technical Specification — LabDesk

## 1. Overview

LabDesk is a native Linux desktop client for **self-hosted** GitLab,
Gitea, Forgejo, and OneDev. It provides GitHub Desktop-style
functionality (clone, branch, commit, push/pull, diff view, merge/pull
request creation) for users who run their own forge.

**V1 (GitLab vertical slice) is complete.** Post-V1 includes multi-forge
backends (dedicated API modules per forge, shared UI), LAN `http://`
base URLs, and forge CI surfaces where available.

Public SaaS hosts (`gitlab.com`, `github.com`, `gitea.com`,
`codeberg.org`, `code.onedev.io`, …) are **not supported** and must be
rejected at instance setup (see ADR-001).

## 2. System Architecture

### 2.1 Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ LabDesk Application                                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  UI Layer (Python + PySide6)                                │
│  ├── MainWindow (menubar + stacked ViewPlugin host)         │
│  ├── View plugins (Projects, Settings; more later)          │
│  ├── RepoWindow (Changes, History, Branches, Pipelines)     │
│  ├── DiffViewer (read-only QTextEdit)                       │
│  ├── InstanceConfigDialog (URL + PAT; git auth via helper)  │
│  └── MRDialog (Merge request creation form)                 │
│                                                             │
│  ──── PyO3 Bridge ────────────────────────────────────      │
│                                                             │
│  Core Layer (Rust)                                          │
│  ├── git_ops (libgit2 + credential helper; SSH)             │
│  ├── api / forge backends (GitLab, Gitea, Forgejo, OneDev)   │
│  ├── cache (SQLite read/write, sync logic)                  │
│  ├── diff_engine (libgit2 diff → text for QTextEdit)        │
│  ├── config (TOML parser, instance management)              │
│  └── secrets (system keyring for API PAT)                   │
│                                                             │
│  Storage                                                    │
│  ├── SQLite (cache: projects, branches, MR metadata)        │
│  ├── TOML (config: instance + preferences; no raw secrets)  │
│  ├── OS keyring (API PAT)                                   │
│  └── Git credential helper store (HTTPS git creds)          │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ External Interfaces                                         │
├─────────────────────────────────────────────────────────────┤
│  GitLab API v4 (REST over HTTPS, PRIVATE-TOKEN)             │
│  Git Protocol (SSH, or HTTPS via credential helper)         │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Technology Stack Summary

| Layer        | Technology              | License (summary)              | Role                          |
|--------------|-------------------------|--------------------------------|-------------------------------|
| UI Framework | PySide6 (Qt 6)          | LGPL-3.0 OR GPL-2.0 OR GPL-3.0 | Window management, widgets    |
| Diff viewer  | Qt `QTextEdit` (+ highlighter) | via PySide6/Qt            | Read-only diffs / file view   |
| Backend      | Rust                    | MIT/Apache (typical crates)    | Core logic, git ops, API      |
| Bridge       | Maturin / PyO3          | MIT                            | Python ↔ Rust                 |
| Git Library  | libgit2                 | GPLv2 with linking exception   | Local git operations          |
| Database     | SQLite                  | Public domain                  | Local cache                   |
| Config       | TOML                    | MIT/Apache                     | Instance + preference storage |
| Secrets      | OS keyring              | (platform)                     | API PAT at rest               |
| Git HTTPS    | Git credential helper   | (helper-dependent)             | Username/password or PAT-as-password |
| Distribution | Flatpak                 | (runtime/deps vary)            | Linux packaging; remote from `Ranga/flatpaks` |

Riverbank QScintilla is **not** used (ADR-002, ADR-003).

## 3. Data Flow

### 3.1 Happy Path: Clone → Edit (external) → Commit → Push → Create MR

```
User          UI Layer         Core (Rust)              GitLab / Git
 │               │                  │                        │
 │── Add Instance ─→ validate() ────→ GET /user ─────────────→│
 │               │←── result ────────←── 200 OK ─────────────│
 │               │                  │                        │
 │── List Projects → fetch() ───────→ GET /projects ─────────→│
 │               │←── project_list ──←── JSON ───────────────│
 │               │                  │                        │
 │── Clone Repo ──→ clone(url,path) → libgit2.clone()        │
 │               │←── success ───────│                        │
 │               │                  │                        │
 │── Edit Files ──→ open external editor (xdg-open / portal) │
 │               │                  │                        │
 │── View Changes → status() ───────→ libgit2.status()       │
 │               │←── file_list ─────│ (local)                │
 │               │                  │                        │
 │── Stage+Commit → commit(msg) ────→ libgit2.commit()       │
 │               │←── success ───────│ (local)                │
 │               │                  │                        │
 │── Push ────────→ push() ─────────→ libgit2.push()         │
 │               │                  │ (SSH or HTTPS via       │
 │               │                  │  credential helper)     │
 │               │←── success ───────│                        │
 │               │                  │                        │
 │── Force push ──→ push(--force) ──→ after explicit confirm │
 │               │                  │                        │
 │── Create MR ───→ create_mr() ────→ POST /merge_requests ─→│
 │               │                  │ (PRIVATE-TOKEN)        │
 │               │←── mr_web_url ────←── 201 Created ────────│
 │               │                  │                        │
 │── Open in GitLab → open_url() ───→ (xdg-open)             │
```

Editing is **always external** in V1. Diff view is read-only. Any
future in-app editor would be built from scratch (not QScintilla).

API calls use header **`PRIVATE-TOKEN`** (ADR-008). Git HTTPS uses the
**credential helper**; SSH uses agent/keys.

### 3.2 Offline Behavior

| Operation              | Requires Network? | Behavior When Offline                          |
|------------------------|-------------------|------------------------------------------------|
| View repo status       | No                | Full functionality                             |
| Stage/unstage files    | No                | Full functionality                             |
| Commit                 | No                | Full functionality                             |
| View diff              | No                | Full functionality                             |
| Create/switch branch   | No                | Full functionality                             |
| Merge (local, clean)   | No                | Full functionality; conflicts → external       |
| Push/Pull              | Yes               | Disable button, show warning                   |
| Force push             | Yes               | Disabled offline; confirm dialog when used     |
| List remote projects   | Yes               | Show cached list with staleness indicator      |
| Create MR              | Yes               | Disable, show "requires connection"            |
| View pipeline status   | Yes               | Post-V1: latest for current branch; play manual jobs |

## 4. Configuration Model

### 4.1 File Locations

**Flatpak (production):**

```
~/.var/app/com.bigrangatech.LabDesk/
├── config/
│   └── labdesk/
│       ├── config.toml          # Instance + preferences (no raw PAT)
│       └── trusted_certs/       # Imported CA certificates
└── data/
    └── labdesk/
        ├── cache.db             # SQLite database
        └── logs/                # Application logs
```

**Unpackaged / development (XDG):**

```
$XDG_CONFIG_HOME/labdesk/        # default: ~/.config/labdesk/
    config.toml
    trusted_certs/
$XDG_DATA_HOME/labdesk/          # default: ~/.local/share/labdesk/
    cache.db
    logs/
```

PATs for the **API** are stored in the **system keyring**, not in
`config.toml`. Git HTTPS username/password (or PAT-as-password) is
handled by the **Git credential helper** (ADR-008).

### 4.2 Configuration Structure

V1 UX configures **one** GitLab instance. The on-disk schema uses an
`[[instances]]` array so multiple instances can be added later without
a storage redesign.

**Config philosophy:** `config.toml` is the source of truth and the
**wide** preference surface — document and ship keys there early
(including experimental / tester-only). The **Settings** UI is
**narrow**: only controls for options that are confirmed working or
intentionally ready for end users. The UI writes those ready options
into the same file; other options stay config-only until promoted.
Changed settings are persisted (UI or file); Settings saves preserve
unknown keys and only update the fields they own. On **startup hang**,
revert to a **last known good** config, relaunch, and show an error
(what was happening + that config was reset). See `data-model.md` §3.0.

```toml
# Example (Flatpak path shown; XDG path equivalent in unpackaged runs)

[general]
theme = "system"                 # UI: Settings — "light", "dark", "system"
default_clone_dir = "~/Projects" # UI: Settings
check_for_updates = true         # UI: Settings — Flatpak remote (Ranga/flatpaks)
active_instance_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
active_ui_view = "projects"      # View menu (+ config); not Settings form
ui_shell = "classic"             # UI: Settings / View — "classic" | "sidebar"
projects_layout = "table"        # UI: Settings — "table" | "cards"
progress_overlay_color = "#2ecc71"  # UI: Settings — clone/push row fill
progress_overlay_alpha = 70      # UI: Settings — 0–255
[[instances]]
id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
name = "BigRanga Tech GitLab"
base_url = "https://gitlab.bigrangatech.com"
api_version = "v4"               # Detected/confirmed on first connect
api_auth = "PAT"                 # API always uses PRIVATE-TOKEN + PAT
# API PAT lives in the OS keyring; config only references it.
keyring_account = "labdesk:https://gitlab.bigrangatech.com"
# Git HTTPS uses the Git credential helper (username/password or PAT-as-password).
git_https_auth = "credential_helper"
ssl_mode = "strict"              # "strict", "allow_self_signed", "imported_ca"
created_at = "2026-07-01T12:00:00Z"
last_connected = "2026-07-01T15:30:00Z"
```

SaaS base URLs such as `https://gitlab.com` must be rejected when adding
an instance. **HTTPS** is required for public DNS names; **`http://`**
is allowed only for loopback and RFC1918 hosts (LAN / offline-domain
GitLab). Instance `id` and `active_instance_id` are required for
cache foreign keys and a future multi-instance UI; V1 still exposes one
active instance in the UI. See `data-model.md`.

## 5. V1 Feature Matrix

| Feature              | Local (libgit2)     | Remote (API)                         | Priority |
|----------------------|---------------------|--------------------------------------|----------|
| Instance setup       | —                   | `GET /user`, `GET /version`          | P0       |
| List projects        | —                   | owned + membership + group projects  | P0       |
| Clone repository     | `clone()`           | —                                    | P0       |
| View changes/status  | `status()`          | —                                    | P0       |
| Stage/unstage        | index APIs          | —                                    | P0       |
| Commit               | `commit()`          | —                                    | P0       |
| Diff view            | `diff()`            | —                                    | P0       |
| Push/Pull/Fetch      | push/pull/fetch     | credential helper or SSH         | P0       |
| Force push           | push (force)        | explicit confirm; not default    | P0       |
| Branch create/switch | branch APIs         | —                                | P0       |
| Local merge (clean)  | merge               | —                                    | P0       |
| Create MR            | —                   | `POST /merge_requests`               | P0       |
| Open in GitLab       | —                   | `xdg-open` / portal                  | P0       |
| Pipeline status + play manual jobs | —          | `GET /pipelines`, jobs, `POST …/play` | Post-V1 |
| Branch comparison    | compare             | remote branch verify                 | Nice-to-have |
| LAN HTTP base URL    | —                   | loopback + RFC1918 only              | Post-V1 |
| Build-date version   | —                   | `YYYY.MM.DD` in About / User-Agent   | Post-V1 |
| Background UI work   | —                   | Qt workers for clone/push/API        | Post-V1 |

## 6. Error Handling Strategy

Every user-visible failure should surface a stable **`LD-…` error code**
plus a short message. Authoritative catalog: [`error-codes.md`](error-codes.md).

| Scenario             | Code (primary) | User-Facing Response                         | Internal Action                    |
|----------------------|----------------|----------------------------------------------|------------------------------------|
| SaaS URL rejected    | `LD-CFG-004`   | "LabDesk supports self-hosted GitLab only."  | Block save; do not store           |
| Invalid PAT          | `LD-AUTH-001`  | "Authentication failed. Check your token."   | Clear keyring entry; prompt re-entry |
| Git auth failed      | `LD-GIT-002`   | "Git authentication failed. Check credentials or SSH keys." | Prompt helper / guide to SSH or PAT |
| 2FA blocks password  | `LD-GIT-003`   | "Password git auth blocked. Use SSH or a PAT." | Point to ADR-008 options        |
| Self-signed cert     | `LD-NET-010`   | "Certificate not trusted. Import CA or allow." | Offer trust override             |
| Network unreachable  | `LD-NET-001`   | "Cannot reach instance. Working offline."    | Switch to cached mode              |
| API rate limited     | `LD-API-429`   | "Rate limited. Retrying in N seconds."       | Exponential backoff                |
| Git push rejected    | `LD-GIT-010`   | "Push rejected. Pull first?"                 | Offer pull; force push only via separate confirmed action |
| Force push confirm   | `LD-UI-002`    | "Force push to {branch}? This can overwrite remote history." | Proceed only on explicit yes |
| Merge conflict       | `LD-GIT-020`   | "Conflicts detected. Resolve externally."    | Do not offer in-app resolve        |
| MR creation fails    | `LD-API-MR-001`| "Failed to create MR: {error}"               | Preserve form data; allow retry    |
| SQLite corruption    | `LD-CACHE-001` | "Cache corrupted. Rebuilding."               | Delete + recreate cache.db         |
| Keyring unavailable  | `LD-AUTH-002`  | "Cannot access system keyring."              | Block PAT save; explain            |
| Startup hang         | `LD-CFG-010`   | "Startup hung; config reset to last known good. {detail}" | Revert config snapshot; relaunch |

## 7. Known Constraints (V1)

- **One active instance in the UI** for now; storage schema remains
  multi-instance-ready.
- **One human user of the app; one API PAT** for that instance (no
  multi-account per instance).
- **API auth:** PAT via **`PRIVATE-TOKEN`** only. No OAuth, SSO, or
  LDAP pass-through for the API (ADR-008).
- **Git HTTPS auth:** Git **credential helper** (username/password when
  the instance allows it, or username + PAT as password). **SSH** also
  supported.
- **API PAT in system keyring only** — never plaintext in config. Git
  passwords are not stored in `config.toml` either.
- **Force push** is available behind an explicit confirmation dialog;
  it is not the default recovery from a rejected push.
- **No in-app code editing.** Diff view is read-only. Open files with
  an external editor via `xdg-open` / portal. A future in-app editor,
  if any, would be built from scratch.
- **No conflict resolution UI.** Conflicts are detected; user resolves
  externally. Clean local merges are supported.
- **No admin/runner management.** Developer workflow only.
- **English-only UI.** Localization deferred.
- **No repository search** in V1 (may change if SQLite caching makes it
  trivial).
- **Linux only.** No Windows or macOS.
- **Richer branch comparison** remains nice-to-have (not a V1 blocker).
- **Post-V1 shipped/planned:** LAN HTTP allowlist, build-date version,
  background workers, pipeline status + play manual jobs.
