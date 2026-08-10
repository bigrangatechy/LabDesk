#!/usr/bin/env bash
# Create a GPG key for signing the LabDesk Flatpak ostree remote.
# Run once on a trusted machine; store the private key only in GitLab CI.
set -euo pipefail

NAME="${FLATPAK_GPG_NAME:-BigRanga Flatpak}"
EMAIL="${FLATPAK_GPG_EMAIL:-flatpak@bigrangatech.com}"

# Absolute GNUPGHOME — relative paths break gpg-agent on some hosts
# ("agent_genkey failed: No such file or directory").
if [[ $# -ge 1 && -n "${1}" ]]; then
  if [[ "${1}" = /* ]]; then
    OUT_DIR="${1}"
  else
    OUT_DIR="$(pwd)/${1}"
  fi
else
  OUT_DIR="$(pwd)/flatpak-gpg-out"
fi

mkdir -p "${OUT_DIR}"
export GNUPGHOME="${OUT_DIR}/gnupg"
rm -rf "${GNUPGHOME}"
mkdir -p "${GNUPGHOME}"
chmod 700 "${GNUPGHOME}"

# Avoid picking up a stale agent from ~/.gnupg.
gpgconf --kill all >/dev/null 2>&1 || true
gpgconf --launch gpg-agent

echo "Generating signing key for ${NAME} <${EMAIL}>…"
echo "GNUPGHOME=${GNUPGHOME}"

# Batch file is more reliable than --quick-generate-key with empty passphrase
# across pinentry / agent setups.
BATCH="$(mktemp)"
trap 'rm -f "${BATCH}"; gpgconf --kill all >/dev/null 2>&1 || true' EXIT
cat >"${BATCH}" <<EOF
%echo Generating LabDesk Flatpak signing key
Key-Type: EDDSA
Key-Curve: Ed25519
Key-Usage: sign
Name-Real: ${NAME}
Name-Email: ${EMAIL}
Expire-Date: 0
%no-protection
%commit
%echo done
EOF

if ! gpg --batch --generate-key "${BATCH}"; then
  echo "Batch keygen failed; trying quick-generate-key…" >&2
  gpg --batch --pinentry-mode loopback --passphrase '' \
    --quick-generate-key "${NAME} <${EMAIL}>" ed25519 sign never
fi

FPR="$(gpg --list-secret-keys --with-colons | awk -F: '/^fpr:/ {print $10; exit}')"
if [[ -z "${FPR}" ]]; then
  echo "ERROR: could not read fingerprint" >&2
  exit 1
fi

gpg --armor --export "${FPR}" > "${OUT_DIR}/bigrangatech-flatpak.gpg"
gpg --armor --export-secret-keys "${FPR}" > "${OUT_DIR}/bigrangatech-flatpak-secret.gpg"
# Single-line secret for GitLab Masked CI variables (no whitespace allowed).
base64 -w0 "${OUT_DIR}/bigrangatech-flatpak-secret.gpg" \
  > "${OUT_DIR}/bigrangatech-flatpak-secret.gpg.b64"
gpg --export "${FPR}" | base64 -w0 > "${OUT_DIR}/bigrangatech-flatpak.gpg.b64"
printf '%s\n' "${FPR}" > "${OUT_DIR}/key-id.txt"

cat <<EOF

Created key ${FPR}

Files in ${OUT_DIR}/:
  bigrangatech-flatpak.gpg              public (safe to publish)
  bigrangatech-flatpak-secret.gpg       PRIVATE armored — do not commit
  bigrangatech-flatpak-secret.gpg.b64   PRIVATE base64 — use this for Masked CI
  bigrangatech-flatpak.gpg.b64          public key base64 (for .flatpakrepo)
  key-id.txt                            fingerprint / key id
  gnupg/                                temporary homedir — delete after import

GitLab CI variables on project labdesk:
  Key:    FLATPAK_GPG_PRIVATE_KEY
  Value:  paste contents of bigrangatech-flatpak-secret.gpg.b64 (one line)
  Type:   Variable
  Masked: yes  (armored multiline secrets cannot be Masked — use base64)
  Optional Key FLATPAK_GPG_KEY_ID = ${FPR}

  Alternatively Type=File with the armored .gpg file, without Masked.

After the next signed publish, users install with:

  flatpak remote-add --if-not-exists bigrangatech-flatpaks \\
    https://git.bigrangatech.com/Ranga/flatpaks/-/raw/main/labdesk/labdesk.flatpakrepo

EOF
