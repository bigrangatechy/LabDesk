# Data Model — LabDesk

**Status:** Draft (docs stage)  
**Related:** Technical Specification §4, `api-contract.md`,
`security-credentials.md`, ADR-004, ADR-006, ADR-008

This document describes **what LabDesk persists and caches**, and how
entities relate. It is the on-disk / in-app model — not the full GitLab
server schema.

V1 shipped with one active connection; storage now supports **multiple
GitLab hosts (instances)** and **multiple accounts (users) per host**.

---

## 1. Storage map

| Store | Path (concept) | Contents |
|-------|----------------|----------|
| Config TOML | Config dir / `config.toml` | Preferences + instance/account metadata (no secrets) |
| Trusted CAs | Config dir / `trusted_certs/` | PEM files when `ssl_mode = imported_ca` |
| SQLite cache | Data dir / `cache.db` | Projects, local repos, pipeline cache (keyed by **account**) |
| Logs | Data dir / `logs/` | Application logs (redacted) |
| OS keyring | Secret Service | API PAT only (per account) |
| Git credential helper | Helper-defined | Git HTTPS username/password (or PAT-as-password) |
| Git working copies | User-chosen paths | Real git repos on disk (libgit2); not inside LabDesk data dir |

Flatpak vs XDG locations: Technical Specification §4.1.

---

## 2. Entity overview

```text
AppPreferences (1)
    ├── active_instance_id? ──► Instance (GitLab host, 1..N)
    └── active_account_id?  ──► Account (user/PAT on a host, 1..N)
                                    │
                                    ├── instance_id ──► Instance
                                    ├── keyring_account ──► OS keyring (API PAT)
                                    ├── ProjectCache (0..N)   [SQLite, account_id]
                                    └── LocalRepo / pipelines [SQLite, account_id]
                                              │
                                              └── git working tree (libgit2)
```

**Instance** = a different GitLab **machine** (`base_url` + TLS).  
**Account** = a different GitLab **user** (PAT) on one machine.  
API auth and project membership always follow **`active_account_id`**.

Git HTTPS secrets are **not** LabDesk entities; they belong to the
credential helper (ADR-008).

---

## 3. Config TOML

### 3.0 Philosophy — file first, UI when ready

`config.toml` is the **source of truth** for non-secret settings.

- **Expose options in the file aggressively.** Prefer documenting and
  shipping a key in `config.toml` as soon as the core can read it —
  even if behaviour is incomplete, experimental, or tester-only. The
  file is the wide surface; the Settings UI is the narrow one.
- **Settings / Preferences UI is conservative.** Only put a control in
  Settings when the option is **confirmed working** (or deliberately
  ready for end users). Do not mirror every config key in the UI.
- Options may exist in the file **before** a Settings control exists.
  That lets developers and testers turn features on via the config
  without shipping incomplete UI.
- Hand-editing `config.toml` is a supported testing path (document
  paths in the user/dev guides).
- **Persistence:** if a setting has been changed — whether in the **UI**
  or by editing the **config file** — it should be **saved**. The UI
  must **preserve unknown keys and sections** it does not manage yet,
  so hand-edited testing options are not wiped on Preferences save.
  Settings saves update **only** the UI-exposed fields they own.
- **Known-good snapshot:** after a successful launch reaches a stable
  “running” state, LabDesk keeps a **last known good** copy of
  `config.toml` (exact filename/location — implementation detail).
- **Hang on open → recover:** if the app **hangs while opening /
  starting**, LabDesk (or a small launcher/watchdog) should:
  1. Detect the hang (**timeout: 45 seconds** from process start until
     the main window signals ready).
  2. **Revert** `config.toml` to the last known good snapshot
     (`config.known-good.toml`).
  3. **Relaunch** the app.
  4. Show an **error** with code **`LD-CFG-010`**, explaining that
     startup hung, that the config was reset to the last known good
     state, and whatever diagnostic is available about what was
     happening when it hung (best-effort; see `error-codes.md`).
     If no snapshot existed → **`LD-CFG-011`**.
- Secrets still never go in this file (ADR-008 / security-credentials).

Mark each preference as **UI-exposed** (Settings), **elsewhere in UI**
(e.g. View menu), or **config-only (until ready)** as features land.
V1 Settings stays small; the file may grow ahead of the UI.

- Docs are **living**: behaviour refined here can be adjusted when coding
  proves better mechanisms (ADR-007 does not require freezing every
  timeout before the first line of real code). Documentation and code
  advance together; empty stubs (Flatpak detail, full guides, tests)
  must not block starting a vertical slice once architecture is clear.

### 3.1 `[general]` — AppPreferences

| Key | Type | Required | Exposure | Notes |
|-----|------|----------|----------|--------|
| `theme` | string | yes | **UI-exposed** | `"light"` \| `"dark"` \| `"system"` |
| `default_clone_dir` | string | yes | **UI-exposed** | Clone destination folder |
| `check_for_updates` | bool | yes | **UI-exposed** | Check the **LabDesk Flatpak remote** (from `Ranga/flatpaks`, ADR-004); Settings toggle + Check now |
| `active_instance_id` | string | no | **config / connect flow** | Active host; kept in lockstep with the active account’s `instance_id` |
| `active_account_id` | string | no | **config / connect flow** | Active account (PAT); **required** once ≥1 account exists; drives API auth |
| `active_ui_view` | string | no | **View menu** (+ config) | Pluggable main view id (`projects`, `settings`, …); default `projects` |
| `ui_shell` | string | no | **UI-exposed** | Main-window shell layout: `"classic"` \| `"sidebar"`; default `classic` |

### 3.2 `[[instances]]` — Instance (GitLab host)

| Key | Type | Required | Notes |
|-----|------|----------|--------|
| `id` | string | yes | Stable id (UUID) |
| `name` | string | yes | Display name for the host |
| `base_url` | string | yes | Origin only; no `/api/v4`. SaaS hosts rejected. HTTPS required except loopback/RFC1918 may use `http://` |
| `api_version` | string | yes | `"v4"` |
| `ssl_mode` | string | yes | `"strict"` \| `"allow_self_signed"` \| `"imported_ca"` |
| `created_at` | string | yes | ISO 8601 UTC |

Host rows do **not** store `keyring_account` (that lives on accounts).

### 3.3 `[[accounts]]` — Account (user on a host)

| Key | Type | Required | Notes |
|-----|------|----------|--------|
| `id` | string | yes | Stable id (UUID). Used as SQLite **`account_id`** partition key |
| `instance_id` | string | yes | FK → `[[instances]].id` |
| `name` | string | yes | Display label (e.g. “Work”, “Personal”) |
| `username` | string | no | From `GET /user` when known |
| `api_auth` | string | yes | `"PAT"` |
| `keyring_account` | string | yes | Keyring lookup id: `labdesk:{base_url}:{account_id}` (legacy single-host installs may keep `labdesk:{base_url}`) |
| `git_https_auth` | string | yes | `"credential_helper"` |
| `created_at` | string | yes | ISO 8601 UTC |
| `last_connected` | string | no | ISO 8601 UTC; updated on successful API use |
| `gitlab_version` | string | no | From `GET /version` when available |
| `gitlab_revision` | string | no | From `GET /version` when available |

**Not stored in TOML:** API PAT, git passwords, Authorization headers.

**Migration:** legacy `[[instances]]` that still carry `keyring_account`
are split on load into one host + one account; `active_account_id` is set.

Example (illustrative):

```toml
[general]
theme = "system"
default_clone_dir = "~/Projects"
check_for_updates = true
active_instance_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
active_account_id = "11111111-2222-3333-4444-555555555555"
active_ui_view = "projects"
ui_shell = "classic"

[[instances]]
id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
name = "BigRanga Tech GitLab"
base_url = "https://gitlab.bigrangatech.com"
api_version = "v4"
ssl_mode = "strict"
created_at = "2026-07-01T12:00:00Z"

[[accounts]]
id = "11111111-2222-3333-4444-555555555555"
instance_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
name = "Jessie"
username = "jessie"
api_auth = "PAT"
keyring_account = "labdesk:https://gitlab.bigrangatech.com:11111111-2222-3333-4444-555555555555"
git_https_auth = "credential_helper"
created_at = "2026-07-01T12:00:00Z"
last_connected = "2026-07-01T15:30:00Z"
```

---

## 4. SQLite — `cache.db`

### 4.1 Design rules

- Cache is **disposable**: corruption → delete and rebuild (tech spec §6).
- Do not store secrets in SQLite.
- Use `schema_version` for migrations.
- Timestamps: ISO 8601 text or integer Unix time — pick one in
  implementation and stick to it; examples below use ISO 8601 text.

### 4.2 `schema_meta`

| Column | Type | Notes |
|--------|------|--------|
| `key` | TEXT PK | e.g. `schema_version` |
| `value` | TEXT | e.g. `1` |

### 4.3 `projects` (API project cache)

Populated from `GET /projects?membership=true…` (`api-contract.md`).

| Column | Type | Notes |
|--------|------|--------|
| `account_id` | TEXT | FK → config account `id` (membership differs per user) |
| `project_id` | INTEGER | GitLab numeric id |
| `name` | TEXT | |
| `name_with_namespace` | TEXT | |
| `path_with_namespace` | TEXT | |
| `http_url_to_repo` | TEXT | |
| `ssh_url_to_repo` | TEXT | |
| `web_url` | TEXT | |
| `default_branch` | TEXT NULL | |
| `visibility` | TEXT NULL | |
| `last_activity_at` | TEXT NULL | From API |
| `fetched_at` | TEXT | When LabDesk last upserted this row (per-row staleness) |

**Primary key:** `(account_id, project_id)`

**Schema:** version **4** uses `account_id` (v1–3 used `instance_id`).
Cache is disposable — upgrade rebuilds empty tables.

**Staleness:** UI uses each row’s `fetched_at` (not a single list-wide
watermark) so offline/cached indicators can be accurate per project.

### 4.4 `local_repos` (known clones)

LabDesk needs to remember working copies the user opened/cloned.

| Column | Type | Notes |
|--------|------|--------|
| `id` | TEXT | Stable local id (UUID) |
| `account_id` | TEXT | FK → account |
| `project_id` | INTEGER NULL | FK-ish to `projects.project_id` when known |
| `path` | TEXT UNIQUE | Absolute filesystem path to repo root |
| `preferred_remote` | TEXT NULL | e.g. `origin` |
| `clone_url` | TEXT NULL | URL used at clone time |
| `added_at` | TEXT | |
| `last_opened_at` | TEXT NULL | |
| `last_push_at` | TEXT NULL | **UI frame of reference:** when this working copy was last successfully pushed to its remote. Helps people who leave commits (or unfinished work) sitting locally for a while. Updated when LabDesk completes a push/force-push; exact derivation from git state vs LabDesk-only recording can be settled at implementation time |

If `path` no longer exists, mark missing in UI; do not auto-delete
without user action (exact UX in user guide later).

**Note on `last_push_at`:** This is not a substitute for `git status` /
ahead-behind. It answers “how long since I last got this onto the
remote?” — useful when someone does not commit and push every change.
Uncommitted work has no push time; the stamp only moves on a successful
push.

### 4.5 `merge_requests` (shipped — opened per project)

Caches **opened** merge requests for a project so the repo **Merge
requests** tab can show a thin list offline. Refresh replaces all rows
for that `(account_id, project_id)`.

| Column | Type | Notes |
|--------|------|--------|
| `account_id` | TEXT | |
| `project_id` | INTEGER | |
| `mr_iid` | INTEGER | |
| `title` | TEXT | |
| `state` | TEXT | |
| `web_url` | TEXT | |
| `source_branch` | TEXT | |
| `target_branch` | TEXT | |
| `updated_at` | TEXT NULL | From API |
| `fetched_at` | TEXT | When LabDesk wrote the row |

**Primary key:** `(account_id, project_id, mr_iid)`.

**Schema:** version **5** adds this table (v4 used `account_id` on
projects/pipelines only). Cache upgrade rebuilds disposable DB.

### 4.6 `pipelines` (shipped — latest per ref)

Caches the **latest** pipeline for a branch/tag so the repo Pipelines
tab can show status offline. **No history** — one row per ref.

| Column | Type | Notes |
|--------|------|--------|
| `account_id` | TEXT | |
| `project_id` | INTEGER | |
| `ref` | TEXT | Branch/tag |
| `pipeline_id` | INTEGER | |
| `status` | TEXT | |
| `web_url` | TEXT | |
| `updated_at` | TEXT | From API |
| `jobs_json` | TEXT | JSON array of last jobs list (for offline UI) |
| `fetched_at` | TEXT | When LabDesk wrote the row |

**Primary key:** `(account_id, project_id, ref)`.

Play remains **online-only**; cached jobs are display-only when offline.

---

## 5. Secrets (not SQL)

| Secret | Store | Key / identity |
|--------|-------|----------------|
| API PAT | OS keyring | `keyring_account` from Account |
| Git HTTPS password / PAT-as-password | Credential helper | Host/URL attributes per helper |
| SSH private keys | User agent / files | Outside LabDesk |

Lifecycle: `security-credentials.md`.

---

## 6. Runtime-only (not persisted as LabDesk tables)

Derived via libgit2 from `local_repos.path`:

- Working tree status (staged / unstaged / untracked)
- Diff text for `QTextEdit`
- Local branches, ahead/behind (after fetch)
- Merge conflict presence (boolean / detection only)

Persist nothing sensitive from these into SQLite beyond what §4 already
allows.

---

## 7. Integrity & cleanup

| Event | Behaviour |
|-------|-----------|
| Instance / account removed | Delete keyring entry for that account; delete SQLite rows for `account_id`; leave git working copies on disk unless user asks to delete |
| PAT invalid | Clear keyring secret; keep Account row |
| Cache corrupt | Delete `cache.db`, recreate empty schema, refetch when online |
| SaaS URL attempted | Do not write Instance/Account or secrets |

---

## 8. Open points / deferred to implementation

Some fields are **intent-locked** but mechanism-flexible until coding
proves what libgit2 / the UI can reliably provide.

1. ~~**`id` / `active_instance_id` in config**~~ — **Accepted**; tech
   spec §4.2 aligned.
2. ~~**Project list staleness**~~ — **Accepted:** per-row `fetched_at`
   on `projects`.
3. **`last_push_at` on `local_repos`** — **Intent accepted** (UI frame:
   time since last successful push to remote). Recording vs deriving
   from git: decide while implementing.
4. ~~**`merge_requests` table**~~ — **Accepted:** opened MRs per project
   for the Merge requests tab (`account_id`); replace on refresh.
5. ~~**Pipeline primary key / history depth**~~ — **Accepted:** latest
   only per `(account_id, project_id, ref)` + `jobs_json`; no history.
6. ~~**Multi-instance / multi-account**~~ — **Accepted:** hosts in
   `[[instances]]`, users in `[[accounts]]`, cache keyed by `account_id`.

---

## 9. Change control

Schema or config key changes: update this file, tech spec §4 if
examples diverge, and `CHANGELOG.md`.
