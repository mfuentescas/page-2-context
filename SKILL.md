---
name: page-2-context
description: Capture any webpage (screenshot + live DOM HTML) into a Markdown file so you can visually understand a page's layout, CSS and structure. Use this when the user asks you to inspect, analyse or replicate any web page — especially localhost dev servers.
---

# page2context

Capture a webpage (full-page screenshot + live DOM HTML) into a `context.md` file
that you can read to understand the page's visual layout and CSS.

## When to use

- User asks you to inspect, replicate or fix the layout of a web page
- User wants you to analyse CSS, colours, spacing or component structure
- User shows you a `localhost` dev server and wants visual context
- You need to compare what a page looks like versus what the code says

## How to call

Always add `--json` so you can parse the result reliably.

```bash
python page2context.py --url "<URL>" [--size <WxH>] [--crop <COLSxROWS:TILES>] [--output <DIR>] --json
```

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--url` | ✅ | — | URL to capture (always quote it) |
| `--size` | ❌ | `1280x720` | Viewport: `1920x1080`, `375x812`, etc. |
| `--crop` | ❌ | *(none)* | Capture only specific grid tiles — see below |
| `--output` | ❌ | `page2context` | Output folder name |
| `--json` | ✅ | *(flag)* | Always pass this for structured output |

### Crop parameter

Format: `COLSxROWS:TILE[,TILE,...]`

Divides the full-page screenshot into a COLS×ROWS grid. Tiles are numbered
left-to-right, top-to-bottom from 1. Each tile is saved as a separate PNG.

```
--crop "3x9:1,27"   → tile 1 (top-left) + tile 27 (bottom-right)
--crop "2x4:1,2,3"  → first three tiles of a 2×4 grid
```

## Output on success (exit 0)

```json
{
  "status":     "success",
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
> Without crop, `screenshot.png` is the full-page image.

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
3. Read <output_dir>/context.md — it contains screenshot(s) + full DOM HTML
4. Use that context to answer the user's question about layout / CSS / structure
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

