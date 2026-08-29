# ADR-001: Self-Hosted Forges Only Policy

**Status:** Accepted (supersedes original GitLab-only wording)  
**Date:** 2026-07-01  
**Updated:** 2026-08-30 (multi-forge: GitLab, Gitea, Forgejo, OneDev)

## Context

LabDesk began as a Linux desktop client for self-hosted GitLab. Users also
run Gitea, Forgejo, and OneDev on their own infrastructure and want the
same local-git + forge workflow without depending on public SaaS
products that already have first-party clients.

## Decision

LabDesk supports **self-hosted** instances of:

- **GitLab**
- **Gitea**
- **Forgejo**
- **OneDev**

Each forge has a **dedicated Rust API backend** (tightly coupled to that
product’s REST API) with its own regression tests. The PySide6 UI and
local git layer are shared and consume forge-neutral DTOs. The active
host’s `forge` field in config selects the backend.

Known **public SaaS** hosts — including but not limited to
`gitlab.com`, `github.com`, `gitea.com`, `codeberg.org`, and
`code.onedev.io` — are **rejected** at instance setup (`LD-CFG-004`).

- All API endpoints are built from the user-provided base URL.
- Authentication remains API PAT (or forge-equivalent access token) in
  the system keyring plus git credential helper / SSH (ADR-008).

## Consequences

- **Positive:** Clear product boundary (self-hosted only); forge-specific
  quirks stay isolated; UI stays one codebase.
- **Negative:** Each new forge is ongoing maintenance; feature parity
  (especially CI “play job”) may lag per forge.
- **Migration:** Existing configs without `forge` default to `gitlab`.
