# API Contract — Gitea

**Status:** Post-V1  
**Related:** ADR-001, `api-contract.md` (GitLab), forge backends in `src/labdesk_core/src/gitea/`

Self-hosted Gitea via REST **`/api/v1`**. Auth: `Authorization: token <PAT>`.

| LabDesk operation | Method / path |
|-------------------|---------------|
| Current user | `GET /user` |
| Version | `GET /version` |
| List repos | `GET /user/repos` |
| List PRs | `GET /repos/{owner}/{repo}/pulls` |
| Create PR | `POST /repos/{owner}/{repo}/pulls` |
| Branch exists | `GET /repos/{owner}/{repo}/branches/{branch}` |
| Actions runs | `GET /repos/{owner}/{repo}/actions/runs` |
| Run jobs | `GET /repos/{owner}/{repo}/actions/runs/{id}/jobs` |

Play manual job: **not supported** in LabDesk for Gitea.
