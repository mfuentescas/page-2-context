# page2context

> Capture any webpage (screenshot + live DOM HTML) into a single Markdown file —
> perfect for feeding visual context to GitHub Copilot, Cursor, or any AI assistant.

---

## Why?

When you ask an AI to help with CSS, layout or UI code, it can't *see* your browser.
**page2context** fixes that: it opens the page in a real Chromium browser (via Playwright),
takes a full-page screenshot, grabs the live DOM, and writes everything into
`<output_dir>/context.md` — ready to drop into any AI chat.

```
+----------------------+    page2context    +--------------------------+
|  Any URL / localhost | ────────────────►  |  page2context/           |
|  (real Chromium)     |                    |  ├── context.md          |
+----------------------+                    |  ├── screenshot.png      |
                                            |  └── tile_1.png  (opt.) |
                                            +--------------------------+
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
| `--size <WxH>` | ❌ | `1280x720` | Viewport size, e.g. `1920x1080` |
| `--crop <spec>` | ❌ | *(none)* | Grid crop — see below |
| `--output <dir>` | ❌ | `page2context` | Output folder |
| `--json` | ❌ | *(flag)* | Machine-readable JSON output (for AI callers) |

---

### Examples

```bash
# Basic capture → prints: page2context
python page2context.py --url "http://localhost:4200/"

# Custom viewport
python page2context.py --url "https://example.com" --size 1920x1080

# Capture only specific tiles of a long page
python page2context.py --url "https://example.com" --crop "3x9:1,27"

# All options — AI-friendly JSON output
python page2context.py --url "https://example.com" \
  --size 1440x900 --crop "2x4:1,2" --output my_capture --json
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
| 1 | 2 | 3 |  row 1   ← tile 1 captured → tile_1.png
+---+---+---+
| 4 | 5 | 6 |  row 2
    ...
+---+---+---+
|25 |26 |27 |  row 9   ← tile 27 captured → tile_27.png
+---+---+---+
```

Each tile becomes its own PNG file and its own numbered section in `context.md`.

---

## Output

### Without `--crop`

```
page2context/
├── context.md      ← markdown with screenshot + full DOM
└── screenshot.png  ← full-page screenshot
```

`context.md` structure:
```markdown
# Page context: https://example.com

## Screenshot
![...](screenshot.png)

## DOM
```html
...
```

### With `--crop "3x9:1,27"`

```
page2context/
├── context.md      ← markdown with tile sections + full DOM
├── screenshot.png  ← full-page screenshot (kept for reference)
├── tile_1.png
└── tile_27.png
```

`context.md` structure:
```markdown
# Page context: https://example.com

## Screenshots
> Grid: 3x9 | captured tiles: 1, 27

### Screenshot 1 (tile 1)
![tile 1](tile_1.png)

### Screenshot 2 (tile 27)
![tile 27](tile_27.png)

## DOM
```html
...
```

---

## Output modes

### Default — prints the output folder path

```
page2context
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
2. Open `page2context/context.md` in your IDE
3. Reference it in Copilot Chat:
   - Drag the file into chat, or type `#file:page2context/context.md`
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
