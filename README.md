# Bot Zanuda — интеграционные тесты

Нужны Linux, Make, Python 3.10+ и PyYAML; для тестов на хосте — uv/Python 3.13,
для контейнерных режимов — Docker с Compose. Инициализируйте testkit: `git submodule update --init --recursive`.

## Полный запуск в контейнерах

Из **pytests**:

```sh
make integration-run
```

Команда поднимает зависимости и auth-service latest, ждёт миграций сервиса,
запускает текущие тесты; их сессионная фикстура подготавливает SQL-данные. Успех удаляет окружение;
ошибка оставляет его и `.logs/testkit-auth-local/run.log`. После ошибки перед новым
контейнерным прогоном выполните `make integration-down`.

## Сервис и тесты на хосте с локальными конфигами

Из **auth-service** используйте существующую команду:

```sh
make containers-up
```

Запустите сервис в IDE с рабочим каталогом **auth-service** и своим `config.yaml`
(при явном аргументе — `-config config.yaml`). Конфиг сервиса не нужно заменять
файлом из testkit. При сборке из IDE сохраните Go ldflags с непустыми Version,
BuildDate и GitCommit; альтернативный запуск — `make run`.

Из **pytests** выполняйте и повторяйте одну команду:

```sh
make integration-run AUTH_MODE=host TEST_MODE=host
```

Она читает **pytests/config.yaml**, ждёт сервис и запускает pytest. Сессионная
фикстура auth-service подготавливает SQL перед тестами. Runner не вызывает Docker, не собирает образы, не поднимает
зависимости и не требует integration-up. Для тестов и отдельного seed нужны
uv/Python 3.13; migrate устанавливать не нужно.
Содержимое ваших YAML не меняется и не выводится в журнал.

Параметры БД, RabbitMQ, Vault, JWT и OpenFGA в конфиге тестов должны соответствовать
вашему сервису/окружению. OpenFGA по умолчанию — localhost:8081, store bot-zanuda;
если они отличаются, задайте `openfga.base_url` и `openfga.store_name` в config.yaml.

```sh
# Пропустить seed, если данные уже подготовлены.
make integration-run AUTH_MODE=host TEST_MODE=host SEED_DATA=false
# Другой локальный конфиг, одинаковый для readiness, seed и pytest.
make integration-run AUTH_MODE=host TEST_MODE=host PYTEST_CONFIG=config-local.yaml
```

Относительный PYTEST_CONFIG считается от репозитория, из которого вызван make,
несмотря на делегирование через `make -C testkit`. Процесс IDE и зависимости остаются
работать после успеха и ошибки. Останавливайте зависимости через `make containers-down`
из **auth-service**, а сервис — в IDE. Integration-down не предназначен для этого окружения.

Отдельные этапы из **pytests**, без оркестрации и без подготовки testkit:

```sh
make test-data-auth-service-up   # Только SQL, конфиг по умолчанию config.yaml.
make test-auth-service           # Только pytest с тем же config.yaml.
```

Команды integration-seed/integration-test с AUTH_MODE=host TEST_MODE=host также
работают без предварительного integration-up и сохраняют диагностику runner.
Подготовка повторно применяет SQL: ON CONFLICT обновляет поля записей с фиксированными
тестовыми ID, остальные записи не затрагиваются. Все файлы выполняются одной транзакцией;
ошибка откатывает весь набор и блокирует тесты. Базовый набор остаётся для отладки.

При `AUTH_MODE=host` runner ждёт запущенный разработчиком сервис: сразу показывает
health URL и `READY_TIMEOUT` (по умолчанию 180 секунд), затем причину отказа и статус
примерно каждые 10 секунд. По таймауту сохраняется ошибка с адресом и последней
причиной; Ctrl+C отмечается как прерывание пользователем. В полном `integration-run`
это происходит до сборки тестового образа и запуска pytest. Для короткой проверки
можно задать `READY_TIMEOUT=5`, например из pytests:

```sh
make integration-run AUTH_MODE=host TEST_MODE=container SEED_DATA=true READY_TIMEOUT=5
```

## Режимы и настройки

| AUTH_MODE | TEST_MODE | Что запускается |
| --- | --- | --- |
| container | container | Сервис и pytest в Docker; значения по умолчанию для нового стенда |
| container | host | Сервис в Docker, pytest на компьютере |
| host | container | Сервис в IDE, pytest в Docker |
| host | host | Сервис в IDE, pytest на компьютере |

Для нового контейнерного сервиса и pytest на хосте: `make integration-run TEST_MODE=host`.
TEST_MODE можно менять между запусками IDE-сессии. Для смены AUTH_MODE нужен явный down.
На компьютере используется один стенд с постоянными loopback-портами: auth 8080,
PostgreSQL 5432, Redis 6379, Vault 8200, RabbitMQ AMQP 5672, OpenFGA HTTP 8081.
Если порт занят, освободите его самостоятельно: runner не меняет порты и не останавливает
посторонние контейнеры. CI не публикует host-порты и использует отдельные RUN_ID.

| Параметр | Назначение |
| --- | --- |
| PYTEST_CONFIG | Локальный YAML тестов и seed; для IDE по умолчанию pytests/config.yaml |
| AUTH_IMAGE | Другой образ сервиса вместо latest |
| SEED_DATA | true по умолчанию; false — пропуск автоматической подготовки фикстурой локально |
| TESTKIT_DIR | Другая рабочая копия, например ../testkit, вместо сабмодуля |
| READY_TIMEOUT | Таймаут готовности/seed, 180 секунд по умолчанию; не ограничивает pytest |
| RUN_ID | CI/адресная диагностика отдельного прогона; локально не требуется |
| TESTKIT_SUBNET_POOL | Только обход ошибки выделения Docker-сети, обычно не нужен |

Для сервиса IDE используются локальные YAML потребителей. Для управляемого
контейнерного стенда testkit хранит отдельные тестовые конфиги: config-pytest.yaml
в сети Compose и config-host.yaml для pytest на хосте. Их реквизиты относятся именно
к этому стенду. PYTEST_CONFIG позволяет выбрать свой файл и для TEST_MODE=host
с контейнерным сервисом; подключение должно соответствовать поднятым зависимостям.
Для прямого pytest из IDE достаточно cwd pytests (config.yaml по умолчанию).
Логи контейнерного стенда: make integration-logs; логи сервиса IDE — в IDE.
Подробнее: [README testkit](https://github.com/Pizhlo/bot-zanuda-testkit/blob/b8302789ae962b0e75fb0310ba46437f688a8afc/README.md).

Testkit — приватный репозиторий: для ссылки и клонирования нужен доступ к нему.
Без авторизации GitHub может показывать 404, хотя файл существует.

Повторный прогон использует ту же инфраструктуру. Тесты создания ресурсов удаляют
свои связи OpenFGA после каждого сценария; проверка `already exists` сама создаёт
нужный ресурс заранее. Для очистки в YAML указан блок `openfga` с адресом и именем
тестового хранилища. Очередь ошибок auth-service очищается перед проверкой audit-сообщения.
Общий SQL-загрузчик подготавливает базовые записи PostgreSQL; отдельные фикстуры
по-прежнему очищают временные связи OpenFGA и тестовую очередь.

## Прямые команды без управления окружением

Если инфраструктура и сервис уже готовы, можно запускать отдельно:

```sh
make test-data-auth-service-up
make test-auth-service
```

Make test-data-auth-service-up вызывает python -m tools.seed_auth и тот же загрузчик,
что фикстура. Pytest при этом не запускается. SQL находятся в testdata/auth-service;
TESTDATA_PATH позволяет выбрать другой каталог, TESTDATA_DATABASE_URL — отдельную БД.
Таблица версий не требуется; старую testdata_schema_migrations код не читает/не удаляет.
Эти команды не управляют Docker и не собирают его логи.

В integration-командах эти параметры также работают при TEST_MODE=container:
каталог TESTDATA_PATH подключается только для чтения, TESTDATA_DATABASE_URL
передаётся загрузчику через окружение. Относительный SQL-путь считается от репозитория
потребителя; при прямом seed/pytest — от cwd. DSN меняет только БД подготовки данных:
она должна соответствовать БД проверяемого сервиса. Параметры задаются для каждой команды;
без TESTDATA_PATH контейнер использует SQL выбранного образа.

При прямом запуске pytest/seed путь PYTEST_CONFIG (в том числе относительный)
считается от рабочего каталога процесса; без него используется config.yaml из cwd.
Тесты и загрузчик читают PostgreSQL через общий источник и одинаковые defaults.
Для seed достаточно секции postgres, остальные настройки сервисов не обязательны.
Отсутствующий файл — ошибка до подключения к БД. Integration-команды по-прежнему
передают явный путь к конфигу потребителя.
Подробнее: [контракт пайплайна](specs/autotests/pipeline.md).

## Где смотреть результат pytest

В GitHub Actions откройте запуск → Summary: там находится блок «pytest: auth-service»
с настоящей строкой результата, например `86 passed in 2.20s`, и общим статусом прогона.
Полный вывод каждого теста — в задании, шаг «Выполнить полный прогон тестов auth-service».
Подготовка, логи контейнеров и уборка свёрнуты в отдельные группы; pytest выведен открыто.
В конце шага сводка повторяется после служебных логов. Если pytest не запускался,
это указано явно. Ошибка уборки означает неуспех прогона даже при успешных тестах.
Ранее завершённые запуски сохраняют прежний вид логов.

## Как Make-команды находят реализацию

В auth-service и pytests `make integration-seed` вызывает
`make -C ./testkit integration-seed`. Флаг `-C` выбирает другой каталог:
вложенный make читает `testkit/Makefile`. Переменная `$@` означает запрошенную цель,
а `$(MAKE)` — используемую программу make. Префикс `@` скрывает текст команды,
но не её вывод. Параметры командной строки передаются вложенному make автоматически.

В `testkit/Makefile` выражение `$(patsubst integration-%,%,$@)` превращает
`integration-seed` в `seed`, после чего выполняется `python3 scripts/integration.py seed`.
Метод `Runner.seed()` ждёт готовности сервиса и запускает загрузку тестовых данных.
Остальные integration-команды делегируются тем же способом; вся оркестрация остаётся в testkit.


## Образ сервиса в GitHub Actions

Workflow «Тесты» берёт адрес auth-service из Actions secret
`AUTH_SERVICE_IMAGE_REPOSITORY` этого репозитория. Значение — адрес без тега
(`[registry/]namespace/repository`); workflow добавляет `:latest`.
Для ручной проверки другого образа задайте полный адрес в input `auth_image`.
Если secret отсутствует и override не задан, запуск остановится с пояснением.

Существующие `DOCKER_USERNAME` и `DOCKER_REPO_NAME` относятся к публикации
собственного образа pytests и не заменяют адрес образа сервиса.
Локальный запуск сохраняет прежний default latest и параметр `AUTH_IMAGE`;
GitHub Secrets для него не нужны.

## Данные перед тестами и отдельно

`make test-auth-service` в pytests автоматически запускает сессионную фикстуру данных.
Она действует только в tests/auth_service; webserver не затрагивается.
`make test-data-auth-service-up` подготавливает тот же набор без сбора/запуска pytest;
команду можно повторять. `integration-seed` сохраняется как обёртка с готовностью/логами.
Полный integration-run не запускает отдельный seed-процесс перед pytest.

При SEED_DATA=false pytest использует существующие данные без подготовки. Явная команда
seed всегда применяет данные. SQL пишутся без настоящих секретов, с ON CONFLICT по
тестовым первичным ключам; нумерация файлов задаёт порядок, все up-файлы исполняются
при каждой подготовке. Схему и её миграции по-прежнему создаёт auth-service.

Для CI auth-service нужен обновлённый образ pytests с фикстурой auth_data; старый
образ с migrate не соответствует новому контракту. Сначала выпустите тестовый образ,
затем обновляйте закреплённый testkit. Адрес образа задаётся через прежние Secrets.

Проверки самого загрузчика без БД: `make test-seed` (unittest и покрытие не ниже 80%).
Они выполняются также в workflow lint. `make lint` проверяет стиль и типы нового кода.


## Когда запускается workflow «Тесты»

Автоматически — на push в main/develop и PR в эти ветки, если изменены:

- `tests/auth_service/**` (имя каталога с подчёркиванием), общие `tests/fixtures/**`,
  conftest и `tests/__init__.py`;
- `src/**`, `utils/**`, `testdata/auth-service/**` или загрузчик `tools/seed_auth.py`;
- зависимости и настройки pytest/Python, Makefile, Dockerfile или .dockerignore;
- закреплённая версия testkit, .gitmodules или .github/workflows/auth-service.yaml.

Изменения только README/спецификаций или `tests/webserver/**` этот workflow не запускают.
В PR учитывается весь diff ветки: если он уже содержит auth-изменения, добавление
коммита только с README всё равно запускает проверку. Ручной Run workflow доступен всегда.
Единый список путей находится в `paths: &auth_service_paths` этого workflow; при добавлении
зависимостей тестов обновляйте его. Список для pull_request ссылается на него через `*auth_service_paths`.

Интеграционное задание пропускается для PR из fork: такому запуску недоступны
Actions Secrets и приватный testkit. Условие действует до checkout; это пропуск,
а не успешное выполнение тестов. PR из веток этого репозитория и ручные запуски
сохраняют прежнее поведение. Secrets внешнему PR не передаются.


При AUTH_MODE=host `integration-rabbitmq-setup` отказывает до Docker: RabbitMQ
подготавливается `containers-up` из auth-service. Если после контейнерных тестов
переключить TEST_MODE на host, прежние jobs остаются доступны через integration-logs
и удаляются явным integration-down. Эти команды не останавливают зависимости IDE.
Ранние ошибки параметров/инициализации сохраняются в `.logs/<run-id>/initialization.log`;
ошибка параллельной команды не изменяет журнал активного запуска.
