#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${ROOT_DIR}/install-page2context-mac.sh" --ensure --quiet
exec "${ROOT_DIR}/.venv/bin/python3" "${ROOT_DIR}/page2context.py" "$@"
