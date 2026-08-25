.PHONY: help install run run-cli eval test clean

PYTHON ?= python3

help:
	@echo "Doc-QA Assistant - Available Commands:"
	@echo "  make install     - Install required dependencies"
	@echo "  make run         - Run the web backend server (default 127.0.0.1:5000)"
	@echo "  make run-cli     - Launch CLI TUI"
	@echo "  make eval        - Run the evaluation benchmark"
	@echo "  make test        - Run test suite with pytest"
	@echo "  make clean       - Remove cached files and pycache"

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) -m app.main

run-cli:
	$(PYTHON) cli.py interactive

eval:
	$(PYTHON) cli.py evaluate

test:
	$(PYTHON) -m pytest -v

clean:
	rm -rf __pycache__ */__pycache__ */*/__pycache__ .pytest_cache/
