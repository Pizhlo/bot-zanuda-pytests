"""Загрузка тестовых данных auth-service через golang-migrate с отдельной историей версий."""
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import NoReturn
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

MIGRATE_VERSION = "4.19.1"
ROOT = Path(__file__).resolve().parents[1]


def configured_database_url() -> str:
    """Собирает URL PostgreSQL из выбранного YAML, экранируя реквизиты подключения."""
    import yaml

    path = Path(os.environ.get("PYTEST_CONFIG", str(ROOT / "config.yaml")))
    db = yaml.safe_load(path.read_text())["postgres"]
    host = str(db["host"])
    if ":" in host:
        host = f"[{host}]"
    user = quote(str(db["user"]), safe="")
    password = quote(str(db["password"]), safe="")
    return (
        f"postgres://{user}:{password}@{host}:"
        f"{int(db['port'])}/"
        f"{quote(str(db['dbname']), safe='')}?sslmode=disable"
    )


def database_url() -> str:
    """Выбирает URL и принудительно отделяет историю тестовых данных от миграций приложения."""
    raw = os.environ.get("TESTDATA_DATABASE_URL") or configured_database_url()
    url = urlsplit(raw)
    if url.scheme not in {"postgres", "postgresql"} or not url.hostname:
        raise ValueError("Expected a PostgreSQL URL")
    query = [(key, parameter) for key, parameter in parse_qsl(url.query)
             if key not in {"x-migrations-table", "x-migrations-table-quoted"}]
    query.append(("x-migrations-table", "testdata_schema_migrations"))
    return urlunsplit(url._replace(query=urlencode(query)))


def testdata_path() -> Path:
    """Разрешает абсолютный путь к SQL и проверяет наличие нумерованных up-файлов."""
    default = ROOT / "testdata/auth-service"
    path = Path(os.environ.get("TESTDATA_PATH", str(default))).resolve()
    sys.stdout.write(f"Auth test data: {path}\n")
    sys.stdout.flush()
    if not path.is_dir() or not list(path.glob("[0-9]*_*.up.sql")):
        raise ValueError("Missing or empty test data directory")
    return path


def migrate_binary() -> str:
    """Находит migrate и проверяет закреплённую версию перед обращением к БД."""
    binary = os.environ.get("MIGRATE_BIN", "migrate")
    version = subprocess.run([binary, "-version"], capture_output=True, text=True, check=True)
    if (version.stdout + version.stderr).strip().lstrip("v") != MIGRATE_VERSION:
        raise ValueError(f"Expected migrate v{MIGRATE_VERSION}")
    return binary


def main() -> int:
    """Применяет только новые SQL-версии, скрывает реквизиты в выводе и возвращает код migrate."""
    path = testdata_path()
    binary = migrate_binary()
    url = database_url()
    process = subprocess.Popen(
        [binary, "-path", str(path), "-database", url, "up"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(re.sub(r"postgres(?:ql)?://[^\s]+", "postgres://<redacted>",
                               line.replace(url, "postgres://<redacted>")))
        sys.stdout.flush()
    return process.wait()


def fail(error: Exception) -> NoReturn:
    """Сообщает об ошибке подготовки без вывода реквизитов и завершает команду с кодом 1."""
    sys.stderr.write(
        f"Seed preparation failed ({type(error).__name__}); "
        f"check source, configuration and migrate v{MIGRATE_VERSION}\n",
    )
    sys.exit(1)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyError as error:
        fail(error)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        fail(error)
