# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project will use [Semantic Versioning](https://semver.org/)
once releases begin. Until the first tagged release, entries accumulate
under **[Unreleased]**.

## [Unreleased]

### Added

- Dedicated ADR files under `Docs/adr/` with
  `Docs/Architecture-Decision-Records.md` as an index only.
- ADR-008: API PAT + `PRIVATE-TOKEN`; Git HTTPS via credential helper
  (username/password when enabled); SSH for git transport.
- `Docs/security-credentials.md` — keyring-backed API PATs, credential
  helper for git HTTPS, TLS modes, logging redaction, Flatpak secrets.
- `Docs/user-journey.md` — V1 user journeys (connect, clone, local
  work, push/force-push/MR, offline, updates; pipelines as nice-to-have).
- `Docs/api-contract.md` — GitLab REST v4 contract (`PRIVATE-TOKEN`,
  `/user`, `/version`, `/projects?membership=true`, create MR; pipelines
  / branch verify as nice-to-have). Notes that `membership=true` is
  confirmed for small instances (e.g. day-to-day as `Ranga`); multi-user
  gaps may need a later documented extension.
- `Docs/data-model.md` — config TOML, SQLite cache, local repos,
  secrets layout; multi-instance-ready schema with V1 single active
  instance. Instance `id` / `active_instance_id` accepted; per-row
  `fetched_at` and `last_push_at`; MR cache table deferred.
- `Docs/user-guide.md` / `Docs/dev-guide.md` — guide shells for
  end-user (UI-embeddable) and contributor docs.
- `AGENTS.md` — rules for AI-assisted contributions.
- `CONTRIBUTING.md` — human contributor expectations (GPLv2+,
  docs-first, changelog discipline).
- This `CHANGELOG.md` for a durable trace of project changes.

### Changed

- Technical specification rewritten for current decisions: `QTextEdit`
  diffs (no Riverbank QScintilla), system keyring for API PATs, git
  credential helper for HTTPS, active rejection of SaaS hosts,
  one-instance V1 UX with multi-instance-ready config schema, force push
  with confirmation, XDG paths for unpackaged runs, pipeline status
  marked nice-to-have.
- ADR-001…007 updated to match the above (identity repo name `labdesk`,
  Flatpak remote update check, documentation layout).
- ADR-007 now requires root `CHANGELOG.md` discipline.
- Technical specification §4.2: instance `id` and
  `active_instance_id` added to match data model.

### Security

- Documented policy: API PATs must use the OS keyring; no plaintext
  config fallback if the keyring is unavailable.
- Git HTTPS secrets go through the credential helper, not `config.toml`.
- API standardized on `PRIVATE-TOKEN` (not Bearer) for V1.
