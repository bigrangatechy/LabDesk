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
| List PRs | `GET /~api/pull-requests?query=…` |
| Create PR | `POST /~api/pull-requests` |
| Branch exists | `GET /~api/projects/{id}/branches/{branch}` |
| Latest build | `GET /~api/builds?query=…` |
| Build detail | `GET /~api/builds/{id}` |

Play manual job: **not supported** yet in LabDesk.

Exact query language and JSON field names vary by OneDev version; the
backend maps defensively into shared forge DTOs.
