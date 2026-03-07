.PHONY: setup setup-deps setup-chromium setup-firefox setup-edge setup-brave setup-webkit setup-browsers sync-agent-skills version test run run-crop

AGENT_SKILL := agent-skill.md

VENV_DIR ?= .venv
# Resolve venv bin directory (Linux/macOS). For Windows (skills users), they typically run under Git Bash/WSL;
# if native Windows CMD/PowerShell is used, they'll need to adapt to Scripts/.
VENV_BIN := $(VENV_DIR)/bin
VENV_PY  := $(VENV_BIN)/python3

# Install Python deps + Chromium (minimum required to run the tool)
setup: setup-venv setup-deps setup-chromium sync-agent-skills
	@echo ""
	@echo "Core setup complete (Chromium ready)."
	@echo "To install additional browsers interactively, run:  make setup-browsers"

# Create a local venv (preferred for agent-driven installs)
setup-venv:
	@test -x "$(VENV_PY)" || (python3 -m venv "$(VENV_DIR)" && "$(VENV_PY)" -m pip install --upgrade pip)

# Install Python dependencies only (into the local venv)
setup-deps: setup-venv
	"$(VENV_PY)" -m pip install -r requirements.txt

# Individual browser install targets (use venv python)
setup-chromium: setup-venv
	"$(VENV_PY)" -m playwright install chromium

setup-firefox: setup-venv
	"$(VENV_PY)" -m playwright install firefox

setup-edge: setup-venv
	"$(VENV_PY)" -m playwright install msedge

setup-brave: setup-venv
	@echo "Brave uses the Chromium engine — install chromium if not already done:"
	"$(VENV_PY)" -m playwright install chromium

setup-webkit: setup-venv
	"$(VENV_PY)" -m playwright install webkit

# Interactive: ask Y/n for each supported browser
setup-browsers: setup-venv
	@echo ""
	@echo "Optional browser installation (press Enter to accept default Y):"
	@echo ""
	@_ask() { \
	  printf "  Install %-12s for Playwright? [Y/n] " "$$1"; \
	  read ans; \
	  ans=$${ans:-Y}; \
	  case "$$ans" in [Yy]*) return 0;; *) return 1;; esac; \
	}; \
	_ask "Firefox"   && "$(VENV_PY)" -m playwright install firefox   || echo "  Skipping Firefox."; \
	_ask "WebKit"    && "$(VENV_PY)" -m playwright install webkit    || echo "  Skipping WebKit."; \
	_ask "Edge"      && "$(VENV_PY)" -m playwright install msedge    || echo "  Skipping Edge."; \
	echo ""; \
	echo "Done. Brave and Chromium share the same engine (already installed via setup-chromium)."

# Sync agent-skill.md into each AI system's conventional directory
sync-agent-skills: $(AGENT_SKILL)
	@mkdir -p .github .cursor/rules .windsurf/rules
	@for target in \
	  .github/copilot-instructions.md \
	  .cursor/rules/page2context.md \
	  CLAUDE.md \
	  .windsurf/rules/page2context.md \
	  .clinerules ; do \
	  printf '%s\n%s\n\n' \
	    "<!-- AUTO-GENERATED from $(AGENT_SKILL) — do not edit directly. -->" \
	    "<!-- Run: make sync-agent-skills -->" \
	    > "$$target" ; \
	  cat $(AGENT_SKILL) >> "$$target" ; \
	done
	@echo "✔ Agent skill files synced to: .github/ .cursor/ .windsurf/ CLAUDE.md .clinerules"

version:
	@cat VERSION

test:
	bash ./test/test_page2context.sh
	@PY=$$(test -x "$(VENV_PY)" && echo "$(VENV_PY)" || echo "python3"); \
	$$PY -m unittest discover -s test -p "test_cli_params_unit.py" -v

# Quick usage example — override URL as needed
run:
	@PY=$$(test -x "$(VENV_PY)" && echo "$(VENV_PY)" || echo "python3"); \
	$$PY page2context.py --url "http://github.com/"

# Example with viewport size and grid crop
run-crop:
	@PY=$$(test -x "$(VENV_PY)" && echo "$(VENV_PY)" || echo "python3"); \
	$$PY page2context.py --url "http://github.com/" --size 1920x1080 --crop "3x9:1,27"
