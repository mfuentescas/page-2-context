#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUIET="0"
for arg in "$@"; do
  if [[ "$arg" == "--quiet" ]]; then
    QUIET="1"
  fi
done
if [[ "$(uname -s)" != "Darwin" ]]; then
  exec "${ROOT_DIR}/install-page2context.sh" "$@"
fi

ARCH="$(uname -m)"
if [[ "${QUIET}" != "1" ]]; then
  if [[ "${ARCH}" == "arm64" ]]; then
    echo "[info] Detected macOS Apple Silicon (arm64)."
  elif [[ "${ARCH}" == "x86_64" ]]; then
    echo "[info] Detected macOS Intel (x86_64)."
  else
    echo "[info] Detected macOS architecture: ${ARCH}."
  fi
fi

exec "${ROOT_DIR}/install-page2context.sh" "$@"
