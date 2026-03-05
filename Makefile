.PHONY: setup version test run run-crop

setup:
	python3 -m pip install -r requirements.txt
	python3 -m playwright install chromium

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
