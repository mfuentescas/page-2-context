---
name: page-2-context
description: Screenshot + live DOM capture (p2cxt_*) for CSS/layout debugging and visual regression. Includes safe browser-profile temp copies for logged-in sessions.
---

# page2context

Capture a webpage into AI-readable artifacts:
- `p2cxt_screenshot.png` (or `p2cxt_tile_*.png` with `--crop`)
- `p2cxt_html.html` (live DOM snapshot)
- `p2cxt_context.md` (index + notes)

## Best for

- CSS/layout debugging, pixel-perfect comparisons, visual diffs
- Reviewing localhost/dev servers (Angular/React/Vue/etc.)
- Capturing authenticated pages using an existing logged-in browser session

## When to use

Use this skill if you need **visual context + DOM** (not just HTML source) and want **machine-readable output**.

## Setup (important)

If this skill is used from another project (via `npx skills`), Python/Playwright dependencies may not be installed yet.

**Preferred setup (do this): run the Makefile from this repo root. Do not invent extra pip packages.**

```bash
make setup
```

Optional interactive installs (default: Yes):

```bash
make setup-browsers
```

Fallback if `make` is not available:

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

## Safety (browser profiles)

Profile flags let you reuse an already-authenticated session (cookies/storage) **safely**:
- The original browser profile is **never modified**.
- The tool copies the profile to a **temporary directory**, uses the copy, then deletes it.

## Agent contract (must follow)

- Always pass `--json`.
- `--url` is required unless using clean-only mode (`--clean-temp` without `--url`).
- Use **only one** browser profile flag per run:
  - `--chrome-profile-dir`
  - `--edge-profile-dir`
  - `--brave-profile-dir`
  - `--firefox-profile-dir`
  - `--safari-profile-dir`
  - `--chromium-profile-dir`
  - `--webkit-profile-dir`
- Profile flags accept either:
  - an explicit profile directory path, or
  - `""` to auto-detect (fails with a clear error if not found).
- JSON always includes `chrome_profile_source` (path used for Chrome profile mode, or `""` if unused).

## Minimal usage

```bash
python page2context.py --url "<URL>" --json
```

Authenticated capture (Chrome profile auto-detect):

```bash
python page2context.py --url "<URL>" --chrome-profile-dir "" --json
```

Run trusted JS + wait for animations + capture + console log:

```bash
python page2context.py --url "<URL>" --post-load-wait-ms 1200 --run-js-file "./test/example_log_cookies.js" --console-log --json
```

## Agent workflow (deterministic)

1. If dependencies are missing, run `make setup` in this repo first.
2. Run with `--json`.
3. If `status != "success"`, report `message/reason/exit_code` and stop.
4. Read `p2cxt_context.md` → then `p2cxt_html.html` → then `p2cxt_console.log` (if present).

## Common failure hint

If logs mention `Executable doesn't exist at ...`, install the missing Playwright browser, e.g.:

```bash
python3 -m playwright install firefox
```

(or use the Makefile helper like `make setup-firefox`).

## More docs

- `README.md` (user guide + install)
- `agent-skill.md` (full AI instructions + JSON schema + advanced flags)
