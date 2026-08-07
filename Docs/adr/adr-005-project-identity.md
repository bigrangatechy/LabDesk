# ADR-005: Project Identity — LabDesk

**Status:** Accepted  
**Date:** 2026-07-01  
**Updated:** 2026-08-07 (repository name: `labdesk`)

## Context

The project needs a distinctive identity that communicates its purpose
(self-hosted GitLab desktop client) while avoiding trademark
infringement on "GitLab" as a registered trademark. The name should be
discoverable by users searching for a GitLab desktop client.

## Decision

- **Display Name:** LabDesk
- **Icon:** Anvil (symbolizing craftsmanship, self-reliance, and the
  forge/workshop metaphor for self-hosted infrastructure)
- **Domain:** `labdesk.bigrangatech.com`
- **Flatpak App ID:** `com.bigrangatech.LabDesk`
- **Executable:** `labdesk`
- **Repository Name:** `labdesk`

The combination gives us searchability (LabDesk clearly relates to
GitLab + desktop) while the Anvil icon provides a unique visual
identity separate from GitLab's own branding.

## Consequences

- **Discoverability:** "LabDesk" is immediately understood by the
  target audience.
- **Trademarks:** "Lab" references GitLab conceptually but does not
  use the full trademarked name. The Anvil icon has no resemblance
  to GitLab's fox logo.
- **Expansion:** If the project ever supports other self-hosted forges
  (Gitea, Forgejo), the name "LabDesk" may feel restrictive. This is
  acceptable for V1; a rename can happen if the scope expands.
