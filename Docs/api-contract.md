# API Contract — LabDesk ↔ GitLab REST API v4

**Status:** Draft (docs stage)  
**Related:** ADR-001, ADR-006, ADR-008, Technical Specification §3 / §5 / §6,  
`security-credentials.md`

This document defines how LabDesk’s Rust `api_client` talks to a
**self-hosted** GitLab instance. It is not a full mirror of GitLab’s
upstream docs — only the endpoints, parameters, headers, and fields
LabDesk commits to for V1 (plus explicitly marked nice-to-haves).

Git clone / push / force-push are **not** REST API calls; they use
libgit2 + credential helper or SSH (ADR-006, ADR-008).

---

## 1. Base URL

Given instance `base_url` from config (no trailing slash required;
normalize by stripping a single trailing `/`):

```text
{api_root} = {base_url}/api/v4
```

Examples:

| `base_url` | `api_root` |
|------------|------------|
| `https://gitlab.example.com` | `https://gitlab.example.com/api/v4` |
| `https://git.lan:8443` | `https://git.lan:8443/api/v4` |

- V1 targets **API v4** only (`api_version = "v4"`).
- Do not hardcode `gitlab.com`. Reject SaaS hosts at setup (ADR-001)
  before any request is made.

---

## 2. Transport & TLS

- Scheme: **HTTPS** only for API calls in V1.
- TLS verification follows per-instance `ssl_mode`
  (`strict` | `allow_self_signed` | `imported_ca`) — see
  `security-credentials.md`.
- Timeouts and retry policy: implementation detail for the dev guide;
  rate-limit behaviour is specified in §7.

---

## 3. Authentication

Every API request includes:

```http
PRIVATE-TOKEN: <api-pat>
```

- PAT is loaded from the OS keyring (`keyring_account`).
- Do **not** use `Authorization: Bearer` in V1 (ADR-008).
- Do **not** put the PAT in query strings or logged headers.

Optional but recommended:

```http
User-Agent: LabDesk/<app-version>
Accept: application/json
```

---

## 4. Conventions

| Topic | LabDesk rule |
|-------|----------------|
| Format | JSON request/response bodies |
| IDs | Prefer numeric project `id` in path segments once known; `URL-encoded path_with_namespace` is acceptable where GitLab allows either |
| Pagination | `page` + `per_page` (default `per_page=100`, max per GitLab instance settings) |
| Pagination stop | Follow until empty page / no next page (`X-Next-Page` empty or missing) |
| Encoding | UTF-8; path segments URL-encoded |
| Empty optional fields | Omit from JSON rather than send `null` unless GitLab requires null |

---

## 5. V1 endpoints (P0)

### 5.1 Validate instance / PAT — `GET /user`

**When:** Add or re-validate instance.

```http
GET {api_root}/user
PRIVATE-TOKEN: <pat>
```

**Success:** `200 OK`

**Fields LabDesk uses:**

| Field | Type | Use |
|-------|------|-----|
| `id` | number | Cache / display |
| `username` | string | Display |
| `name` | string | Display |
| `web_url` | string | Optional “open profile” |

**Errors of interest:** `401` → invalid/missing PAT (clear keyring entry,
re-prompt).

---

### 5.2 Instance version — `GET /version`

**When:** After successful auth (or alongside); store for diagnostics /
compatibility notes.

```http
GET {api_root}/version
PRIVATE-TOKEN: <pat>
```

**Success:** `200 OK`

| Field | Type | Use |
|-------|------|-----|
| `version` | string | Show in about / logs |
| `revision` | string | Optional diagnostics |

> Note: On some GitLab versions this route may require sufficient token
> access. If `403`/`404`, record “version unknown” and continue; do not
> block instance setup solely on version fetch failure.

---

### 5.3 List projects — `GET /projects`

**When:** Project browser refresh. Must cover **owned**, **membership**,
and **group** projects the user can access.

**V1 approach:** one membership-scoped list (includes projects the user
owns and group projects they can access as a member):

```http
GET {api_root}/projects?membership=true&simple=false&order_by=last_activity_at&sort=desc&per_page=100&page=<n>
PRIVATE-TOKEN: <pat>
```

| Query | Value | Reason |
|-------|-------|--------|
| `membership` | `true` | User’s member projects (owned + group membership access) |
| `simple` | `false` | Need clone URLs and default branch |
| `order_by` | `last_activity_at` | Useful default ordering |
| `sort` | `desc` | Newest activity first |
| `per_page` / `page` | pagination | Full list |

**Audience note:** Confirmed sufficient for a small self-hosted instance
where LabDesk is used as one human with one API PAT (e.g. author setup:
admin account exists on the server, day-to-day work as user `Ranga`).
On larger multi-user instances with complex group sharing or projects
visible without classic membership, this query alone may be incomplete.
V1 still ships `membership=true`; if multi-user reports show gaps, add a
**documented** complementary fetch — do not silently change list
semantics without updating this contract and `CHANGELOG.md`.

**Success:** `200 OK` — JSON array.

**Fields LabDesk uses (per project):**

| Field | Type | Use |
|-------|------|-----|
| `id` | number | API paths, cache key |
| `name` | string | Display |
| `name_with_namespace` | string | Display |
| `path_with_namespace` | string | Display / alternate API id |
| `http_url_to_repo` | string | HTTPS clone |
| `ssh_url_to_repo` | string | SSH clone |
| `web_url` | string | Open in browser |
| `default_branch` | string \| null | Defaults for MR / branch UI |
| `last_activity_at` | string (ISO 8601) | Sort / staleness |
| `visibility` | string | Optional badge |

Paginate until exhausted; upsert into SQLite cache with a fetched-at
timestamp (staleness UI when offline).

---

### 5.4 Create merge request — `POST /projects/:id/merge_requests`

**When:** Journey D after push (or when branches already exist remotely).

```http
POST {api_root}/projects/{id}/merge_requests
PRIVATE-TOKEN: <pat>
Content-Type: application/json
```

**Body (V1):**

```json
{
  "source_branch": "feature/foo",
  "target_branch": "main",
  "title": "Short title",
  "description": "Optional description"
}
```

| Field | Required | Notes |
|-------|----------|--------|
| `source_branch` | yes | Local branch name pushed to remote |
| `target_branch` | yes | Usually `default_branch` unless user picks another |
| `title` | yes | Non-empty |
| `description` | no | May be empty string or omitted |

**Success:** `201 Created`

**Fields LabDesk uses:**

| Field | Type | Use |
|-------|------|-----|
| `iid` | number | Display |
| `web_url` | string | “Open in GitLab” |
| `title` | string | Confirm dialog / toast |
| `state` | string | Optional |

**Errors of interest:**

| Status | Handling |
|--------|----------|
| `400` / `409` / `422` | Show GitLab `message` / `error` to user; keep form data |
| `401` | Re-auth PAT |
| `404` | Project missing or no access |

---

## 6. Nice-to-have endpoints (not V1 blockers)

Documented so a later drop-in does not invent a second style.

### 6.1 Pipeline status — `GET /projects/:id/pipelines`

```http
GET {api_root}/projects/{id}/pipelines?ref=<branch>&per_page=1
PRIVATE-TOKEN: <pat>
```

Use latest pipeline `status`, `web_url`, `updated_at` for UI / cache.
Offline: show last cached value with timestamp.

### 6.2 Verify remote branch — `GET /projects/:id/repository/branches/:branch`

```http
GET {api_root}/projects/{id}/repository/branches/{branch}
PRIVATE-TOKEN: <pat>
```

**Success:** `200` — branch exists. **`404`** — missing on remote.
Used for branch comparison / preflight before MR if implemented.

---

## 7. Errors & rate limits

Map HTTP outcomes to Technical Specification §6 messages.

| HTTP | Meaning for LabDesk | Client action |
|------|---------------------|---------------|
| `401` | Bad/missing PAT | Clear keyring PAT; prompt re-entry |
| `403` | Forbidden | Show message; do not wipe PAT unless also auth-shaped |
| `404` | Missing resource or hidden by permissions | User-visible error |
| `429` | Rate limited | Exponential backoff; surface “Retrying in N seconds” |
| `5xx` | Server error | Retry with backoff (bounded); then fail visibly |
| Network error | Unreachable | Offline / cached mode |

**Response body:** Prefer GitLab’s `message` (string or object). If
object/array, flatten to a short user-visible string; keep raw body in
debug logs **after redacting** tokens.

**Rate limit headers** (when present): honour `Retry-After` if provided;
otherwise use exponential backoff starting at ~1s, cap documented in
dev guide.

---

## 8. What this contract does **not** cover

- Git smart-HTTP / SSH pack protocol (credential helper / SSH).
- GraphQL API.
- OAuth / session cookie login.
- Admin, runners, registry, packages, wikis, issues (unless a future
  ADR expands scope).
- `gitlab.com` or other SaaS hosts.

---

## 9. Compatibility note

Self-hosted GitLab versions differ. V1 assumes a reasonably current
GitLab with REST API v4 as above. Exact minimum GitLab version is
**not locked yet** — record the version from `GET /version` and revisit
this section when first integration testing against your instance(s).

---

## 10. Change control

Changes to paths, required fields, auth headers, or project-list query
semantics require:

1. Update this file.
2. Note in `CHANGELOG.md` under `[Unreleased]`.
3. ADR only if the change alters architecture (e.g. switching away from
   `PRIVATE-TOKEN`).
