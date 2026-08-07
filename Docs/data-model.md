# Data Model — LabDesk

**Status:** Draft (docs stage)  
**Related:** Technical Specification §4, `api-contract.md`,
`security-credentials.md`, ADR-004, ADR-006, ADR-008

This document describes **what LabDesk persists and caches**, and how
entities relate. It is the on-disk / in-app model — not the full GitLab
server schema.

V1 **UI** uses one active instance; the **storage shape** remains
multi-instance-ready.

---

## 1. Storage map

| Store | Path (concept) | Contents |
|-------|----------------|----------|
| Config TOML | Config dir / `config.toml` | Preferences + instance metadata (no secrets) |
| Trusted CAs | Config dir / `trusted_certs/` | PEM files when `ssl_mode = imported_ca` |
| SQLite cache | Data dir / `cache.db` | Projects, local repos, optional MR/pipeline cache |
| Logs | Data dir / `logs/` | Application logs (redacted) |
| OS keyring | Secret Service | API PAT only |
| Git credential helper | Helper-defined | Git HTTPS username/password (or PAT-as-password) |
| Git working copies | User-chosen paths | Real git repos on disk (libgit2); not inside LabDesk data dir |

Flatpak vs XDG locations: Technical Specification §4.1.

---

## 2. Entity overview

```text
AppPreferences (1)
    └── active_instance_id? ──► Instance (1..N in schema; 1 in V1 UI)
                                    │
                                    ├── keyring_account ──► OS keyring (API PAT)
                                    ├── trusted_certs/ (optional files)
                                    ├── ProjectCache (0..N)   [SQLite]
                                    └── LocalRepo (0..N)      [SQLite → filesystem path]
                                              │
                                              └── git working tree (libgit2)
```

Git HTTPS secrets are **not** LabDesk entities; they belong to the
credential helper (ADR-008).

---

## 3. Config TOML

### 3.1 `[general]` — AppPreferences

| Key | Type | Required | Notes |
|-----|------|----------|--------|
| `theme` | string | yes | `"light"` \| `"dark"` \| `"system"` |
| `default_clone_dir` | string | yes | Expanded path hint for clone dialog |
| `check_for_updates` | bool | yes | Means check **Flatpak remote** |
| `active_instance_id` | string | no | Stable id of the instance the UI uses; required once ≥1 instance exists |

### 3.2 `[[instances]]` — Instance

| Key | Type | Required | Notes |
|-----|------|----------|--------|
| `id` | string | yes | Stable id (e.g. UUID). Used as FK into SQLite and `active_instance_id` |
| `name` | string | yes | Display name |
| `base_url` | string | yes | Origin only; no `/api/v4`. SaaS hosts rejected at write time |
| `api_version` | string | yes | `"v4"` for V1 |
| `api_auth` | string | yes | `"PAT"` |
| `keyring_account` | string | yes | Keyring lookup id, e.g. `labdesk:https://…` |
| `git_https_auth` | string | yes | `"credential_helper"` |
| `ssl_mode` | string | yes | `"strict"` \| `"allow_self_signed"` \| `"imported_ca"` |
| `created_at` | string | yes | ISO 8601 UTC |
| `last_connected` | string | no | ISO 8601 UTC; updated on successful API use |
| `gitlab_version` | string | no | From `GET /version` when available |
| `gitlab_revision` | string | no | From `GET /version` when available |

**Not stored in TOML:** API PAT, git passwords, Authorization headers.

Example (illustrative):

```toml
[general]
theme = "system"
default_clone_dir = "~/Projects"
check_for_updates = true
active_instance_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

[[instances]]
id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
name = "BigRanga Tech GitLab"
base_url = "https://gitlab.bigrangatech.com"
api_version = "v4"
api_auth = "PAT"
keyring_account = "labdesk:https://gitlab.bigrangatech.com"
git_https_auth = "credential_helper"
ssl_mode = "strict"
created_at = "2026-07-01T12:00:00Z"
last_connected = "2026-07-01T15:30:00Z"
gitlab_version = "17.x.x"
```

> Tech-spec sample previously omitted `id` / `active_instance_id`.
> **Accepted 2026-08-07** — both are required; see Technical
> Specification §4.2.

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
| `instance_id` | TEXT | FK → config instance `id` |
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

**Primary key:** `(instance_id, project_id)`

**Staleness:** UI uses each row’s `fetched_at` (not a single list-wide
watermark) so offline/cached indicators can be accurate per project.

### 4.4 `local_repos` (known clones)

LabDesk needs to remember working copies the user opened/cloned.

| Column | Type | Notes |
|--------|------|--------|
| `id` | TEXT | Stable local id (UUID) |
| `instance_id` | TEXT | FK → instance |
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

### 4.5 `merge_requests` (deferred)

**Not in V1.** Creating an MR only needs the API response (`web_url`).
Revisit a local MR cache if a “recent MRs” UI is added later.

~~Suggested shape (future):~~

| Column | Type | Notes |
|--------|------|--------|
| `instance_id` | TEXT | |
| `project_id` | INTEGER | |
| `mr_iid` | INTEGER | |
| `title` | TEXT | |
| `state` | TEXT | |
| `web_url` | TEXT | |
| `source_branch` | TEXT | |
| `target_branch` | TEXT | |
| `fetched_at` | TEXT | |

**Primary key (future):** `(instance_id, project_id, mr_iid)`

### 4.6 `pipelines` (nice-to-have)

Only if pipeline UI ships.

| Column | Type | Notes |
|--------|------|--------|
| `instance_id` | TEXT | |
| `project_id` | INTEGER | |
| `ref` | TEXT | Branch/tag |
| `pipeline_id` | INTEGER | |
| `status` | TEXT | |
| `web_url` | TEXT | |
| `updated_at` | TEXT | From API |
| `fetched_at` | TEXT | |

**Primary key:** `(instance_id, project_id, ref)` or include `pipeline_id`
if keeping history — decide when implementing the nice-to-have.

---

## 5. Secrets (not SQL)

| Secret | Store | Key / identity |
|--------|-------|----------------|
| API PAT | OS keyring | `keyring_account` from Instance |
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
| Instance removed | Delete keyring entry; delete SQLite rows for `instance_id`; leave git working copies on disk unless user asks to delete |
| PAT invalid | Clear keyring secret; keep Instance row |
| Cache corrupt | Delete `cache.db`, recreate empty schema, refetch when online |
| SaaS URL attempted | Do not write Instance or secrets |

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
4. ~~**`merge_requests` table in V1**~~ — **Deferred** (not V1).
5. **Pipeline primary key / history depth** — defer until nice-to-have
   is scheduled.

---

## 9. Change control

Schema or config key changes: update this file, tech spec §4 if
examples diverge, and `CHANGELOG.md`.
