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
import sys
import textwrap
import traceback
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
def _error_exit(code: int, message: str, **extra) -> None:
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
      --output <DIR>             Output folder          (default: page2context)
      --json                     Machine-readable JSON output (for AI callers)
    Examples:
      python page2context.py --url "https://example.com"
      python page2context.py --url "https://example.com" --size 1920x1080
      python page2context.py --url "https://example.com" --crop "3x9:1,27"
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
    parser.add_argument("--output", default="page2context", help="Output folder (default: page2context)")
    parser.add_argument("--json",   action="store_true",    help="Emit JSON output (for AI callers)")
    args = parser.parse_args()
    _json_mode = args.json
    return args
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_size(size_str: str) -> tuple[int, int]:
    try:
        w, h = size_str.lower().split("x")
        return int(w), int(h)
    except ValueError:
        _error_exit(
            EXIT_BAD_ARGS,
            f"Invalid --size value: {size_str!r}. Expected format: WIDTHxHEIGHT (e.g. 1920x1080).",
        )
def parse_crop(crop_str: str) -> tuple[int, int, list[int]]:
    try:
        grid_part, tiles_part = crop_str.split(":")
        cols_str, rows_str = grid_part.lower().split("x")
        cols, rows = int(cols_str), int(rows_str)
        tiles = [int(t.strip()) for t in tiles_part.split(",")]
    except ValueError:
        _error_exit(
            EXIT_BAD_ARGS,
            f"Invalid --crop value: {crop_str!r}. Expected format: COLSxROWS:TILE[,TILE] (e.g. 3x9:1,27).",
        )
    max_tile = cols * rows
    out_of_range = [t for t in tiles if t < 1 or t > max_tile]
    if out_of_range:
        _error_exit(
            EXIT_BAD_ARGS,
            f"Tile(s) {out_of_range} out of range for a {cols}x{rows} grid (valid: 1-{max_tile}).",
            grid=f"{cols}x{rows}",
            valid_range=[1, max_tile],
        )
    return cols, rows, tiles
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
        from PIL import Image
    except ImportError:
        _error_exit(
            EXIT_DEP_ERR,
            "Pillow is required for --crop but is not installed.",
            fix="Run: pip install Pillow",
        )
    img    = Image.open(full_screenshot)
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
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    viewport_w, viewport_h = parse_size(args.size)
    output_dir = pathlib.Path(args.output)
    output_already_exists = output_dir.exists()
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_already_exists:
        _cleanup_prefixed_files(output_dir)

    full_screenshot = output_dir / f"{OUTPUT_PREFIX}screenshot.png"
    crop_parsed = None
    if args.crop:
        crop_parsed = parse_crop(args.crop)
    # -- Browser capture -----------------------------------------------------
    html = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page()
            page.set_viewport_size({"width": viewport_w, "height": viewport_h})
            page.goto(args.url, wait_until="networkidle", timeout=30_000)
            page.screenshot(path=str(full_screenshot), full_page=True)
            html = page.content()
            browser.close()
    except PlaywrightError as exc:
        raw = str(exc)
        if   "ERR_NAME_NOT_RESOLVED"    in raw: reason = "DNS resolution failed - host not found."
        elif "ERR_CONNECTION_REFUSED"   in raw: reason = "Connection refused - nothing listening at that address."
        elif "ERR_CONNECTION_TIMED_OUT" in raw or "Timeout" in raw: reason = "Connection timed out."
        elif "ERR_INTERNET_DISCONNECTED" in raw: reason = "No internet connection."
        else: reason = raw.splitlines()[0]
        _error_exit(EXIT_NAVIGATION_ERR, f"Could not load URL: {args.url}", reason=reason, url=args.url)
    # -- Tile extraction (crop) ---------------------------------------------
    tile_paths: list[pathlib.Path] = []
    if crop_parsed:
        cols, rows, tiles = crop_parsed
        try:
            tile_paths = extract_tiles(full_screenshot, output_dir, cols, rows, tiles)
        except Exception as exc:
            _error_exit(EXIT_IO_ERR, f"Crop failed: {exc}", screenshot=str(full_screenshot))
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

    created_files: list[pathlib.Path] = [full_screenshot, md_path, html_path]
    if tile_paths:
        created_files.extend(tile_paths)

    # Stable order + absolute paths for callers that need concrete artifacts.
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
    _success("Page captured successfully.", **result)
if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        _error_exit(EXIT_UNEXPECTED, "An unexpected error occurred.", detail=traceback.format_exc().strip())
