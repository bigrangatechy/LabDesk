# LabDesk

**Linux-only** desktop client for **self-hosted** GitLab, Gitea, Forgejo,
and OneDev (not public SaaS forges).

LabDesk combines local git (libgit2) with forge workflows: projects, clone,
branches, merge/pull requests, CI status, and push/pull — distributed as
**Flatpak** for releases. Stack: **PySide6** UI + **Rust** core via
PyO3/Maturin. License: **GPLv2+**.

> Self-hosted only. SaaS hosts such as `gitlab.com`, `gitea.com`,
> `codeberg.org`, and `code.onedev.io` are rejected at setup
> (see [ADR-001](Docs/adr/adr-001-self-hosted-only.md)).

## Features (current)

- Connect self-hosted forges (GitLab / Gitea / Forgejo / OneDev); API
  token in the system keyring; multi-host / multi-account selectors
- Browse projects (table or cards); clone HTTPS/SSH or open an existing
  local repo; **File → Open repository…** / Recent repositories
- Changes: stage / unstage / commit / discard; **Unified** or **Side by
  side** diffs; dirty-only list + Browse files…; **Edit in LabDesk** or
  open externally
- Branches, Compare, History; stash / rebase / conflict resolve
- Fetch / pull / push (force push only with confirmation); fetch-on-focus
- Merge / pull requests (detail, merge, notes); Pipelines / CI; Admin
  runners/agents + users; repo **Git** tab (submodules + LFS)
- Offline banner when the instance is unreachable
- Localization (system / en / es / de / fr / pt_BR)
- Settings: Appearance, Projects, Repositories, Updates, Paths
  (confirmed prefs only; full surface in `config.toml`)

## Install (Flatpak)

Releases are published into
[`Ranga/flatpaks`](http://git.bigrangatech.com/Ranga/flatpaks.git).
Exact remote URL and install steps: [Docs/user-guide.md](Docs/user-guide.md)
(signed `.flatpakrepo` preferred; temporary `--user --no-gpg-verify` until
GPG is configured in CI).

```bash
# After CI publishes labdesk.flatpakrepo (signed):
flatpak remote-add --if-not-exists bigrangatech-flatpaks \
  https://git.bigrangatech.com/Ranga/flatpaks/-/raw/main/labdesk/labdesk.flatpakrepo
flatpak install bigrangatech-flatpaks com.bigrangatech.LabDesk
flatpak run com.bigrangatech.LabDesk
```

App id: `com.bigrangatech.LabDesk`.

## Develop from source

**Requirements:** Linux, Python 3.10+, Rust stable, [uv](https://github.com/astral-sh/uv),
Secret Service / keyring, PySide6.

```bash
# from repo root
./scripts/run-labdesk.sh
```

That activates `.venv`, runs `maturin develop --uv`, and launches the UI.
Full environment notes: [Docs/dev-guide.md](Docs/dev-guide.md).

Config (unpackaged): `~/.config/labdesk/config.toml`  
Flatpak data: under `~/.var/app/com.bigrangatech.LabDesk/`

## Repository layout

```text
Docs/             living documentation (source of truth)
src/labdesk_ui/   PySide6 UI
src/labdesk_core/ Rust / PyO3 core
flatpak/          Flatpak manifest only (no build artifacts)
scripts/          helpers (e.g. run-labdesk.sh)
```

Development happens on **GitLab `labdesk`**. GitHub is a read-only mirror.
Flatpak **builds** go to `Ranga/flatpaks` via CI — never commit Flatpak
artifacts into this repo.

## Documentation

| Doc | Role |
|-----|------|
| [Docs/user-guide.md](Docs/user-guide.md) | Install, daily use |
| [Docs/dev-guide.md](Docs/dev-guide.md) | Build, layout, Flatpak CI |
| [Docs/Technical-Specification.md](Docs/Technical-Specification.md) | Product / tech contract |
| [Docs/adr/](Docs/adr/) | Architecture decisions |
| [Docs/error-codes.md](Docs/error-codes.md) | `LD-…` error catalog |
| [CHANGELOG.md](CHANGELOG.md) | What changed |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [AGENTS.md](AGENTS.md) | Guidance for AI-assisted work |

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and the relevant docs under `Docs/`
before changing behaviour. Prefer docs + changelog updates for
user-visible or architectural changes. Do not invent undecided product
decisions.

## License

GNU General Public License version 2 or later (**GPLv2+**). See
[ADR-003](Docs/adr/adr-003-gplv2-plus.md).
