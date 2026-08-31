# API Contract — Forgejo

**Status:** Post-V1  
**Related:** ADR-001, `api-contract-gitea.md`, `src/labdesk_core/src/forgejo/`

Self-hosted Forgejo via REST **`/api/v1`** (Gitea-compatible surface).
Auth: `Authorization: token <PAT>`.

LabDesk keeps a **separate** Forgejo backend module and tests even when
endpoints match Gitea, so Forgejo-specific drift does not break Gitea
regressions (and vice versa).

Endpoint map: same as [`api-contract-gitea.md`](api-contract-gitea.md)
(including Actions runners + admin users for Slice J).
Play manual job: **not supported**.
