# ADR-004: Flatpak-First Distribution Strategy

**Status:** Accepted  
**Date:** 2026-07-01  
**Updated:** 2026-08-07 (`check_for_updates` means Flatpak remote)

## Context

Linux distribution fragmentation creates significant challenges for
desktop applications: dependency hell, library mismatches, and update
delays across distros. The goal is a "build once, run anywhere"
experience that guarantees the app runs regardless of the host distro's
version. This aligns with the "outlast me" philosophy by ensuring the
binary remains functional even as host systems evolve.

LabDesk targets **Linux only** (no Windows or macOS).

## Decision

The application will be distributed **exclusively as a Flatpak**.

- The source repository will include a Flatpak manifest for building
  (see `flatpak/` and related docs).
- The app will bundle all necessary runtime dependencies (Qt libraries,
  libgit2, OpenSSL, etc.) within the Flatpak sandbox or pin them to a
  specific SDK runtime (KDE Platform).
- No DEB, RPM, or AppImage targets will be provided in V1.
- Runtime version will be pinned with documented upgrade path.
- In-app **`check_for_updates`** means checking the **Flatpak remote**
  for a newer LabDesk build — not a custom updater sideloading binaries.

### Config / data paths

- **Flatpak install:** under
  `~/.var/app/com.bigrangatech.LabDesk/` (sandbox XDG).
- **Unpackaged / development runs:** standard **XDG** locations
  (`$XDG_CONFIG_HOME/labdesk`, `$XDG_DATA_HOME/labdesk`, etc.).

## Consequences

- **Stability:** The app runs in an isolated environment, immune to
  host system library updates breaking the app.
- **User Base:** Requires users to have Flatpak/Flathub enabled. This
  filters for users comfortable with modern Linux package management,
  which aligns with the self-hosted target audience.
- **Sandboxing:** Requires careful handling of filesystem permissions
  and portal usage for file dialogs.
- **Maintenance:** Runtime version upgrades must be tested before
  pushing; document the known-compatible range.
