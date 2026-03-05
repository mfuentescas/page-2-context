"""
page2context — Capture a webpage (screenshot + DOM) into Markdown outputs
for use as AI context (GitHub Copilot, Cursor, etc.).
Default output is human-readable. --json gives machine-readable JSON.
Exit codes follow UNIX conventions.
"""
import argparse
import json
import math
import pathlib
import re
import sys
import textwrap
import traceback
from typing import NoReturn
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright, Error as PlaywrightError
# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
def _load_version() -> str:
    version_file = pathlib.Path(__file__).parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
__version__ = _load_version()
# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------
EXIT_OK             = 0
EXIT_BAD_ARGS       = 2
EXIT_NAVIGATION_ERR = 3
EXIT_IO_ERR         = 4
EXIT_DEP_ERR        = 5
EXIT_UNEXPECTED     = 99

OUTPUT_PREFIX = "p2cxt_"
# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
_json_mode: bool = False
def _emit(payload: dict) -> None:
    if _json_mode:
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    else:
        _emit_text(payload)
def _emit_text(payload: dict) -> None:
    status = payload.get("status", "")
    msg    = payload.get("message", "")
    if status == "success":
        outputs = payload.get("output")
        if isinstance(outputs, list) and outputs:
            print("\n".join(str(p) for p in outputs))
        else:
            # Backward-compatible fallback
            print(payload.get("output_dir", ""))
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
    elif status == "info":
        print(payload.get("syntax", ""))
def _success(message: str, **extra) -> None:
    _emit({"status": "success", "message": message, **extra})
def _error_exit(code: int, message: str, **extra) -> NoReturn:
    _emit({"status": "error", "exit_code": code, "message": message, **extra})
    sys.exit(code)
# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
SYNTAX_HELP = textwrap.dedent("""\
    page2context v{version}
    Capture a webpage (screenshot + DOM) into Markdown outputs for AI context.
    Usage:
      python page2context.py --url "<URL>" [OPTIONS]
    Required:
      --url  "<URL>"              URL to capture, e.g. "http://localhost:4200/"
    Optional:
      --size  <WIDTHxHEIGHT>     Viewport size          (default: 1280x720)
      --crop  <COLSxROWS:TILES>  Grid crop, e.g. "3x9:1,27"
                                   Divides the full-page screenshot into a
                                   COLS x ROWS grid and saves each listed
                                   tile as a separate image (p2cxt_tile_1.png, etc.)
                                   in the output folder.
      --console-log             Save browser console/navigation errors to
                                  p2cxt_console.log in the output folder.
      --run-js-file <PATH>      Execute JavaScript file in the opened page
                                  and wait for completion.
      --resources-regex <REGEX> Download resources whose URL matches REGEX
                                   from HTML references and Playwright-observed traffic.
       --output <DIR>             Output folder          (default: page2context)
       --json                     Machine-readable JSON output (for AI callers)
    Examples:
      python page2context.py --url "https://example.com"
      python page2context.py --url "https://example.com" --size 1920x1080
      python page2context.py --url "https://example.com" --crop "3x9:1,27"
      python page2context.py --url "https://example.com" --console-log
      python page2context.py --url "https://example.com" --run-js-file "./script.js"
      python page2context.py --url "https://example.com" --resources-regex "\\.(css|js)(\\?|$)"
      python page2context.py --url "https://example.com" --size 1440x900 \\
                              --crop "2x4:1,2" --output my_capture
    Tile numbering for --crop (e.g. 3x9 grid):
      ┌───┬───┬───┐
      │ 1 │ 2 │ 3 │  row 1
      │ 4 │ 5 │ 6 │  row 2
      │ 7 │ 8 │ 9 │  row 3   max tile = COLS x ROWS
      └───┴───┴───┘
    Output:
      Prints created file paths to stdout (or JSON with --json).
""").format(version=__version__)
class _TextArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        _error_exit(
            EXIT_BAD_ARGS,
            f"Argument error: {message}",
            hint="Run without arguments to see full usage syntax.",
        )
def parse_args():
    global _json_mode
    if len(sys.argv) == 1:
        print(SYNTAX_HELP)
        sys.exit(EXIT_BAD_ARGS)
    # Pre-detect --json before argparse validates required args
    _json_mode = "--json" in sys.argv
    parser = _TextArgumentParser(
        prog="page2context",
        description="Capture a webpage screenshot and DOM HTML into Markdown outputs.",
        add_help=True,
    )
    parser.add_argument("--url",    required=True,          help="URL to capture")
    parser.add_argument("--size",   default="1280x720",     help="Viewport WIDTHxHEIGHT")
    parser.add_argument("--crop",   default=None,           help="Grid crop COLSxROWS:TILE[,TILE]")
    parser.add_argument(
        "--console-log",
        action="store_true",
        help="Save browser console, page errors, and request failures to p2cxt_console.log.",
    )
    parser.add_argument(
        "--run-js-file",
        default=None,
        help="Path to a JavaScript file to execute in the opened page and wait until it completes.",
    )
    parser.add_argument(
        "--resources-regex",
        default=None,
        help="Download resources whose URL matches this regex (checks HTML refs and observed network URLs).",
    )
    parser.add_argument("--output", default="page2context", help="Output folder (default: page2context)")
    parser.add_argument("--json",   action="store_true",    help="Emit JSON output (for AI callers)")
    args = parser.parse_args()
    _json_mode = args.json
    return args
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _CliArgError(Exception):
    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.message = message
        self.extra = extra


def parse_size(size_str: str) -> tuple[int, int]:
    parts = size_str.lower().split("x")
    if len(parts) != 2:
        raise _CliArgError(
            f"Invalid --size value: {size_str!r}. Expected format: WIDTHxHEIGHT (e.g. 1920x1080)."
        )

    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        raise _CliArgError(
            f"Invalid --size value: {size_str!r}. Expected numeric WIDTHxHEIGHT (e.g. 1920x1080)."
        )

    return width, height


def parse_crop(crop_str: str) -> tuple[int, int, list[int]]:
    cols = 0
    rows = 0
    tiles: list[int] = []

    parts = crop_str.split(":", 1)
    if len(parts) != 2:
        raise _CliArgError(
            f"Invalid --crop value: {crop_str!r}. Expected format: COLSxROWS:TILE[,TILE] (e.g. 3x9:1,27)."
        )

    grid_part, tiles_part = parts
    grid_tokens = grid_part.lower().split("x", 1)
    if len(grid_tokens) != 2:
        raise _CliArgError(f"Invalid --crop grid: {grid_part!r}. Expected COLSxROWS.")

    try:
        cols = int(grid_tokens[0])
        rows = int(grid_tokens[1])
        tiles = [int(t.strip()) for t in tiles_part.split(",") if t.strip()]
    except ValueError:
        raise _CliArgError(
            f"Invalid --crop value: {crop_str!r}. Tiles and grid values must be integers."
        )

    if cols < 1 or rows < 1:
        raise _CliArgError(f"Invalid --crop grid: {cols}x{rows}. COLS and ROWS must be >= 1.")
    if not tiles:
        raise _CliArgError(f"Invalid --crop tiles in {crop_str!r}. Provide at least one tile index.")

    max_tile = cols * rows
    out_of_range = [t for t in tiles if t < 1 or t > max_tile]
    if out_of_range:
        raise _CliArgError(
            f"Tile(s) {out_of_range} out of range for a {cols}x{rows} grid (valid: 1-{max_tile}).",
            grid=f"{cols}x{rows}",
            valid_range=[1, max_tile],
        )
    return cols, rows, tiles


def _load_js_file(path_str: str | None) -> tuple[pathlib.Path | None, str | None]:
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
            if lines:
                f.write("\n".join(lines))
                f.write("\n")
            else:
                f.write("[info] No console/page errors captured.\n")
    except OSError as exc:
        _error_exit(EXIT_IO_ERR, f"Cannot write console log: {exc}", path=str(path))


def _cleanup_prefixed_files(output_dir: pathlib.Path) -> None:
    """Remove previously generated files in output_dir to keep runs deterministic."""
    try:
        for path in output_dir.glob(f"{OUTPUT_PREFIX}*"):
            if path.is_file():
                path.unlink()
    except OSError as exc:
        _error_exit(EXIT_IO_ERR, f"Cannot clean output folder: {exc}", path=str(output_dir))


def extract_tiles(
    full_screenshot: pathlib.Path | str,
    output_dir: pathlib.Path,
    cols: int,
    rows: int,
    tiles: list[int],
) -> list[pathlib.Path]:
    """
    Cut each requested tile from the full screenshot and save as
    p2cxt_tile_<N>.png inside output_dir. Returns the list of created paths.
    """
    try:
        from PIL import Image as PILImage
    except ImportError:
        PILImage = None

    if PILImage is None:
        _error_exit(
            EXIT_DEP_ERR,
            "Pillow is required for --crop but is not installed.",
            fix="Run: pip install Pillow",
        )

    img    = PILImage.open(full_screenshot)
    img_w, img_h = img.size
    tile_w = math.ceil(img_w / cols)
    tile_h = math.ceil(img_h / rows)
    paths: list[pathlib.Path] = []
    for tile_idx in tiles:
        zero_idx = tile_idx - 1
        col   = zero_idx % cols
        row   = zero_idx // cols
        left  = col  * tile_w
        upper = row  * tile_h
        right = min(left  + tile_w, img_w)
        lower = min(upper + tile_h, img_h)
        tile_img  = img.crop((left, upper, right, lower))
        tile_path = output_dir / f"{OUTPUT_PREFIX}tile_{tile_idx}.png"
        tile_img.save(tile_path)
        paths.append(tile_path)
    return paths


def _compile_regex_or_exit(pattern: str | None) -> re.Pattern[str] | None:
    if pattern is None:
        return None
    try:
        return re.compile(pattern)
    except re.error as exc:
        _error_exit(
            EXIT_BAD_ARGS,
            f"Invalid --resources-regex value: {pattern!r}",
            reason=str(exc),
        )


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
        token = match.strip().strip('"\'')
        abs_url = urljoin(base_url, token)
        if _looks_downloadable_url(abs_url):
            candidates.add(abs_url)

    return candidates


def _download_resources(
    urls: list[str],
    output_dir: pathlib.Path,
    timeout_seconds: int = 20,
) -> tuple[list[pathlib.Path], list[str]]:
    downloaded: list[pathlib.Path] = []
    failures: list[str] = []

    for idx, url in enumerate(urls, start=1):
        parsed = urlparse(url)
        suffix = pathlib.Path(parsed.path).suffix.lower()
        if not suffix or len(suffix) > 10 or not re.fullmatch(r"\.[a-z0-9]+", suffix):
            suffix = ".bin"

        target = output_dir / f"{OUTPUT_PREFIX}resource_{idx:03d}{suffix}"

        req = Request(url, headers={"User-Agent": f"page2context/{__version__}"})
        try:
            with urlopen(req, timeout=timeout_seconds) as response:
                data = response.read()
            target.write_bytes(data)
            downloaded.append(target)
        except Exception as exc:
            failures.append(f"{url} :: {exc}")

    return downloaded, failures
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    try:
        viewport_w, viewport_h = parse_size(args.size)
    except _CliArgError as exc:
        _error_exit(EXIT_BAD_ARGS, exc.message, **exc.extra)

    resources_regex = _compile_regex_or_exit(args.resources_regex)
    js_file_path, js_source = _load_js_file(args.run_js_file)
    output_dir = pathlib.Path(args.output)
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
    # -- Browser capture -----------------------------------------------------
    html = ""
    script_result = None
    console_lines: list[str] = []

    def _log_console(line: str) -> None:
        console_lines.append(line)

    observed_urls: set[str] = set()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page()

            if args.console_log:
                def _track_console(msg):
                    _log_console(f"[console:{msg.type}] {msg.text}")

                def _track_page_error(err):
                    _log_console(f"[pageerror] {err}")

                def _track_request_failed(req):
                    failure = req.failure
                    failure_text = failure["errorText"] if isinstance(failure, dict) and "errorText" in failure else "unknown"
                    _log_console(f"[requestfailed] {req.url} :: {failure_text}")

                page.on("console", _track_console)
                page.on("pageerror", _track_page_error)
                page.on("requestfailed", _track_request_failed)

                browser.on("disconnected", lambda _browser: _log_console("[browser] disconnected"))

            def _track_request(req):
                observed_urls.add(req.url)

            def _track_response(resp):
                observed_urls.add(resp.url)

            page.on("request", _track_request)
            page.on("response", _track_response)

            page.set_viewport_size({"width": viewport_w, "height": viewport_h})
            page.goto(args.url, wait_until="networkidle", timeout=30_000)

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
                    _error_exit(
                        EXIT_NAVIGATION_ERR,
                        f"JS execution failed for file: {args.run_js_file}",
                        reason=str(exc).splitlines()[0],
                        js_file=str(js_file_path) if js_file_path else args.run_js_file,
                    )

            page.screenshot(path=str(full_screenshot), full_page=True)
            html = page.content()
            browser.close()
    except PlaywrightError as exc:
        if args.console_log:
            _log_console(f"[navigation:error] {exc}")
            _write_console_log(console_log_path, console_lines)
        raw = str(exc)
        if   "ERR_NAME_NOT_RESOLVED"    in raw: reason = "DNS resolution failed - host not found."
        elif "ERR_CONNECTION_REFUSED"   in raw: reason = "Connection refused - nothing listening at that address."
        elif "ERR_CONNECTION_TIMED_OUT" in raw or "Timeout" in raw: reason = "Connection timed out."
        elif "ERR_INTERNET_DISCONNECTED" in raw: reason = "No internet connection."
        else: reason = raw.splitlines()[0]
        _error_exit(EXIT_NAVIGATION_ERR, f"Could not load URL: {args.url}", reason=reason, url=args.url)
    if args.console_log:
        _write_console_log(console_log_path, console_lines)
    # -- Tile extraction (crop) ---------------------------------------------
    tile_paths: list[pathlib.Path] = []
    if crop_parsed:
        cols, rows, tiles = crop_parsed
        try:
            tile_paths = extract_tiles(full_screenshot, output_dir, cols, rows, tiles)
        except Exception as exc:
            _error_exit(EXIT_IO_ERR, f"Crop failed: {exc}", screenshot=str(full_screenshot))

    # -- Optional resource download (regex) --------------------------------
    resource_paths: list[pathlib.Path] = []
    resource_failures: list[str] = []
    matched_resource_urls: list[str] = []
    if resources_regex is not None:
        candidates = _extract_resource_candidates_from_html(html, args.url)
        for observed in observed_urls:
            if _looks_downloadable_url(observed):
                candidates.add(observed)

        matched_resource_urls = sorted(url for url in candidates if resources_regex.search(url))
        resource_paths, resource_failures = _download_resources(matched_resource_urls, output_dir)

    # -- Write Markdown ------------------------------------------------------
    md_path = output_dir / f"{OUTPUT_PREFIX}context.md"
    html_path = output_dir / f"{OUTPUT_PREFIX}html.html"
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Page context: {args.url}\n\n")
            if tile_paths:
                # Multiple cropped tiles -> numbered Screenshots section
                cols, rows, tiles = crop_parsed
                f.write("## Screenshots\n\n")
                f.write(f"> Grid: {cols}x{rows} | captured tiles: {', '.join(str(t) for t in tiles)}\n\n")
                for i, (tile_idx, tile_path) in enumerate(zip(tiles, tile_paths), start=1):
                    f.write(f"### Screenshot {i} (tile {tile_idx})\n\n")
                    f.write(f"![tile {tile_idx}]({tile_path.name})\n\n")
            else:
                # No crop -> single full-page screenshot
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

            if resources_regex is not None:
                f.write("\n## Downloaded Resources\n\n")
                f.write(f"Regex: `{args.resources_regex}`\n\n")
                if resource_paths:
                    for rp in resource_paths:
                        f.write(f"- {rp.name}\n")
                else:
                    f.write("- No resources matched and downloaded.\n")

                if resource_failures:
                    f.write("\n### Resource download failures\n\n")
                    for failure in resource_failures:
                        f.write(f"- {failure}\n")
    except OSError as exc:
        _error_exit(EXIT_IO_ERR, f"Cannot write output file: {exc}", path=str(md_path))

    # -- Success output: emit created artifacts -----------------------------
    result: dict = {
        "version":    __version__,
        "url":        args.url,
        "viewport":   f"{viewport_w}x{viewport_h}",
        "output_dir": str(output_dir),
        "context":    str(md_path),
        "html":       str(html_path),
        "screenshot": str(full_screenshot),
    }

    if args.console_log:
        result["console_log"] = str(console_log_path)

    if js_file_path is not None:
        result["script"] = {
            "file": str(js_file_path),
            "result": script_result,
        }

    created_files: list[pathlib.Path] = [full_screenshot, md_path, html_path]
    if args.console_log:
        created_files.append(console_log_path)
    if resource_paths:
        created_files.extend(resource_paths)
    if tile_paths:
        created_files.extend(tile_paths)

    absolute_files = [str(path.resolve()) for path in created_files]
    result["output"] = absolute_files
    result["files"] = absolute_files

    if crop_parsed:
        cols, rows, tiles = crop_parsed
        result["crop"] = {
            "grid":  f"{cols}x{rows}",
            "tiles": tiles,
            "files": [str(p.resolve()) for p in tile_paths],
        }

    if resources_regex is not None:
        result["resources"] = {
            "regex": args.resources_regex,
            "matched_urls": matched_resource_urls,
            "files": [str(p.resolve()) for p in resource_paths],
            "failed": resource_failures,
        }

    _success("Page captured successfully.", **result)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        _error_exit(EXIT_UNEXPECTED, "An unexpected error occurred.", detail=traceback.format_exc().strip())
