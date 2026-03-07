"""
page2context - Capture a webpage (screenshot + DOM) into Markdown outputs
for use as AI context (GitHub Copilot, Cursor, etc.).
"""
import argparse
import ipaddress
import json
import math
import os
import pathlib
import re
import shutil
import sys
import tempfile
import textwrap
import traceback
from typing import NoReturn, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.request import Request
from playwright.sync_api import sync_playwright, Error as PlaywrightError
import time

def _load_version() -> str:
    version_file = pathlib.Path(__file__).parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
__version__ = _load_version()
EXIT_OK             = 0
EXIT_BAD_ARGS       = 2
EXIT_NAVIGATION_ERR = 3
EXIT_IO_ERR         = 4
EXIT_DEP_ERR        = 5
EXIT_UNEXPECTED     = 99
OUTPUT_PREFIX = "p2cxt_"
STATE_DIR_ENV = "P2CXT_STATE_DIR"
STATE_FILE_NAME = "artifact_history.json"
CHROME_VOLATILE_SINGLETON_FILES = {"SingletonLock", "SingletonCookie", "SingletonSocket"}
FIREFOX_VOLATILE_FILES = {"lock", ".parentlock", "parent.lock", "places.sqlite-wal", "places.sqlite-shm"}

# Security: only allow http/https for --url to prevent file:// local file reads etc.
ALLOWED_URL_SCHEMES = {"http", "https"}

# Security: max bytes to download per resource to prevent memory/disk exhaustion (50 MB).
RESOURCE_MAX_BYTES = 50 * 1024 * 1024  # 50 MB

def _is_private_host(host: str) -> bool:
    """Return True if host resolves to a private/loopback/link-local/reserved address.
    Used to block SSRF in resource downloads."""
    # Strip IPv6 brackets
    host = host.strip("[]")
    try:
        addr = ipaddress.ip_address(host)
        return (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified)
    except ValueError:
        # It's a hostname — check for obvious localhost patterns;
        # full DNS resolution would be needed for complete SSRF protection but
        # that would require a blocking lookup. We block the most common cases.
        lower = host.lower()
        return lower == "localhost" or lower.endswith(".local") or lower.endswith(".internal")


# ---------------------------------------------------------------------------
# URL Safety / allowlist policy
# ---------------------------------------------------------------------------

def _host_is_local_allowed_default(hostname: str) -> bool:
    """True if hostname is allowed without requiring --allow-external-urls.

    Default policy is intentionally conservative:
      - allow: localhost/127.0.0.1/::1
      - allow: IP literals that are private/loopback/link-local
      - do NOT DNS-resolve arbitrary hostnames
    """
    host = (hostname or "").strip().strip("[]")
    if not host:
        return False

    lower = host.lower()
    if lower == "localhost":
        return True

    try:
        ip = ipaddress.ip_address(host)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        return False


def _compile_allow_external_regex_or_exit(pattern: Optional[str]) -> Optional["re.Pattern[str]"]:
    """Compile allow-external regex; empty string means allow-all."""
    if pattern is None or pattern == "":
        return None
    try:
        return re.compile(pattern)
    except re.error as exc:
        _error_exit(EXIT_BAD_ARGS, f"Invalid --allow-external-urls value: {pattern!r}", reason=str(exc))


def _external_url_allowed(url: str, regex: Optional["re.Pattern[str]"], allow_all_external: bool) -> bool:
    if allow_all_external:
        return True
    if regex is None:
        return False
    return regex.search(url) is not None


def _validate_target_url_or_exit(url: str, allow_external_raw: Optional[str]) -> None:
    """Validate --url against the local-only default policy unless explicitly allowed."""
    parsed = urlparse(url)
    host = parsed.hostname or ""

    allow_all_external = allow_external_raw is not None and allow_external_raw == ""
    allow_regex = _compile_allow_external_regex_or_exit(allow_external_raw)

    if _host_is_local_allowed_default(host):
        return

    if allow_external_raw is None:
        _error_exit(
            EXIT_BAD_ARGS,
            "External URLs are disabled by default. Only localhost/127.0.0.1/::1 and local/private IPs are allowed for --url.",
            hint=(
                "If you really need to capture an external site, pass --allow-external-urls. "
                "For safer use, pass a regex to restrict which external URLs are allowed (e.g. --allow-external-urls \"^https://example\\.com/\")."
            ),
            url=url,
        )

    if not _external_url_allowed(url, allow_regex, allow_all_external):
        _error_exit(
            EXIT_BAD_ARGS,
            "External URL does not match --allow-external-urls policy.",
            hint="Adjust --allow-external-urls regex or pass an empty value to allow all external URLs.",
            url=url,
        )


PROFILE_ARG_TO_KEY: dict[str, str] = {
    "chrome_profile_dir":   "chrome",
    "edge_profile_dir":     "edge",
    "brave_profile_dir":    "brave",
    "firefox_profile_dir":  "firefox",
    "safari_profile_dir":   "safari",
    "chromium_profile_dir": "chromium",
    "webkit_profile_dir":   "webkit",
}
PROFILE_KEY_TO_BROWSER_TYPE: dict[str, str] = {
    "chrome":   "chromium",
    "edge":     "chromium",
    "brave":    "chromium",
    "chromium": "chromium",
    "firefox":  "firefox",
    "safari":   "webkit",
    "webkit":   "webkit",
}
BROWSER_KEYS: tuple[str, ...] = ("chrome", "edge", "brave", "firefox", "safari", "chromium", "webkit")

# Local persistent profiles live under <project_root>/browser/<browser>.
BROWSER_PROFILE_ROOT = pathlib.Path(__file__).resolve().parent / "browser"

def _history_file_full_path() -> str:
    return str(_state_file().resolve())
_json_mode: bool = False
_profile_source_output: str = ""

def _emit(payload: dict) -> None:
    # Clean-only modes omit profile source fields.
    browser_clean_only = payload.get("status") == "success" and payload.get("message") == "Browser profile directories cleaned."
    clean_only_messages = {
        "Historical temporary artifacts cleaned.",
        "Browser profile directories cleaned.",
    }
    is_clean_only = payload.get("status") == "success" and payload.get("message") in clean_only_messages

    if "history_file" not in payload and not browser_clean_only:
        payload = {**payload, "history_file": _history_file_full_path()}
    if not is_clean_only and "chrome_profile_source" not in payload:
        payload = {**payload, "chrome_profile_source": _profile_source_output}
    if not is_clean_only and "browser_profile_source" not in payload:
        payload = {**payload, "browser_profile_source": _profile_source_output}

    if _json_mode:
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    else:
        _emit_text(payload)


def _emit_text(payload: dict) -> None:
    status = payload.get("status", "")
    msg    = payload.get("message", "")

    if status == "success":
        # Special-case: clean-only output should show what was deleted.
        if msg == "Historical temporary artifacts cleaned.":
            cleaned = payload.get("cleaned", [])
            failed  = payload.get("failed", [])
            cleaned_files = payload.get("cleaned_files", 0)

            # Temp-root sweep extras
            temp_cleaned = payload.get("temp_cleaned", [])
            temp_failed = payload.get("temp_failed", [])
            temp_cleaned_dirs = payload.get("temp_cleaned_dirs_list", [])

            try:
                cleaned_files_int = int(cleaned_files)
            except Exception:
                cleaned_files_int = 0

            print(f"cleaned_files: {cleaned_files_int}")
            if isinstance(cleaned, list) and cleaned:
                print("cleaned:")
                for p in cleaned:
                    print(str(p))

            # Show temp deletions (every file and every directory)
            if isinstance(temp_cleaned, list) and temp_cleaned:
                print("temp_cleaned:")
                for p in temp_cleaned:
                    print(str(p))
            if isinstance(temp_cleaned_dirs, list) and temp_cleaned_dirs:
                print("temp_cleaned_dirs:")
                for d in temp_cleaned_dirs:
                    print(str(d))

            if isinstance(failed, list) and failed:
                print("failed:")
                for entry in failed:
                    print(str(entry))
            if isinstance(temp_failed, list) and temp_failed:
                print("temp_failed:")
                for entry in temp_failed:
                    print(str(entry))

            history_file = payload.get("history_file")
            if history_file:
                print(f"history_file: {history_file}")
            return

        if msg == "Browser profile directories cleaned.":
            cleaned_dirs = payload.get("cleaned_browser_dirs", [])
            failed_dirs = payload.get("failed_browser_dirs", [])
            reclaimed_bytes = payload.get("reclaimed_bytes", 0)
            reclaimed_human = payload.get("reclaimed_human", "0 B")
            details = payload.get("cleaned_browser_details", [])
            print(f"cleaned_browser_count: {payload.get('cleaned_browser_count', 0)}")
            print(f"reclaimed_bytes: {reclaimed_bytes}")
            print(f"reclaimed_human: {reclaimed_human}")
            if isinstance(cleaned_dirs, list) and cleaned_dirs:
                print("cleaned_browser_dirs:")
                for p in cleaned_dirs:
                    print(str(p))
            if isinstance(details, list) and details:
                print("cleaned_browser_details:")
                for item in details:
                    if isinstance(item, dict):
                        print(f"{item.get('path', '')} :: {item.get('reclaimed_human', '0 B')} ({item.get('reclaimed_bytes', 0)} bytes)")
            if isinstance(failed_dirs, list) and failed_dirs:
                print("failed_browser_dirs:")
                for entry in failed_dirs:
                    print(str(entry))
            return

        outputs = payload.get("output")
        if isinstance(outputs, list) and outputs:
            print("\n".join(str(p) for p in outputs))
        else:
            print(payload.get("output_dir", ""))
        if "browser_profile_source" in payload:
            print(f"browser_profile_source: {payload.get('browser_profile_source', '')}")
        # Backward-compat line (existing integrations may parse it)
        if "chrome_profile_source" in payload:
            print(f"chrome_profile_source: {payload.get('chrome_profile_source', '')}")
        history_file = payload.get("history_file")
        if history_file:
            print(f"history_file: {history_file}")
    elif status == "error":
        code = payload.get("exit_code", "")
        print(f"ERROR ({code}): {msg}", file=sys.stderr)
        for key in ("reason", "hint", "fix"):
            if key in payload:
                print(f"  {key}: {payload[key]}", file=sys.stderr)
        if "valid_range" in payload:
            r = payload["valid_range"]
            print(f"  valid tile range: {r[0]}-{r[1]}", file=sys.stderr)
        if "detail" in payload:
            print(f"  detail: {payload['detail']}", file=sys.stderr)
        if "browser_profile_source" in payload:
            print(f"  browser_profile_source: {payload.get('browser_profile_source', '')}", file=sys.stderr)
        if "chrome_profile_source" in payload:
            print(f"  chrome_profile_source: {payload.get('chrome_profile_source', '')}", file=sys.stderr)
        history_file = payload.get("history_file")
        if history_file:
            print(f"  history_file: {history_file}", file=sys.stderr)
    elif status == "info":
        print(payload.get("syntax", ""))
        history_file = payload.get("history_file")
        if history_file:
            print(f"history_file: {history_file}")
def _success(message: str, **extra) -> None:
    _emit({"status": "success", "message": message, **extra})
def _error_exit(code: int, message: str, **extra) -> NoReturn:
    payload = {"status": "error", "exit_code": code, "message": message, **extra}

    # Add a navigation hint when we have URL + reason and caller didn't already provide a hint.
    if code == EXIT_NAVIGATION_ERR and "hint" not in payload:
        url = payload.get("url")
        if isinstance(url, str) and url:
            hint = _navigation_hint(url, payload.get("reason") if isinstance(payload.get("reason"), str) else None)
            if hint:
                payload["hint"] = hint

    _emit(payload)
    sys.exit(code)

def _navigation_hint(url: str, reason: Optional[str] = None) -> Optional[str]:
    """Return a short, actionable hint for common navigation failures.

    Goal: help users/agents distinguish *network reachability* problems from
    missing dependencies, so they don't try random pip installs.
    """
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except Exception:
        host = ""

    r = (reason or "").lower()

    # Localhost/dev-server specific guidance.
    if host in {"localhost", "127.0.0.1", "::1"}:
        return (
            "This looks like a localhost/dev-server URL. Verify the server is running and reachable from the same machine/runtime running page2context. "
            "If you're running this inside a container/CI/agent sandbox, `localhost` refers to that runtime, not your host OS; try the host IP, `host.docker.internal`, or expose the port."
        )

    # Generic hints.
    if "dns" in r or "name not resolved" in r or "host not found" in r:
        return "DNS resolution failed. Check your network, VPN/proxy settings, and /etc/resolv.conf (or corporate DNS rules)."
    if "refused" in r:
        return "Connection refused. The server may not be listening on that host/port, or a firewall is blocking it."
    if "timeout" in r:
        return "Navigation timed out. The server may be slow/down, or network access is restricted in this runtime."
    return None

SYNTAX_HELP = textwrap.dedent("""\
    page2context v{version}
    Capture a webpage (screenshot + DOM) into Markdown outputs for AI context.
    Usage:
      python3 page2context.py --url "<URL>" [OPTIONS]
    Required:
      --url  "<URL>"                URL to capture (required unless using clean-only flags)
    Optional:
      --help                       Show this help and exit.
      --clean-temp                 Clean historical p2cxt temporary artifacts.
      --clean-chrome               Remove local browser profile dir: ./browser/chrome
      --clean-edge                 Remove local browser profile dir: ./browser/edge
      --clean-brave                Remove local browser profile dir: ./browser/brave
      --clean-firefox              Remove local browser profile dir: ./browser/firefox
      --clean-safari               Remove local browser profile dir: ./browser/safari
      --clean-chromium             Remove local browser profile dir: ./browser/chromium
      --clean-webkit               Remove local browser profile dir: ./browser/webkit
      --allow-external-urls [REGEX]
                                   Allow external (non-localhost/non-private IP) URLs for --url and resource downloads.
                                   - If omitted: external URLs are blocked (default is local-only).
                                   - If provided as empty string: allow ALL external URLs.
                                   - If REGEX provided: allow only external URLs whose full URL matches REGEX.
      --size  <WIDTHxHEIGHT>       Viewport size (default: 1280x720)
      --crop  <COLSxROWS:TILES>    Grid crop, e.g. "3x9:1,27"
      --console-log                Save browser console/navigation errors to p2cxt_console.log.
      --use-chrome                 Use local profile ./browser/chrome (default if no --use-* is given).
      --use-edge                   Use local profile ./browser/edge.
      --use-brave                  Use local profile ./browser/brave.
      --use-firefox                Use local profile ./browser/firefox.
      --use-safari                 Use local profile ./browser/safari (webkit engine).
      --use-chromium               Use local profile ./browser/chromium.
      --use-webkit                 Use local profile ./browser/webkit.
      --show-chrome                Show browser window (headed mode) using chrome profile; no time limit (waits for manual completion).
      --show-edge                  Show browser window (headed mode) using edge profile; no time limit (waits for manual completion).
      --show-brave                 Show browser window (headed mode) using brave profile; no time limit (waits for manual completion).
      --show-firefox               Show browser window (headed mode) using firefox profile; no time limit (waits for manual completion).
      --show-safari                Show browser window (headed mode) using safari profile; no time limit (waits for manual completion).
      --show-chromium              Show browser window (headed mode) using chromium profile; no time limit (waits for manual completion).
      --show-webkit                Show browser window (headed mode) using webkit profile; no time limit (waits for manual completion).
                                   Only one --use-* and one --show-* browser can be selected per run.
      --run-js-file <PATH>         Execute JavaScript file in the opened page.
      --post-load-wait-ms <MS>     Extra wait after page load before JS/screenshot (default: 0).
      --resources-regex <REGEX>    Download resources whose URL matches REGEX.
      --output <DIR>               Output folder (default: a new temp dir under /tmp)
      --json                       Machine-readable JSON output (for AI callers)
    Examples:
      python3 page2context.py --help
      python3 page2context.py --url "http://localhost:4200" --json
      python3 page2context.py --url "http://localhost:4200" --use-firefox --json
      python3 page2context.py --url "http://localhost:4200" --show-chrome --json
      python3 page2context.py --clean-temp --clean-chrome --clean-firefox --json
""").format(version=__version__)
class _TextArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        _error_exit(EXIT_BAD_ARGS, f"Argument error: {message}",
                    hint="Run without arguments to see full usage syntax.")
def parse_args():
    global _json_mode

    # Implement a predictable --help that works even without other args.
    if any(a in {"-h", "--help"} for a in sys.argv[1:]):
        _json_mode = "--json" in sys.argv
        _emit({"status": "info", "syntax": SYNTAX_HELP})
        sys.exit(EXIT_OK)

    if len(sys.argv) == 1:
        _emit({"status": "info", "syntax": SYNTAX_HELP})
        sys.exit(EXIT_BAD_ARGS)

    _json_mode = "--json" in sys.argv
    parser = _TextArgumentParser(
        prog="page2context",
        description="Capture a webpage screenshot and DOM HTML into Markdown outputs.",
        add_help=False,
    )

    # Add our own help flag (argparse's default help is disabled above).
    parser.add_argument("-h", "--help", action="store_true", help="Show this help and exit.")

    parser.add_argument("--url",         required=False,       help="URL to capture")
    parser.add_argument("--clean-temp",  action="store_true",  help="Clean historical p2cxt artifacts.")
    parser.add_argument(
        "--allow-external-urls",
        nargs="?",
        const="",
        default=None,
        help=(
            "Allow external URLs for --url and resource downloads. "
            "If omitted, only localhost/127.0.0.1/::1 and local/private IPs are allowed. "
            "Pass empty to allow all external URLs, or provide a regex to allow only matching URLs."
        ),
    )
    parser.add_argument("--size",        default="1280x720",   help="Viewport WIDTHxHEIGHT")
    parser.add_argument("--crop",        default=None,         help="Grid crop COLSxROWS:TILE[,TILE]")
    parser.add_argument("--console-log", action="store_true",  help="Save browser console/errors to p2cxt_console.log.")
    for browser in BROWSER_KEYS:
        parser.add_argument(f"--use-{browser}", action="store_true", dest=f"use_{browser}",
                            help=f"Use local profile ./browser/{browser}")
        parser.add_argument(f"--show-{browser}", action="store_true", dest=f"show_{browser}",
                            help=f"Show {browser} window (headed mode).")
        parser.add_argument(f"--clean-{browser}", action="store_true", dest=f"clean_{browser}",
                            help=f"Delete local profile ./browser/{browser}")
    parser.add_argument("--run-js-file",       default=None,           help="JS file to execute in the opened page.")
    parser.add_argument("--post-load-wait-ms", default="0",            help="Wait (ms) after page load.")
    parser.add_argument("--resources-regex",   default=None,           help="Download resources whose URL matches this regex.")
    parser.add_argument(
        "--output",
        default=None,
        help="Output folder. If omitted, a new unique temp dir is created.",
    )
    parser.add_argument("--json",              action="store_true",    help="Emit JSON output.")
    args = parser.parse_args()

    selected_use = [b for b in BROWSER_KEYS if getattr(args, f"use_{b}")]
    selected_show = [b for b in BROWSER_KEYS if getattr(args, f"show_{b}")]
    selected_clean = [b for b in BROWSER_KEYS if getattr(args, f"clean_{b}")]

    if len(selected_use) > 1:
        flags = ", ".join(f"--use-{b}" for b in selected_use)
        _error_exit(EXIT_BAD_ARGS, "Argument error: only one --use-* browser can be selected per run.", hint=f"Received: {flags}")

    if len(selected_show) > 1:
        flags = ", ".join(f"--show-{b}" for b in selected_show)
        _error_exit(EXIT_BAD_ARGS, "Argument error: only one --show-* browser can be selected per run.", hint=f"Received: {flags}")

    selected_browser = selected_use[0] if selected_use else (selected_show[0] if selected_show else "chrome")
    if selected_show and selected_use and selected_show[0] != selected_use[0]:
        _error_exit(
            EXIT_BAD_ARGS,
            "Argument error: --show-* browser must match --use-* browser when both are provided.",
            hint=f"Received --use-{selected_use[0]} with --show-{selected_show[0]}",
        )

    args.selected_browser = selected_browser
    args.headed = bool(selected_show)
    args.clean_browsers = selected_clean

    if not args.clean_temp and not args.clean_browsers and not args.url:
        _error_exit(EXIT_BAD_ARGS, "Argument error: --url is required unless using clean-only flags.",
                    hint="Use --clean-temp/--clean-<browser> alone to clean, or provide --url for capture.")

    _json_mode = args.json
    if args.url:
        parsed_url = urlparse(args.url)
        if parsed_url.scheme.lower() not in ALLOWED_URL_SCHEMES:
            _error_exit(EXIT_BAD_ARGS,
                        f"Invalid --url scheme: {parsed_url.scheme!r}. Only http and https are allowed.",
                        hint="Use --url \"http://...\" or --url \"https://...\"")

        # Enforce local-only policy unless explicitly allowed.
        _validate_target_url_or_exit(args.url, args.allow_external_urls)

    return args
class _CliArgError(Exception):
    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.message = message
        self.extra = extra
def parse_size(size_str: str) -> tuple[int, int]:
    parts = size_str.lower().split("x")
    if len(parts) != 2:
        raise _CliArgError(f"Invalid --size value: {size_str!r}. Expected WIDTHxHEIGHT (e.g. 1920x1080).")
    try:
        width, height = int(parts[0]), int(parts[1])
    except ValueError:
        raise _CliArgError(f"Invalid --size value: {size_str!r}. Expected numeric WIDTHxHEIGHT.")
    return width, height
def parse_crop(crop_str: str) -> tuple[int, int, list[int]]:
    cols = rows = 0
    tiles: list[int] = []
    parts = crop_str.split(":", 1)
    if len(parts) != 2:
        raise _CliArgError(f"Invalid --crop value: {crop_str!r}. Expected COLSxROWS:TILE[,TILE] (e.g. 3x9:1,27).")
    grid_part, tiles_part = parts
    grid_tokens = grid_part.lower().split("x", 1)
    if len(grid_tokens) != 2:
        raise _CliArgError(f"Invalid --crop grid: {grid_part!r}. Expected COLSxROWS.")
    try:
        cols = int(grid_tokens[0])
        rows = int(grid_tokens[1])
        tiles = [int(t.strip()) for t in tiles_part.split(",") if t.strip()]
    except ValueError:
        raise _CliArgError(f"Invalid --crop value: {crop_str!r}. Values must be integers.")
    if cols < 1 or rows < 1:
        raise _CliArgError(f"Invalid --crop grid: {cols}x{rows}. COLS and ROWS must be >= 1.")
    if not tiles:
        raise _CliArgError(f"Invalid --crop tiles in {crop_str!r}. Provide at least one tile index.")
    max_tile = cols * rows
    out_of_range = [t for t in tiles if t < 1 or t > max_tile]
    if out_of_range:
        raise _CliArgError(
            f"Tile(s) {out_of_range} out of range for a {cols}x{rows} grid (valid: 1-{max_tile}).",
            grid=f"{cols}x{rows}", valid_range=[1, max_tile])
    return cols, rows, tiles
def parse_wait_ms(wait_ms_str: str) -> int:
    try:
        wait_ms = int(wait_ms_str)
    except ValueError:
        raise _CliArgError(f"Invalid --post-load-wait-ms value: {wait_ms_str!r}. Expected a non-negative integer.")
    if wait_ms < 0:
        raise _CliArgError(f"Invalid --post-load-wait-ms value: {wait_ms!r}. Expected >= 0.")
    return wait_ms
def _load_js_file(path_str: Optional[str]) -> Tuple[Optional[pathlib.Path], Optional[str]]:
    if not path_str:
        return None, None
    js_path = pathlib.Path(path_str)
    try:
        return js_path, js_path.read_text(encoding="utf-8")
    except OSError as exc:
        _error_exit(EXIT_IO_ERR, f"Cannot read JS file: {exc}", path=str(js_path))
def _write_console_log(path: pathlib.Path, lines: list[str]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(("\n".join(lines) + "\n") if lines else "[info] No console/page errors captured.\n")
    except OSError as exc:
        _error_exit(EXIT_IO_ERR, f"Cannot write console log: {exc}", path=str(path))
# ---------------------------------------------------------------------------
# Browser profile auto-discovery
# ---------------------------------------------------------------------------
def _candidate_profile_dirs(profile_key: str) -> list[pathlib.Path]:
    home = pathlib.Path.home()
    candidates: list[pathlib.Path] = []
    if profile_key in {"chrome", "chromium", "edge", "brave"}:
        if sys.platform.startswith("linux"):
            lmap: dict[str, list[pathlib.Path]] = {
                "chrome":   [home / ".config" / "google-chrome",
                             home / ".var" / "app" / "com.google.Chrome" / "config" / "google-chrome"],
                "chromium": [home / ".config" / "chromium"],
                "edge":     [home / ".config" / "microsoft-edge"],
                "brave":    [home / ".config" / "BraveSoftware" / "Brave-Browser"],
            }
            candidates.extend(lmap.get(profile_key, []))
        elif sys.platform == "darwin":
            dmap: dict[str, list[pathlib.Path]] = {
                "chrome":   [home / "Library" / "Application Support" / "Google" / "Chrome"],
                "chromium": [home / "Library" / "Application Support" / "Chromium"],
                "edge":     [home / "Library" / "Application Support" / "Microsoft Edge"],
                "brave":    [home / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser"],
            }
            candidates.extend(dmap.get(profile_key, []))
        elif os.name == "nt":
            local   = os.environ.get("LOCALAPPDATA")
            roaming = os.environ.get("APPDATA")
            if local:
                lp = pathlib.Path(local)
                wmap: dict[str, list[pathlib.Path]] = {
                    "chrome":   [lp / "Google" / "Chrome" / "User Data"],
                    "chromium": [lp / "Chromium" / "User Data"],
                    "edge":     [lp / "Microsoft" / "Edge" / "User Data"],
                    "brave":    [lp / "BraveSoftware" / "Brave-Browser" / "User Data"],
                }
                candidates.extend(wmap.get(profile_key, []))
            if roaming and profile_key == "chrome":
                candidates.append(pathlib.Path(roaming) / "Google" / "Chrome" / "User Data")
    elif profile_key == "firefox":
        if sys.platform.startswith("linux"):
            candidates.append(home / ".mozilla" / "firefox")
        elif sys.platform == "darwin":
            candidates.append(home / "Library" / "Application Support" / "Firefox")
        elif os.name == "nt":
            app_data = os.environ.get("APPDATA")
            if app_data:
                candidates.append(pathlib.Path(app_data) / "Mozilla" / "Firefox")
    elif profile_key in {"safari", "webkit"}:
        if sys.platform == "darwin":
            if profile_key == "safari":
                candidates.append(home / "Library" / "Safari")
            candidates.append(home / "Library" / "WebKit")
    return list(dict.fromkeys(candidates))
def _looks_like_chromium_profile_dir(path: pathlib.Path) -> bool:
    return ((path / "Local State").is_file()
            or (path / "Default").is_dir()
            or any(path.glob("Profile *")))
def _find_firefox_profile_in_root(root: pathlib.Path) -> Optional[pathlib.Path]:
    profiles_ini = root / "profiles.ini"
    resolved_root = root.resolve()
    if profiles_ini.is_file():
        try:
            is_relative = True
            for line in profiles_ini.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = line.strip()
                if s.lower().startswith("isrelative="):
                    is_relative = s.split("=", 1)[1].strip() != "0"
                elif s.lower().startswith("path="):
                    value = s.split("=", 1)[1].strip()
                    candidate = (root / value) if is_relative else pathlib.Path(value).expanduser()
                    candidate = candidate.resolve()
                    # Security: ensure candidate stays within the profile root to prevent
                    # path traversal attacks via a malicious Path= entry in profiles.ini.
                    try:
                        candidate.relative_to(resolved_root)
                    except ValueError:
                        continue  # Path escapes root — skip silently
                    if candidate.exists() and candidate.is_dir():
                        return candidate
        except OSError:
            pass
    for pattern in ("*.default-release", "*.default"):
        matches = sorted(root.glob(pattern))
        if matches:
            return matches[0].resolve()
    return None
def _looks_like_profile(profile_key: str, path: pathlib.Path) -> bool:
    if profile_key in {"chrome", "chromium", "edge", "brave"}:
        return _looks_like_chromium_profile_dir(path)
    if profile_key == "firefox":
        return (path / "prefs.js").is_file() or (path / "profiles.ini").is_file()
    if profile_key == "safari":
        return (path / "History.db").exists() or (path / "Cookies").exists()
    return path.exists() and path.is_dir()
def _discover_profile_dir(profile_key: str) -> Optional[pathlib.Path]:
    for candidate in _candidate_profile_dirs(profile_key):
        expanded = candidate.expanduser().resolve()
        if not expanded.exists() or not expanded.is_dir():
            continue
        if profile_key == "firefox":
            found = _find_firefox_profile_in_root(expanded)
            if found is not None:
                return found
            continue
        if _looks_like_profile(profile_key, expanded):
            return expanded
    return None
def _resolve_profile(profile_key: str, path_str: Optional[str]) -> Optional[pathlib.Path]:
    if path_str is None:
        return None
    if path_str.strip() == "":
        discovered = _discover_profile_dir(profile_key)
        if discovered is None:
            _error_exit(EXIT_IO_ERR,
                        f"Could not auto-detect a {profile_key} profile for --{profile_key}-profile-dir.",
                        hint=f"Pass --{profile_key}-profile-dir <DIR> with your browser user data folder.")
        return discovered
    resolved = pathlib.Path(path_str).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        _error_exit(EXIT_IO_ERR,
                    f"Invalid --{profile_key}-profile-dir: directory does not exist.", path=str(resolved))
    # For Firefox: if the explicit path is a root (contains profiles.ini), resolve to the
    # actual profile subdirectory just like auto-discovery does.
    if profile_key == "firefox":
        found = _find_firefox_profile_in_root(resolved)
        if found is not None:
            return found
        # Check if the path itself looks like a profile
        if not _looks_like_profile(profile_key, resolved):
            _error_exit(EXIT_IO_ERR,
                        f"Directory does not look like a Firefox profile: {resolved}",
                        hint="Pass the Firefox root dir (~/.mozilla/firefox) or a specific profile folder containing prefs.js.")
    return resolved
def _selected_profile(args) -> Tuple[Optional[str], Optional[pathlib.Path]]:
    for arg_name, profile_key in PROFILE_ARG_TO_KEY.items():
        raw = getattr(args, arg_name)
        if raw is not None:
            return profile_key, _resolve_profile(profile_key, raw)
    return None, None
# ---------------------------------------------------------------------------
# Profile temp-copy helpers
# ---------------------------------------------------------------------------
def _prepare_profile_temp_copy(
    profile_key: Optional[str],
    source: Optional[pathlib.Path],
) -> Tuple[Optional[pathlib.Path], Optional[pathlib.Path], Optional[pathlib.Path]]:
    if profile_key is None or source is None:
        return None, None, None
    if not source.exists() or not source.is_dir():
        _error_exit(EXIT_IO_ERR,
                    f"Invalid --{profile_key}-profile-dir: directory does not exist.", path=str(source))
    browser_type = PROFILE_KEY_TO_BROWSER_TYPE.get(profile_key, "chromium")
    def _ignore(dir_path: str, names: list[str]) -> set[str]:
        if pathlib.Path(dir_path).resolve() != source:
            return set()
        if browser_type == "chromium":
            return {n for n in names if n in CHROME_VOLATILE_SINGLETON_FILES}
        if browser_type == "firefox":
            return {n for n in names if n in FIREFOX_VOLATILE_FILES}
        return set()
    try:
        copy_root = pathlib.Path(tempfile.mkdtemp(prefix=f"p2cxt_{profile_key}_copy_"))
        copy_dir  = copy_root / "profile"
        shutil.copytree(source, copy_dir, ignore=_ignore)
        return source, copy_dir, copy_root
    except OSError as exc:
        _error_exit(EXIT_IO_ERR, f"Cannot prepare {profile_key} temp copy: {exc}", path=str(source))
def _cleanup_temp_copy(copy_root: Optional[pathlib.Path]) -> bool:
    if copy_root is None:
        return True
    try:
        shutil.rmtree(copy_root)
        return True
    except OSError:
        return False
# ---------------------------------------------------------------------------
# Browser profile local helpers
# ---------------------------------------------------------------------------
def _format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    n = float(max(0, num_bytes))
    for unit in units:
        if n < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{int(num_bytes)} B"


def _dir_size_bytes(path: pathlib.Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            fp = pathlib.Path(root) / name
            try:
                if fp.is_file():
                    total += fp.stat().st_size
            except OSError:
                continue
    return total


def _local_browser_profile_dir(browser_key: str) -> pathlib.Path:
    return (BROWSER_PROFILE_ROOT / browser_key).resolve()


def _ensure_local_browser_profile_dir(browser_key: str) -> pathlib.Path:
    profile_dir = _local_browser_profile_dir(browser_key)
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _error_exit(EXIT_IO_ERR, f"Cannot create local browser profile dir: {exc}", path=str(profile_dir))
    return profile_dir


def _clean_selected_browser_profiles(browser_keys: list[str]) -> dict:
    cleaned_dirs: list[str] = []
    failed_dirs: list[str] = []
    cleaned_details: list[dict] = []
    total_reclaimed = 0
    for browser in browser_keys:
        path = _local_browser_profile_dir(browser)
        if not path.exists():
            continue
        if not path.is_dir():
            failed_dirs.append(f"{path} :: not a directory")
            continue
        size_before = _dir_size_bytes(path)
        try:
            shutil.rmtree(path)
            cleaned_dirs.append(str(path))
            total_reclaimed += size_before
            cleaned_details.append({
                "browser": browser,
                "path": str(path),
                "reclaimed_bytes": size_before,
                "reclaimed_human": _format_bytes(size_before),
            })
        except OSError as exc:
            failed_dirs.append(f"{path} :: {exc}")
    return {
        "cleaned_browser_dirs": cleaned_dirs,
        "cleaned_browser_details": cleaned_details,
        "failed_browser_dirs": failed_dirs,
        "cleaned_browser_count": len(cleaned_dirs),
        "reclaimed_bytes": total_reclaimed,
        "reclaimed_human": _format_bytes(total_reclaimed),
    }
def _pause_for_manual_interaction_if_headed(args, browser_key: str) -> None:
    if not getattr(args, "headed", False):
        return
    if not sys.stdin.isatty():
        return
    # In interactive headed mode we intentionally wait indefinitely for manual login/MFA.
    print(
        f"[info] Headed mode enabled for {browser_key}. "
        "This uses the local project profile (./browser/<browser>), not your regular browser profile."
    )
    print("[info] Complete login/MFA manually in the opened window, then press Enter to capture.")
    try:
        input()
    except EOFError:
        return


def _capture_screenshot_resilient(page, screenshot_path: pathlib.Path) -> dict:
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        return {"mode": "full_page", "fallback_used": False}
    except PlaywrightError as first_exc:
        first_reason = str(first_exc).splitlines()[0]
        # Fallback to viewport screenshot when full-page capture fails (common on complex sites).
        page.wait_for_timeout(300)
        try:
            page.screenshot(path=str(screenshot_path), full_page=False)
            return {
                "mode": "viewport",
                "fallback_used": True,
                "fallback_reason": first_reason,
            }
        except PlaywrightError as second_exc:
            second_reason = str(second_exc).splitlines()[0]
            raise PlaywrightError(
                "Page.screenshot failed in full_page and viewport modes. "
                f"full_page: {first_reason} | viewport: {second_reason}"
            )


def _cleanup_prefixed_files(output_dir: pathlib.Path) -> None:
    try:
        for path in output_dir.glob(f"{OUTPUT_PREFIX}*"):
            if path.is_file():
                path.unlink()
    except OSError as exc:
        _error_exit(EXIT_IO_ERR, f"Cannot clean output folder: {exc}", path=str(output_dir))


# ---------------------------------------------------------------------------
# Tile extraction
# ---------------------------------------------------------------------------
def extract_tiles(full_screenshot: "pathlib.Path | str", output_dir: pathlib.Path,
                  cols: int, rows: int, tiles: list[int]) -> list[pathlib.Path]:
    try:
        from PIL import Image as PILImage  # type: ignore
    except ImportError:
        PILImage = None
    if PILImage is None:
        _error_exit(EXIT_DEP_ERR, "Pillow is required for --crop but is not installed.", fix="Run: pip install Pillow")
    img = PILImage.open(full_screenshot)
    img_w, img_h = img.size
    tile_w = math.ceil(img_w / cols)
    tile_h = math.ceil(img_h / rows)
    paths: list[pathlib.Path] = []
    for tile_idx in tiles:
        zi = tile_idx - 1
        col, row = zi % cols, zi // cols
        left, upper = col * tile_w, row * tile_h
        right, lower = min(left + tile_w, img_w), min(upper + tile_h, img_h)
        tile_img = img.crop((left, upper, right, lower))
        tile_path = output_dir / f"{OUTPUT_PREFIX}tile_{tile_idx}.png"
        tile_img.save(tile_path)
        paths.append(tile_path)
    return paths


# ---------------------------------------------------------------------------
# Regex / resource helpers
# ---------------------------------------------------------------------------
def _compile_regex_or_exit(pattern: Optional[str]) -> Optional["re.Pattern[str]"]:
    if pattern is None:
        return None
    try:
        return re.compile(pattern)
    except re.error as exc:
        _error_exit(EXIT_BAD_ARGS, f"Invalid --resources-regex value: {pattern!r}", reason=str(exc))


def _looks_downloadable_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract_resource_candidates_from_html(html: str, base_url: str) -> set[str]:
    candidates: set[str] = set()
    for match in re.findall(r"(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]", html, flags=re.IGNORECASE):
        abs_url = urljoin(base_url, match.strip())
        if _looks_downloadable_url(abs_url):
            candidates.add(abs_url)
    for match in re.findall(r"url\(([^)]+)\)", html, flags=re.IGNORECASE):
        token = match.strip().strip("\"'")
        abs_url = urljoin(base_url, token)
        if _looks_downloadable_url(abs_url):
            candidates.add(abs_url)
    return candidates


def _download_resources(
    urls: list[str],
    output_dir: pathlib.Path,
    timeout_seconds: int = 20,
    allowed_host: str = "",
    allow_external_raw: Optional[str] = None,
) -> tuple[list[pathlib.Path], list[str], list[str]]:
    import urllib.request as _urllib_req

    class _NoRedirectHandler(_urllib_req.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):  # type: ignore[override]
            return None

    opener = _urllib_req.build_opener(_NoRedirectHandler)
    allow_all_external = allow_external_raw is not None and allow_external_raw == ""
    allow_regex = _compile_allow_external_regex_or_exit(allow_external_raw)
    allowed_host_norm = (allowed_host or "").lower().split(":")[0]

    downloaded: list[pathlib.Path] = []
    failures: list[str] = []
    skipped: list[str] = []

    for idx, url in enumerate(urls, start=1):
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
            failures.append(f"{url} :: blocked: scheme '{parsed.scheme}' not allowed")
            continue

        resource_host = (parsed.hostname or "").lower()
        if resource_host and not _host_is_local_allowed_default(resource_host):
            if resource_host != allowed_host_norm:
                if not _external_url_allowed(url, allow_regex, allow_all_external):
                    skipped.append(url)
                    continue

        if resource_host != allowed_host_norm and _is_private_host(resource_host):
            failures.append(f"{url} :: blocked: private/internal host")
            continue

        suffix = pathlib.Path(parsed.path).suffix.lower()
        if not suffix or len(suffix) > 10 or not re.fullmatch(r"\.[a-z0-9]+", suffix):
            suffix = ".bin"
        target = output_dir / f"{OUTPUT_PREFIX}resource_{idx:03d}{suffix}"
        req = Request(url, headers={"User-Agent": f"page2context/{__version__}"})
        try:
            with opener.open(req, timeout=timeout_seconds) as response:
                data = response.read(RESOURCE_MAX_BYTES + 1)
                if len(data) > RESOURCE_MAX_BYTES:
                    failures.append(f"{url} :: blocked: response exceeds {RESOURCE_MAX_BYTES // (1024*1024)} MB limit")
                    continue
            target.write_bytes(data)
            downloaded.append(target)
        except Exception as exc:
            failures.append(f"{url} :: {exc}")

    return downloaded, failures, skipped


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------
def _state_dir() -> pathlib.Path:
    custom = os.environ.get(STATE_DIR_ENV)
    if custom:
        return pathlib.Path(custom).expanduser()
    return pathlib.Path.home() / ".cache" / "page2context"


def _state_file() -> pathlib.Path:
    return _state_dir() / STATE_FILE_NAME


def _load_artifact_history() -> list[str]:
    sf = _state_file()
    if not sf.exists():
        return []
    try:
        raw = json.loads(sf.read_text(encoding="utf-8"))
        return [p for p in raw if isinstance(p, str)] if isinstance(raw, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_artifact_history(paths: list[str]) -> None:
    sd = _state_dir()
    sf = _state_file()
    try:
        sd.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps(paths, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        _error_exit(EXIT_IO_ERR, f"Cannot write artifact history: {exc}", path=str(sf))


def _record_artifacts(paths: list[str]) -> None:
    existing = _load_artifact_history()
    deduped = list(dict.fromkeys(existing + paths))
    alive = [p for p in deduped if pathlib.Path(p).exists()]
    _save_artifact_history(alive)


def _clean_historical_artifacts() -> dict:
    history = _load_artifact_history()
    cleaned: list[str] = []
    failed: list[str] = []
    kept: list[str] = []
    for entry in history:
        path = pathlib.Path(entry)
        if not path.exists():
            continue
        if not path.is_file() or not path.name.startswith(OUTPUT_PREFIX):
            kept.append(str(path))
            continue
        try:
            path.unlink()
            cleaned.append(str(path))
        except OSError as exc:
            failed.append(f"{path} :: {exc}")
            kept.append(str(path))
    _save_artifact_history(kept)
    return {"cleaned": cleaned, "failed": failed, "cleaned_files": len(cleaned)}


def _browser_install_hint(exc: "PlaywrightError", browser_key: str) -> Optional[str]:
    raw = str(exc)
    if "Executable doesn't exist" in raw or "executable doesn't exist" in raw:
        pw_engine = PROFILE_KEY_TO_BROWSER_TYPE.get(browser_key, browser_key)
        make_target_map = {
            "chrome": "setup-chromium", "chromium": "setup-chromium",
            "edge": "setup-edge", "brave": "setup-brave",
            "firefox": "setup-firefox",
            "safari": "setup-webkit", "webkit": "setup-webkit",
        }
        make_target = make_target_map.get(browser_key, f"setup-{pw_engine}")
        py = sys.executable
        return (
            f"Browser '{browser_key}' is not installed for Playwright. "
            f"Run:  {py} -m playwright install {pw_engine}  "
            f"(or:  make {make_target})"
        )
    return None


LOCK_FILE_NAME = "clean_temp.lock"
DEFAULT_CLEAN_WAIT_SECONDS = 60
LOCK_STALE_SECONDS = 6 * 60 * 60


def _lock_file_path() -> pathlib.Path:
    return _state_dir() / LOCK_FILE_NAME


def _acquire_clean_lock(wait_seconds: int = DEFAULT_CLEAN_WAIT_SECONDS, poll_seconds: float = 0.25) -> Optional[pathlib.Path]:
    lock_path = _lock_file_path()
    deadline = time.time() + max(0, int(wait_seconds))
    while True:
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"pid={os.getpid()}\n")
                f.write(f"started={time.time()}\n")
            return lock_path
        except FileExistsError:
            try:
                st = lock_path.stat()
                if time.time() - st.st_mtime > LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.time() >= deadline:
                _error_exit(
                    EXIT_IO_ERR,
                    "Timed out waiting for another page2context instance to finish (clean-temp lock).",
                    hint=(
                        "Another page2context run seems to be active. Wait and retry. "
                        f"If you're sure no run is active, delete the lock file: {lock_path}"
                    ),
                )
            time.sleep(poll_seconds)


def _release_clean_lock(lock_path: Optional[pathlib.Path]) -> None:
    if lock_path is None:
        return
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def _is_system_temp_child(path: pathlib.Path) -> bool:
    try:
        tmp_root = pathlib.Path(tempfile.gettempdir()).resolve()
        path.resolve().relative_to(tmp_root)
        return True
    except Exception:
        return False


def _clean_temp_root_p2cxt_artifacts() -> dict:
    tmp_root = pathlib.Path(tempfile.gettempdir()).resolve()
    cleaned: list[str] = []
    failed: list[str] = []
    try:
        candidates = [p for p in tmp_root.iterdir() if p.is_dir() and p.name.startswith("p2cxt_")]
    except OSError as exc:
        return {"temp_cleaned": [], "temp_failed": [f"{tmp_root} :: {exc}"], "temp_cleaned_files": 0, "temp_cleaned_dirs": 0}

    for d in candidates:
        if not _is_system_temp_child(d):
            continue
        try:
            for file_path in d.rglob(f"{OUTPUT_PREFIX}*"):
                try:
                    if file_path.is_file() and file_path.name.startswith(OUTPUT_PREFIX):
                        file_path.unlink()
                        cleaned.append(str(file_path))
                except OSError as exc:
                    failed.append(f"{file_path} :: {exc}")
        except OSError as exc:
            failed.append(f"{d} :: {exc}")

    cleaned_dirs: list[str] = []
    for d in candidates:
        try:
            for sub in sorted([p for p in d.rglob("*") if p.is_dir() and p.name.startswith("p2cxt_")], key=lambda p: len(str(p)), reverse=True):
                if not _is_system_temp_child(sub):
                    continue
                try:
                    if not any(sub.iterdir()):
                        sub.rmdir()
                        cleaned_dirs.append(str(sub))
                except OSError:
                    pass
            if not any(d.iterdir()):
                d.rmdir()
                cleaned_dirs.append(str(d))
        except OSError:
            continue

    return {
        "temp_cleaned": cleaned,
        "temp_failed": failed,
        "temp_cleaned_files": len(cleaned),
        "temp_cleaned_dirs": len(cleaned_dirs),
        "temp_cleaned_dirs_list": cleaned_dirs,
    }
def main() -> None:
    global _profile_source_output
    args = parse_args()

    clean_result = None
    temp_clean_result = None
    browser_clean_result = None

    if args.clean_temp:
        lock_path: Optional[pathlib.Path] = None
        try:
            lock_path = _acquire_clean_lock()
            clean_result = _clean_historical_artifacts()
            temp_clean_result = _clean_temp_root_p2cxt_artifacts()
        finally:
            _release_clean_lock(lock_path)

    if args.clean_browsers:
        browser_clean_result = _clean_selected_browser_profiles(args.clean_browsers)

    if not args.url:
        payload: dict = {
            "version": __version__,
            "output": [],
            "files": [],
        }
        if clean_result is not None:
            payload.update(clean_result)
        if temp_clean_result is not None:
            payload.update(temp_clean_result)
        if browser_clean_result is not None:
            payload.update(browser_clean_result)
        if clean_result is not None:
            _success("Historical temporary artifacts cleaned.", **payload)
        elif browser_clean_result is not None:
            _success("Browser profile directories cleaned.", **payload)
        return

    try:
        viewport_w, viewport_h = parse_size(args.size)
    except _CliArgError as exc:
        _error_exit(EXIT_BAD_ARGS, exc.message, **exc.extra)
    try:
        post_load_wait_ms = parse_wait_ms(args.post_load_wait_ms)
    except _CliArgError as exc:
        _error_exit(EXIT_BAD_ARGS, exc.message, **exc.extra)

    resources_regex = _compile_regex_or_exit(args.resources_regex)
    js_file_path, js_source = _load_js_file(args.run_js_file)

    selected_profile_key = args.selected_browser
    profile_source_dir = _ensure_local_browser_profile_dir(selected_profile_key)
    _profile_source_output = str(profile_source_dir)
    profile_used = False
    selected_browser_type = PROFILE_KEY_TO_BROWSER_TYPE.get(selected_profile_key, "chromium")

    if args.output:
        output_dir = pathlib.Path(args.output)
    else:
        try:
            output_dir = pathlib.Path(tempfile.mkdtemp(prefix="p2cxt_run_", dir=tempfile.gettempdir()))
        except OSError as exc:
            _error_exit(
                EXIT_IO_ERR,
                "Could not create a temporary output directory.",
                reason=str(exc),
                hint="Pass --output <DIR> to write outputs to a specific directory.",
            )

    output_already_exists = output_dir.exists()
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_already_exists:
        _cleanup_prefixed_files(output_dir)

    full_screenshot = output_dir / f"{OUTPUT_PREFIX}screenshot.png"
    console_log_path = output_dir / f"{OUTPUT_PREFIX}console.log"

    crop_parsed = None
    if args.crop:
        try:
            crop_parsed = parse_crop(args.crop)
        except _CliArgError as exc:
            _error_exit(EXIT_BAD_ARGS, exc.message, **exc.extra)

    html           = ""
    script_result  = None
    screenshot_meta = {"mode": "full_page", "fallback_used": False}
    console_lines: list[str] = []
    def _log_console(line: str) -> None:
        console_lines.append(line)
    observed_urls: set[str] = set()
    try:
        with sync_playwright() as p:
            browser_type = getattr(p, selected_browser_type)
            try:
                context = browser_type.launch_persistent_context(
                    user_data_dir=str(profile_source_dir),
                    headless=not args.headed,
                )
                page = context.pages[0] if context.pages else context.new_page()
                profile_used = True
            except PlaywrightError as exc:
                hint = _browser_install_hint(exc, selected_profile_key or selected_browser_type)
                if hint:
                    _error_exit(EXIT_NAVIGATION_ERR, hint,
                                fix=f"{sys.executable} -m playwright install {selected_browser_type}")
                raise
            if args.console_log:
                page.on("console",       lambda msg: _log_console(f"[console:{msg.type}] {msg.text}"))
                page.on("pageerror",     lambda err: _log_console(f"[pageerror] {err}"))
                page.on("requestfailed", lambda req: _log_console(
                    f"[requestfailed] {req.url} :: "
                    + (req.failure.get("errorText", "unknown") if isinstance(req.failure, dict) else "unknown")))
            page.on("request",  lambda req:  observed_urls.add(req.url))
            page.on("response", lambda resp: observed_urls.add(resp.url))
            page.set_viewport_size({"width": viewport_w, "height": viewport_h})
            page.goto(args.url, wait_until="networkidle", timeout=30_000)
            if post_load_wait_ms > 0:
                page.wait_for_timeout(post_load_wait_ms)
            _pause_for_manual_interaction_if_headed(args, selected_profile_key)
            if js_source is not None:
                try:
                    script_result = page.evaluate(
                        """async (source) => {
                            const runner = new Function("return (async () => {\\n" + source + "\\n})()");
                            return await runner();
                        }""",
                        js_source,
                    )
                    if args.console_log and js_file_path is not None:
                        _log_console(f"[script] completed {js_file_path}")
                except PlaywrightError as exc:
                    if args.console_log:
                        _log_console(f"[script:error] {exc}")
                        _write_console_log(console_log_path, console_lines)
                    _error_exit(EXIT_NAVIGATION_ERR,
                                f"JS execution failed for file: {args.run_js_file}",
                                reason=str(exc).splitlines()[0],
                                js_file=str(js_file_path) if js_file_path else args.run_js_file)
            screenshot_meta = _capture_screenshot_resilient(page, full_screenshot)
            html = page.content()
            if args.headed:
                # Keep the visible browser open indefinitely until the user closes it manually.
                print("[info] Capture completed. Close the browser window manually to finish.")
                try:
                    page.wait_for_event("close", timeout=0)
                except PlaywrightError:
                    pass
            try:
                context.close()
            except PlaywrightError:
                pass
    except PlaywrightError as exc:
        if args.console_log:
            _log_console(f"[navigation:error] {exc}")
            _write_console_log(console_log_path, console_lines)
        raw = str(exc)
        hint = _browser_install_hint(exc, selected_profile_key or selected_browser_type)
        if hint:
            _error_exit(EXIT_NAVIGATION_ERR, hint,
                        fix=f"{sys.executable} -m playwright install {selected_browser_type}")
        if   "ERR_NAME_NOT_RESOLVED"     in raw: reason = "DNS resolution failed - host not found."
        elif "ERR_CONNECTION_REFUSED"    in raw: reason = "Connection refused - nothing listening at that address."
        elif "ERR_CONNECTION_TIMED_OUT"  in raw or "Timeout" in raw: reason = "Connection timed out."
        elif "ERR_INTERNET_DISCONNECTED" in raw: reason = "No internet connection."
        else: reason = raw.splitlines()[0]
        _error_exit(EXIT_NAVIGATION_ERR, f"Could not load URL: {args.url}", reason=reason, url=args.url)
    if args.console_log:
        _write_console_log(console_log_path, console_lines)
    # -- Tile extraction ---------------------------------------------------
    tile_paths: list[pathlib.Path] = []
    if crop_parsed:
        try:
            cols, rows, tiles = crop_parsed
            tile_paths = extract_tiles(full_screenshot, output_dir, cols, rows, tiles)
        except Exception as exc:
            _error_exit(EXIT_IO_ERR, f"Crop failed: {exc}", screenshot=str(full_screenshot))
    # -- Optional resource download ----------------------------------------
    resource_paths:       list[pathlib.Path] = []
    resource_failures:    list[str]          = []
    resource_skipped:     list[str]          = []
    matched_resource_urls: list[str]         = []
    if resources_regex is not None:
        candidates = _extract_resource_candidates_from_html(html, args.url)
        for obs in observed_urls:
            if _looks_downloadable_url(obs):
                candidates.add(obs)
        matched_resource_urls = sorted(u for u in candidates if resources_regex.search(u))
        resource_paths, resource_failures, resource_skipped = _download_resources(
            matched_resource_urls,
            output_dir,
            allowed_host=urlparse(args.url).hostname or "",
            allow_external_raw=args.allow_external_urls,
        )
    # -- Write Markdown ----------------------------------------------------
    md_path   = output_dir / f"{OUTPUT_PREFIX}context.md"
    html_path = output_dir / f"{OUTPUT_PREFIX}html.html"
    try:
        html_path.write_text(html, encoding="utf-8")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Page context: {args.url}\n\n")
            if tile_paths and crop_parsed:
                cols, rows, tiles = crop_parsed
                f.write("## Screenshots\n\n")
                f.write(f"> Grid: {cols}x{rows} | captured tiles: {', '.join(str(t) for t in tiles)}\n\n")
                for i, (tile_idx, tile_path) in enumerate(zip(tiles, tile_paths), start=1):
                    f.write(f"### Screenshot {i} (tile {tile_idx})\n\n")
                    f.write(f"![tile {tile_idx}]({tile_path.name})\n\n")
            else:
                f.write("## Screenshot\n\n")
                f.write(f"![{args.url}]({full_screenshot.name})\n\n")
            f.write("## DOM\n\n")
            f.write(f"See [{html_path.name}]({html_path.name}) for the full DOM HTML.\n")
            if args.console_log:
                f.write("\n## Console and Browser Errors\n\n")
                f.write(f"See [{console_log_path.name}]({console_log_path.name}) for captured console output and browser/navigation errors.\n")
            if js_file_path is not None:
                f.write("\n## Executed JS\n\n")
                f.write(f"- File: `{js_file_path}`\n")
                f.write(f"- Result: `{script_result}`\n")
            if profile_source_dir is not None:
                f.write("\n## Browser Profile\n\n")
                f.write(f"- Browser: `{selected_profile_key}`\n")
                f.write(f"- Local profile dir: `{profile_source_dir}`\n")
                f.write(f"- Used as persistent profile: `{profile_used}`\n")
                f.write(f"- Headless mode: `{not args.headed}`\n")
            if resources_regex is not None:
                f.write("\n## Downloaded Resources\n\n")
                f.write(f"Regex: `{args.resources_regex}`\n\n")
                for rp in resource_paths:
                    f.write(f"- {rp.name}\n")
                if not resource_paths:
                    f.write("- No resources matched and downloaded.\n")
                if resource_skipped:
                    f.write("\n### Skipped (external URLs blocked)\n\n")
                    for u in resource_skipped:
                        f.write(f"- {u}\n")
                if resource_failures:
                    f.write("\n### Resource download failures\n\n")
                    for failure in resource_failures:
                        f.write(f"- {failure}\n")
    except OSError as exc:
        _error_exit(EXIT_IO_ERR, f"Cannot write output file: {exc}", path=str(md_path))
    # -- Build result dict -------------------------------------------------
    chrome_profile_source_value = (
        str(profile_source_dir)
        if selected_profile_key == "chrome" and profile_source_dir is not None
        else ""
    )
    result: dict = {
        "version":              __version__,
        "url":                  args.url,
        "viewport":             f"{viewport_w}x{viewport_h}",
        "post_load_wait_ms":    post_load_wait_ms,
        "output_dir":           str(output_dir),
        "context":              str(md_path),
        "html":                 str(html_path),
        "screenshot":           str(full_screenshot),
        # Always: the real profile source used for navigation (any browser), or "".
        "browser_profile_source": str(profile_source_dir) if profile_source_dir is not None else "",
        # Backward compatibility: keep chrome_profile_source behavior (only populated in chrome mode)
        "chrome_profile_source": chrome_profile_source_value,
    }
    if clean_result is not None:
        result["cleanup_before_run"] = clean_result
    if temp_clean_result is not None:
        result["cleanup_temp_root"] = temp_clean_result
    if browser_clean_result is not None:
        result["cleanup_browser_profiles"] = browser_clean_result
    if args.console_log:
        result["console_log"] = str(console_log_path)
    if js_file_path is not None:
        result["script"] = {"file": str(js_file_path), "result": script_result}
    if screenshot_meta.get("fallback_used"):
        result["screenshot_capture"] = screenshot_meta
    if profile_source_dir is not None:
        result["browser_profile"] = {
            "browser": selected_profile_key,
            "source": str(profile_source_dir),
            "local_dir": str(profile_source_dir),
            "used": profile_used,
            "headless": (not args.headed),
        }
        if selected_profile_key == "chrome":
            result["chrome_profile"] = {
                "source": str(profile_source_dir),
                "local_dir": str(profile_source_dir),
                "used": profile_used,
                "headless": (not args.headed),
            }
    created_files: list[pathlib.Path] = [full_screenshot, md_path, html_path]
    if args.console_log:
        created_files.append(console_log_path)
    created_files.extend(resource_paths)
    created_files.extend(tile_paths)
    absolute_files = [str(p.resolve()) for p in created_files]
    result["output"] = absolute_files
    result["files"]  = absolute_files
    _record_artifacts(absolute_files)
    if crop_parsed:
        cols, rows, tiles = crop_parsed
        result["crop"] = {
            "grid":  f"{cols}x{rows}",
            "tiles": tiles,
            "files": [str(p.resolve()) for p in tile_paths],
        }
    if resources_regex is not None:
        result["resources"] = {
            "regex":        args.resources_regex,
            "matched_urls": matched_resource_urls,
            "files":        [str(p.resolve()) for p in resource_paths],
            "failed":       resource_failures,
            "skipped":      resource_skipped,
            "skip_reason":  "external URLs blocked by default; use --allow-external-urls to permit",
        }
    _success("Page captured successfully.", **result)
if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        _error_exit(EXIT_UNEXPECTED, "An unexpected error occurred.", detail=traceback.format_exc().strip())
