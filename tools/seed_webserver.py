"""Standalone загрузка webserver SQL без запуска pytest."""

import sys

from tests.fixtures.auth_data import AuthDataError
from tests.fixtures.webserver_data import prepare_webserver_data


def main() -> int:
    """Возвращает безопасный статус подготовки для Make и CI."""
    try:
        count = prepare_webserver_data()
    except AuthDataError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(f"Webserver test data prepared: {count} SQL files\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
