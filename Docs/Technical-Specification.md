# Technical Specification — LabDesk

## 1. Overview

LabDesk is a native Linux desktop client for self-hosted GitLab
instances. It provides GitHub Desktop-style functionality (clone,
branch, commit, push/pull, diff view, merge request creation) targeted
exclusively at users who run their own GitLab infrastructure.

## 2. System Architecture

### 2.1 Layer Diagram

┌─────────────────────────────────────────────────────────────┐ │ LabDesk Application │ ├─────────────────────────────────────────────────────────────┤ │ │ │ UI Layer (Python + PySide6 + QScintilla) │ │ ├── MainWindow (sidebar + content area) │ │ ├── RepoView (Changes, History, Branches tabs) │ │ ├── DiffViewer (QScintilla widget) │ │ ├── InstanceConfigDialog (URL + PAT setup) │ │ └── MRDialog (Merge request creation form) │ │ │ │ ──── PyO3 Bridge ──────────────────────────────────── │ │ │ │ Core Layer (Rust) │ │ ├── git_ops (libgit2 wrapper: status, commit, push) │ │ ├── api_client (GitLab REST API v4 client) │ │ ├── cache (SQLite read/write, sync logic) │ │ ├── diff_engine (libgit2 diff formatting for QScintilla) │ │ ├── config (TOML parser, instance management) │ │ └── crypto (PAT encryption at rest) │ │ │ │ Storage │ │ ├── SQLite (cache: projects, branches, MR metadata) │ │ └── TOML (config: instances, preferences) │ │ │ ├─────────────────────────────────────────────────────────────┤ │ External Interfaces │ ├─────────────────────────────────────────────────────────────┤ │ GitLab API v4 (REST over HTTPS) │ │ Git Protocol (SSH or HTTPS with embedded PAT) │ └─────────────────────────────────────────────────────────────┘


### 2.2 Technology Stack Summary

| Layer        | Technology         | License    | Role                           |
|--------------|--------------------|------------|--------------------------------|
| UI Framework | PySide6 (Qt 6)     | LGPL v3    | Window management, widgets    |
| Code Viewer  | QScintilla         | Apache 2.0 | Diff rendering, syntax highlight |
| Backend      | Rust               | MIT/Apache  | Core logic, git ops, API       |
| Bridge       | Maturin / PyO3     | MIT        | Python ↔ Rust interoperability |
| Git Library  | libgit2            | GPLv2+     | Local git operations           |
| Database     | SQLite             | Public dom | Local cache                    |
| Config       | TOML (toml crate)  | MIT/Apache  | Instance + preference storage  |
| Distribution | Flatpak            | LGPL       | Linux packaging                |

## 3. Data Flow

### 3.1 Happy Path: Clone → Edit → Commit → Push → Create MR

User UI Layer Core (Rust) GitLab API │ │ │ │ │── Add Instance ──→ │── validate() ────→│── GET /user ──────→│ │ │←── result ─────────│←── 200 OK ────────│ │ │ │ │ │── List Projects ──→│── fetch() ───────→│── GET /projects ──→│ │ │←── project_list ───│←── JSON array ─────│ │ │ │ │ │── Clone Repo ─────→│── clone(url,path)→│── libgit2.clone() │ │ │ │ (no API needed) │ │ │←── success ────────│ │ │ │ │ │ │── Edit Files ─────→│ │ │ │ │ │ │ │── View Changes ───→│── status() ──────→│── libgit2.status() │ │ │←── file_list ──────│ (local only) │ │ │ │ │ │── Stage + Commit ─→│── commit(msg) ───→│── libgit2.commit() │ │ │←── success ────────│ (local only) │ │ │ │ │ │── Push ──────────→│── push() ────────→│── libgit2.push() │ │ │ │ (SSH/HTTPS) │ │ │←── success ────────│ │ │ │ │ │ │── Create MR ─────→│── create_mr() ───→│── POST /mr ───────→│ │ │←── mr_web_url ─────│←── 201 Created ────│ │ │ │ │ │── Open in Browser→│── open_url() ────→│ (xdg-open) │


### 3.2 Offline Behavior

| Operation              | Requires Network? | Behavior When Offline          |
|------------------------|--------------------|-------------------------------|
| View repo status       | No                 | Full functionality             |
| Stage/unstage files    | No                 | Full functionality             |
| Commit                 | No                 | Full functionality             |
| View diff              | No                 | Full functionality             |
| Create/switch branch   | No                 | Full functionality             |
| Merge (local)          | No                 | Full functionality             |
| Push/Pull              | Yes                | Disable button, show warning   |
| List remote projects   | Yes                | Show cached list with staleness indicator |
| Create MR              | Yes                | Disable, show "requires connection" |
| View pipeline status   | Yes                | Show last cached status with timestamp |

## 4. Configuration Model

### 4.1 File Locations (Flatpak-aware)

~/.var/app/com.bigrangatech.LabDesk/ ├── config/ │ └── labdesk/ │ ├── config.toml # Instances + preferences │ └── trusted_certs/ # Imported CA certificates └── data/ └── labdesk/ ├── cache.db # SQLite database └── logs/ # Application logs


### 4.2 Configuration Structure

```toml
# ~/.var/app/com.bigrangatech.LabDesk/config/labdesk/config.toml

[general]
theme = "system"           # "light", "dark", "system"
default_clone_dir = "~/Projects"
check_for_updates = true

[[instances]]
name = "BigRanga Tech GitLab"
base_url = "https://gitlab.bigrangatech.com"
api_version = "v4"           # Auto-detected on first connect
auth_type = "PAT"
token_encrypted = true       # Stored in system keyring or encrypted blob
created_at = "2026-07-01T12:00:00Z"
last_connected = "2026-07-01T15:30:00Z"

[[instances]]
name = "Personal Server"
base_url = "https://gitlab.personal.lan:8443"
api_version = "v4"
auth_type = "PAT"
token_encrypted = true
ssl_mode = "strict"          # "strict", "allow_self_signed", "imported_ca"
created_at = "2026-07-01T12:00:00Z"

5. V1 Feature Matrix
Feature	Local (libgit2)	Remote (API)	Priority
Instance setup	—	GET /user, GET /version	P0
List projects	—	GET /projects?owned=true	P0
Clone repository	libgit2.clone()	—	P0
View changes/status	libgit2.status()	—	P0
Stage/unstage	libgit2.stage()	—	P0
Commit	libgit2.commit()	—	P0
Diff view	libgit2.diff()	—	P0
Push/Pull/Fetch	libgit2.push()	—	P0
Branch create/switch	libgit2.branch()	—	P0
Create MR	—	POST /merge_requests	P0
Open in GitLab	—	(xdg-open)	P0
Pipeline status	—	GET /pipelines	P1
Branch comparison	libgit2.compare	GET /branches (verify remote)	P1
6. Error Handling Strategy
Scenario	User-Facing Response	Internal Action
Invalid PAT	"Authentication failed. Check your token."	Clear token, prompt re-entry
Self-signed cert	"Certificate not trusted. Import CA or allow."	Offer trust override
Network unreachable	"Cannot reach instance. Working offline."	Switch to cached mode
API rate limited	"Rate limited. Retrying in N seconds."	Exponential backoff
Git push rejected	"Push rejected. Pull first?"	Offer pull/merge dialog
MR creation fails	"Failed to create MR: {error}"	Preserve form data, allow retry
SQLite corruption	"Cache corrupted. Rebuilding."	Delete + recreate cache.db
7. Known Constraints (V1)

    Single-user focus. No multi-account within a single instance.
    PAT authentication only. No OAuth, SSO, or LDAP pass-through.
    No in-app code editing. Diff view is read-only. External editor launches via xdg-open.
    No conflict resolution UI. Conflicts are detected and the user is directed to resolve externally.
    No admin/runner management. Focused on developer workflow only.
    English-only UI. Localization deferred to post-V1.
    No repository search. Project list is browsable but not searchable in V1 (may change if SQLite caching makes it trivial).

