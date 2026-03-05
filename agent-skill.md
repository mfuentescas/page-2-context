# Skill: page2context

> Capture any webpage (screenshot + live DOM HTML) into a Markdown file
> so an AI assistant can visually understand a page's layout, CSS and structure.

---

## What this skill does

Runs a real Chromium browser (via Playwright), navigates to a URL, takes a
full-page screenshot and grabs the live DOM, then writes everything into
`<output_dir>/context.md`.

- **No crop** → one `screenshot.png` + DOM in `context.md`
- **With `--crop`** → individual tile PNGs (`tile_1.png`, `tile_27.png`, …) each
  in their own numbered section inside `context.md`

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
  --output "<folder-name>" \
  --json
```

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--url` | ✅ | — | URL to capture (always quote it) |
| `--size` | ❌ | `1280x720` | Viewport size, e.g. `1920x1080` or `375x812` |
| `--crop` | ❌ | *(none)* | Grid crop spec — see below |
| `--output` | ❌ | `page2context` | Output folder |
| `--json` | ✅ for AI | *(flag)* | Always use when calling programmatically |

---

## Crop parameter explained

Format: `COLSxROWS:TILE[,TILE,...]`

Divides the full-page screenshot into a COLS×ROWS grid.
Tiles are numbered **left-to-right, top-to-bottom** starting at 1.
Each selected tile is saved as a **separate PNG** (`tile_N.png`).

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

Output files: tile_1.png, tile_27.png
context.md:
  ## Screenshots
  ### Screenshot 1 (tile 1)
  ![tile 1](tile_1.png)
  ### Screenshot 2 (tile 27)
  ![tile 27](tile_27.png)
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
  "context":    "page2context/context.md",
  "screenshot": "page2context/screenshot.png",
  "crop": {
    "grid":  "3x9",
    "tiles": [1, 27],
    "files": ["page2context/tile_1.png", "page2context/tile_27.png"]
  }
}
```

> `crop` is only present when `--crop` was used.

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
3. Read <output_dir>/context.md — contains screenshots + full DOM
4. Use screenshot images and DOM to answer user's question
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
