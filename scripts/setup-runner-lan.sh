#!/usr/bin/env bash
# Configure system gitlab-runner to use LAN GitLab (bypass Cloudflare).
# Run: sudo bash scripts/setup-runner-lan.sh
set -euo pipefail

CFG="${1:-/etc/gitlab-runner/config.toml}"
LAN="${LAN_GITLAB:-http://192.168.0.214:8929}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run with sudo: sudo bash $0" >&2
  exit 1
fi

if [[ ! -f "${CFG}" ]]; then
  echo "Missing ${CFG}" >&2
  exit 1
fi

cp -a "${CFG}" "${CFG}.bak.$(date +%Y%m%d%H%M%S)"
python3 - "${CFG}" "${LAN}" <<'PY'
import re, sys
path, lan = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()

def patch_runner(block: str) -> str:
    # Only touch Labdesk / labdesk runners
    if not re.search(r'^\s*name\s*=\s*"(Labdesk|labdesk)"', block, re.M):
        return block
    if re.search(r'^\s*url\s*=', block, re.M):
        block = re.sub(r'^(\s*url\s*=\s*)".*"', rf'\1"{lan}"', block, count=1, flags=re.M)
    else:
        block = re.sub(r'(^\s*name\s*=\s*".*"\s*$)', rf'\1\n  url = "{lan}"', block, count=1, flags=re.M)
    if re.search(r'^\s*clone_url\s*=', block, re.M):
        block = re.sub(r'^(\s*clone_url\s*=\s*)".*"', rf'\1"{lan}"', block, count=1, flags=re.M)
    else:
        block = re.sub(r'(^\s*url\s*=\s*".*"\s*$)', rf'\1\n  clone_url = "{lan}"', block, count=1, flags=re.M)
    return block

parts = re.split(r'(?=^\[\[runners\]\])', text, flags=re.M)
out = parts[0]
for p in parts[1:]:
    out += patch_runner(p)
open(path, "w", encoding="utf-8").write(out)
print(f"Updated Labdesk runners in {path} → url/clone_url = {lan}")
PY

gitlab-runner verify || true
systemctl restart gitlab-runner
systemctl --no-pager --full status gitlab-runner | head -25
echo
echo "Done. In GitLab labdesk → Settings → CI/CD → Variables set:"
echo "  FLATPAKS_REPO_URL = ${LAN}/Ranga/flatpaks.git"
echo "If an old public URL variable exists, edit or delete it (it overrides the job default)."
