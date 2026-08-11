#!/usr/bin/env bash
# Configure the system "labdesk" runner to clone via LAN GitLab
# (bypass Cloudflare for git fetch), without changing job-polling url.
#
#   sudo bash scripts/setup-runner-lan.sh
#
# Only touches the runner named exactly "labdesk".
set -euo pipefail

CFG="${1:-/etc/gitlab-runner/config.toml}"
LAN="${LAN_GITLAB:-http://192.168.0.214:8929}"
# Keep job API on the public hostname (registration / tokens expect this).
API_URL="${GITLAB_API_URL:-https://git.bigrangatech.com}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run with sudo: sudo bash $0" >&2
  exit 1
fi

if [[ ! -f "${CFG}" ]]; then
  echo "Missing ${CFG}" >&2
  exit 1
fi

cp -a "${CFG}" "${CFG}.bak.$(date +%Y%m%d%H%M%S)"
python3 - "${CFG}" "${LAN}" "${API_URL}" <<'PY'
import re, sys
path, lan, api = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()

def patch_runner(block: str) -> str:
    # Exact name "labdesk" only (not "Labdesk" / "openten").
    if not re.search(r'^\s*name\s*=\s*"labdesk"\s*$', block, re.M):
        return block
    if re.search(r'^\s*url\s*=', block, re.M):
        block = re.sub(r'^(\s*url\s*=\s*)".*"', rf'\1"{api}"', block, count=1, flags=re.M)
    else:
        block = re.sub(
            r'(^\s*name\s*=\s*"labdesk"\s*$)',
            rf'\1\n  url = "{api}"',
            block,
            count=1,
            flags=re.M,
        )
    if re.search(r'^\s*clone_url\s*=', block, re.M):
        block = re.sub(
            r'^(\s*clone_url\s*=\s*)".*"', rf'\1"{lan}"', block, count=1, flags=re.M
        )
    else:
        block = re.sub(
            r'(^\s*url\s*=\s*".*"\s*$)',
            rf'\1\n  clone_url = "{lan}"',
            block,
            count=1,
            flags=re.M,
        )
    return block

parts = re.split(r'(?=^\[\[runners\]\])', text, flags=re.M)
out = parts[0]
for p in parts[1:]:
    out += patch_runner(p)
open(path, "w", encoding="utf-8").write(out)
print(f"Updated runner name=labdesk in {path}")
print(f"  url       = {api}   (job polling / API)")
print(f"  clone_url = {lan}   (git clone only)")
PY

echo
echo "Config (tokens redacted):"
sed -E 's/(token|password) *= *"[^"]*"/token = "REDACTED"/g' "${CFG}" | awk '
  /^\[\[runners\]\]/ {show=0}
  /name *= *"labdesk"/ {show=1}
  show {print}
  /^\[\[runners\]\]/ && seen++ { }
'

# Clear "unhealthy" disable by restarting after config fix.
gitlab-runner verify --name labdesk || true
systemctl restart gitlab-runner
sleep 2
systemctl --no-pager --full status gitlab-runner | head -20
echo
echo "Recent logs:"
journalctl -u gitlab-runner -n 15 --no-pager || true
echo
echo "Publish still uses FLATPAKS_REPO_URL in .gitlab-ci.yml:"
echo "  http://192.168.0.214:8929/Ranga/flatpaks.git"
echo "Push commit 7d657c9 (or newer) so CI uses that default."
