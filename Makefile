
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

# Поднять прежнее окружение корневого Compose; для auth используйте integration-up.
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
COMPOSE_FILE = testkit/compose/docker-compose.integration.yaml
ENV_FILE ?= .env # в пайплайне указан .env в testkit

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
# integration-up: подготовить зависимости и конфиги без загрузки данных и тестов.
# integration-run: выполнить подготовку, загрузку данных, тесты и завершение прогона.
# integration-seed: дождаться сервиса и применить тестовые SQL выбранного RUN_ID.
# integration-test: выполнить только тесты авторизации после успешной загрузки данных.
# integration-rabbitmq-setup: повторить настройку очередей отдельно от загрузки SQL.
# integration-logs: показать логи всех контейнеров указанного RUN_ID.
# integration-down: удалить контейнеры, тома, сеть и временные файлы своего прогона.
.PHONY: integration-up integration-run integration-seed integration-test integration-down integration-logs integration-rabbitmq-setup
# $@ — запрошенная цель; -C выбирает каталог testkit и его Makefile.
# Например: make integration-seed → make -C ./testkit integration-seed
# → python3 scripts/integration.py seed (реализация находится в testkit).
# @ скрывает только саму команду make, вывод Python/pytest остаётся виден.
integration-up integration-run integration-seed integration-test integration-down integration-logs integration-rabbitmq-setup:
	@$(MAKE) -C "$(TESTKIT_DIR)" $@

.PHONY: test-data-auth-service-up
# Применить тестовые данные через migrate напрямую, без Docker внутри команды.
test-data-auth-service-up:
	uv run --frozen python tools/seed_auth.py

# Совместимость со старыми командами: общий прогон, уборка, подготовка и загрузка данных.
.PHONY: docker-tests-auth-service-up docker-tests-auth-service-down docker-tests-auth-service test-env seed-data test-full
# Старые имена полного прогона; выполняют integration-run.
docker-tests-auth-service-up docker-tests-auth-service test-full: integration-run
# Старое имя адресной уборки; требует RUN_ID.
docker-tests-auth-service-down: integration-down
# Подготовить окружение без тестов через integration-up.
test-env: integration-up
# Загрузить данные в подготовленный RUN_ID через integration-seed.
seed-data: integration-seed

# Отказаться от частичного отката данных: удалить изолированный прогон через down.
test-data-auth-service-down:
	@echo 'Use integration-down RUN_ID=... to discard an isolated test environment.'
	@exit 1
