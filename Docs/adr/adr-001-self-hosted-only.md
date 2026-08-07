# ADR-001: Self-Hosted GitLab Only Policy

**Status:** Accepted  
**Date:** 2026-07-01  
**Updated:** 2026-08-07 (auth details moved to ADR-008)

## Context

Existing Git GUI clients with forge integration (e.g., GitHub Desktop) are
tightly coupled to specific SaaS providers (`github.com`, `gitlab.com`).
While generic Git clients exist, they lack the workflow automation
(MR creation, pipeline status, branch tracking) that makes the desktop
experience valuable. There is currently no open-source, native Linux GUI
client specifically designed for self-hosted GitLab instances that offers
this level of integration.

## Decision

The application will support **only user-configured self-hosted GitLab
instances**.

- Known public SaaS hosts — including **`gitlab.com`** and
  **`github.com`** — are **not supported** and must be **rejected** at
  instance-setup time (not merely left without special handling).
- All API endpoints will be constructed dynamically based on the
  user-provided base URL.
- Instance type detection or automatic routing to public SaaS endpoints
  will not be implemented.
- **How** users authenticate (API PAT, git credential helper, SSH) is
  defined in **ADR-008**, not here.

## Consequences

- **Positive:** Drastically reduced complexity (no OAuth flows, no
  multi-provider abstraction layers). Focus remains entirely on the
  self-hosted use case. Stability is anchored to the version the
  administrator controls, not a remote SaaS release cycle.
- **Negative:** Users of GitLab.com SaaS cannot use this tool; they
  must use existing alternatives. The total addressable market is
  smaller, but highly targeted.
- **Maintenance:** Easier to test and verify compatibility since the
  target environment is always a user-controlled instance.
