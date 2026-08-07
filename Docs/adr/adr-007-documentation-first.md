# ADR-007: Documentation-First Development

**Status:** Accepted  
**Date:** 2026-07-01  
**Updated:** 2026-08-07 (doc layout: ADR files, user guide, dev guide)

## Context

The project is designed to outlast its original author. Undocumented
decisions become unmaintainable technical debt. Writing documentation
before code ensures architectural flaws are caught when they're cheap
to fix — in a text file — rather than expensive — in a refactor.

## Decision

All architectural decisions, data models, API contracts, user journeys,
security policies, and build configurations will be documented **before**
implementation begins.

- An `AGENTS.md` file will guide AI-assisted contributions.
- ADRs live as **dedicated files** under `Docs/adr/`; 
  `Architecture-Decision-Records.md` is an **index only**.
- End-user material goes in a **user guide** (suitable to embed in the
  UI later without dragging in developer detail).
- Contributor / maintainer material goes in a **dev guide** (and
  focused reference docs such as security, API contract, data model as
  needed).
- Existing `src/` tree is **placeholder scaffolding** until the
  documentation set for the relevant area is in place.
- A root `CHANGELOG.md` (Keep a Changelog style) records notable docs
  and code changes under `[Unreleased]` until the first tagged release,
  so there is a trace when something goes wrong.

## Consequences

- **Slower Start:** Initial velocity is lower due to documentation
  overhead.
- **Higher Quality:** Fewer mid-development architectural pivots.
- **Onboarding:** New contributors (human or AI) can understand the
  project without tribal knowledge.
- **Maintenance:** Every decision has a recorded rationale, preventing
  "why was it done this way?" archaeology.
