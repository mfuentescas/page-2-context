#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS_NAME="$(uname -s)"

if [[ "${OS_NAME}" == "Darwin" ]]; then
  exec "${ROOT_DIR}/run-page2context-mac.sh" "$@"
fi

"${ROOT_DIR}/install-page2context.sh" --ensure --quiet
exec "${ROOT_DIR}/.venv/bin/python3" "${ROOT_DIR}/page2context.py" "$@"
