---
name: page-2-context
description: Capture any webpage (screenshot + live DOM HTML) into `p2cxt_*` artifacts so you can visually understand a page's layout, CSS and structure. Use this when the user asks you to inspect, analyse or replicate any web page — especially localhost dev servers.
---

# page2context

Capture a webpage (full-page screenshot + live DOM HTML) into `p2cxt_context.md`
plus a separate fixed DOM file `p2cxt_html.html`.

## When to use

- User asks you to inspect, replicate or fix the layout of a web page
- User wants you to analyse CSS, colours, spacing or component structure
- User shows you a `localhost` dev server and wants visual context
- You need to compare what a page looks like versus what the code says

## How to call

Always add `--json` so you can parse the result reliably.

```bash
python page2context.py [--clean-temp] [--url "<URL>"] [--size <WxH>] [--crop <COLSxROWS:TILES>] [--console-log] [--chrome-profile-dir [DIR]] [--run-js-file <PATH>] [--post-load-wait-ms <MS>] [--resources-regex <REGEX>] [--output <DIR>] --json
```

`--url` is required unless using only `--clean-temp`.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--url` | ✅ | — | URL to capture (always quote it) |
| `--size` | ❌ | `1280x720` | Viewport: `1920x1080`, `375x812`, etc. |
| `--crop` | ❌ | *(none)* | Capture only specific grid tiles — see below |
| `--clean-temp` | ❌ | *(flag)* | Clean historical `p2cxt_*` artifacts from the history cache |
| `--console-log` | ❌ | *(flag)* | Save console/page/navigation errors to `p2cxt_console.log` |
| `--chrome-profile-dir` | ❌ | *(none)* | Copy Chrome user-data dir to a temp folder, use that copy for this run, then delete it. Useful to capture pages that require an active logged-in session. **Original profile is never modified.** Pass empty (`""`) to auto-detect. |
| `--edge-profile-dir` | ❌ | *(none)* | Same as above but for Microsoft Edge. **Original profile is never modified.** |
| `--brave-profile-dir` | ❌ | *(none)* | Same as above but for Brave. **Original profile is never modified.** |
| `--firefox-profile-dir` | ❌ | *(none)* | Same as above but for Firefox. Pass root dir or specific profile folder; empty auto-detects. **Original profile is never modified.** |
| `--safari-profile-dir` | ❌ | *(none)* | Same as above but for Safari (macOS only). **Original profile is never modified.** |
| `--chromium-profile-dir` | ❌ | *(none)* | Same as above but for Chromium. **Original profile is never modified.** |
| `--webkit-profile-dir` | ❌ | *(none)* | Same as above but for Playwright WebKit. **Original profile is never modified.** |
| | | | ⚠️ Only **one** browser profile flag per run |
| `--run-js-file` | ❌ | *(none)* | Execute JS file in page and wait for completion |
| `--post-load-wait-ms` | ❌ | `0` | Extra wait in milliseconds after page load and before `--run-js-file`/screenshot |
| `--resources-regex` | ❌ | *(none)* | Download resources whose URL matches regex from HTML + observed traffic |
| `--output` | ❌ | `page2context` | Output folder name |
| `--json` | ✅ | *(flag)* | Always pass this for structured output |

### Crop parameter

Format: `COLSxROWS:TILE[,TILE,...]`

Divides the full-page screenshot into a COLS×ROWS grid. Tiles are numbered
left-to-right, top-to-bottom from 1. Each tile is saved as a separate PNG.

```
--crop "3x9:1,27"   → tile 1 (top-left) + tile 27 (bottom-right)
--crop "2x4:1,2,3"  → first three tiles of a 2×4 grid
--resources-regex "\\.(css|js)(\\?|$)" → download CSS/JS resources found in source/network
--clean-temp → clean historical `p2cxt_*` files tracked in cache, then exit (or continue if --url is present)
--console-log → write console and browser/page/navigation errors to p2cxt_console.log
--chrome-profile-dir "~/.config/google-chrome" → run with a temporary copied Chrome profile, cleaned at script end
--chrome-profile-dir "" → auto-detect first default Chrome profile; errors if not found
--firefox-profile-dir "" → auto-detect first default Firefox profile; errors if not found
--edge-profile-dir "" → auto-detect first default Edge profile; errors if not found
--brave-profile-dir "" → auto-detect first default Brave profile; errors if not found
--run-js-file "./script.js" → execute script in browser and wait until it finishes
--post-load-wait-ms 1200 → wait after load before running JS/screenshot (useful for animations)
--run-js-file "./test/example_log_cookies.js" --console-log → log accessible browser cookies into p2cxt_console.log
```

History cache location:

- Default: `~/.cache/page2context/artifact_history.json`
- Override: env var `P2CXT_STATE_DIR`

## Output on success (exit 0)

```json
{
  "status":     "success",
  "message":    "Page captured successfully.",
  "version":    "1.0.0",
  "url":        "https://example.com",
  "viewport":   "1280x720",
  "post_load_wait_ms": 1200,
  "output_dir": "page2context",
  "context":    "page2context/p2cxt_context.md",
  "html":       "page2context/p2cxt_html.html",
  "screenshot": "page2context/p2cxt_screenshot.png",
  "chrome_profile_source": "/home/user/.config/google-chrome",
  "cleanup_before_run": {
    "cleaned": ["/abs/path/old/p2cxt_context.md"],
    "failed": [],
    "cleaned_files": 1
  },
  "console_log": "page2context/p2cxt_console.log",
  "browser_profile": {
    "browser":   "chrome",
    "source":    "/home/user/.config/google-chrome",
    "temp_copy": "/tmp/p2cxt_chrome_copy_xxx/profile",
    "used": true,
    "cleaned": true
  },
  "chrome_profile": {
    "source":    "/home/user/.config/google-chrome",
    "temp_copy": "/tmp/p2cxt_chrome_copy_xxx/profile",
    "used": true,
    "cleaned": true
  },
  "script": {
    "file": "script.js",
    "result": "done"
  },
  "output": [
    "/abs/path/page2context/p2cxt_screenshot.png",
    "/abs/path/page2context/p2cxt_context.md",
    "/abs/path/page2context/p2cxt_html.html",
    "/abs/path/page2context/p2cxt_console.log"
  ],
  "files": [
    "/abs/path/page2context/p2cxt_screenshot.png",
    "/abs/path/page2context/p2cxt_context.md",
    "/abs/path/page2context/p2cxt_html.html",
    "/abs/path/page2context/p2cxt_console.log"
  ],
  "resources": {
    "regex": "\\.(css|js)(\\?|$)",
    "matched_urls": ["https://example.com/styles.css", "https://example.com/app.js"],
    "files": ["/abs/path/page2context/p2cxt_resource_001.css", "/abs/path/page2context/p2cxt_resource_002.js"],
    "failed": []
  },
  "crop": {
    "grid":  "3x9",
    "tiles": [1, 27],
    "files": ["/abs/path/page2context/p2cxt_tile_1.png", "/abs/path/page2context/p2cxt_tile_27.png"]
  },
  "history_file": "/home/user/.cache/page2context/artifact_history.json"
}
```

> `crop` is only present when `--crop` was used.
> Without crop, `p2cxt_screenshot.png` is the full-page image.
> `resources` is only present when `--resources-regex` is used.
> `console_log` is only present when `--console-log` is used.
> `chrome_profile_source` is always present — populated for `--chrome-profile-dir` only; `""` otherwise.
> `browser_profile` is present when any `--*-profile-dir` flag is used; `browser` field names the browser used.
> `chrome_profile` is also present (backward compat) when `--chrome-profile-dir` is used.
> `cleanup_before_run` is only present when `--clean-temp` is combined with capture.
> `history_file` is always present.
> `output`/`files` always contain absolute paths to created artifacts.
>
> **Browser profile safety**: all `--*-profile-dir` flags work by copying the user profile to a
> temporary directory. The browser runs against that copy exclusively. The original profile is
> **never opened or modified**. The temporary copy is deleted when the script exits (success or
> error). It is safe to run while the real browser is open. The main purpose is to access pages
> that require an already-authenticated session (cookies and local storage from the real browser).

Clean-only success (`--clean-temp` without `--url`):

```json
{
  "status": "success",
  "message": "Historical temporary artifacts cleaned.",
  "version": "1.0.0",
  "chrome_profile_source": "",
  "cleaned_files": 3,
  "cleaned": ["/abs/path/.../p2cxt_context.md"],
  "failed": [],
  "output": [],
  "files": []
}
```

## Output on error

```json
{
  "status":    "error",
  "exit_code": 3,
  "message":   "Could not load URL: https://example.com",
  "reason":    "DNS resolution failed - host not found."
}
```

## Exit codes

| Code | Meaning |
|------|---------|
| `0`  | Success |
| `2`  | Bad argument |
| `3`  | URL unreachable (DNS / refused / timeout) |
| `4`  | File I/O error |
| `5`  | Missing Pillow dependency |
| `99` | Unexpected error — check `detail` field |

## Suggested workflow

```
1. Run page2context with --json
2. Parse output_dir from JSON
3. Read <output_dir>/p2cxt_context.md for screenshots and structure
4. Read <output_dir>/p2cxt_html.html for full DOM HTML
5. If clean-only mode was requested, report cleaned_files/failed and stop
6. If enabled, inspect <output_dir>/p2cxt_console.log for console/navigation/browser errors
7. If enabled, inspect `chrome_profile.cleaned` to confirm ephemeral copy cleanup
8. If regex used, inspect `resources.files` and downloaded `p2cxt_resource_*` artifacts
9. If JS used, inspect `script.result` and context section "Executed JS"
10. Use all artifacts to answer layout / CSS / structure questions
11. Remember: existing `p2cxt_*` files are cleaned at run start in an existing output dir
```

## Installation

```bash
git clone https://github.com/mfuentescas/page-2-context.git
cd page-2-context
pip install -r requirements.txt
playwright install chromium
```

Or:
```bash
make setup
```
