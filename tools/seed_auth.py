"""Применяет данные тем же загрузчиком, что фикстура, без запуска pytest.

Вызывается как python -m tools.seed_auth из Makefile. Импорт модуля с фикстурой
не запускает тесты; напрямую вызывается общая функция подготовки SQL.
"""

import sys

from tests.fixtures.auth_data import AuthDataError, prepare_auth_data


def main() -> int:
    """Возвращает статус подготовки и печатает безопасный результат для Make/CI."""
    try:
        count = prepare_auth_data()
    except AuthDataError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(f"Auth test data prepared: {count} SQL files\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
