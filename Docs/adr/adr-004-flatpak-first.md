# ADR-004: Flatpak-First Distribution Strategy

**Status:** Accepted  
**Date:** 2026-07-01  
**Updated:** 2026-08-10 (self-hosted remote `Ranga/flatpaks`; CI publish;
GitHub mirror stays LFS-free)

## Context

Linux distribution fragmentation creates significant challenges for
desktop applications: dependency hell, library mismatches, and update
delays across distros. The goal is a "build once, run anywhere"
experience that guarantees the app runs regardless of the host distro's
version. This aligns with the "outlast me" philosophy by ensuring the
binary remains functional even as host systems evolve.

LabDesk targets **Linux only** (no Windows or macOS). Releases are
hosted on the operator’s **self-hosted GitLab**, not only Flathub.

## Decision

The application will be distributed **exclusively as a Flatpak**.

- App id: **`com.bigrangatech.LabDesk`**.
- The **labdesk** source repository includes the Flatpak **manifest**
  (`flatpak/`) and CI that **builds** the app.
- Built Flatpak / ostree content is **published by CI** into the
  dedicated host repo
  [`Ranga/flatpaks`](http://git.bigrangatech.com/Ranga/flatpaks.git).
  That repo is **not** mirrored to GitHub and **may** use LFS.
- **Do not** commit Flatpak build artifacts into `labdesk` (keeps the
  GitHub read-only mirror of source clean; same commits cannot have
  different ignore rules per remote).
- The app bundles necessary runtime dependencies within the Flatpak
  sandbox or pins them to a specific SDK runtime (KDE / Freedesktop).
- No DEB, RPM, or AppImage targets will be provided in V1.
- Runtime version will be pinned with a documented upgrade path.
- In-app **`check_for_updates`** means checking the **LabDesk Flatpak
  remote** backed by `Ranga/flatpaks` — not a custom updater sideloading
  binaries, and not “any Flathub app”.

### Config / data paths

- **Flatpak install:** under
  `~/.var/app/com.bigrangatech.LabDesk/` (sandbox XDG).
- **Unpackaged / development runs:** standard **XDG** locations
  (`$XDG_CONFIG_HOME/labdesk`, `$XDG_DATA_HOME/labdesk`, etc.).

### Updates

1. User adds the Flatpak remote served from `Ranga/flatpaks` (exact
   `flatpak remote-add` URL documented in `user-guide.md` once the
   remote layout is published).
2. `flatpak update com.bigrangatech.LabDesk` (or in-app check when
   `check_for_updates` is UI-wired).
3. CI on `labdesk` is responsible for pushing new builds into
   `Ranga/flatpaks` so that remote stays current.

## Consequences

- **Stability:** The app runs in an isolated environment, immune to
  host system library updates breaking the app.
- **User Base:** Requires Flatpak. The primary remote is the operator’s
  GitLab-hosted `flatpaks` repo; Flathub is optional later, not required
  for beta.
- **Sandboxing:** Requires careful handling of filesystem permissions
  and portal usage for file dialogs and the secrets service.
- **Maintenance:** Runtime version upgrades must be tested before
  pushing to `Ranga/flatpaks`.
- **Mirrors:** Source visibility on GitHub does not imply GitHub LFS or
  Flatpak hosting on GitHub.
