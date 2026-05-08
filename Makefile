.PHONY: install dev test lint typecheck check

install:
	pip install -e ".[rembg]"

dev:
	pip install -e ".[dev,rembg]"

test:
	pytest

lint:
	ruff check .

typecheck:
	mypy src

check:
	ruff check .
	mypy src
	pytest
