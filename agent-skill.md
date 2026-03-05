# Skill: page2context

> Capture any webpage (screenshot + live DOM HTML) into `p2cxt_*` artifacts
> so an AI assistant can visually understand a page's layout, CSS and structure.

---

## What this skill does

Runs a real browser (Chromium by default, or Firefox/WebKit when a browser profile
flag is used) via Playwright, navigates to a URL, takes a full-page screenshot
and grabs the live DOM, then writes everything into
`<output_dir>/p2cxt_context.md` and `<output_dir>/p2cxt_html.html`.

- **No crop** → one `p2cxt_screenshot.png` + raw DOM in `p2cxt_html.html`
- **With `--crop`** → individual tile PNGs (`p2cxt_tile_1.png`, `p2cxt_tile_27.png`, …)
  in numbered sections inside `p2cxt_context.md`

Use this whenever you need to:
- Understand the CSS or layout of a page you can't see
- Capture a local dev server (`localhost`) for AI review
- Focus on a specific region of a large page (grid crop)

---

## How to call (AI instructions)

Always pass `--json` so output is machine-readable.

### Minimal call
```bash
python3 page2context.py --url "<URL>" --json
```

### Full call
```bash
python3 page2context.py \
  --clean-temp \
  --url    "<URL>" \
  --size   "<WIDTHxHEIGHT>" \
  --crop   "<COLSxROWS:TILE[,TILE]>" \
  --console-log \
  --chrome-profile-dir "<DIR>" \
  --run-js-file "<PATH>" \
  --post-load-wait-ms "<MS>" \
  --resources-regex "<REGEX>" \
  --output "<folder-name>" \
  --json
```

> Use exactly **one** of the following instead of `--chrome-profile-dir`, depending on the user's browser.
> Only one browser profile flag can be used per run — passing two returns exit code 2.

```bash
# Chrome (default — uses Chromium engine)
python3 page2context.py --url "<URL>" --chrome-profile-dir "" --json

# Microsoft Edge
python3 page2context.py --url "<URL>" --edge-profile-dir "" --json

# Brave
python3 page2context.py --url "<URL>" --brave-profile-dir "" --json

# Firefox
python3 page2context.py --url "<URL>" --firefox-profile-dir "" --json

# Safari (macOS only)
python3 page2context.py --url "<URL>" --safari-profile-dir "" --json

# Chromium (open-source build)
python3 page2context.py --url "<URL>" --chromium-profile-dir "" --json

# Playwright WebKit
python3 page2context.py --url "<URL>" --webkit-profile-dir "" --json
```

> Pass `""` to auto-detect the profile, or pass the explicit directory path.
> All flags copy the profile to a temp folder and delete it after the run — **original profile is never modified.**

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--url` | ✅ | — | URL to capture (always quote it) |
| `--size` | ❌ | `1280x720` | Viewport size, e.g. `1920x1080` or `375x812` |
| `--crop` | ❌ | *(none)* | Grid crop spec — see below |
| `--clean-temp` | ❌ | *(flag)* | Clean historical `p2cxt_*` artifacts from tracked cache |
| `--console-log` | ❌ | *(flag)* | Save console/page/navigation errors into `p2cxt_console.log` |
| `--chrome-profile-dir` | ❌ | *(none)* | Copy Chrome user-data dir to a temp folder, use that copy for this run, then delete it. Lets you capture pages that require an active logged-in session (cookies/storage from your real browser). **Your original profile is never modified or opened.** Pass empty (`""`) to auto-detect. |
| `--edge-profile-dir` | ❌ | *(none)* | Same as above but for Microsoft Edge. **Original profile is never modified.** |
| `--brave-profile-dir` | ❌ | *(none)* | Same as above but for Brave. **Original profile is never modified.** |
| `--firefox-profile-dir` | ❌ | *(none)* | Same as above but for Firefox. Pass root dir or specific profile folder; empty auto-detects. **Original profile is never modified.** |
| `--safari-profile-dir` | ❌ | *(none)* | Same as above but for Safari (macOS only). **Original profile is never modified.** |
| `--chromium-profile-dir` | ❌ | *(none)* | Same as above but for Chromium. **Original profile is never modified.** |
| `--webkit-profile-dir` | ❌ | *(none)* | Same as above but for Playwright WebKit. **Original profile is never modified.** |
| | | | ⚠️ Only **one** browser profile flag per run — passing two returns exit code 2 |
| `--run-js-file` | ❌ | *(none)* | Execute JS file in browser page and wait until it finishes |
| `--post-load-wait-ms` | ❌ | `0` | Extra wait in milliseconds after page load and before `--run-js-file`/screenshot |
| `--resources-regex` | ❌ | *(none)* | Download resources whose URL matches regex from HTML refs + observed traffic |
| `--output` | ❌ | `page2context` | Output folder |
| `--json` | ✅ for AI | *(flag)* | Always use when calling programmatically |

---

## Crop parameter explained

Format: `COLSxROWS:TILE[,TILE,...]`

Divides the full-page screenshot into a COLS×ROWS grid.
Tiles are numbered **left-to-right, top-to-bottom** starting at 1.
Each selected tile is saved as a **separate PNG** (`p2cxt_tile_N.png`).

```
3x9 grid — --crop "3x9:1,27"

+---+---+---+
| 1 | 2 | 3 |  row 1   ← tile 1 selected
+---+---+---+
| 4 | 5 | 6 |  row 2
    ...
+---+---+---+
|25 |26 |27 |  row 9   ← tile 27 selected
+---+---+---+

Output files: p2cxt_tile_1.png, p2cxt_tile_27.png
p2cxt_context.md:
  ## Screenshots
  ### Screenshot 1 (tile 1)
  ![tile 1](p2cxt_tile_1.png)
  ### Screenshot 2 (tile 27)
  ![tile 27](p2cxt_tile_27.png)
  ## DOM
  See [p2cxt_html.html](p2cxt_html.html) for the full DOM HTML.
```

---

## JSON output schema

### On success (exit code 0)

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
> `resources` is only present when `--resources-regex` was used.
> `output`/`files` are always present and contain absolute artifact paths.
> `chrome_profile_source` is always present — populated for `--chrome-profile-dir` only; `""` otherwise.
> `browser_profile` is present when any `--*-profile-dir` flag is used; contains `browser` key indicating which browser.
> `chrome_profile` is also present for backward compatibility when `--chrome-profile-dir` is used.
> `console_log` is only present when `--console-log` is used.
> `script` is only present when `--run-js-file` is used.
> `cleanup_before_run` is only present when `--clean-temp` is combined with capture.
> `history_file` is always present.
>
> **Browser profile safety**: the `--*-profile-dir` flags copy the user profile to a temporary
> directory before launching the browser. The original profile directory is **never opened or
> modified**. The temporary copy is deleted automatically when the script exits (success or error).
> This makes it safe to use even while the real browser is running. The main use case is capturing
> pages that require an authenticated session (cookies / local storage already present in the
> real browser profile).

### Clean-only success (`--clean-temp` without `--url`)

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

### On error

```json
{
  "status":    "error",
  "exit_code": 3,
  "message":   "Could not load URL: https://example.com",
  "reason":    "DNS resolution failed - host not found.",
  "url":       "https://example.com"
}
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0`  | Success |
| `2`  | Bad argument (bad `--size`, tile out of range, missing `--url`) |
| `3`  | Navigation error (DNS, refused, timeout) |
| `4`  | File I/O error |
| `5`  | Missing Pillow dependency |
| `99` | Unexpected error — check `detail` field |

---

## Suggested AI workflow

```
1. Call page2context --json
2. Check status == "success", else report reason to user and stop
3. Read <output_dir>/p2cxt_context.md — contains screenshots + structure
4. Read <output_dir>/p2cxt_html.html — contains full DOM HTML
5. If clean-only mode was requested, report cleaned_files/failed and stop
6. If enabled, read <output_dir>/p2cxt_console.log for console/navigation/browser errors
7. If enabled, inspect `browser_profile.cleaned` to confirm temp-copy cleanup
8. If provided, use `resources.files` artifacts (`p2cxt_resource_*`) for CSS/JS inspection
9. If provided, inspect `script.result` from executed JS (only run trusted JS files)
10. Use all files to answer the user's question
11. Be aware the tool cleans previous `p2cxt_*` files in an existing output dir
```

---

## Installation

```bash
git clone https://github.com/mfuentescas/page-2-context.git
cd page2context
pip install -r requirements.txt
playwright install chromium
```

Or with make:
```bash
make setup                # installs deps + Chromium
make setup-browsers       # interactive Y/n prompt for Firefox, Edge, WebKit
make setup-firefox        # Firefox only
make setup-edge           # Edge only
make setup-webkit         # WebKit only (Safari)
```

> If the tool exits with `Executable doesn't exist at ...`, run the corresponding
> `make setup-<browser>` command or `python3 -m playwright install <browser>`.

Use `test/example_log_cookies.js` as a ready-to-run sample for `--run-js-file`:

```bash
python3 page2context.py --url "<URL>" --console-log --run-js-file "./test/example_log_cookies.js" --json
```

When your JS file uses `return ...`, the value appears in `script.result`.
