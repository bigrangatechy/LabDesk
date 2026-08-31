# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).
User-visible Flatpak builds use a **build-date** version (`YYYY.MM.DD`);
changelog section labels may still use semantic milestones (e.g. `1.0.0`
for the V1 feature freeze).

**Timestamps:** each new bullet starts with local wall time
`HH:MM:SS  DD/MM/YYYY` (24-hour clock, day/month/year), then an em dash
and the note. Example:

`- **19:12:00  10/08/2026** — Short description of what landed.`

Use the machine’s local timezone when the change is recorded. Older
bullets without a stamp predate this convention.

## [Unreleased]

 ### Fixed

- **03:21:47  01/09/2026** — CI pytest: stop `PYTHONPATH=src` from
  treating the Rust crate as a namespace `labdesk_core`; UI tests stub
  the extension when maturin is absent; core-only tests skip cleanly.

 ### Added

- **03:09:06  01/09/2026** — Flatpak smoke-test deps: bundle `git`
  2.49 + `git-lfs` 3.8, `--socket=ssh-auth`, rebuild `.qm` at package
  time, put `/app/bin` on the launcher PATH.
- **02:58:07  01/09/2026** — Slice N submodule / LFS: repo **Git** tab
  (libgit2 submodule list/init/update/sync; `git-lfs` status + pull
  when available); codes `LD-GIT-050`–`054`, `LD-GIT-060`–`062`.
- **02:48:23  01/09/2026** — Slice M MR/PR note posting: forge-aware
  `create_merge_request_note` on GitLab / Gitea / Forgejo / OneDev;
  capability `supports_mr_note_create`; MR detail composer with
  **Post note** and **Quote selection**; `LD-API-MR-005` on failure.
  Threaded resolve / approve / inline comments deferred (M.2).
- **02:17:52  01/09/2026** — Slice L localization (Qt Linguist):
  `general.locale` + Settings **Language** (system / en / es / de / fr /
  pt_BR); `tr()` across UI chrome; `.ts`/`.qm` catalogs (280 strings);
  restart to fully refresh open windows. Rebuild via
  `scripts/build_translations.py`.
- **01:54:39  01/09/2026** — Slice K side-by-side diff: DiffView with
  Unified / Side by side toggle on Changes, History, and Compare;
  aligned panes from unified patches; synced scroll; no QScintilla.
- **01:49:37  01/09/2026** — Slice J admin + runners/agents: Admin view
  (instance runners + users), repo Runners tab; GitLab / Gitea / Forgejo
  pause·enable·delete; OneDev agents list + open (`LD-API-RUN-004` for
  pause/delete). Capability matrix + docs/contracts.
- **01:42:44  01/09/2026** — Slice J runner/agent + admin-user API helpers on
  Gitea, Forgejo, and OneDev (mirror GitLab); uniform optional
  `project_id`/`path_hint` on pause/delete; `LD-API-RUN-001` /
  `LD-API-RUN-004`.
- **00:59:16  01/09/2026** — Slice I from-scratch in-app editor:
  `QPlainTextEdit` + line numbers, find/replace, basic syntax highlight,
  save/undo, large/binary caps; **Edit in LabDesk** from Changes /
  Browse / conflicts; **Open external** retained. No QScintilla.
- **00:54:36  01/09/2026** — Slice H notifications + V1 completeness:
  notify chip wires pipeline failure + MR list changes; **File → Recent
  repositories**; touch `last_opened_at` on open; post-push **Set
  upstream?**; **Job log…** opens forge URL (stub). Shortcuts/docs
  already covered discard/delete/search/filter.
- **00:49:43  01/09/2026** — Slice G SSH host-switch + richer diffs: SSH
  `origin` retarget on host switch (incl. `ssh://`); Compare/History
  per-file lists with binary badge; path-scoped diffs;
  truncated/binary → **Open external…**. Docs + tests.
- **00:44:52  01/09/2026** — Slice F MR/PR merge + read-only notes: Merge…
  offers default or squash (`LD-API-MR-003`); notes reload + load-more
  (page>1 empty on Gitea/Forgejo/OneDev to avoid duplicates); merge
  disabled when not open. User-guide + tests.
- **00:41:31  01/09/2026** — Slice E MR/PR detail + create-from-Compare:
  Details gated on forge capability + online; double-click opens detail;
  create-from-Compare only when ahead of base (nested `origin/` branches
  preserved); draft checkbox where supported; post-create opens Details.
  User-guide / journey updated.
- **00:37:36  01/09/2026** — Locked Slice I editor approach: **from scratch**
  on PySide6/Qt (`QPlainTextEdit` / `QTextEdit` + highlighters). ADR-002 /
  ADR-003 updated; Riverbank QScintilla remains rejected (GPLv2+).
- **00:35:18  01/09/2026** — V2 roadmap extended: Slices I–N (in-app
  editor, admin/runners, fancy side-by-side diff, localization, MR review
  replies, submodule/LFS UIs) plus a post-feature **UI/UX polish** pass.
  OAuth/SSO and Windows/macOS remain deferred.
- **00:32:10  01/09/2026** — Slice D conflict resolve: Working/Ours/Theirs
  read-only tabs, Continue gated until clear, multi-step rebase conflicts
  stay in the dialog (`LD-GIT-020`). `repo_conflict_side_text`; merge
  ours/theirs → continue Rust fixtures; Python dialog smoke tests.
- **00:26:40  01/09/2026** — Slice C stash/rebase/safer pull: **Pop stash…**,
  stash with or without untracked, stash-before-pull then optional pop,
  diverged pull → merge/rebase (`LD-GIT-024`/`LD-GIT-020`/`LD-GIT-021`–
  `022`). User-guide “When the remote moved”; Rust stash/rebase tests.
- **00:21:32  01/09/2026** — Slice B large-repo UX: Changes is dirty-only by
  default; tracked files open in a virtualized Browse dialog (`QListView` +
  filter + load-more) using `browse_files_page_size` / `history_page_size`
  from `config.toml`. Regression tests updated.
- **00:13:27  01/09/2026** — Forge capability matrix (`forge_feature_matrix` /
  `active_forge_info` flags): play-job, MR detail/update/retarget/merge/notes,
  draft create. Unsupported actions return `LD-API-MR-004` or `LD-API-JOB-001`
  with forge-named detail. OneDev PR detail/update/merge/notes via `~api/pulls`.
  Dedicated capability tests per forge (Rust + Python).
- **23:49:20  31/08/2026** — V2 roadmap (`Docs/v2-roadmap.md`): sync banner,
  large-repo UX, stash/rebase, in-app conflict resolve, MR detail/merge/notes,
  SSH host-switch, notifications. ADR-006 + tech spec/error codes updated for
  structured conflict UI.
  **Forgejo**, and **OneDev** alongside GitLab (dedicated Rust API modules +
  shared UI). Connect dialog forge picker; `[[instances]].forge`; SaaS reject
  list extended (`gitea.com`, `codeberg.org`, `code.onedev.io`). ADR-001
  updated; API contract stubs per forge.

- **20:26:22  27/08/2026** — Projects **table/cards** layout option; clone/push
  progress as a translucent fill on the matching row/card (colour + alpha
  in Settings). Core exposes `get_git_op_progress`.
- **21:17:29  13/08/2026** — `ssl_mode = imported_ca`: trust PEMs in
  `trusted_certs/` for API (reqwest) and git HTTPS (`GIT_SSL_CAINFO`
  bundle); Connect dialog **Import CA…**; empty folder → `LD-NET-010`.
- **20:45:45  13/08/2026** — Projects list shows a default-branch pipeline
  status icon (filled on **Refresh projects**; cached offline). Schema v6
  stores `pipeline_status` / `pipeline_web_url` on project rows.
- **19:51:52  13/08/2026** — Repo window **Compare** tab (local tip
  compare + optional remote branch check) and **Merge requests** tab
  (opened MRs + SQLite cache). Uses existing Flatpak-bundled stack only
  (vendored libgit2 / PySide6; no host system libs).
- **19:03:02  13/08/2026** — Multi-host instances + multi-account users
  per host (switchers, unique keyring ids); Projects list filter;
  cache keyed by `account_id`.
- **17:55:36  13/08/2026** — Pipeline offline cache (latest per branch +
  jobs JSON); richer Pipelines job list; Help → User Guide… (bundled
  `user-guide.md`).

### Fixed

- **23:30:07  31/08/2026** — Staging an untracked directory row (shown as a
  single path after the large-repo status change) now expands like
  `git add <dir>/` instead of treating the folder as a deletion path.
  Regression: `test_stage_untracked_dir.py` + Rust `stage_paths_expands_*`.
- **23:30:07  31/08/2026** — After switching to a LAN/local host, clone /
  Open-in / MR / pipeline http(s) URLs follow the active Base URL (not
  the forge’s public hostname); project cache is rebased on host switch.
  Helpers `http_clone_url_for` / `rebase_http_url_to_base` exposed for
  tests (`test_active_host_urls.py`).
- **03:36:06  30/08/2026** — Large-repo Flatpak follow-up: do not recurse into
  untracked directories for status, cap Changes-list rows, and truncate file /
  diff / commit text fed to Qt viewers (avoids another `QArrayData` / OOM path
  when `build/` or huge lockfiles appear).
- **02:28:01  30/08/2026** — Opening a large local repo no longer SIGABRTs in Qt
  (`QArrayData::allocate`): tracked-file listing is capped, and repo status /
  history load off the UI thread after the window paints.
- **21:03:10  27/08/2026** — Intermittent `LD-AUTH-003` Secret Service crypto
  failures (`message decryption failed`): serialize keyring access, retry
  transient errors with a fresh session, and cache the PAT in-process after
  a successful read.
- **20:55:34  27/08/2026** — Save no longer forces Projects layout back to
  table: form values are snapshotted before `set_ui_shell` re-enters
  Settings and reloads from disk.
- **20:53:08  27/08/2026** — Projects **Cards** layout sticks: Settings applies
  the choice immediately (not only via Save/Done), persists with `itemData`,
  and Projects switches via `QStackedWidget` instead of hide/show.

### Changed

- **04:00:43  30/08/2026** — Docs refresh for multi-forge + large-repo
  behaviour: user guide (Changes caps / truncated previews), technical
  spec / journeys / data-model / README / API contract index, and
  dev-guide test table (`test_forge_labels`, expanded big-repo coverage).

- **03:29:25  30/08/2026** — Forge-aware UI copy: merge/pull request dialogs,
  repo tabs/buttons, push→create prompt, compare remote check, offline
  banners, About, and host combo fallbacks follow the active forge (no more
  hard-coded “GitLab” / “merge request” where the host is Gitea/Forgejo/
  OneDev). User guide wording updated to match.

- **02:44:09  30/08/2026** — Switching **Host** (e.g. public domain ↔ LAN)
  retargets `origin` on local clones that still point at the previous host
  when the project path exists under the newly selected account; SSH and
  non-overlapping accounts are left alone. Regression tests cover the
  tracked-file cap and host-switch remotes.
- **21:04:31  13/08/2026** — Packaging polish: richer AppStream/desktop
  metadata, `StartupWMClass` aligned with Flatpak desktop id, LabDesk
  logo SVGs for app icon + About wordmark, About shows Flatpak vs
  unpackaged and build-date version via `APP_VERSION`.
- **18:24:51  13/08/2026** — User guide: end-user only (Discover/app-store
  updates; drop CI / unsigned / unpackaged notes into `dev-guide`).
- **18:20:52  13/08/2026** — User guide install: signed `.flatpakrepo`
  only (§2.1); drop unsigned `--no-gpg-verify` path and default
  `remote-delete` for new users.

### Fixed

- **20:38:11  13/08/2026** — Theme switch: call `QWidget.update` explicitly when
  re-polishing widgets so PySide does not bind `QListView.update(QModelIndex)`
  (CI `TypeError` on dark/light theme tests).
- **20:31:32  13/08/2026** — Dark theme: fill out Fusion palette roles used by
  stylesheets (`Mid` / `Light` / disabled text, etc.) and re-polish existing
  widgets so secondary labels and borders update when switching theme.
- **20:25:44  13/08/2026** — Sidebar shell: stop parenting the unused
  classic column (and nav leftovers) to `QMainWindow`, which sat over the
  central widget and ate all clicks (filter, project rows, Projects/Settings
  nav). Unused hosts are parked hidden under the body instead.
- **20:20:09  13/08/2026** — Startup / Settings Flatpak update check no
  longer runs `flatpak update --appstream` on the UI thread (could block
  for minutes and make Projects look hung). Unpackaged/dev runs skip the
  host `flatpak` CLI entirely.
- **20:12:08  13/08/2026** — Projects list: use a `QTableView` model with
  debounced filter and background cache load (avoid per-row
  `QTableWidgetItem` fills that stall large membership lists).
- **14:35:42  13/08/2026** — Pipelines: treat GitLab jobs with
  `status: manual` as playable (not only `when: manual`), so rules-based
  manual jobs like Flatpak publish can be started from LabDesk.
- **14:27:37  13/08/2026** — CI pytest: `format_error` must not treat the
  empty `src/labdesk_core` namespace (PYTHONPATH=src) as the PyO3 module;
  parse `[LD-…]` in pure Python when the extension is missing.
- **14:07:05  13/08/2026** — Async jobs: do not parent `QThread` to the
  owner widget (Qt aborts if the window is closed mid-job); quit the
  thread on `destroyed`. Added pytest suite for this and repo reopen.
  Strengthened assertions so restored bugs fail (thread parent, UI-thread
  callback affinity, dead-wrapper reopen, `validate_base_url`).
- **13:55:49  13/08/2026** — Repo windows: detect closed wrappers with
  `shiboken6.isValid` (not `repo_path`, which survives C++ delete) and
  only reuse still-visible windows so reopen after close works.
- **13:51:46  13/08/2026** — Background jobs: marshal results through a
  UI-thread `QObject` bridge. Bare Python callables on worker signals
  could run off-thread and SIGSEGV in `QLabel`/`libQt6Gui` (Python 3.14
  crash notification after connect/refresh).
- **22:35:22  12/08/2026** — Flatpak CI: drop unsupported
  `flatpak-builder --env=…`; sed-inject `LABDESK_VERSION` into the
  manifest `build-options.env` instead.
- **22:25:10  12/08/2026** — Flatpak CI: replace column-0 Python heredoc in
  `.gitlab-ci.yml` with indented `sed` so GitLab can parse the YAML
  (metainfo release injection still works).

### Added

- **14:07:05  13/08/2026** — Pytest suite (`./scripts/run-tests.sh`,
  `tests/python/`): async UI-thread bridge, repo reopen after close,
  LAN/SaaS URL validation, version/helpers, packaging smoke; CI job
  `python_pytest`.
- **15:52:29  12/08/2026** — Post-V1: LAN `http://` for loopback/RFC1918
  GitLab URLs; build-date versioning (`YYYY.MM.DD`); background Qt workers
  for clone/refresh/fetch/push/API; pipeline status + play manual jobs.

## [1.0.0] - 2026-08-12

V1 complete — connect → projects → local git → MR → Flatpak. Feature set
frozen; further work is post-V1 (LAN HTTP, versioning, threads, pipelines).

### Added

- **15:35:14  12/08/2026** — Proper repo window handling: independent
  top-level windows (no transient parent, so the taskbar can switch to
  them), reuse/focus if the same repo is already open, prune on close,
  Window menu, close repo windows with the main window.

- **14:32:04  11/08/2026** — Store API PATs via FreeDesktop **Secret
  Service** (`keyring` async-secret-service) instead of linux-native
  keyutils, and grant Flatpak `--socket=session-bus` so Flatpak can
  save tokens (`LD-AUTH-002`). Git credential helper remains for git
  HTTPS only (ADR-008) — not a substitute for the API PAT.
- **14:11:33  11/08/2026** — Wire official PNG app icons
  (`com.bigrangatech.LabDesk-{64,128,256,512}x….png` in UI assets) into
  branding, Flatpak hicolor install, and start-menu entry.
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
