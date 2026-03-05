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

json_nested_field() {
  local json_payload="$1"
  local parent="$2"
  local child="$3"
  python3 - "$json_payload" "$parent" "$child" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
parent = sys.argv[2]
child = sys.argv[3]
node = payload.get(parent, {}) if isinstance(payload, dict) else {}
value = node.get(child) if isinstance(node, dict) else None

if value is None:
    print("")
elif isinstance(value, (dict, list)):
    print(json.dumps(value))
else:
    print(value)
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
export P2CXT_STATE_DIR="${TMP_DIR}/state"
check_runtime_deps
PLAYWRIGHT_BROWSERS_PATH_VALUE="$(python3 - <<'PY'
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    print(Path(p.chromium.executable_path).resolve().parents[2])
PY
)"
start_server

info "Test 1: no arguments prints syntax and exits 2"
run_and_capture OUT EC "${SCRIPT[@]}"
assert_eq "exit code is 2" "$EC" "2"
[[ "$OUT" == *"--url"* ]] && ok "help contains --url" || fail "help missing --url"
[[ "$OUT" == *"--json"* ]] && ok "help contains --json" || fail "help missing --json"
[[ "$OUT" == *"--chrome-profile-dir"* ]] && ok "help contains --chrome-profile-dir" || fail "help missing --chrome-profile-dir"

info "Test 2: JSON success returns absolute output list and prefixed files"
OUT_DIR="${TMP_DIR}/run_json"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR}" --json
assert_eq "json exit code is 0" "$EC" "0"
assert_eq "json status=success" "$(json_field "$OUT" "status")" "success"
assert_eq "json files has 3 files (no crop)" "$(json_len "$OUT" "files")" "3"
assert_eq "json files values are absolute" "$(json_all_abs "$OUT" "files")" "True"
assert_eq "json output has 3 files (no crop)" "$(json_len "$OUT" "output")" "3"
assert_eq "json chrome_profile_source key present" "$(json_has_key "$OUT" "chrome_profile_source")" "True"
assert_eq "json chrome_profile_source empty without profile option" "$(json_field "$OUT" "chrome_profile_source")" ""
[[ -f "${OUT_DIR}/p2cxt_screenshot.png" ]] && ok "p2cxt_screenshot.png created" || fail "p2cxt_screenshot.png missing"
[[ -f "${OUT_DIR}/p2cxt_context.md" ]] && ok "p2cxt_context.md created" || fail "p2cxt_context.md missing"
[[ -f "${OUT_DIR}/p2cxt_html.html" ]] && ok "p2cxt_html.html created" || fail "p2cxt_html.html missing"
grep -q "p2cxt_html.html" "${OUT_DIR}/p2cxt_context.md" && ok "context references p2cxt_html.html" || fail "context missing p2cxt_html.html reference"

info "Test 3: text mode prints created files as absolute paths"
OUT_DIR_TEXT="${TMP_DIR}/run_text"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_TEXT}"
assert_eq "text exit code is 0" "$EC" "0"
LINE_COUNT="$(printf '%s\n' "$OUT" | sed '/^$/d' | wc -l | tr -d ' ')"
assert_eq "text output has 5 lines" "$LINE_COUNT" "5"
HISTORY_LINE_SEEN="False"
CHROME_PROFILE_SOURCE_SEEN="False"
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  if [[ "$line" == chrome_profile_source:* ]]; then
    CHROME_VALUE="${line#chrome_profile_source: }"
    [[ -z "$CHROME_VALUE" ]] && ok "chrome_profile_source empty when no profile is used" || fail "chrome_profile_source expected empty but got: $CHROME_VALUE"
    CHROME_PROFILE_SOURCE_SEEN="True"
    continue
  fi
  if [[ "$line" == history_file:* ]]; then
    HISTORY_PATH="${line#history_file: }"
    [[ "$HISTORY_PATH" == /* ]] && ok "history file path is absolute" || fail "history file path is not absolute"
    [[ -f "$HISTORY_PATH" ]] && ok "history file exists: $HISTORY_PATH" || fail "history file missing: $HISTORY_PATH"
    HISTORY_LINE_SEEN="True"
    continue
  fi
  [[ "$line" == /* ]] && ok "line is absolute: $line" || fail "line is not absolute: $line"
  [[ -f "$line" ]] && ok "file exists: $line" || fail "file does not exist: $line"
done <<< "$OUT"
assert_eq "chrome_profile_source line present" "$CHROME_PROFILE_SOURCE_SEEN" "True"
assert_eq "history_file line present" "$HISTORY_LINE_SEEN" "True"

info "Test 4: clean-temp alone removes historical artifacts and exits 0"
OUT_DIR_CLEAN_ONLY_SRC="${TMP_DIR}/run_clean_only_src"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_CLEAN_ONLY_SRC}" --json
assert_eq "prep clean-only source exit code is 0" "$EC" "0"
[[ -f "${OUT_DIR_CLEAN_ONLY_SRC}/p2cxt_screenshot.png" ]] && ok "clean-only source screenshot exists" || fail "clean-only source screenshot missing"

run_and_capture OUT EC "${SCRIPT[@]}" --clean-temp --json
assert_eq "clean-temp only exit code is 0" "$EC" "0"
assert_eq "clean-temp only status=success" "$(json_field "$OUT" "status")" "success"
assert_eq "clean-temp only cleaned_files key present" "$(json_has_key "$OUT" "cleaned_files")" "True"
[[ ! -f "${OUT_DIR_CLEAN_ONLY_SRC}/p2cxt_screenshot.png" ]] && ok "clean-temp removed historical screenshot" || fail "clean-temp did not remove historical screenshot"

info "Test 5: clean-temp with url cleans before capture and continues"
OUT_DIR_CLEAN_MIX_OLD="${TMP_DIR}/run_clean_mix_old"
OUT_DIR_CLEAN_MIX_NEW="${TMP_DIR}/run_clean_mix_new"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_CLEAN_MIX_OLD}" --json
assert_eq "prep clean-mix old exit code is 0" "$EC" "0"
[[ -f "${OUT_DIR_CLEAN_MIX_OLD}/p2cxt_screenshot.png" ]] && ok "clean-mix old screenshot exists" || fail "clean-mix old screenshot missing"

run_and_capture OUT EC "${SCRIPT[@]}" --clean-temp --url "${TEST_URL}" --output "${OUT_DIR_CLEAN_MIX_NEW}" --json
assert_eq "clean-temp+url exit code is 0" "$EC" "0"
assert_eq "clean-temp+url status=success" "$(json_field "$OUT" "status")" "success"
assert_eq "clean-temp+url cleanup_before_run key present" "$(json_has_key "$OUT" "cleanup_before_run")" "True"
[[ ! -f "${OUT_DIR_CLEAN_MIX_OLD}/p2cxt_screenshot.png" ]] && ok "clean-temp+url removed old historical screenshot" || fail "clean-temp+url did not remove old historical screenshot"
[[ -f "${OUT_DIR_CLEAN_MIX_NEW}/p2cxt_screenshot.png" ]] && ok "clean-temp+url created new screenshot" || fail "clean-temp+url new screenshot missing"

info "Test 6: text mode prints created files as absolute paths"
OUT_DIR_TEXT="${TMP_DIR}/run_text"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_TEXT}"
assert_eq "text exit code is 0" "$EC" "0"
LINE_COUNT="$(printf '%s\n' "$OUT" | sed '/^$/d' | wc -l | tr -d ' ')"
assert_eq "text output has 5 lines" "$LINE_COUNT" "5"
HISTORY_LINE_SEEN="False"
CHROME_PROFILE_SOURCE_SEEN="False"
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  if [[ "$line" == chrome_profile_source:* ]]; then
    CHROME_VALUE="${line#chrome_profile_source: }"
    [[ -z "$CHROME_VALUE" ]] && ok "chrome_profile_source empty when no profile is used" || fail "chrome_profile_source expected empty but got: $CHROME_VALUE"
    CHROME_PROFILE_SOURCE_SEEN="True"
    continue
  fi
  if [[ "$line" == history_file:* ]]; then
    HISTORY_PATH="${line#history_file: }"
    [[ "$HISTORY_PATH" == /* ]] && ok "history file path is absolute" || fail "history file path is not absolute"
    [[ -f "$HISTORY_PATH" ]] && ok "history file exists: $HISTORY_PATH" || fail "history file missing: $HISTORY_PATH"
    HISTORY_LINE_SEEN="True"
    continue
  fi
  [[ "$line" == /* ]] && ok "line is absolute: $line" || fail "line is not absolute: $line"
  [[ -f "$line" ]] && ok "file exists: $line" || fail "file does not exist: $line"
done <<< "$OUT"
assert_eq "chrome_profile_source line present" "$CHROME_PROFILE_SOURCE_SEEN" "True"
assert_eq "history_file line present" "$HISTORY_LINE_SEEN" "True"

info "Test 7: crop creates prefixed tiles and reports them"
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

info "Test 8: resources-regex downloads css/js from HTML/network"
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

info "Test 9: console-log + run-js-file create log and execute script"
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

info "Test 10: chrome-profile-dir uses ephemeral copy and cleans it"
OUT_DIR_CHROME_TMP="${TMP_DIR}/run_chrome_tmp"
CHROME_TMP_SRC="${TMP_DIR}/chrome_temp_source"
mkdir -p "${CHROME_TMP_SRC}/Default"
printf 'local-state' > "${CHROME_TMP_SRC}/Local State"
printf '{"test":true}' > "${CHROME_TMP_SRC}/Default/Preferences"
CHROME_TMP_SRC_ABS="$(cd "${CHROME_TMP_SRC}" && pwd)"

run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_CHROME_TMP}" --chrome-profile-dir "${CHROME_TMP_SRC}" --json
assert_eq "chrome-profile-dir exit code is 0" "$EC" "0"
assert_eq "chrome-profile-dir status=success" "$(json_field "$OUT" "status")" "success"
assert_eq "chrome_profile_source matches explicit profile" "$(json_field "$OUT" "chrome_profile_source")" "${CHROME_TMP_SRC_ABS}"
assert_eq "chrome_profile key present" "$(json_has_key "$OUT" "chrome_profile")" "True"
assert_eq "chrome_profile source matches" "$(json_nested_field "$OUT" "chrome_profile" "source")" "${CHROME_TMP_SRC_ABS}"
assert_eq "chrome_profile cleaned=true" "$(json_nested_field "$OUT" "chrome_profile" "cleaned")" "True"
TEMP_COPY_PATH="$(json_nested_field "$OUT" "chrome_profile" "temp_copy")"
[[ "$TEMP_COPY_PATH" == /* ]] && ok "chrome temp copy path is absolute" || fail "chrome temp copy path is not absolute"
[[ ! -e "$TEMP_COPY_PATH" ]] && ok "chrome temp copy removed after run" || fail "chrome temp copy still exists after run"
grep -q "Chrome Profile Copy" "${OUT_DIR_CHROME_TMP}/p2cxt_context.md" && ok "context includes chrome profile copy section" || fail "context missing chrome profile copy section"

info "Test 11: chrome-profile-dir empty auto-discovers first default profile"
OUT_DIR_CHROME_AUTO="${TMP_DIR}/run_chrome_auto"
AUTO_HOME="${TMP_DIR}/home_auto"
AUTO_PROFILE="${AUTO_HOME}/.config/google-chrome"
mkdir -p "${AUTO_PROFILE}/Default"
printf 'local-state' > "${AUTO_PROFILE}/Local State"
AUTO_PROFILE_ABS="$(cd "${AUTO_PROFILE}" && pwd)"

run_and_capture OUT EC env HOME="${AUTO_HOME}" PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH_VALUE}" "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_CHROME_AUTO}" --chrome-profile-dir "" --json
STATUS_AUTO="$(json_field "$OUT" "status")"
if [[ "$STATUS_AUTO" == "success" || "$STATUS_AUTO" == "error" ]]; then
  ok "chrome-profile-dir auto-discovery returned a valid status"
else
  fail "chrome-profile-dir auto-discovery returned unexpected status: $STATUS_AUTO"
fi
assert_eq "chrome_profile_source matches auto-discovered profile" "$(json_field "$OUT" "chrome_profile_source")" "${AUTO_PROFILE_ABS}"
if [[ "$STATUS_AUTO" == "success" ]]; then
  assert_eq "chrome_profile source matches auto-discovered profile" "$(json_nested_field "$OUT" "chrome_profile" "source")" "${AUTO_PROFILE_ABS}"
fi

info "Test 12: chrome-profile-dir empty returns exit_code=4 when no profile is found"
MISSING_HOME="${TMP_DIR}/home_missing"
mkdir -p "${MISSING_HOME}"
run_and_capture OUT EC env HOME="${MISSING_HOME}" "${SCRIPT[@]}" --url "${TEST_URL}" --output "${TMP_DIR}/run_chrome_missing" --chrome-profile-dir "" --json
assert_eq "chrome-profile-dir missing auto-discovery process exit code is 4" "$EC" "4"
assert_eq "chrome-profile-dir missing auto-discovery status=error" "$(json_field "$OUT" "status")" "error"
assert_eq "chrome-profile-dir missing auto-discovery chrome_profile_source key present" "$(json_has_key "$OUT" "chrome_profile_source")" "True"
assert_eq "chrome-profile-dir missing auto-discovery chrome_profile_source is empty" "$(json_field "$OUT" "chrome_profile_source")" ""
assert_eq "chrome-profile-dir missing auto-discovery exit_code field=4" "$(json_field "$OUT" "exit_code")" "4"

info "Test 13: existing output dir cleans only p2cxt_* files"
OUT_DIR_CLEAN="${TMP_DIR}/run_cleanup"
mkdir -p "${OUT_DIR_CLEAN}"
printf 'keep' > "${OUT_DIR_CLEAN}/keep.txt"
printf 'old' > "${OUT_DIR_CLEAN}/p2cxt_old.tmp"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --output "${OUT_DIR_CLEAN}" --json
assert_eq "cleanup run exit code is 0" "$EC" "0"
[[ -f "${OUT_DIR_CLEAN}/keep.txt" ]] && ok "non-prefixed file kept" || fail "non-prefixed file removed"
[[ ! -e "${OUT_DIR_CLEAN}/p2cxt_old.tmp" ]] && ok "old prefixed file removed" || fail "old prefixed file not removed"

info "Test 14: invalid --size returns exit_code=2 in json"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --size "bad" --json
assert_eq "invalid size process exit code is 2" "$EC" "2"
assert_eq "invalid size status=error" "$(json_field "$OUT" "status")" "error"
assert_eq "invalid size exit_code field=2" "$(json_field "$OUT" "exit_code")" "2"

info "Test 15: out-of-range tile returns exit_code=2 and valid_range"
run_and_capture OUT EC "${SCRIPT[@]}" --url "${TEST_URL}" --crop "2x2:99" --json
assert_eq "out-of-range process exit code is 2" "$EC" "2"
assert_eq "out-of-range status=error" "$(json_field "$OUT" "status")" "error"
assert_eq "out-of-range exit_code field=2" "$(json_field "$OUT" "exit_code")" "2"
assert_eq "valid_range is present" "$(json_has_key "$OUT" "valid_range")" "True"

info "Test 16: invalid --resources-regex returns exit_code=2 in json"
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
