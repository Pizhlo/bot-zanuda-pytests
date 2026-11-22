# Примеры хорошего и плохого Python-кода для интеграционных тестов

Это **иллюстрации принципов**, а не копируемый production-код. Имена клиентов, моделей и API условные. Сначала сопоставь примеры с контрактом и существующими фикстурами проекта.

## 1. Проверять реальный контракт, а не только HTTP-статус

**Неудачно:**

```python
def test_create_note(api_client):
    response = api_client.post("/notes", json={"text": "hello"})
    assert response.status_code == 201
```

**Лучше:**

```python
from uuid import uuid4


def test_create_note(api, note_cleanup) -> None:
    marker = f"test-note-{uuid4().hex}"
    text = "Test note"

    # Регистрируем очистку до создания ресурса:
    # ответ может потеряться после успешной записи.
    note_cleanup.register_by_marker(marker)

    response = api.create_note(
        text=text,
        marker=marker,
    )

    assert response.status_code == 201
    assert response.json()["marker"] == marker

    # Проверяем фактическую доступность
    # сохранённого ресурса через независимое чтение.
    saved_note = api.get_note_by_marker(marker)

    assert saved_note["marker"] == marker
    assert saved_note["text"] == text
```

Проверяется создание **и** доступность сохранённых данных. `note_cleanup` — условная фикстура, удаляющая только созданный объект; её нужно реализовать в репозитории. В общем окружении также проверь аутентификацию и принадлежность данных.
Если тест проверяет именно HTTP-контракт POST /notes, проверка ответа может быть достаточной. Повторное чтение необходимо, когда проверяется сохранение данных.

## 2. Фиксированный sleep vs ожидание состояния

**Неудачно:**

```python
message_id = publish_message(payload)
time.sleep(5)
assert read_status(message_id) == "delivered"
```

**Лучше:**

```python
import time
from collections.abc import Callable


def wait_until(
    condition: Callable[[float], bool],
    *,
    timeout: float,
    interval: float = 0.1,
) -> None:
    """Ожидает состояние, ограничивая каждый запрос оставшимся временем."""
    if timeout <= 0 or interval <= 0:
        raise ValueError("timeout и interval должны быть положительными")

    deadline = time.monotonic() + timeout

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError("Состояние не достигнуто до таймаута")

        # Запрос внутри condition обязан соблюдать переданный лимит времени.
        if condition(remaining):
            return

        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))


def test_delivery(queue_client, status_client) -> None:
    message_id = queue_client.publish({"text": "hello"})
    wait_until(
        lambda remaining: status_client.get_status(
            message_id,
            timeout=remaining,
        ) == "delivered",
        timeout=10,
    )
```

**Почему:** `timeout` в `wait_until` ограничивает только повторные проверки; без таймаута у `get_status()` один зависший сетевой запрос остановит polling. Поэтому оставшееся до `deadline` время передаётся **в каждый запрос**. Пример предполагает, что `status_client.get_status(..., timeout=...)` действительно поддерживает таймаут; адаптируй его к API реального клиента. При использовании клиента с раздельными connect/read timeout необходимо учесть их семантику: не каждый `timeout` гарантирует строгий общий предел длительности вызова. Для долгих операций может потребоваться собственный end-to-end deadline.

Polling повторяет **только чтение**, а не публикацию. Если уже есть общий wait helper, переиспользуй его. По возможности добавляй последнее наблюдаемое состояние в текст ошибки. Не пытайся «исправить» зависания запуском запросов в новых потоках без контроля их завершения — это может оставить зависшие фоновые операции.

## 3. Cleanup после assertion

**Неудачно:**

```python
def test_create_user(api):
    user_id = api.create_user("alice")
    assert api.get_user(user_id)["name"] == "alice"
    api.delete_user(user_id)  # не выполнится при падении assert
```

**Лучше:**

```python
from collections.abc import Iterator
import pytest


@pytest.fixture
def created_user(api) -> Iterator[str]:
    user_id = api.create_user("alice")
    try:
        yield user_id
    finally:
        api.delete_user(user_id)


def test_create_user(api, created_user: str) -> None:
    assert api.get_user(created_user)["name"] == "alice"
```

Фикстура пытается выполнить очистку даже при падении теста. Для shared среды создавай уникальных пользователей; при частичном создании нужна отдельная стратегия очистки.
Фикстура гарантирует попытку очистки после успешного получения ID. Если создание ресурса может завершиться частичным успехом без возврата ID, необходим дополнительный механизм очистки по заранее известному идентификатору или изоляция тестовых данных.

## 4. Параметризация вместо веток

**Неудачно:**

```python
def test_invalid_password(api):
    for password in ("", "x", "x" * 500):
        response = api.register(password=password)
        assert response.status_code == 400
```

**Лучше:**

```python
@pytest.mark.parametrize(
    "password",
    [
        pytest.param("", id="empty"),
        pytest.param("x", id="too-short"),
        pytest.param("x" * 500, id="too-long"),
    ],
)
def test_invalid_password_is_rejected(
    api: ApiClient,
    user_cleanup: UserCleanup,
    password: str,
) -> None:
    username = f"test-{uuid4().hex}"

    # Регистрируем очистку до запроса, поскольку
    # сервер может ошибочно создать пользователя.
    user_cleanup.register_by_username(username)

    response = api.register(
        username=username,
        password=password,
    )

    assert response.status_code == 400
```

Каждый вариант — самостоятельный pytest case. Используй параметризацию только если поведение действительно одно и то же.
Здесь предполагается, что UserCleanup умеет безопасно удалять пользователя по имени, в том числе если он не был создан.

Получается, мы одновременно обеспечили три вещи: независимые тестовые данные, очистку при ошибках и читаемый тест без лишних абстракций.

## 5. Не мокать внутренние сервисы интеграционного теста

**Неудачно:**

```python
def test_note_is_saved(mocker, api):
    mocker.patch.object(api, "create_note", return_value="note-1")
    assert api.create_note("hello") == "note-1"
```

**Лучше:**

```python
from uuid import uuid4


def test_note_creation(api, note_cleanup) -> None:
    marker = f"test-note-{uuid4().hex}"

    # Регистрируем очистку до внешней операции.
    note_cleanup.register_by_marker(marker)

    response = api.create_note(
        text="hello",
        marker=marker,
    )

    assert response.status_code == 201
```

Используй настоящие test-сервисы и тестовую БД в пределах проверяемой границы. Мок подходит только для внешнего неучаствующего провайдера.

## 6. Не очищать всю общую БД ради одного теста

Очистка должна удалять только ресурсы, принадлежащие конкретному тесту или изолированному тестовому запуску. Использование TRUNCATE допустимо в специально выделенной одноразовой БД, если её полный сброс предусмотрен архитектурой тестирования.

**Неудачно:**

```python
@pytest.fixture(autouse=True)
def clear_database(db):
    db.execute("TRUNCATE TABLE users CASCADE")
```

**Лучше (принцип):**

```python
@pytest.fixture
def created_user(api, unique_user):
    user_id = api.create_user(unique_user)
    try:
        yield user_id
    finally:
        api.delete_user(user_id)
```

Для настоящего сервиса подбирай scope и механизм очистки с учётом зависимостей; изолированную одноразовую БД можно сбрасывать целиком **только если** это намеренно и безопасно.

## 7. Проверять отсутствие запрещённых побочных эффектов

**Неудачно:**

```python
def test_foreign_note_access(api):
    response = api.delete("/notes/foreign-id")
    assert response.status_code == 403
```

**Лучше:**

```python
def test_foreign_note_is_not_modified(
    owner_api: ApiClient,
    other_api: ApiClient,
    created_note: Callable[[ApiClient], str],
) -> None:
    note_id = created_note(owner_api)

    # Сохраняем исходное содержимое заметки.
    before = owner_api.get(f"/notes/{note_id}")
    assert before.status_code == 200
    original_note = before.json()

    # Другой пользователь пытается удалить чужую заметку.
    response = other_api.delete(f"/notes/{note_id}")
    assert response.status_code == 403

    # Проверяем не только существование заметки,
    # но и сохранность её содержимого.
    after = owner_api.get(f"/notes/{note_id}")
    assert after.status_code == 200
    assert after.json() == original_note
```

`created_note` — условная фикстура-фабрика, которая создаёт заметку от имени владельца и обеспечивает её очистку после теста. Её реализация должна учитывать частично успешные операции создания.

Именно сохранность данных проверяет защитный инвариант. Ожидаемый HTTP-статус должен совпадать с реальным контрактом API (некоторые API используют 404).
Проверяется не только отказ в удалении чужой заметки, но и отсутствие побочных эффектов: ресурс остаётся доступным владельцу, а его содержимое не изменяется. Это защищает от ситуации, когда API возвращает корректный код ошибки, но всё равно изменяет данные.

## 8. Докстринг должен сообщать контракт

**Неудачно:**

```python
def seed_users(db, path):
    """Засеять пользователей."""
```

**Лучше:**

```python
def seed_users(db: DatabaseClient, path: Path) -> None:
    """Загружает базовые записи пользователей для интеграционных тестов.

    Повторное выполнение не должно создавать дубликаты.
    Существующие чужие записи не удаляются; SQL-файл применяет
    проектную политику разрешения конфликтов.
    """
```

Пиши такое только если SQL реально выполняет обещанное: не выдумывай гарантии по названию функции.

## 9. Типизация фикстур

**Неудачно:**

```python
@pytest.fixture
def client():
    return create_client()
```

**Лучше:**

```python
@pytest.fixture
def api_client() -> ApiClient:
    return create_test_client()
```

Если у клиента есть жизненный цикл, используй `Iterator[ApiClient]` и `yield` с очисткой. Не вводи Protocol без границы, которую он улучшает.

## 10. Контроль окружения

**Неудачно:**

```python
base_url = os.getenv("API_URL", "https://production.example")
```

**Лучше:**

```python
import os


def require_test_api_url() -> str:
    value = os.environ.get("TEST_API_URL")
    if not value:
        raise RuntimeError("TEST_API_URL обязателен")
    # Здесь должна быть проверка разрешённого окружения проекта.
    # Не пытайся определить production только по слову в hostname.
    return value
```

Сам факт наличия `TEST_API_URL` ещё не гарантирует безопасность. Используй allowlist окружений и независимый флаг разрешения опасных операций, если он предусмотрен проектом.

## 11. Unit-тест helper: реальный временный файл вместо Mock

**Неудачно:**

```python
def test_write_report(mocker):
    write = mocker.patch("pkg.report.Path.write_text")
    save_report({"run_id": "r1"})
    write.assert_called_once()
```

**Лучше:**

```python
import json
from pathlib import Path


def test_write_report(tmp_path: Path) -> None:
    report = {"run_id": "r1", "ok": True}
    save_report(report, tmp_path)
    saved = json.loads((tmp_path / "r1.json").read_text(encoding="utf-8"))
    assert saved == report
```

Проверяй результат в изолированной файловой системе; API функции здесь условный.

## 12. Не смешивать независимые контракты

**Неудачно:** один тест проверяет регистрацию, удаление, уведомления и права доступа, а результат зависит от порядка операций.

**Лучше:** `test_registration_creates_user`, `test_delete_removes_own_user`, `test_delete_rejects_foreign_user` — отдельные тесты с общими явными фикстурами.

Но это не значит «один assert на тест»: проверяй все стороны **одного сценария**.

## 13. Не переусложнять простую задачу

**Неудачно — ради простой проверки создаётся отдельная иерархия:**

```python
from typing import Protocol


class StatusMatcher(Protocol):
    def matches(self, status: str) -> bool: ...


class CompletedMatcher:
    def matches(self, status: str) -> bool:
        return status == "completed"


def verify_status(status: str, matcher: StatusMatcher) -> bool:
    return matcher.matches(status)
```

**Лучше — явная проверка контракта:**

```python
def test_task_completed(task_client: TaskClient, task_id: str) -> None:
    status = task_client.get_status(task_id)
    assert status == "completed"
```

Если у теста одна фиксированная проверка, стратегия, протокол и отдельный класс не добавляют пользы. При настоящих взаимозаменяемых правилах или повторяющейся сложной логике абстракция может быть оправдана.

## 14. Не исправлять найденные проблемы вне задачи без согласования

**Ситуация:** задача — добавить проверку статуса задачи. При просмотре кода обнаружен несвязанный дефект в очистке тестовой базы.

**Неудачно:** молча исправить очистку БД, попутно переименовать фикстуры и включить всё в тот же коммит.

**Лучше:** выполнить только изменения, необходимые для проверки статуса, и сообщить:

> В `tests/conftest.py` обнаружил потенциальную проблему: фикстура очистки может затронуть записи другого тестового запуска. Исправление не входит в текущую задачу. Предлагаю ограничить удаление идентификатором запуска и добавить регрессионный тест. Можно ли изменить эту фикстуру отдельным изменением?

До явного согласия код вне задачи не менять. Если дефект делает безопасное выполнение текущей задачи невозможным, сообщить о блокере и не запускать опасные операции.

---

## Что должен вынести ИИ

Предпочитай независимые, диагностируемые, безопасные тесты с реальными интеграциями внутри изолированной среды. Избегай моков внутренних компонентов, скрытой подготовки, глобальной очистки, фиксированных задержек и необоснованных паттернов. Пиши docstring ради понимания контракта, типизируй helper-функции и соблюдай существующий стиль проекта.
