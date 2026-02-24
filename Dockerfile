# Dockerfile.tests
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала только файлы зависимостей, чтобы кеш не инвалидировать по каждому изменению теста
COPY pyproject.toml uv.lock ./ 

# Установим uv (если им пользуешься) и зависимости
RUN pip install --no-cache-dir \
    --upgrade pip setuptools wheel uv

RUN uv sync --frozen

# Теперь копируем остальной код проекта
COPY . .

RUN apt-get update \
   && apt-get install -y --no-install-recommends make \
   && rm -rf /var/lib/apt/lists/*
