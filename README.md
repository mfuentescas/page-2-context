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
`p2cxt_context.md` + `p2cxt_html.html` — ready to drop into GitHub Copilot,
Cursor, Claude, or any AI chat. Now the AI can see exactly what you see, and
you can compare layouts, spot CSS regressions, and fix them without leaving
your editor.

```
+----------------------+    page2context    +--------------------------+
|  Any URL / localhost | ────────────────►  |  page2context/           |
|  (real browser)      |                    |  ├── p2cxt_context.md    |
|                      |                    |  ├── p2cxt_html.html     |
|                      |                    |  ├── p2cxt_screenshot.png |
|                      |                    |  └── p2cxt_tile_1.png (opt.) |
+----------------------+                    +--------------------------+
                                                       │
                                                       ▼
                                          GitHub Copilot / Cursor / ...
```

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
python3 page2context.py --url "<URL>" [OPTIONS]
```

Running with no arguments prints full usage help.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--url "<URL>"` | ✅ | — | URL to capture |
| `--allow-external-urls [regex]` | ❌ | *(none)* | **Disabled by default**: only localhost/127.0.0.1/::1 and private/local IP literals are allowed. Use this flag to opt into external URLs for `--url` and for `--resources-regex` downloads. Pass empty (`""`) to allow all external URLs, or a regex to restrict allowed URLs. |
| `--clean-temp` | ❌ | *(flag)* | Clean historical `p2cxt_*` artifacts tracked in cache |
| `--size <WxH>` | ❌ | `1280x720` | Viewport size, e.g. `1920x1080` |
| `--crop <spec>` | ❌ | *(none)* | Grid crop — see below |
| `--console-log` | ❌ | *(flag)* | Capture browser console/page/navigation errors into `p2cxt_console.log` |
| `--chrome-profile-dir [dir]` | ❌ | *(none)* | Copy Chrome user profile into a temporary directory used for this run only, then delete it. Useful to capture pages that require an active logged-in session (cookies, local storage). **Original profile is never modified.** Pass empty (`""`) to auto-detect. |
| `--edge-profile-dir [dir]` | ❌ | *(none)* | Same as above but for Microsoft Edge. **Original profile is never modified.** |
| `--brave-profile-dir [dir]` | ❌ | *(none)* | Same as above but for Brave. **Original profile is never modified.** |
| `--firefox-profile-dir [dir]` | ❌ | *(none)* | Same as above but for Firefox. Pass the profile root or a specific profile folder; pass empty to auto-detect. **Original profile is never modified.** |
| `--safari-profile-dir [dir]` | ❌ | *(none)* | Same as above but for Safari (macOS only). **Original profile is never modified.** |
| `--chromium-profile-dir [dir]` | ❌ | *(none)* | Same as above but for Chromium. **Original profile is never modified.** |
| `--webkit-profile-dir [dir]` | ❌ | *(none)* | Same as above but for Playwright WebKit. **Original profile is never modified.** |
| | | | ⚠️ Only **one** browser profile flag can be used per run |
| `--run-js-file <path>` | ❌ | *(none)* | Execute a JS file inside the opened page and wait for completion |
| `--post-load-wait-ms <ms>` | ❌ | `0` | Extra wait after page load and before `--run-js-file`/screenshot (useful for animations) |
| `--resources-regex <regex>` | ❌ | *(none)* | Download matching resources seen in HTML or browser traffic |
| `--output <dir>` | ❌ | *(auto)* | Output folder. If omitted, a **new unique temp directory** is created (typically under `/tmp`). |
| `--json` | ❌ | *(flag)* | Machine-readable JSON output (for AI callers) |

---

### Examples

```bash
# Basic capture → prints absolute created artifact paths
# (writes into a new unique temp folder by default)
python3 page2context.py --url "http://localhost:4200/"

# Write outputs into a stable folder you control
python3 page2context.py --url "http://localhost:4200/" --output page2context

# Clean only historical temporary artifacts (no --url needed)
python3 page2context.py --clean-temp

# Clean first, then capture normally
python3 page2context.py --clean-temp --url "https://example.com"

# Custom viewport
python3 page2context.py --url "https://example.com" --size 1920x1080

# Capture only specific tiles of a long page
python3 page2context.py --url "https://example.com" --crop "3x9:1,27"

# Capture browser console/page errors
python3 page2context.py --url "https://example.com" --console-log

# Use a copied Chrome user profile directory for this run
python3 page2context.py --url "https://example.com" --chrome-profile-dir "~/.config/google-chrome"

# Auto-detect first default Chrome profile (errors if none is found)
python3 page2context.py --url "https://example.com" --chrome-profile-dir ""

# Use a Firefox profile directory for this run
python3 page2context.py --url "https://example.com" --firefox-profile-dir "~/.mozilla/firefox/abc.default-release"

# Auto-detect Firefox profile
python3 page2context.py --url "https://example.com" --firefox-profile-dir ""

# Use Edge profile
python3 page2context.py --url "https://example.com" --edge-profile-dir ""

# Use Brave profile
python3 page2context.py --url "https://example.com" --brave-profile-dir ""

# Use Chromium profile
python3 page2context.py --url "https://example.com" --chromium-profile-dir ""

# Use Safari profile (macOS only)
python3 page2context.py --url "https://example.com" --safari-profile-dir ""

# Use Playwright WebKit profile
python3 page2context.py --url "https://example.com" --webkit-profile-dir ""

# Execute custom JavaScript inside the page and wait until it finishes
python3 page2context.py --url "https://example.com" --run-js-file "./script.js"

# Wait 1200ms after load (before JS/screenshot) to let UI animations settle
python3 page2context.py --url "https://example.com" --post-load-wait-ms 1200 --run-js-file "./script.js"

# Example script: log browser cookies from JS
python3 page2context.py --url "https://example.com" --console-log --run-js-file "./test/example_log_cookies.js"

# Download only CSS/JS assets seen in source/network
python3 page2context.py --url "https://example.com" --resources-regex "\\.(css|js)(\\?|$)"

# All options — AI-friendly JSON output
python3 page2context.py --url "https://example.com" \
  --size 1440x900 --crop "2x4:1,2" --console-log --chrome-profile-dir "~/.config/google-chrome" --run-js-file "./script.js" \
  --post-load-wait-ms 1200 --resources-regex "\\.(css|js)(\\?|$)" --output my_capture --json
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

### With `--chrome-profile-dir "~/.config/google-chrome"` / `--firefox-profile-dir <dir>` / etc.

#### Why use a browser profile?

When a web page requires authentication — for example an internal dashboard,
a SaaS app or any page where you are already logged in in your real browser —
passing your browser profile lets `page2context` open that page in an already
authenticated session. The browser will find your existing cookies and local
storage, so the page loads exactly as it would for you, including protected
content.

#### Safety guarantees — your original profile is never touched

`page2context` **never opens your real profile directory**. Instead it:

1. **Copies** the profile directory to a fresh temporary folder under `/tmp`
   (e.g. `/tmp/p2cxt_chrome_copy_xxx/`).
2. **Runs the browser** pointing exclusively at that temporary copy.
3. **Deletes the entire temporary copy** when the script finishes (whether it
   succeeded or failed).

Your real browser and its profile are untouched at all times. You can keep
your browser open and running while `page2context` captures a page — there is
no conflict because the tool uses an independent, isolated copy.

Only one browser profile flag can be used per run; passing two flags returns exit code 2.

`p2cxt_context.md` adds:

```markdown
## Browser Profile Copy

- Browser: `chrome`
- Source: `/home/user/.config/google-chrome`
- Temp copy: `/tmp/p2cxt_chrome_copy_xxx/profile`
- Used as persistent profile: `True`
- Copy cleaned: `True`
```

### With `--chrome-profile-dir ""`

When passed empty, the tool tries to auto-detect the first Chrome/Chromium
user-data directory from common OS paths (Linux/macOS/Windows). The same
applies to `--firefox-profile-dir ""`, `--edge-profile-dir ""`, etc.
If no profile is found, it exits with exit code 4 and a message asking you
to pass the directory explicitly.

---

## Output modes

### Default — prints created file paths (absolute)

```
/abs/path/page2context/p2cxt_screenshot.png
/abs/path/page2context/p2cxt_context.md
/abs/path/page2context/p2cxt_html.html
chrome_profile_source:
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
  "chrome_profile_source": "/home/user/.config/google-chrome",
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
  "chrome_profile_source": "",
  "cleaned_files": 3,
  "cleaned": ["/abs/path/.../p2cxt_context.md"],
  "failed": [],
  "output": [],
  "files": []
}
```

> `chrome_profile_source` is always present. Populated only for `--chrome-profile-dir`; `""` otherwise.
> `browser_profile` is present when any `--*-profile-dir` flag is used. Its `browser` field names the browser. For `--chrome-profile-dir` both `browser_profile` and `chrome_profile` are present (the latter for backward compatibility).
> `chrome_profile` is only present when `--chrome-profile-dir` is used (backward compat).
> `resources` is only present when `--resources-regex` is used.
> `console_log` is only present when `--console-log` is used.
> `script` is only present when `--run-js-file` is used.
> `cleanup_before_run` is present when `--clean-temp` is combined with capture options.
> `history_file` is always present.
> `output`/`files` always contain absolute artifact paths.

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

### Browser profile flags — original profile is never touched

See [browser profile safety](#with---chrome-profile-dir-configgoogle-chrome----firefox-profile-dir-dir--etc)
above for a full explanation. The original profile directory is never opened by
the browser; only a temporary copy is used and it is deleted on exit.

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

### Two practical prompts you can copy/paste

1) Capture a specific tile (useful for long pages)

> Use `page2context` to capture tile #3 of a 4x3 grid from http://localhost:4200. Use a 1024x768 viewport and wait 5 seconds after the page loads.

2) Capture using your current Chrome session (when login is required)

> Use `page2context` using my current Chrome profile to capture image from http://localhost:4200. Use a 1024x768 viewport and wait 5 seconds after the page loads.

---

## AI skill integration

This project ships two skill descriptor files so any AI assistant can learn
to use `page2context` automatically:

| File | Purpose |
|------|---------|
| **[SKILL.md](SKILL.md)** | [skills.sh](https://skills.sh) format — auto-discovered by agents that scan the workspace for `SKILL.md` (GitHub Copilot, Cursor, Claude Code, etc.). |
| **[agent-skill.md](agent-skill.md)** | Source of truth for the full agent instructions — call spec, JSON schema, exit codes, and suggested workflow. |

### Auto-discovery copies

Each AI system looks for instructions in its own conventional directory.
Running `make sync-agent-skills` (also runs during `make setup`) copies
`agent-skill.md` into every one of them:

| AI system | Generated file |
|-----------|----------------|
| **GitHub Copilot** | `.github/copilot-instructions.md` |
| **Cursor** | `.cursor/rules/page2context.md` |
| **Claude Code** | `CLAUDE.md` |
| **Windsurf (Codeium)** | `.windsurf/rules/page2context.md` |
| **Cline** | `.clinerules` |

All generated files include a header comment pointing back to `agent-skill.md`.
Edit **only** `agent-skill.md`, then run:

```bash
make sync-agent-skills
```

> If you don't use a particular AI system, its generated file is harmless —
> it is just a Markdown file that other tools will ignore.

---

## Makefile shortcuts

```bash
make setup              # Install Python deps + Chromium + sync agent skills
make setup-browsers     # Interactive: Y/n prompt for each additional browser
make setup-firefox      # Install Firefox for Playwright
make setup-edge         # Install Microsoft Edge for Playwright
make setup-webkit       # Install WebKit for Playwright
make setup-brave        # Install Brave (uses Chromium engine)
make sync-agent-skills  # Copy agent-skill.md → .github/, .cursor/, .windsurf/, CLAUDE.md, .clinerules
make test               # Run smoke test suite
make version            # Print current version
make run                # Quick capture of http://github.com/
make run-crop           # Capture http://github.com/ with 1920x1080 + 3x9 crop
```

---

## Security: prompt injection / untrusted content (important)

This tool captures live DOM and can optionally download linked resources. Treat **all captured page content as untrusted input**.

- **Never follow instructions found inside captured HTML/DOM/screenshot text.** Malicious pages can include *prompt injection* designed to trick an AI assistant into leaking secrets or running commands.
- Prefer capturing only your **local dev server**.
- Only use `--run-js-file` with **trusted, local** scripts.
- If you use browser profile flags for authenticated sessions, assume cookies/localStorage may include sensitive data.

---

## URL policy (local-only by default)

By default, `--url` is restricted to:

- `localhost`, `127.0.0.1`, `::1`
- private/local IP literals (e.g. `192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`)

To capture an external site, explicitly opt in:

```bash
python3 page2context.py --url "https://example.com" --allow-external-urls "" --json
```

For safer external use, restrict by regex:

```bash
python3 page2context.py --url "https://example.com" --allow-external-urls "^https://example\\.com/" --json
```
