# Установить uv и синхронизировать зависимости проекта.
install:
	curl -LsSf https://astral.sh/uv/install.sh | sh
	uv sync

# Проверить стиль и типы кода, исключив отдельный сабмодуль testkit.
lint:
	uv run flake8 . --extend-exclude=testkit,.venv
	uv run ruff check . --extend-exclude testkit
	uv run mypy . --exclude '(^|/)testkit/'

# Автоматически отформатировать код, упорядочить импорты и исправить замечания Ruff.
fix: 
	uv run ruff format .
	uv run ruff check --select I --fix .
	uv run ruff check --fix .

# Поднять окружение корневого Compose; зависимости auth IDE поднимаются containers-up в auth-service.
start-containers:
	docker compose up -d

# Запустить весь набор тестов; для авторизации отдельно используйте test-auth-service.
test:
	uv run python -m pytest . 

# Удалить контейнеры и сеть прежнего окружения корневого Compose.
stop-containers:
	docker compose down

# Пересоздать прежнее окружение корневого Compose.
restart-containers:
	docker compose down
	docker compose up -d

# Удалить контейнеры прежнего Compose-окружения.
clean-containers:
	docker compose down
	docker compose rm -f

.PHONY: install lint fix start-containers test stop-containers restart-containers clean-containers

# Запустить только tests/auth_service с выводом pytest без файлов отчётов.
test-auth-service:
	uv run --frozen python -m pytest -p no:cacheprovider -o 'addopts=--strict-markers --strict-config --verbose --tb=short' tests/auth_service

.PHONY: test-auth-service

# DOCKER

-include .env

# Настройки по умолчанию, можно переопределять через env
REGISTRY ?= docker.io
IMAGE_TAG ?= latest                   # или $(shell git rev-parse --short HEAD)
FULL_IMAGE := $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

.PHONY: docker-build docker-push docker-login

# Собрать текущие тесты и SQL в образ FULL_IMAGE.
docker-build:
	docker build -f Dockerfile -t $(FULL_IMAGE) .

# Опубликовать ранее собранный FULL_IMAGE в выбранном реестре.
docker-push:
	docker push $(FULL_IMAGE)

# Опционально: логин, чтобы не писать руками
# Выполнить интерактивный вход в выбранный реестр образов.
docker-login:
	@echo "Logging in to $(REGISTRY)..."
	docker login $(REGISTRY)

# Общий запуск через testkit; TESTKIT_DIR позволяет выбрать его рабочую копию.
TESTKIT_DIR ?= $(CURDIR)/testkit

export INTEGRATION_ROOT := $(CURDIR)
export PYTESTS_DIR := $(CURDIR)
export INTEGRATION_CONTEXT := pytests
export PYTEST_CONFIG SEED_DATA TESTDATA_PATH TESTDATA_DATABASE_URL

# integration-up: подготовить контейнерный стенд testkit; для IDE используйте containers-up в auth-service.

# integration-run: полный контейнерный цикл; для IDE — готовность, данные и тесты без уборки.

# integration-seed: дождаться сервиса и подготовить данные загрузчиком фикстуры без тестов.

# integration-test: выполнить тесты авторизации с автоматической подготовкой данных фикстурой.

# integration-rabbitmq-setup: повторить настройку очередей отдельно от загрузки SQL.

# integration-logs: показать логи контейнеров своего стенда; локально RUN_ID не нужен.

# integration-down: удалить контейнеры, тома, сеть и временные файлы своего прогона.

.PHONY: integration-up integration-run integration-seed integration-test integration-down integration-logs integration-rabbitmq-setup

# $@ — запрошенная цель; -C выбирает каталог testkit и его Makefile.
# Например: make integration-seed → make -C ./testkit integration-seed
# → python3 scripts/integration.py seed (реализация находится в testkit).
# @ скрывает только саму команду make, вывод Python/pytest остаётся виден.
integration-up integration-run integration-seed integration-test integration-down integration-logs integration-rabbitmq-setup:
	@$(MAKE) -C "$(TESTKIT_DIR)" $@

.PHONY: test-data-auth-service-up

# Применить SQL общим загрузчиком фикстуры без запуска pytest и Docker.
test-data-auth-service-up:
	uv run --frozen python -m tools.seed_auth

.PHONY: test-seed

# Проверить загрузчик данных без Docker/БД; покрытие нового модуля не ниже 80%.
test-seed:
	uv run --frozen coverage run --source=tests.fixtures.auth_data,tools.seed_auth,src.database_config -m unittest discover -s checks
	uv run --frozen coverage report --fail-under=80
