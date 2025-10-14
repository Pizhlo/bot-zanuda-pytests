
install:
	curl -LsSf https://astral.sh/uv/install.sh | sh
	uv sync

lint:
	uv run flake8 .
	uv run ruff check .
	uv run mypy .

fix: 
	uv run ruff format .
	uv run ruff check --select I --fix .
	uv run ruff check --fix .

test:
	uv run python -m pytest . 