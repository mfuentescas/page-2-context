# page2context

> Capture any webpage (screenshot + live DOM HTML) into linked Markdown outputs —
> perfect for feeding visual context to GitHub Copilot, Cursor, or any AI assistant.

---

## Why?

When you ask an AI to help with CSS, layout or UI code, it can't *see* your browser.
**page2context** fixes that: it opens the page in a real Chromium browser (via Playwright),
takes a full-page screenshot, grabs the live DOM, and writes output files into
`<output_dir>/p2cxt_context.md` (screenshots + reference) and `<output_dir>/p2cxt_html.html` (raw DOM HTML) — ready to drop into any AI chat.

```
+----------------------+    page2context    +--------------------------+
|  Any URL / localhost | ────────────────►  |  page2context/           |
|  (real Chromium)     |                    |  ├── p2cxt_context.md    |
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

---

## Installation

```bash
git clone https://github.com/mfuentescas/page-2-context.git
cd page2context
make setup
```

`make setup` runs:
```bash
pip install -r requirements.txt   # Playwright + Pillow
playwright install chromium       # Downloads Chromium
```

---

## Usage

```bash
python page2context.py --url "<URL>" [OPTIONS]
```

Running with no arguments prints full usage help.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--url "<URL>"` | ✅ | — | URL to capture |
| `--clean-temp` | ❌ | *(flag)* | Clean historical `p2cxt_*` artifacts tracked in cache |
| `--size <WxH>` | ❌ | `1280x720` | Viewport size, e.g. `1920x1080` |
| `--crop <spec>` | ❌ | *(none)* | Grid crop — see below |
| `--console-log` | ❌ | *(flag)* | Capture browser console/page/navigation errors into `p2cxt_console.log` |
| `--run-js-file <path>` | ❌ | *(none)* | Execute a JS file inside the opened page and wait for completion |
| `--resources-regex <regex>` | ❌ | *(none)* | Download matching resources seen in HTML or browser traffic |
| `--output <dir>` | ❌ | `page2context` | Output folder |
| `--json` | ❌ | *(flag)* | Machine-readable JSON output (for AI callers) |

---

### Examples

```bash
# Basic capture → prints absolute created artifact paths
python page2context.py --url "http://localhost:4200/"

# Clean only historical temporary artifacts (no --url needed)
python page2context.py --clean-temp

# Clean first, then capture normally
python page2context.py --clean-temp --url "https://example.com"

# Custom viewport
python page2context.py --url "https://example.com" --size 1920x1080

# Capture only specific tiles of a long page
python page2context.py --url "https://example.com" --crop "3x9:1,27"

# Capture browser console/page errors
python page2context.py --url "https://example.com" --console-log

# Execute custom JavaScript inside the page and wait until it finishes
python page2context.py --url "https://example.com" --run-js-file "./script.js"

# Download only CSS/JS assets seen in source/network
python page2context.py --url "https://example.com" --resources-regex "\\.(css|js)(\\?|$)"

# All options — AI-friendly JSON output
python page2context.py --url "https://example.com" \
  --size 1440x900 --crop "2x4:1,2" --console-log --run-js-file "./script.js" \
  --resources-regex "\\.(css|js)(\\?|$)" --output my_capture --json
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

### Without `--crop`

```
page2context/
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

`p2cxt_context.md` adds:

```markdown
## Executed JS

- File: `script.js`
- Result: `...`
```

---

## Output modes

### Default — prints created file paths (absolute)

```
/abs/path/page2context/p2cxt_screenshot.png
/abs/path/page2context/p2cxt_context.md
/abs/path/page2context/p2cxt_html.html
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
  "output_dir": "page2context",
  "context":    "page2context/p2cxt_context.md",
  "html":       "page2context/p2cxt_html.html",
  "screenshot": "page2context/p2cxt_screenshot.png",
  "console_log": "page2context/p2cxt_console.log",
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
  }
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

> `resources` is only present when `--resources-regex` is used.
> `console_log` is only present when `--console-log` is used.
> `script` is only present when `--run-js-file` is used.
> `cleanup_before_run` is present when `--clean-temp` is combined with capture options.
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

## Using with GitHub Copilot / Cursor

1. Run `page2context.py` against your target page
2. Open `page2context/p2cxt_context.md` in your IDE
3. Reference it in Copilot Chat:
   - Drag the file into chat, or type `#file:page2context/p2cxt_context.md`
4. Ask things like:
   - *"Based on the screenshot and DOM, fix the navbar alignment."*
   - *"What CSS class controls the hero section padding?"*
   - *"Rewrite this component so its layout matches tile 1."*

---

## AI skill integration

For AI assistants that can invoke CLI tools, see **[agent-skill.md](agent-skill.md)** —
full call spec, JSON schema and error codes optimised for programmatic use.

For skills.sh compatible agents (GitHub Copilot, Cursor, Claude Code, etc.),
see **[SKILL.md](SKILL.md)**.

---

## Makefile shortcuts

```bash
make setup      # Install dependencies + Chromium
make test       # Run smoke test suite
make version    # Print current version
make run        # Quick capture of http://localhost:4200/
make run-crop   # Capture with 1920x1080 + 3x9 crop tiles 1,27
```
