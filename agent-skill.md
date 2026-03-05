# Skill: page2context

> Capture any webpage (screenshot + live DOM HTML) into `p2cxt_*` artifacts
> so an AI assistant can visually understand a page's layout, CSS and structure.

---

## What this skill does

Runs a real Chromium browser (via Playwright), navigates to a URL, takes a
full-page screenshot and grabs the live DOM, then writes everything into
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
python page2context.py --url "<URL>" --json
```

### Full call
```bash
python page2context.py \
  --url    "<URL>" \
  --size   "<WIDTHxHEIGHT>" \
  --crop   "<COLSxROWS:TILE[,TILE]>" \
  --console-log \
  --run-js-file "<PATH>" \
  --resources-regex "<REGEX>" \
  --output "<folder-name>" \
  --json
```

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--url` | ✅ | — | URL to capture (always quote it) |
| `--size` | ❌ | `1280x720` | Viewport size, e.g. `1920x1080` or `375x812` |
| `--crop` | ❌ | *(none)* | Grid crop spec — see below |
| `--console-log` | ❌ | *(flag)* | Save console/page/navigation errors into `p2cxt_console.log` |
| `--run-js-file` | ❌ | *(none)* | Execute JS file in browser page and wait until it finishes |
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
    "matched_urls": ["https://example.com/styles.css", "https://example.com/app.js"],
    "files": ["/abs/path/page2context/p2cxt_resource_001.css", "/abs/path/page2context/p2cxt_resource_002.js"],
    "failed": []
  },
  "crop": {
    "grid":  "3x9",
    "tiles": [1, 27],
    "files": ["/abs/path/page2context/p2cxt_tile_1.png", "/abs/path/page2context/p2cxt_tile_27.png"]
  }
}
```

> `crop` is only present when `--crop` was used.
> `resources` is only present when `--resources-regex` was used.
> `output`/`files` are always present and contain absolute artifact paths.
> `console_log` is only present when `--console-log` is used.
> `script` is only present when `--run-js-file` is used.

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
5. If enabled, read <output_dir>/p2cxt_console.log for console/navigation/browser errors
6. If provided, use `resources.files` artifacts (`p2cxt_resource_*`) for CSS/JS inspection
7. If provided, inspect `script.result` from executed JS
8. Use all files to answer the user's question
9. Be aware the tool cleans previous `p2cxt_*` files in an existing output dir
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
make setup
```
