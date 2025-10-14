# Образ тестов и загрузчика данных: один комплект SQL и тестов для каждого тега.
FROM migrate/migrate:v4.19.1 AS migrate
FROM python:3.13-slim

# Закреплённый CLI ведёт отдельную историю тестовых данных. Docker socket не нужен.
COPY --from=migrate /usr/local/bin/migrate /usr/local/bin/migrate

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
   && apt-get install -y --no-install-recommends make \
   && rm -rf /var/lib/apt/lists/*

# Сначала только файлы зависимостей, чтобы кеш не инвалидировать по каждому изменению теста
COPY pyproject.toml uv.lock ./ 

# Установим uv (если им пользуешься) и зависимости
RUN pip install --no-cache-dir \
    --upgrade pip setuptools wheel uv

RUN uv sync --frozen

# Теперь копируем остальной код проекта
COPY . .
