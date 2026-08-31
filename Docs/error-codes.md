# Error Codes — LabDesk

**Status:** Draft (living doc)  
**Related:** Technical Specification §6, `api-contract.md` §7,
`data-model.md` §3.0, `security-credentials.md`

Stable, greppable codes for UI, logs, and support. Prefer showing
**code + short message** to the user; put longer detail in logs (never
secrets).

## 1. Format

```text
LD-<CATEGORY>-<NNN>
```

| Part | Meaning |
|------|---------|
| `LD` | LabDesk |
| `CATEGORY` | 2–5 letter area (below) |
| `NNN` | Three-digit id within that category |

Examples: `LD-AUTH-001`, `LD-CFG-010`, `LD-API-429`.

### Categories

| Code | Area |
|------|------|
| `CFG` | Config file, known-good snapshot, startup recovery |
| `AUTH` | API PAT, keyring |
| `GIT` | libgit2 / credential helper / SSH |
| `API` | GitLab REST client |
| `NET` | Connectivity / TLS (when not API-specific) |
| `CACHE` | SQLite cache |
| `UI` | Dialog / validation that is purely presentation |
| `SYS` | Process, Flatpak, portals, unexpected internal faults |

### Rules

1. Every user-visible failure path should carry an `LD-…` code.
2. Codes are **stable once shipped** in a release; do not reuse numbers
   for a different meaning. Deprecate instead.
3. Logs: `code`, human `message`, optional `detail` / cause chain
   (redacted).
4. Rust/Python errors should map into this catalog at the boundary
   (core → UI), not invent parallel string-only errors for the same case.
5. New codes: add a row here + `CHANGELOG.md` under `[Unreleased]`.

---

## 2. Catalog (V1)

### CFG — configuration & startup

| Code | When | User message (default) | Action |
|------|------|------------------------|--------|
| `LD-CFG-001` | `config.toml` missing; creating defaults | (usually silent / info) | Write default config |
| `LD-CFG-002` | TOML parse failure | "Config file is invalid and could not be read." | Keep last known good if present; otherwise safe defaults; show error |
| `LD-CFG-003` | Required field missing / invalid type | "Config value invalid: {field}." | Reject apply for that field; preserve rest |
| `LD-CFG-004` | SaaS / unsupported host in `base_url` | "LabDesk supports self-hosted GitLab, Gitea, Forgejo, and OneDev only." | Do not save instance |
| `LD-CFG-010` | **Startup hang detected**; config reverted | "Startup hung; config reset to last known good. {detail}" | Restore snapshot; relaunch; show this code |
| `LD-CFG-011` | No known-good snapshot available after hang/corrupt | "Startup failed and no good config backup was found." | Safe defaults; guided setup |
| `LD-CFG-012` | Failed to write config (permissions, disk) | "Could not save settings." | Keep in-memory; retry guidance |

### AUTH — API PAT & keyring

| Code | When | User message (default) | Action |
|------|------|------------------------|--------|
| `LD-AUTH-001` | PAT rejected (`401` / invalid) | "Authentication failed. Check your token." | Clear keyring PAT; re-prompt |
| `LD-AUTH-002` | Keyring unavailable / locked | "Cannot access system keyring." | Block PAT save |
| `LD-AUTH-003` | Keyring read/write failed | "Could not store or read the access token." | Retry; unlock Secret Service; LabDesk serializes + retries transient crypto/session errors |
| `LD-AUTH-004` | PAT missing when API call needs it | "No access token configured." | Open instance setup |

### GIT — local git & transport

| Code | When | User message (default) | Action |
|------|------|------------------------|--------|
| `LD-GIT-001` | Generic git operation failure | "Git operation failed: {summary}" | Show detail in log |
| `LD-GIT-002` | HTTPS git auth failed | "Git authentication failed. Check credentials or SSH keys." | Credential helper / SSH guidance |
| `LD-GIT-003` | 2FA blocked password git auth | "Password git auth blocked. Use SSH or a PAT." | ADR-008 options |
| `LD-GIT-010` | Push rejected (non-fast-forward, etc.) | "Push rejected. Pull first?" | Offer pull; force push separate |
| `LD-GIT-011` | Force push failed | "Force push failed: {summary}" | Preserve branch; show remote message |
| `LD-GIT-020` | Merge/rebase conflict detected | "Conflicts detected. Resolve in LabDesk or externally." | Offer conflict UI; Abort available |
| `LD-GIT-021` | Rebase failed | "Rebase failed: {summary}" | Leave or abort rebase with guidance |
| `LD-GIT-022` | Stash failed | "Stash failed: {summary}" | Preserve working tree |
| `LD-GIT-023` | Continue merge/rebase failed | "Could not continue: {summary}" | Stay in conflict UI |
| `LD-GIT-024` | Pull non-fast-forward (diverged) | "Histories have diverged. Choose merge or rebase." | Offer merge/rebase |
| `LD-GIT-030` | Clone failed | "Clone failed: {summary}" | Keep dialog data |
| `LD-GIT-031` | Local repo path missing | "Repository folder is missing." | Mark local_repos row; offer remove/re-add |
| `LD-GIT-032` | Path is not a git repository | "Not a git repository." | Pick another folder / clone |
| `LD-GIT-040` | Missing `user.name` / `user.email` | "Git user.name / user.email not configured." | Configure git identity |
| `LD-GIT-041` | Empty commit message | "Commit message is required." | Focus message field |
| `LD-GIT-042` | Commit with nothing staged | "Nothing staged to commit." | Stage files first |

### API — GitLab REST

| Code | When | User message (default) | Action |
|------|------|------------------------|--------|
| `LD-API-001` | Unexpected API / JSON error | "GitLab API error: {summary}" | Log body (redacted) |
| `LD-API-401` | HTTP 401 | (use `LD-AUTH-001` at UI; log may cite both) | Clear PAT |
| `LD-API-403` | HTTP 403 | "Access denied by GitLab." | Do not wipe PAT by default |
| `LD-API-404` | HTTP 404 | "Not found or no access." | User-visible |
| `LD-API-422` | HTTP 422 (e.g. MR validation) | "Request rejected: {summary}" | Preserve form |
| `LD-API-429` | HTTP 429 | "Rate limited. Retrying in N seconds." | Backoff |
| `LD-API-5XX` | HTTP 5xx | "GitLab server error ({status})." | Bounded retry then fail |
| `LD-API-MR-001` | Create MR failed (mapped) | "Failed to create MR: {error}" | Preserve form |
| `LD-API-MR-002` | Update MR/PR metadata failed | "Failed to update MR." | Preserve form |
| `LD-API-MR-003` | Merge MR/PR via API failed | "Failed to merge MR." | Preserve UI; allow retry |
| `LD-API-MR-004` | MR/PR feature unsupported on this forge | "… is not supported on this forge." | Disable control; do not retry same action |
| `LD-API-JOB-001` | Play / pipeline job failed | "Failed to run CI job: {summary}" | Preserve UI; allow retry |
| `LD-API-RUN-001` | Pause / delete runner failed | "Failed to update/delete runner." | Preserve UI; allow retry |
| `LD-API-RUN-004` | Runner/agent action unsupported on forge | "Agent pause/delete is not supported via API from LabDesk; open in OneDev." | Open forge UI; do not retry |

Prefer mapping HTTP failures to `LD-API-<status>` when the status is the
main signal; use `LD-AUTH-001` for auth UX even if the wire code was 401.

### NET — connectivity & TLS

| Code | When | User message (default) | Action |
|------|------|------------------------|--------|
| `LD-NET-001` | Host unreachable / DNS / timeout | "Cannot reach instance. Working offline." | Cached mode |
| `LD-NET-010` | TLS certificate not trusted | "Certificate not trusted. Import CA or allow." | Offer ssl_mode paths |
| `LD-NET-011` | TLS other failure | "Secure connection failed." | Log detail |

### CACHE — SQLite

| Code | When | User message (default) | Action |
|------|------|------------------------|--------|
| `LD-CACHE-001` | Corruption / open failure | "Cache corrupted. Rebuilding." | Delete + recreate `cache.db` |
| `LD-CACHE-002` | Migration failure | "Cache upgrade failed. Rebuilding." | Rebuild; log |

### UI — presentation / validation

| Code | When | User message (default) | Action |
|------|------|------------------------|--------|
| `LD-UI-001` | Empty required field (generic) | "Please fill in required fields." | Focus field |
| `LD-UI-002` | Force-push confirmation required | (dialog; not always an “error”) | Proceed only on yes |

### SYS — process / environment

| Code | When | User message (default) | Action |
|------|------|------------------------|--------|
| `LD-SYS-001` | Unexpected internal error | "Something went wrong ({code})." | Log stack; offer report path later |
| `LD-SYS-010` | External open failed (`xdg-open` / portal) | "Could not open external application." | Show path/URL |
| `LD-SYS-020` | Flatpak / portal permission issue | "Permission denied by the desktop sandbox." | Doc hint |
| `LD-SYS-021` | Flatpak update check failed | "Could not check for Flatpak updates." | Fall back to `flatpak update`; see user-guide |

---

## 3. Structured error shape (core → UI)

Logical shape for the PyO3 / UI boundary (names illustrative):

| Field | Required | Notes |
|-------|----------|--------|
| `code` | yes | e.g. `LD-CFG-010` |
| `message` | yes | Short, user-safe |
| `detail` | no | Extra context; may be shown in “Details” |
| `cause` | no | Nested/machine cause; logs only if sensitive |
| `retryable` | no | Hint for UI (e.g. `LD-API-429`) |

Never put PAT, passwords, or raw `PRIVATE-TOKEN` values in any field.

---

## 4. Startup hang (`LD-CFG-010`)

Timeout: **45 seconds** from process start until the main window marks
ready (`labdesk_ui.startup`).

Must include in the post-relaunch UI:

1. Code `LD-CFG-010`
2. That config was **reset to last known good**
3. Best-effort **detail** (last subsystem / step if known)

If no snapshot existed → `LD-CFG-011`.

---

## 5. Change control

Adding or redefining a code: update this file and `CHANGELOG.md`.
Technical Specification §6 stays a scenario summary; **this file is
authoritative for code strings**.
