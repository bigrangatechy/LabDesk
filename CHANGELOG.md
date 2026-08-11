# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project will use [Semantic Versioning](https://semver.org/)
once releases begin. Until the first tagged release, entries accumulate
under **[Unreleased]**.

**Timestamps:** each new bullet starts with local wall time
`HH:MM:SS  DD/MM/YYYY` (24-hour clock, day/month/year), then an em dash
and the note. Example:

`- **19:12:00  10/08/2026** — Short description of what landed.`

Use the machine’s local timezone when the change is recorded. Older
bullets without a stamp predate this convention.

## [Unreleased]

### Added

- **13:59:35  11/08/2026** — Flatpak start-menu `.desktop` + AppStream
  metainfo; Anvil icon asset for menu / window / tray; StatusNotifier
  talk-name. Drop final logo over
  `src/labdesk_ui/assets/com.bigrangatech.LabDesk.svg` (optional PNGs
  in `flatpak/icons/`).

- **13:43:35  11/08/2026** — Trim API PAT / base URL on connect (password
  paste often includes a trailing newline that breaks auth or headers).
- **13:27:15  11/08/2026** — Flatpak CI: stop uploading `repo/` as job
  artifacts (258 MB+ causes coordinator **413**); ostree already lives
  in `Ranga/flatpaks` after publish.
- **13:04:04  11/08/2026** — Default `FLATPAKS_REPO_URL` to LAN GitLab
  (`http://192.168.0.214:8929/...`); warn in job log when publish host
  is still Cloudflare; add `scripts/setup-runner-lan.sh` for system
  runner `url`/`clone_url`.
- **12:43:08  11/08/2026** — Flatpak publish: keep LAN `http://192.168.x`
  `FLATPAKS_REPO_URL` as HTTP (do not force HTTPS); document Cloudflare
  Tunnel + runner `clone_url` LAN bypass for 413 / clone failures.
- **12:01:24  11/08/2026** — Flatpak publish **413** docs: Cloudflare
  Free/Pro ~100 MB body limit is the usual cause when orange-clouding
  GitLab; prefer grey-cloud / direct host / SSH for ostree pushes.
- **11:59:59  11/08/2026** — Flatpak publish: detect HTTP **413** (ostree
  too large for GitLab/nginx) with host-side `client_max_body_size` /
  push-size guidance; do not treat it as a deploy-token failure.
- **01:48:36  11/08/2026** — Flatpak GPG CI var: accept single-line
  **base64** secrets so GitLab **Masked** works (armored keys have
  newlines and are rejected).
- **01:36:50  11/08/2026** — Flatpak remote GPG signing in CI
  (`FLATPAK_GPG_PRIVATE_KEY`), `scripts/flatpak-gpg-create.sh`, and
  install docs for signed `.flatpakrepo` vs temporary `--user
  --no-gpg-verify` (fixes untrusted non-gpg remote installs).
- **01:26:16  11/08/2026** — Replace default GitLab README with a proper
  LabDesk project README (features, Flatpak, develop, docs map).
- **01:22:30  11/08/2026** — Local merge (clean only; `LD-GIT-020` on
  conflict), Fetch + ahead/behind in repo window, Flatpak bundles
  PySide6, in-app Flatpak update check (`LD-SYS-021` / Settings),
  first-run connect prompt, and Create MR offer after push.
- **00:45:08  11/08/2026** — Flatpak CI: push to credentialed URL directly;
  clearer failure hints when token can clone but not write.
- **00:34:36  11/08/2026** — Flatpak CI publish: force **https** for
  `flatpaks` remote (http redirects strip Basic auth); optional
  `FLATPAKS_DEPLOY_USER` for deploy-token usernames.
- **00:24:16  11/08/2026** — Flatpak CI publish: use `cp -a` instead of
  `rsync` (image has no rsync).
- **00:14:19  11/08/2026** — Flatpak: `maturin --skip-auditwheel` and
  `git2` `vendored-openssl` so the wheel does not need to bundle
  `libssl`/`libcrypto` (fixes maturin repair failure).
- **23:53:36  10/08/2026** — Flatpak module `labdesk-core`:
  `build-args: --share=network` so crates.io / PyPI resolve inside
  the build sandbox (fixes DNS failures during `cargo` / `pip`).
- **23:41:51  10/08/2026** — Flatpak CI: fail-fast userns check + docs for
  `privileged` / `security_opt` / Ubuntu AppArmor (module build bwrap).
- **23:28:19  10/08/2026** — Flatpak CI: `flatpak-builder
  --disable-rofiles-fuse` so Docker jobs do not need `/dev/fuse`
  (fixes `Failure spawning rofiles-fuse`).
- **22:44:29  10/08/2026** — V1 journey gaps: Branches tab
  (list/create/switch); Create merge request dialog + API; Open in
  editor (`LD-SYS-010`); offline banner disables refresh/push/MR;
  45s startup hang watchdog → known-good revert + `LD-CFG-010`/`011`.
  Flatpak CI docs: Docker runner needs `privileged` + `/dev/fuse`.
- **22:19:34  10/08/2026** — Flatpak CI: install Freedesktop Platform /
  Sdk / rust-stable 24.08 from Flathub before `flatpak-builder`
  (fixes `org.freedesktop.Platform/x86_64/24.08 not installed`).
- **21:35:31  10/08/2026** — Harden UI shell switching: permanent
  nav/column/stack hosts (no deleteLater of parents that own shared
  widgets); recreate nav buttons on switch. Addresses SIGSEGV after
  classic ↔ sidebar (Python crash notification).
- **21:30:56  10/08/2026** — Fix shell switch crash: reparent nav
  buttons/stack before tearing down classic/sidebar layouts
  (`RuntimeError: Internal C++ object already deleted`).
- **20:29:05  10/08/2026** — Beta packaging prep: remotes policy (GitLab
  canonical, GitHub read-only mirror, CI publish to
  `Ranga/flatpaks`); Flatpak manifest skeleton; CI job to build/push;
  docs sweep for install/update; `ui_shell` classic/sidebar layouts;
  light main-window polish; `LD-SYS-021`.
- **19:36:41  10/08/2026** — Stage / unstage / commit in the repo
  **Changes** tab (message box, staged vs changes lists). Codes
  `LD-GIT-040`…`042` for identity, empty message, nothing staged.
- **19:26:11  10/08/2026** — Docs: existing clones on the same instance
  with username/password (credential helper), including `http://`
  remotes, are supported; adopt keeps remotes; PAT stays API-only.
- **19:24:17  10/08/2026** — Existing clones: auto-discover under the
  clone folder on **Open local**; **Add existing…** to register any
  folder; **File → Open repository…**; Clone adopts a repo already at
  the destination. New code `LD-GIT-032`.
- **19:21:57  10/08/2026** — Repo window **History** tab: commit list
  (subject, author, local time), metadata, and coloured patch vs parent
  (`repo_log` / `repo_commit_info` / `repo_commit_diff`).
- **19:18:25  10/08/2026** — Repo window: clean clones looked empty because
  only *changes* were listed. Now lists tracked files, shows file
  contents (read-only), auto-opens README when clean, HEAD summary,
  theme-aware diff colours; `find_local_repo` prefers an existing path.
  Settings **← Back to Projects** and **Done** so that view is not a
  dead end.
- **19:07:00  10/08/2026** — Settings UI narrowed to confirmed options
  (clone folder, theme); `check_for_updates` stays config-only until
  Flatpak update UX works. Docs/AGENTS: config.toml is the wide
  preference surface; Settings stays conservative.
- **19:04:00  10/08/2026** — Pluggable main UI: `ViewPlugin` registry +
  stacked host; built-in **Projects** and **Settings** views; **View** /
  **Settings** menus; `general.active_ui_view` remembers the last view.
- First coding slice: Rust `labdesk_core` (TOML config + unknown-key
  preserve, OS keyring PAT, `PRIVATE-TOKEN` `GET /user`/`version`,
  known-good config snapshot) and PySide6 connect/status shell with
  `LD-…` error display.
- Project list slice: paginated `GET /projects?membership=true`, SQLite
  `projects` cache with per-row `fetched_at`, UI table + refresh /
  open-in-browser.
- Clone destination preference: UI **Clone into** field + Browse/Save
  writes `general.default_clone_dir` (expands `~`). (Moved into
  Settings view; same config key.)
- Clone slice: libgit2 clone into `{clone_dir}/{path_with_namespace}`,
  HTTPS (credential helper + PAT fallback) or SSH (agent),
  `local_repos` cache rows, UI **Clone** / **Clone (SSH)**.
- Repo window: **Open local** / double-click opens clone (not Firefox);
  status list + colored diff; **Pull**, **Push**, confirmed **Force push**.
  **Open in browser** remains separate.
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
- `Docs/error-codes.md` — stable `LD-<CATEGORY>-<NNN>` catalog for UI,
  logs, and startup-hang recovery (`LD-CFG-010`).
- `AGENTS.md` — rules for AI-assisted contributions.
- `CONTRIBUTING.md` — human contributor expectations (GPLv2+,
  docs-first, changelog discipline).
- This `CHANGELOG.md` for a durable trace of project changes.

### Changed

- **19:12:30  10/08/2026** — Changelog bullets now carry local
  `HH:MM:SS  DD/MM/YYYY` stamps (see header).
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
- Config philosophy / hang recovery wording; `error-codes.md` wired into
  tech spec and API contract.
- Dev guide: minimal uv/maturin/PySide6 run instructions for the first
  slice.

### Security

- Documented policy: API PATs must use the OS keyring; no plaintext
  config fallback if the keyring is unavailable.
- Git HTTPS secrets go through the credential helper, not `config.toml`.
- API standardized on `PRIVATE-TOKEN` (not Bearer) for V1.
