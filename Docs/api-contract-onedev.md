# API Contract — OneDev

**Status:** Post-V1  
**Related:** ADR-001, `src/labdesk_core/src/onedev/`

Self-hosted OneDev via REST under **`/~api`**. Auth: HTTP Basic with the
**access token as username** and an empty password.

| LabDesk operation | Method / path |
|-------------------|---------------|
| Current user | `GET /~api/users/me` (fallback synthetic user if missing) |
| List projects | `GET /~api/projects?offset=&count=` |
| Clone URLs | `GET /~api/projects/{id}/clone-url` |
| List PRs | `GET /~api/pulls?query=…` |
| Create PR | `POST /~api/pulls` |
| Get PR | `GET /~api/pulls/{requestId}` (resolve number → id via query) |
| Set title | `POST /~api/pulls/{requestId}/title` |
| Set description | `POST /~api/pulls/{requestId}/description` |
| Merge PR | `POST /~api/pulls/{requestId}/merge` |
| PR comments | `GET /~api/pulls/{requestId}/comments` |
| Branch exists | `GET /~api/projects/{id}/branches/{branch}` |
| Latest build | `GET /~api/builds?query=…` |
| Build detail | `GET /~api/builds/{id}` |

**Not supported from LabDesk (returns `LD-API-MR-004` / `LD-API-JOB-001`):**
- Draft PR create
- Changing PR target branch
- Playing a manual CI job

Play manual job: **not supported** (capability gate → `LD-API-JOB-001`).

Exact query language and JSON field names vary by OneDev version; the
backend maps defensively into shared forge DTOs.
