.PHONY: setup setup-deps setup-chromium setup-firefox setup-edge setup-brave setup-webkit setup-browsers version test run run-crop

# Install Python deps + Chromium (minimum required to run the tool)
setup: setup-deps setup-chromium
	@echo ""
	@echo "Core setup complete (Chromium ready)."
	@echo "To install additional browsers interactively, run:  make setup-browsers"

# Install Python dependencies only
setup-deps:
	python3 -m pip install -r requirements.txt

# Individual browser install targets
setup-chromium:
	python3 -m playwright install chromium

setup-firefox:
	python3 -m playwright install firefox

setup-edge:
	python3 -m playwright install msedge

setup-brave:
	@echo "Brave uses the Chromium engine — install chromium if not already done:"
	python3 -m playwright install chromium

setup-webkit:
	python3 -m playwright install webkit

# Interactive: ask Y/n for each supported browser
setup-browsers:
	@echo ""
	@echo "Optional browser installation (press Enter to accept default Y):"
	@echo ""
	@_ask() { \
	  printf "  Install %-12s for Playwright? [Y/n] " "$$1"; \
	  read ans; \
	  ans=$${ans:-Y}; \
	  case "$$ans" in [Yy]*) return 0;; *) return 1;; esac; \
	}; \
	_ask "Firefox"   && python3 -m playwright install firefox   || echo "  Skipping Firefox."; \
	_ask "WebKit"    && python3 -m playwright install webkit    || echo "  Skipping WebKit."; \
	_ask "Edge"      && python3 -m playwright install msedge    || echo "  Skipping Edge."; \
	echo ""; \
	echo "Done. Brave and Chromium share the same engine (already installed via setup-chromium)."

version:
	@cat VERSION

test:
	bash ./test/test_page2context.sh

# Quick usage example — override URL as needed
run:
	python3 page2context.py --url "http://github.com/"

# Example with viewport size and grid crop
run-crop:
	python3 page2context.py --url "http://github.com/" --size 1920x1080 --crop "3x9:1,27"
