#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_JSON="${ROOT_DIR}/spec/current-target.json"

read_target_field() {
  python3 - "$TARGET_JSON" "$1" <<'PY'
import json
import sys

target_path, dotted_path = sys.argv[1:3]
value = json.load(open(target_path))
for part in dotted_path.split("."):
    value = value[part]
print(value)
PY
}

sudo_cmd() {
  if command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    "$@"
  fi
}

ENGINE_VERSION="$(read_target_field docker.engine_version)"
CLI_VERSION="$(read_target_field docker.cli_version)"

if [[ "$ENGINE_VERSION" != "$CLI_VERSION" ]]; then
  echo "Docker engine and CLI versions must match for this installer." >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Cannot determine Linux distribution from /etc/os-release." >&2
  exit 1
fi

. /etc/os-release

if [[ "${ID:-}" != "ubuntu" ]]; then
  echo "Pinned Docker CI install currently supports Ubuntu only, got ${ID:-unknown}." >&2
  exit 1
fi

if [[ -z "${VERSION_ID:-}" || -z "${VERSION_CODENAME:-}" ]]; then
  echo "Cannot determine Ubuntu version and codename." >&2
  exit 1
fi

DEB_VERSION="5:${ENGINE_VERSION}-1~ubuntu.${VERSION_ID}~${VERSION_CODENAME}"

echo "Installing Docker Engine and CLI ${ENGINE_VERSION} (${DEB_VERSION})"

if [[ "${CI:-}" == "true" || -n "${TRAVIS:-}" ]]; then
  sudo_cmd apt-get remove -y docker docker-engine docker.io containerd runc || true
fi

sudo_cmd apt-get update
sudo_cmd apt-get install -y ca-certificates curl gnupg
sudo_cmd install -m 0755 -d /etc/apt/keyrings

if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg |
    sudo_cmd gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo_cmd chmod a+r /etc/apt/keyrings/docker.gpg
fi

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" |
  sudo_cmd tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo_cmd apt-get update

if ! apt-cache madison docker-ce | awk '{print $3}' | grep -Fx "$DEB_VERSION" >/dev/null; then
  echo "Docker package version ${DEB_VERSION} is not available from the Docker apt repository." >&2
  exit 1
fi

sudo_cmd apt-get install -y \
  "docker-ce=${DEB_VERSION}" \
  "docker-ce-cli=${DEB_VERSION}" \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

sudo_cmd systemctl restart docker || sudo_cmd service docker restart
docker version
