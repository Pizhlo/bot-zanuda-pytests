
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

start-containers:
	docker compose up -d

test:
	uv run python -m pytest . 

stop-containers:
	docker compose down

restart-containers:
	docker compose down
	docker compose up -d

clean-containers:
	docker compose down
	docker compose rm -f

.PHONY: install lint fix start-containers test stop-containers restart-containers clean-containers