#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="${ROOT_DIR}/page2context.py"
LAUNCHER_SH="${ROOT_DIR}/run-page2context.sh"
if [[ -x "${ROOT_DIR}/.venv/bin/python3" ]]; then
  PYTHON="${ROOT_DIR}/.venv/bin/python3"
else
  PYTHON="python3"
fi
TMP_DIR="${ROOT_DIR}/.tmp_test_page2context"
TEST_PORT=$((18080 + (RANDOM % 1000)))
TEST_URL="http://localhost:${TEST_PORT}"
PASS=0
FAIL=0
SERVER_PID=""

ok()   { echo "[PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }

run_cmd() {
  local __outvar="$1"
  local __ecvar="$2"
  shift 2
  set +e
  local _captured_out
  _captured_out=$("$@" 2>&1)
  local _captured_ec=$?
  set -e
  printf -v "$__outvar" '%s' "$_captured_out"
  printf -v "$__ecvar" '%s' "$_captured_ec"
}

json_expr() {
  local payload="$1"
  local expr="$2"
  python3 - "$payload" "$expr" <<'PY'
import json
import sys
obj=json.loads(sys.argv[1])
expr=sys.argv[2]
val=eval(expr, {"obj": obj})
if isinstance(val, (dict, list)):
    print(json.dumps(val))
else:
    print(val)
PY
}

start_server() {
  mkdir -p "${TMP_DIR}/www"
  cat > "${TMP_DIR}/www/index.html" <<'HTML'
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>p2cxt test</title></head>
<body><h1>page2context test page</h1></body>
</html>
HTML
  python3 -m http.server "${TEST_PORT}" --directory "${TMP_DIR}/www" > "${TMP_DIR}/server.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 20); do
    if curl -sf "${TEST_URL}" | grep -q "page2context test page"; then
      return
    fi
    sleep 0.25
  done
  echo "Could not start local test server" >&2
  [[ -f "${TMP_DIR}/server.log" ]] && cat "${TMP_DIR}/server.log" >&2
  exit 1
}

cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

mkdir -p "${TMP_DIR}"
start_server

# 1) Launcher smoke test with JSON output.
out=""; ec=""
run_cmd out ec "${LAUNCHER_SH}" --runtime-env-dir --json
if [[ "${ec}" == "0" ]] && [[ "$(json_expr "${out}" "obj.get('status')")" == "success" ]]; then
  ok "launcher runtime-env-dir"
else
  fail "launcher runtime-env-dir"
fi

# 2) Help mentions new flags and not legacy profile-dir flags.
out=""; ec=""
run_cmd out ec "${PYTHON}" "${SCRIPT}" --help
if [[ "${out}" == *"--capture <browser>"* && "${out}" == *"--open <browser>"* && "${out}" == *"--clean <browser>"* && "${out}" != *"--chrome-profile-dir"* ]]; then
  ok "help advertises new browser flags"
else
  fail "help flags mismatch"
fi

# 3) Mismatch between --capture and --open returns bad args.
out=""; ec=""
run_cmd out ec "${PYTHON}" "${SCRIPT}" --url "${TEST_URL}" --capture chrome --open firefox --json
if [[ "${ec}" == "2" ]] && [[ "$(json_expr "${out}" "obj.get('status')")" == "error" ]]; then
  ok "--capture/--open mismatch validation"
else
  fail "--capture/--open mismatch validation"
fi

# 4) --clean chrome JSON returns reclaimed fields and no history_file.
out=""; ec=""
run_cmd out ec "${PYTHON}" "${SCRIPT}" --clean chrome --json
if [[ "${ec}" == "0" ]] && \
   [[ "$(json_expr "${out}" "obj.get('status')")" == "success" ]] && \
   [[ "$(json_expr "${out}" "'history_file' in obj")" == "False" ]] && \
   [[ "$(json_expr "${out}" "'reclaimed_bytes' in obj")" == "True" ]]; then
  ok "clean-browser json schema"
else
  fail "clean-browser json schema"
fi

# 5) --clean chrome text prints reclaimed info and not history_file.
out=""; ec=""
run_cmd out ec "${PYTHON}" "${SCRIPT}" --clean chrome
if [[ "${ec}" == "0" ]] && [[ "${out}" == *"reclaimed_human:"* ]] && [[ "${out}" != *"history_file:"* ]]; then
  ok "clean-browser text output"
else
  fail "clean-browser text output"
fi

# 6) Local capture default browser (chrome profile) works on local server.
out=""; ec=""
run_cmd out ec "${PYTHON}" "${SCRIPT}" --url "${TEST_URL}" --json
if [[ "${ec}" == "0" ]] && [[ "$(json_expr "${out}" "obj.get('status')")" == "success" ]] && [[ "$(json_expr "${out}" "obj.get('browser_profile', {}).get('browser')")" == "chrome" ]]; then
  ok "default capture uses chrome profile"
else
  fail "default capture uses chrome profile"
fi

# 7) Explicit --capture chromium accepted and reported.
out=""; ec=""
run_cmd out ec "${PYTHON}" "${SCRIPT}" --url "${TEST_URL}" --capture chromium --json
if [[ "${ec}" == "0" ]] && [[ "$(json_expr "${out}" "obj.get('browser_profile', {}).get('browser')")" == "chromium" ]]; then
  ok "--capture-chromium capture"
else
  fail "--capture-chromium capture"
fi

# 8) --clean-temp output still includes history file (historical cleanup contract).
out=""; ec=""
run_cmd out ec "${PYTHON}" "${SCRIPT}" --clean-temp --json
if [[ "${ec}" == "0" ]] && [[ "$(json_expr "${out}" "'history_file' in obj")" == "True" ]]; then
  ok "clean-temp keeps history_file"
else
  fail "clean-temp keeps history_file"
fi

echo
echo "Passed: ${PASS}"
echo "Failed: ${FAIL}"

if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
