# Flatpak Manifest Spec — LabDesk

**Status:** Living (beta)  
**App id:** `com.bigrangatech.LabDesk`  
**Related:** ADR-004, `dev-guide.md` §1.1 / §6, `user-guide.md` §2

## 1. Goals

- Ship LabDesk as a Flatpak from the self-hosted remote backed by
  [`Ranga/flatpaks`](http://git.bigrangatech.com/Ranga/flatpaks.git).
- Keep **build artifacts out of the `labdesk` git tree** (CI publishes
  into `flatpaks`).
- Document finish args so keyring, network, and clone directories work
  under the sandbox.

## 2. Files in `labdesk`

| Path | Role |
|------|------|
| `flatpak/com.bigrangatech.LabDesk.yml` | Manifest |
| `flatpak/icons/` | App icons (placeholder until artwork lands) |
| `.gitlab-ci.yml` | Build + push job into `Ranga/flatpaks` |

**Never commit:** `.flatpak-builder/`, `repo/`, `*.flatpak`, ostree
checkouts (see root `.gitignore`).

## 3. Runtime

- Prefer **Freedesktop** or **KDE** Platform/Sdk with Qt 6 suitable for
  PySide6 (pin exact runtime versions in the manifest; bump only after
  testing).
- Bundle / build: Rust `labdesk_core` (maturin/cargo), Python UI, PySide6,
  libgit2 (via crates or system in module). Beta builds use
  `build-args: [--share=network]` so crates.io/PyPI work; vendor
  crates for stricter/offline Flathub-style builds later.

## 4. Finish args (required for V1 behaviour)

| Finish arg / permission | Why |
|-------------------------|-----|
| `--share=network` | GitLab API + git HTTPS/SSH |
| `--socket=wayland` / `--socket=fallback-x11` | UI |
| `--device=dri` | Qt rendering |
| `--talk-name=org.freedesktop.secrets` | API PAT keyring |
| `--filesystem=xdg-documents` (and/or home) | Default clone dirs under Documents |
| `--filesystem=xdg-download:ro` | Optional |
| `--talk-name=org.freedesktop.Flatpak` | Optional in-app update checks later |

Exact YAML lives in `flatpak/com.bigrangatech.LabDesk.yml` and may grow;
keep this table in sync when permissions change.

## 5. CI publish path

1. Job on `labdesk` adds Flathub (user install), installs
   `org.freedesktop.Platform//24.08`, `Sdk//24.08`, and
   `Sdk.Extension.rust-stable//24.08`, then runs `flatpak-builder`
   (`--user --install-deps-from=flathub`).
2. Job authenticates to GitLab (CI job token / deploy token / deploy key
   with **write** to `Ranga/flatpaks` only).
3. Job **pushes** the Flatpak repository / ostree commit / `.flatpak`
   bundle into `Ranga/flatpaks` (LFS allowed there).
4. Users’ Flatpak remote points at the published remote from that repo
   (see `user-guide.md`). Updating `flatpaks` is what makes
   `flatpak update` / `check_for_updates` see new versions.

The Docker runner for `flatpak_build_publish` **must** allow bubblewrap
user namespaces. Without that, module builds fail with
`bwrap: No permissions to creating new namespace`.

Under `[runners.docker]` for the Labdesk runner:

```toml
privileged = true
security_opt = ["seccomp:unconfined", "apparmor:unconfined"]
# optional; CI also uses --disable-rofiles-fuse
# devices = ["/dev/fuse"]
```

On **Ubuntu 24.04+ / 26.04** hosts, AppArmor often blocks nested userns
even in privileged containers. Persistently enable:

```bash
# temporary
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
# permanent
echo 'kernel.apparmor_restrict_unprivileged_userns=0' | sudo tee \
  /etc/sysctl.d/99-labdesk-userns.conf
sudo sysctl --system
sudo systemctl restart gitlab-runner
```

openh264 `apply_extra` / bwrap warnings during `flatpak install` are
often non-fatal; the hard failure is when **module build** hits bwrap.

CI uses **`flatpak-builder --disable-rofiles-fuse`** so `/dev/fuse` is
not required.

CI variables (set in GitLab `labdesk` project settings, not in git):

| Variable | Purpose |
|----------|---------|
| `FLATPAKS_REPO_URL` | Default `http://git.bigrangatech.com/Ranga/flatpaks.git` |
| `FLATPAKS_DEPLOY_TOKEN` or SSH deploy key | Push access to `flatpaks` |

## 6. Local build (optional)

```bash
# from labdesk repo root — outputs stay untracked
flatpak remote-add --if-not-exists --user flathub \
  https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install -y --user \
  org.freedesktop.Platform//24.08 \
  org.freedesktop.Sdk//24.08 \
  org.freedesktop.Sdk.Extension.rust-stable//24.08
flatpak-builder --user --force-clean --install-deps-from=flathub \
  --repo=repo flatpak-build \
  flatpak/com.bigrangatech.LabDesk.yml
# do not git-add repo/ or flatpak-build/
```

Publishing to users still goes through CI → `Ranga/flatpaks`.

## Document history

Filled for beta packaging (self-hosted `flatpaks` host, no artifacts in
source).
