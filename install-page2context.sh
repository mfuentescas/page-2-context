#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ_FILE="${ROOT_DIR}/requirements.txt"
VENV_DIR="${ROOT_DIR}/.venv"
VENV_PY="${VENV_DIR}/bin/python3"
STAMP_FILE="${VENV_DIR}/.p2cxt_install_stamp"

MODE="install"
FORCE="0"
QUIET="0"
for arg in "$@"; do
  case "$arg" in
    --ensure) MODE="ensure" ;;
    --force) FORCE="1" ;;
    --quiet) QUIET="1" ;;
  esac
done

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  echo ""
}

hash_requirements() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${REQ_FILE}" | awk '{print $1}'
    return
  fi
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${REQ_FILE}" | awk '{print $1}'
    return
  fi
  local py
  py="$(find_python)"
  if [[ -n "${py}" ]]; then
    "${py}" -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path(r'${REQ_FILE}').read_bytes()).hexdigest())"
    return
  fi
  echo ""
}

load_stamp_value() {
  local key="$1"
  if [[ ! -f "${STAMP_FILE}" ]]; then
    return
  fi
  awk -F= -v k="${key}" '$1==k {print substr($0, index($0, "=")+1)}' "${STAMP_FILE}" | tail -n 1
}

PY_CMD="$(find_python)"
if [[ -z "${PY_CMD}" ]]; then
  echo "[error] Python was not found. Install Python 3.11+ and run this installer again." >&2
  exit 1
fi

mkdir -p "${VENV_DIR}"

if [[ ! -x "${VENV_PY}" ]]; then
  "${PY_CMD}" -m venv "${VENV_DIR}"
fi

REQ_HASH="$(hash_requirements)"
if [[ -z "${REQ_HASH}" ]]; then
  echo "[error] Could not compute requirements hash for ${REQ_FILE}." >&2
  exit 1
fi

PY_VER="$(${VENV_PY} -c 'import platform; print(platform.python_version())')"
PLATFORM_TAG="$(uname -s)-$(uname -m)"

NEEDS_INSTALL="1"
if [[ "${FORCE}" == "0" ]] && [[ -f "${STAMP_FILE}" ]]; then
  STAMP_REQ="$(load_stamp_value REQ_SHA256)"
  STAMP_PY="$(load_stamp_value PYTHON_VERSION)"
  STAMP_PLATFORM="$(load_stamp_value PLATFORM)"
  if [[ "${STAMP_REQ}" == "${REQ_HASH}" ]] && [[ "${STAMP_PY}" == "${PY_VER}" ]] && [[ "${STAMP_PLATFORM}" == "${PLATFORM_TAG}" ]]; then
    NEEDS_INSTALL="0"
  fi
fi

if [[ "${NEEDS_INSTALL}" == "0" ]]; then
  exit 0
fi

if [[ "${QUIET}" != "1" ]]; then
  echo "[info] Installing/updating Python dependencies in ${VENV_DIR}"
fi
"${VENV_PY}" -m pip install --upgrade pip
"${VENV_PY}" -m pip install -r "${REQ_FILE}"
"${VENV_PY}" -m playwright install chromium

cat > "${STAMP_FILE}" <<EOF
REQ_SHA256=${REQ_HASH}
PYTHON_VERSION=${PY_VER}
PLATFORM=${PLATFORM_TAG}
EOF

if [[ "${QUIET}" != "1" ]]; then
  echo "[info] page2context runtime is ready."
fi
