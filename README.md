# page2context

> Capture any webpage (screenshot + live DOM HTML) into linked Markdown outputs —
> perfect for feeding visual context to GitHub Copilot, Cursor, or any AI assistant.

---

## Why?

This tool was born while migrating an Angular 17 web app to Angular 21.
The upgrade broke dozens of CSS rules and layout details — the kind of issues
that only show up visually. Comparing before and after pixel by pixel, while
asking an AI to help fix each regression, was painfully slow because no AI can
*see* your browser.

**page2context** fixes that: it opens any URL in a real browser (via Playwright),
takes a full-page screenshot, grabs the live DOM, and writes everything into
`p2cxt_context.md` + `p2cxt_html.html` (and, when requested, matching CSS/JS assets)
ready to drop into GitHub Copilot, Cursor, Claude, or any AI chat. Now the AI can
see exactly what you see, and you can compare layouts, spot CSS regressions, and
fix them without leaving your editor.

```
+----------------------+    page2context    +-----------------------------+
|  Any URL / localhost | ────────────────►  |  page2context/              |
|  (real browser)      |                    |  ├── p2cxt_context.md       |
|                      |                    |  ├── p2cxt_html.html        |
|                      |                    |  ├── p2cxt_screenshot.png   |
|                      |                    |  ├── p2cxt_resource_001.css |
|                      |                    |  ├── p2cxt_resource_002.js  |
|                      |                    |  └── p2cxt_tile_1.png (opt.) |
+----------------------+                    +-----------------------------+
                                                       │
                                                       ▼
                                          GitHub Copilot / Cursor / ...
```

### Visual Example (Prompt-Driven Run)

Prompt used:

> Use page2context to load github.com, wait 5 seconds, then capture tile #5 of a 4×10 grid of the page and retrieve the copilot* CSS file. Show me the capture and compare that CSS file with the one existing in the project and show me the differences.

> Important for this example: the browser profile was already logged in to GitHub beforehand. To prepare that state, run an interactive session first with `--show-chrome`, complete login, close the window, and then run the capture command.

Example screenshot from that flow:

![Prompt-driven GitHub tile capture and copilot CSS retrieval example](readme_example_github_tile5_copilot_css.png)

---

## Requirements

- Python 3.11+
- Chromium (installed automatically via `make setup`)
- Other browsers optional — install only what you need

---

## Installation

```bash
git clone https://github.com/mfuentescas/page-2-context.git
cd page2context
make setup
```

`make setup` installs Python dependencies and Chromium — the minimum required to run the tool.

### Installing additional browsers

To capture pages using Firefox, Edge, Brave, or WebKit profiles, the corresponding Playwright browser must be installed. Run the interactive installer to choose which ones you need:

```bash
make setup-browsers   # prompts Y/n for each browser (default: Y)
```

Or install them individually:

```bash
make setup-firefox    # Firefox
make setup-edge       # Microsoft Edge
make setup-webkit     # WebKit (Safari engine)
make setup-brave      # Brave (uses Chromium engine — same as make setup-chromium)
```

> If you see an error like `Executable doesn't exist at ...firefox...`, just run `make setup-firefox` (or the corresponding command for your browser).

---

## Usage

```bash
python3 page2context.py [--url "<URL>"] [OPTIONS]
```

Running with no arguments prints full usage help.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--url "<URL>"` | ⚠️ | — | URL to capture. **Required for capture mode**, optional when using `--show-*` interactive mode. |
| `--allow-external-urls [regex]` | ❌ | *(none)* | **Disabled by default**: only localhost/127.0.0.1/::1 and private/local IP literals are allowed. Use this flag to opt into external URLs for `--url` and for `--resources-regex` downloads. Pass empty (`""`) to allow all external URLs, or a regex to restrict allowed URLs. |
| `--clean-temp` | ❌ | *(flag)* | Clean historical `p2cxt_*` artifacts tracked in cache |
| `--size <WxH>` | ❌ | `1280x720` | Viewport size, e.g. `1920x1080` |
| `--crop <spec>` | ❌ | *(none)* | Grid crop — see below |
| `--console-log` | ❌ | *(flag)* | Capture browser console/page/navigation errors into `p2cxt_console.log` |
| `--use-<browser>` | ❌ | `chrome` | Select local browser profile `./browser/<browser>`. Allowed values for `<browser>`: `chrome`, `edge`, `brave`, `firefox`, `safari`, `chromium`, `webkit`. |
| `--show-<browser>` | ❌ | *(off)* | Open interactive browser session for `<browser>` using the same profile folder pattern; close the window when done. |
| `--clean-<browser>` | ❌ | *(flag)* | Remove local browser profile directory `./browser/<browser>` for the selected browser value. |
| | | | ⚠️ Use only one `--use-*` and one `--show-*` per run. If both are set, they must target the same browser. |
| `--run-js-file <path>` | ❌ | *(none)* | Execute a JS file inside the opened page and wait for completion |
| `--post-load-wait-ms <ms>` | ❌ | `0` | Extra wait after page load and before `--run-js-file`/screenshot (useful for animations) |
| `--resources-regex <regex>` | ❌ | *(none)* | Download matching resources seen in HTML or browser traffic. **Use this whenever you ask to retrieve CSS/JS/assets (for example `copilot*` CSS).** |
| `--output <dir>` | ❌ | *(auto)* | Output folder. If omitted, a **new unique temp directory** is created (typically under `/tmp`). |
| `--json` | ❌ | *(flag)* | Machine-readable JSON output (for AI callers) |

---

### Examples

```bash
# Basic capture (chrome local profile by default) -> prints absolute created artifact paths
# (writes into a new unique temp folder by default)
python3 page2context.py --url "http://localhost:4200/"

# Write outputs into a stable folder you control
python3 page2context.py --url "http://localhost:4200/" --output page2context

# Clean only historical temporary artifacts (no --url needed)
python3 page2context.py --clean-temp

# Clean one or more local browser profile directories (no --url needed)
python3 page2context.py --clean-chrome --clean-firefox

# Clean first, then capture normally
python3 page2context.py --clean-temp --url "http://localhost:4200/"

# Use Firefox local profile
python3 page2context.py --url "http://localhost:4200/" --use-firefox

# Show Chrome browser window only (interactive session mode, no URL required)
python3 page2context.py --show-chrome

# Show Chrome browser window and open an initial URL (still interactive session mode)
python3 page2context.py --url "http://localhost:4200/" --show-chrome

# Use and show Firefox explicitly (headed mode)
python3 page2context.py --url "http://localhost:4200/" --use-firefox --show-firefox

# Custom viewport
python3 page2context.py --url "http://localhost:4200/" --size 1920x1080

# Capture only specific tiles of a long page
python3 page2context.py --url "http://localhost:4200/" --crop "3x9:1,27"

# Capture browser console/page errors
python3 page2context.py --url "http://localhost:4200/" --console-log

# Execute custom JavaScript inside the page and wait until it finishes
python3 page2context.py --url "http://localhost:4200/" --run-js-file "./script.js"

# Wait 1200ms after load (before JS/screenshot) to let UI animations settle
python3 page2context.py --url "http://localhost:4200/" --post-load-wait-ms 1200 --run-js-file "./script.js"

# Example script: log browser cookies from JS
python3 page2context.py --url "http://localhost:4200/" --console-log --run-js-file "./test/example_log_cookies.js"

# Download only CSS/JS assets seen in source/network
python3 page2context.py --url "http://localhost:4200/" --resources-regex "\\.(css|js)(\\?|$)"

# Download only copilot* CSS from GitHub (external URL regex policy)
python3 page2context.py --url "https://github.com" --allow-external-urls "^https://([^/]+\\.)?(github\\.com|githubassets\\.com)/" --post-load-wait-ms 5000 --crop "4x10:3" --resources-regex "(?i)/copilot[^/]*\\.css(\\?|$)" --output "./tmp/github_copilot_css" --json

# Compare downloaded copilot* CSS with your local file
diff -u ./tmp/github_copilot_css/p2cxt_resource_001.css ./path/to/local/copilot.css
```

---

## Grid Crop (`--crop`)

Slices the full-page screenshot into a grid and saves only the tiles you need
as **individual PNGs** — useful when a page is too tall for the AI's context
window or you only care about a specific region.

### Format: `COLSxROWS:TILE[,TILE,...]`

```
3x9 grid — --crop "3x9:1,27"

+---+---+---+
| 1 | 2 | 3 |  row 1   ← tile 1 captured → p2cxt_tile_1.png
+---+---+---+
| 4 | 5 | 6 |  row 2
    ...
+---+---+---+
|25 |26 |27 |  row 9   ← tile 27 captured → p2cxt_tile_27.png
+---+---+---+
```

Each tile becomes its own PNG file and its own numbered section in `p2cxt_context.md`.

---

## Output

`page2context` keeps a historical artifact list in:

- `~/.cache/page2context/artifact_history.json` (by default)
- Override for automation/tests: env var `P2CXT_STATE_DIR`

This history is used by `--clean-temp` to remove previously generated `p2cxt_*` files.

### Default output directory

If you **don’t** pass `--output`, each run writes into a **new unique directory** under your system temp folder (typically `/tmp` on Linux), for example:

- `/tmp/p2cxt_run_abcd1234/`

This avoids clobbering previous runs and keeps your project tree clean.

If you want a stable folder (e.g. to check artifacts into a bug report), pass `--output <dir>`.

### Without `--crop`

```text
<output_dir>/
├── p2cxt_context.md      ← markdown with screenshot + reference to DOM file
├── p2cxt_html.html       ← full downloaded DOM HTML
└── p2cxt_screenshot.png  ← full-page screenshot
```

`p2cxt_context.md` structure:
```markdown
# Page context: https://example.com

## Screenshot
![...](p2cxt_screenshot.png)

## DOM
See [p2cxt_html.html](p2cxt_html.html) for the full DOM HTML.
```

### With `--crop "3x9:1,27"`

```
page2context/
├── p2cxt_context.md      ← markdown with tile sections + DOM reference
├── p2cxt_html.html       ← full downloaded DOM HTML in a separate file
├── p2cxt_screenshot.png  ← full-page screenshot (kept for reference)
├── p2cxt_tile_1.png
└── p2cxt_tile_27.png
```

`p2cxt_context.md` structure:
```markdown
# Page context: https://example.com

## Screenshots
> Grid: 3x9 | captured tiles: 1, 27

### Screenshot 1 (tile 1)
![tile 1](p2cxt_tile_1.png)

### Screenshot 2 (tile 27)
![tile 27](p2cxt_tile_27.png)

## DOM
See [p2cxt_html.html](p2cxt_html.html) for the full DOM HTML.
```

### With `--resources-regex "\\.(css|js)(\\?|$)"`

```text
page2context/
├── p2cxt_context.md
├── p2cxt_html.html
├── p2cxt_screenshot.png
├── p2cxt_resource_001.css
└── p2cxt_resource_002.js
```

`p2cxt_context.md` adds a section:

```markdown
## Downloaded Resources

Regex: `\.(css|js)(\?|$)`

- p2cxt_resource_001.css
- p2cxt_resource_002.js
```

When `--resources-regex` is used with `--json`, inspect these JSON fields for deterministic automation:

- `resources.matched_urls`
- `resources.files`
- `resources.failed`
- `resources.skipped`

For external pages (for example `https://github.com`), combine `--resources-regex` with `--allow-external-urls` or matching resources will be skipped by policy.

### With `--console-log`

```text
page2context/
├── p2cxt_context.md
├── p2cxt_html.html
├── p2cxt_screenshot.png
└── p2cxt_console.log
```

`p2cxt_context.md` adds:

```markdown
## Console and Browser Errors

See [p2cxt_console.log](p2cxt_console.log) for captured console output and browser/navigation errors.
```

### With `--run-js-file "./script.js"`

```markdown
## Executed JS

- File: `script.js`
- Result: `...`
```

### With `--use-<browser>` / `--show-<browser>`

#### Why use a browser profile?

Some pages require authentication. `page2context` stores browser state in local
project folders under `./browser/<browser>`, so you can keep cookies/session data
between runs and capture authenticated pages reliably.

#### Local profile behavior

- Each browser uses its own folder only when selected (`./browser/chrome`,
  `./browser/firefox`, etc.).
- If the folder does not exist, it is created automatically.
- Chrome is the default browser if no `--use-*`/`--show-*` is provided.
- `--show-<browser>` launches an interactive browser session (headed mode).
  No capture confirmation is required: close the window whenever you are done.
- This is useful because project profiles (`./browser/<browser>`) are different
  from your normal personal browser profile.
- If you ever see Chrome's "Restore pages? Chrome didn't shut down correctly" dialog,
  close it and retry; if it persists, run `--clean-chrome` once to reset the project-local profile.

Use `--clean-<browser>` to remove these local profile folders when desired.

`p2cxt_context.md` adds:

```markdown
## Browser Profile

- Browser: `chrome`
- Local profile dir: `/path/to/project/browser/chrome`
- Used as persistent profile: `True`
- Headless mode: `True`
```

---

## Output modes

### Default — prints created file paths (absolute)

```
/abs/path/page2context/p2cxt_screenshot.png
/abs/path/page2context/p2cxt_context.md
/abs/path/page2context/p2cxt_html.html
browser_profile_source: /abs/project/browser/chrome
chrome_profile_source: /abs/project/browser/chrome
history_file: /home/user/.cache/page2context/artifact_history.json
```

Errors go to **stderr**:
```
ERROR (3): Could not load URL: https://bad-url.invalid
  reason: DNS resolution failed - host not found.
```

### `--json` — machine-readable (for AI callers)

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
  "chrome_profile_source": "/path/to/project/browser/chrome",
  "console_log": "page2cxt_console.log",
  "browser_profile": {
    "browser":  "chrome",
    "source":   "/path/to/project/browser/chrome",
    "local_dir": "/path/to/project/browser/chrome",
    "used": true,
    "headless": true
  },
  "chrome_profile": {
    "source":   "/path/to/project/browser/chrome",
    "local_dir": "/path/to/project/browser/chrome",
    "used": true,
    "headless": true
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
    "matched_urls": [
      "https://example.com/styles.css",
      "https://example.com/app.js"
    ],
    "files": [
      "/abs/path/page2context/p2cxt_resource_001.css",
      "/abs/path/page2context/p2cxt_resource_002.js"
    ],
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

### `--clean-temp` only (no `--url`)

```json
{
  "status": "success",
  "message": "Historical temporary artifacts cleaned.",
  "version": "1.0.0",
  "cleaned_files": 3,
  "cleaned": ["/abs/path/.../p2cxt_context.md"],
  "failed": [],
  "output": [],
  "files": []
}
```

> `chrome_profile_source` is present for capture runs. It is populated when selected browser is chrome; `""` otherwise.
> `browser_profile` is present for capture runs and describes the selected local browser profile.
> `chrome_profile` is present when selected browser is chrome (backward compatibility).

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `2` | Bad argument |
| `3` | URL unreachable (DNS / refused / timeout) |
| `4` | File I/O error |
| `5` | Missing Pillow |
| `99` | Unexpected error |

---

## Security

### `--url` — only `http` and `https` allowed

`--url` rejects any scheme other than `http` or `https` (e.g. `file://`, `ftp://` are blocked).
This prevents the browser from reading local files or connecting to non-web targets.

### `--resources-regex` — SSRF and size protection

When `--resources-regex` is used, the tool downloads matched resources. The following
protections are enforced for every download:

- **Scheme check** — only `http`/`https` URLs are downloaded.
- **Private host block** — requests to loopback (`127.x`), private ranges (`10.x`, `192.168.x`,
  `172.16-31.x`), link-local (`169.254.x`), `localhost`, `*.local`, and `*.internal` are blocked
  to prevent Server-Side Request Forgery (SSRF) attacks from a malicious page.
- **No redirect following** — HTTP redirects are not followed, preventing SSRF via open redirects
  on public servers that redirect to internal addresses.
- **50 MB size cap** — each resource download is capped at 50 MB to prevent memory/disk exhaustion.

### `--run-js-file` — executes arbitrary JavaScript

The file passed to `--run-js-file` runs inside the opened page with full browser
permissions (DOM access, cookies, network). **Only pass files you trust.** Do not
point this flag at untrusted or user-supplied JS.

### Browser profile flags — local project profile directories

Browser state is stored in `./browser/<browser>` directories under the project root.
These folders are reused between runs and can be removed explicitly with `--clean-<browser>`.
Use `--show-<browser>` when you need manual interaction in a visible browser window.
In interactive mode, `--show-<browser>` runs until you close the browser window.

---

## Using with GitHub Copilot / Cursor

1. Run `page2context.py` against your target page
2. Open `page2context/p2cxt_context.md` in your IDE
3. Reference it in Copilot Chat:
   - Drag the file into chat, or type `#file:page2context/p2cxt_context.md`
4. Ask things like:
   - *"Based on the screenshot and DOM, fix the navbar alignment."*
   - *"What CSS class controls the hero section padding?"*
   - *"Rewrite this component so its layout matches tile 1."*

### If Copilot says a command was blocked

This is usually an IDE safety policy issue, not a `page2context` failure. Common causes:

- The IDE requires manual approval for command execution and the command was denied.
- The invoked folder does not have the expected runtime/dependencies. Run `make setup`.
- Copilot tried to run from a different folder than your trusted workspace (for example `~/.agents/skills/page-2-context` instead of your project folder).

Recommended fix:

```bash
cd "~/Documents/docs/+Personal/MySources/generate_markdown_from_website"
python3 page2context.py --show-chrome --json
```

Then close the interactive window and run your capture command from the same project folder so the same local profile (`./browser/chrome`) is reused.

### Two practical prompts you can copy/paste

1) Capture a specific tile (useful for long pages)

> Use `page2context` to capture tile #3 of a 4x3 grid from http://localhost:4200. Use a 1024x768 viewport and wait 5 seconds after the page loads.

2) Capture using your current project Chrome profile (when login is required)

> Use `page2context` with `--show-chrome` to open a visible browser, log in if needed, then capture http://localhost:4200 with 1024x768 viewport and 5 seconds wait after load.

### Browser login caveat (Google/Gmail)

Some identity providers (especially Google) can still reject automation-controlled sessions with messages like:
`This browser or app may not be secure`.

`page2context` now prefers real installed browser channels (for example Chrome via `channel=chrome`) in `--use-chrome` runs and reduces default automation flags, but providers can still enforce stricter checks.

If this happens:

1. Use `--show-chrome` and complete login manually in the visible window.
2. Keep using the same project profile folder (`./browser/chrome`) for later captures.
3. Ensure your system Chrome is installed and up to date.
