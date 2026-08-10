# Contributing to LabDesk

Thanks for helping. LabDesk is meant to outlast any one maintainer:
documentation and licensing discipline matter as much as code.

## License

By contributing, you agree that your contributions are licensed under
the **GNU General Public License version 2 or later (GPLv2+)**, unless
a different written agreement exists with the maintainers.

See ADR-003 (`Docs/adr/adr-003-gplv2-plus.md`) and the project
`COPYING` file (to be added with the license text).

## Documentation first

Please read ADR-007. For new behaviour:

1. Update or add documentation (tech spec, ADR, security, journeys,
   user/dev guide as appropriate).
2. Note the change in `CHANGELOG.md` under `[Unreleased]`.
3. Implement only after the docs for that area are clear.

The `src/` tree is currently **placeholder** scaffolding. Do not assume
it reflects final APIs.

## Project scope (short)

- Linux desktop client for **self-hosted GitLab** only (not GitLab.com).
- Flatpak distribution for releases.
- PySide6 + Rust (PyO3); read-only diffs via `QTextEdit`.
- API: PAT with **`PRIVATE-TOKEN`**, stored in the **system keyring**.
- Git HTTPS: **credential helper** (username/password when the instance
  allows it); SSH also supported.
- Force push only with explicit confirmation.

Details: `README.md` (when rewritten), `Docs/Technical-Specification.md`,
and `Docs/adr/`.

## How to propose changes

1. Open an issue or draft MR on the LabDesk GitLab project describing
   the problem or goal.
2. For architecture changes, add or update an ADR under `Docs/adr/` and
   link it from `Docs/Architecture-Decision-Records.md`.
3. Keep MRs focused. Separate doc-only work from large code drops when
   practical.
4. Update `CHANGELOG.md` in the same change set.

## Changelog

`CHANGELOG.md` is the project’s history of what landed and when. Use it
so regressions and decisions are traceable.

Follow [Keep a Changelog](https://keepachangelog.com/) style:

- `[Unreleased]` for work not yet tagged
- Sections such as **Added**, **Changed**, **Fixed**, **Security**,
  **Removed**
- **Timestamp every new bullet** with local wall time in the form
  `HH:MM:SS  DD/MM/YYYY` (24-hour, day/month/year), then an em dash
  and the description. Example:
  `- **19:12:00  10/08/2026** — Short description.`
  Older undated bullets predate this rule; do not invent times for them.
## Code of collaboration

- Ask when requirements are ambiguous; do not silently invent product
  policy.
- Prefer GPLv2-friendly dependencies (see ADR-002 / ADR-003).
- Do not add Windows/macOS ports, SaaS GitLab.com support, plaintext
  token storage, or Bearer API auth without a new accepted ADR.

## Development environment

Concrete build / test steps will live in the **dev guide** and Flatpak
manifest docs once those stubs are filled. Until then, treat tooling
pins as undecided and document proposals before merging them.
