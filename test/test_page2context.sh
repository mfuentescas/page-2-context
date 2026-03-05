#!/usr/bin/env bash
# test_page2context.sh — Smoke tests for page2context.py
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT=(python3 "${ROOT_DIR}/page2context.py")
PASS=0
FAIL=0
SERVER_PID=""
TEST_PORT=$((18080 + (RANDOM % 1000)))
TEST_URL="http://localhost:${TEST_PORT}"
TMP_DIR="${ROOT_DIR}/.tmp_test_page2context"

ok()   { echo "[PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }
info() { echo "[INFO] $1"; }

json_field() {
  local json_payload="$1"
  local field="$2"
  python3 - "$json_payload" "$field" <<'PY'
import json
import sys

payload = sys.argv[1]
field = sys.argv[2]
try:
    data = json.loads(payload)
except Exception:
    sys.exit(2)

value = data.get(field)
if value is None:
    print("")
elif isinstance(value, (dict, list)):
    print(json.dumps(value))
else:
    print(value)
PY
}

json_len() {
  local json_payload="$1"
  local field="$2"
  python3 - "$json_payload" "$field" <<'PY'
import json
import sys

payload = sys.argv[1]
field = sys.argv[2]
try:
    data = json.loads(payload)
except Exception:
    sys.exit(2)

value = data.get(field, [])
print(len(value) if isinstance(value, list) else 0)
PY
}

json_all_abs() {
  local json_payload="$1"
  local field="$2"
  python3 - "$json_payload" "$field" <<'PY'
import json
import sys

payload = sys.argv[1]
field = sys.argv[2]
try:
    data = json.loads(payload)
except Exception:
    sys.exit(2)

value = data.get(field, [])
ok = isinstance(value, list) and all(isinstance(p, str) and p.startswith("/") for p in value)
print("True" if ok else "False")
PY
}

json_has_key() {
  local json_payload="$1"
  local field="$2"
  python3 - "$json_payload" "$field" <<'PY'
import json
import sys

payload = sys.argv[1]
field = sys.argv[2]
try:
    data = json.loads(payload)
except Exception:
    sys.exit(2)

print("True" if field in data else "False")
PY
}

json_nested_len() {
  local json_payload="$1"
  local parent="$2"
  local child="$3"
  python3 - "$json_payload" "$parent" "$child" <<'PY'
import json
import sys

payload = sys.argv[1]
parent = sys.argv[2]
child = sys.argv[3]
try:
    data = json.loads(payload)
except Exception:
    sys.exit(2)

node = data.get(parent, {})
value = node.get(child, []) if isinstance(node, dict) else []
print(len(value) if isinstance(value, list) else 0)
PY
}

json_resources_stats() {
  local json_payload="$1"
  python3 - "$json_payload" <<'PY'
import json
import os
import sys

payload = json.loads(sys.argv[1])
resources = payload.get("resources", {}) if isinstance(payload, dict) else {}
files = resources.get("files", []) if isinstance(resources, dict) else []
files = files if isinstance(files, list) else []

css = sum(1 for p in files if isinstance(p, str) and p.lower().endswith(".css"))
js = sum(1 for p in files if isinstance(p, str) and p.lower().endswith(".js"))
missing = sum(1 for p in files if not (isinstance(p, str) and os.path.isfile(p)))

print(f"{len(files)} {css} {js} {missing}")
PY
}

check_runtime_deps() {
  if ! python3 -c "import playwright" >/dev/null 2>&1; then
    echo "[ERROR] Missing Python dependency: playwright"
    echo "[ERROR] Run: make setup"
    exit 1
  fi

  if ! python3 -c "import PIL" >/dev/null 2>&1; then
    echo "[ERROR] Missing Python dependency: Pillow"
    echo "[ERROR] Run: make setup"
    exit 1
  fi

  if ! python3 - <<'PY' >/dev/null 2>&1
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    chromium_path = Path(p.chromium.executable_path)
    raise SystemExit(0 if chromium_path.exists() else 1)
PY
  then
    echo "[ERROR] Chromium browser is not installed for Playwright"
    echo "[ERROR] Run: python3 -m playwright install chromium"
    exit 1
  fi
}

assert_eq() {
  local label="$1"
  local got="$2"
  local expected="$3"
  if [[ "$got" == "$expected" ]]; then
    ok "$label"
  else
    fail "$label (expected: $expected, got: $got)"
  fi
}

run_and_capture() {
  local __outvar="$1"
  local __ecvar="$2"
  shift 2
  set +e
  local out
  out=$("$@" 2>&1)
  local ec=$?
  set -e
  printf -v "$__outvar" '%s' "$out"
  printf -v "$__ecvar" '%s' "$ec"
}

start_server() {
  mkdir -p "${TMP_DIR}/www"
  cat > "${TMP_DIR}/www/styles.css" <<'CSS'
body { font-family: Arial, sans-serif; }
h1 { color: #0b57d0; }
CSS

  cat > "${TMP_DIR}/www/app.js" <<'JS'
console.log("page2context smoke test");
JS

  cat > "${TMP_DIR}/www/index.html" <<'HTML'
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <title>test</title>
    <link rel="stylesheet" href="/styles.css">
    <script defer src="/app.js"></script>
  </head>
  <body>
    <h1>page2context test page</h1>
    <p>Local smoke-test page.</p>
  </body>
</html>
HTML

  python3 -m http.server "${TEST_PORT}" --directory "${TMP_DIR}/www" > "${TMP_DIR}/server.log" 2>&1 &
  SERVER_PID=$!

  for _ in $(seq 1 20); do
    if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
      echo "Local test server process exited unexpectedly" >&2
      [[ -f "${TMP_DIR}/server.log" ]] && cat "${TMP_DIR}/server.log" >&2
      exit 1
    fi

    if curl -sf "${TEST_URL}" | grep -q "page2context test page"; then
      return
    fi
    sleep 0.25
  done

  echo "Could not start local test server with expected fixture content" >&2
  [[ -f "${TMP_DIR}/server.log" ]] && cat "${TMP_DIR}/server.log" >&2
  exit 1
}

stop_server() {
  if [[ -n "${SERVER_PID}" ]]; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  rm -rf "${TMP_DIR}"
}

mkdir -p "${TMP_DIR}"
trap 'stop_server; cleanup' EXIT
check_runtime_deps
start_server

info "Test 1: no arguments prints syntax and exits 2"
run_and_capture OUT EC "${SCRIPT[@]}"
assert_eq "exit code is 2" "$EC" "2"
[[ "$OUT" == *"--url"* ]] && ok "help contains --url" || fail "help missing --url"
[[ "$OUT" == *"--json"* ]] && ok "help contains --json" || fail "help missing --json"

info "Test 2: JSON success returns absolute output list and prefixed files"
OUT_DIR="${TMP_DIR}/run_json"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR}" --json
assert_eq "json exit code is 0" "$EC" "0"
assert_eq "json status=success" "$(json_field "$OUT" "status")" "success"
assert_eq "json files has 3 files (no crop)" "$(json_len "$OUT" "files")" "3"
assert_eq "json files values are absolute" "$(json_all_abs "$OUT" "files")" "True"
assert_eq "json output has 3 files (no crop)" "$(json_len "$OUT" "output")" "3"
[[ -f "${OUT_DIR}/p2cxt_screenshot.png" ]] && ok "p2cxt_screenshot.png created" || fail "p2cxt_screenshot.png missing"
[[ -f "${OUT_DIR}/p2cxt_context.md" ]] && ok "p2cxt_context.md created" || fail "p2cxt_context.md missing"
[[ -f "${OUT_DIR}/p2cxt_html.html" ]] && ok "p2cxt_html.html created" || fail "p2cxt_html.html missing"
grep -q "p2cxt_html.html" "${OUT_DIR}/p2cxt_context.md" && ok "context references p2cxt_html.html" || fail "context missing p2cxt_html.html reference"

info "Test 3: text mode prints created files as absolute paths"
OUT_DIR_TEXT="${TMP_DIR}/run_text"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_TEXT}"
assert_eq "text exit code is 0" "$EC" "0"
LINE_COUNT="$(printf '%s\n' "$OUT" | sed '/^$/d' | wc -l | tr -d ' ')"
assert_eq "text output has 3 lines" "$LINE_COUNT" "3"
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  [[ "$line" == /* ]] && ok "line is absolute: $line" || fail "line is not absolute: $line"
  [[ -f "$line" ]] && ok "file exists: $line" || fail "file does not exist: $line"
done <<< "$OUT"

info "Test 4: crop creates prefixed tiles and reports them"
OUT_DIR_CROP="${TMP_DIR}/run_crop"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_CROP}" --crop "2x2:1,4" --json
assert_eq "crop exit code is 0" "$EC" "0"
assert_eq "crop status=success" "$(json_field "$OUT" "status")" "success"
assert_eq "crop files has 5 files" "$(json_len "$OUT" "files")" "5"
assert_eq "crop output has 5 files" "$(json_len "$OUT" "output")" "5"
[[ -f "${OUT_DIR_CROP}/p2cxt_tile_1.png" ]] && ok "p2cxt_tile_1.png created" || fail "p2cxt_tile_1.png missing"
[[ -f "${OUT_DIR_CROP}/p2cxt_tile_4.png" ]] && ok "p2cxt_tile_4.png created" || fail "p2cxt_tile_4.png missing"
[[ -f "${OUT_DIR_CROP}/p2cxt_html.html" ]] && ok "p2cxt_html.html created (crop)" || fail "p2cxt_html.html missing (crop)"
grep -q "p2cxt_tile_1.png" "${OUT_DIR_CROP}/p2cxt_context.md" && ok "context references tile 1" || fail "context missing tile 1"
grep -q "p2cxt_html.html" "${OUT_DIR_CROP}/p2cxt_context.md" && ok "context references p2cxt_html.html (crop)" || fail "context missing p2cxt_html.html reference (crop)"

info "Test 5: resources-regex downloads css/js from HTML/network"
OUT_DIR_RES="${TMP_DIR}/run_resources"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_RES}" --resources-regex "\\.(css|js)(\\?|$)" --json
assert_eq "resources exit code is 0" "$EC" "0"
assert_eq "resources status=success" "$(json_field "$OUT" "status")" "success"
assert_eq "resources key present" "$(json_has_key "$OUT" "resources")" "True"
assert_eq "resources files list has 2 entries" "$(json_nested_len "$OUT" "resources" "files")" "2"
assert_eq "resources matched_urls has 2 entries" "$(json_nested_len "$OUT" "resources" "matched_urls")" "2"
assert_eq "resources failed list is empty" "$(json_nested_len "$OUT" "resources" "failed")" "0"
read -r RES_COUNT RES_CSS RES_JS RES_MISSING <<< "$(json_resources_stats "$OUT")"
assert_eq "resources payload paths count" "$RES_COUNT" "2"
assert_eq "resources include one css" "$RES_CSS" "1"
assert_eq "resources include one js" "$RES_JS" "1"
assert_eq "resources payload paths exist on disk" "$RES_MISSING" "0"
grep -q "p2cxt_resource_" "${OUT_DIR_RES}/p2cxt_context.md" && ok "context references downloaded resources" || fail "context missing downloaded resources references"

info "Test 6: console-log + run-js-file create log and execute script"
OUT_DIR_CONSOLE_JS="${TMP_DIR}/run_console_js"
CUSTOM_JS="${TMP_DIR}/custom_script.js"
cat > "${CUSTOM_JS}" <<'JS'
document.body.setAttribute("data-p2cxt-js", "done");
console.log("custom js executed");
return "done";
JS
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_CONSOLE_JS}" --console-log --run-js-file "${CUSTOM_JS}" --json
assert_eq "console+js exit code is 0" "$EC" "0"
assert_eq "console+js status=success" "$(json_field "$OUT" "status")" "success"
assert_eq "console_log key present" "$(json_has_key "$OUT" "console_log")" "True"
assert_eq "script key present" "$(json_has_key "$OUT" "script")" "True"
assert_eq "console+js files has 4 files" "$(json_len "$OUT" "files")" "4"
[[ -f "${OUT_DIR_CONSOLE_JS}/p2cxt_console.log" ]] && ok "p2cxt_console.log created" || fail "p2cxt_console.log missing"
grep -q "p2cxt_console.log" "${OUT_DIR_CONSOLE_JS}/p2cxt_context.md" && ok "context references console log" || fail "context missing console log reference"
grep -q "custom js executed" "${OUT_DIR_CONSOLE_JS}/p2cxt_console.log" && ok "console log captured custom script output" || fail "console log missing custom script output"
grep -q "data-p2cxt-js=\"done\"" "${OUT_DIR_CONSOLE_JS}/p2cxt_html.html" && ok "custom JS modified DOM" || fail "custom JS DOM effect missing"

info "Test 7: existing output dir cleans only p2cxt_* files"
OUT_DIR_CLEAN="${TMP_DIR}/run_cleanup"
mkdir -p "${OUT_DIR_CLEAN}"
printf 'keep' > "${OUT_DIR_CLEAN}/keep.txt"
printf 'old' > "${OUT_DIR_CLEAN}/p2cxt_old.tmp"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_CLEAN}" --json
assert_eq "cleanup run exit code is 0" "$EC" "0"
[[ -f "${OUT_DIR_CLEAN}/keep.txt" ]] && ok "non-prefixed file kept" || fail "non-prefixed file removed"
[[ ! -e "${OUT_DIR_CLEAN}/p2cxt_old.tmp" ]] && ok "old prefixed file removed" || fail "old prefixed file not removed"

info "Test 8: invalid --size returns exit_code=2 in json"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --size "bad" --json
assert_eq "invalid size process exit code is 2" "$EC" "2"
assert_eq "invalid size status=error" "$(json_field "$OUT" "status")" "error"
assert_eq "invalid size exit_code field=2" "$(json_field "$OUT" "exit_code")" "2"

info "Test 9: out-of-range tile returns exit_code=2 and valid_range"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --crop "2x2:99" --json
assert_eq "out-of-range process exit code is 2" "$EC" "2"
assert_eq "out-of-range status=error" "$(json_field "$OUT" "status")" "error"
assert_eq "out-of-range exit_code field=2" "$(json_field "$OUT" "exit_code")" "2"
assert_eq "valid_range is present" "$(json_has_key "$OUT" "valid_range")" "True"

info "Test 10: invalid --resources-regex returns exit_code=2 in json"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --resources-regex "(" --json
assert_eq "invalid regex process exit code is 2" "$EC" "2"
assert_eq "invalid regex status=error" "$(json_field "$OUT" "status")" "error"
assert_eq "invalid regex exit_code field=2" "$(json_field "$OUT" "exit_code")" "2"
assert_eq "invalid regex reason present" "$(json_has_key "$OUT" "reason")" "True"

echo "------------------------------------"
echo "Results: ${PASS} passed  ${FAIL} failed"
echo "------------------------------------"

if [[ $FAIL -eq 0 ]]; then
  exit 0
fi
exit 1
