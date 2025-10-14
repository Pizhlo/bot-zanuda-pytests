# Bot Zanuda — интеграционные тесты

## Тесты auth-service на Linux

Установите Docker с Compose, Make, Python 3 и PyYAML. Инициализируйте закреплённый
сабмодуль `testkit`: `git submodule update --init --recursive`.
Для pytest на хосте также нужны uv и Python 3.13.
Конфигурацию окружения предоставляет testkit; копировать файлы из GitHub Secrets не нужно.

```sh
make integration-run
# Во время разработки можно выбрать рабочую копию testkit:
make integration-run TESTKIT_DIR=../testkit
```

Скрипт собирает текущие исходники тестов и по умолчанию использует auth-service latest.
`AUTH_IMAGE` переопределяет образ сервиса. `integration-up` только готовит окружение;
`integration-run` выполняет подготовку, загрузку данных и тесты. Каждый новый прогон изолирован.

Для сервиса, запущенного из IDE:

```sh
make integration-up AUTH_MODE=native
# Запустите auth-service из его репозитория с -config <напечатанный-путь-auth-host.yaml>.
# Флаги Go в IDE: -ldflags="-X main.Version=dev -X main.BuildDate=local -X main.GitCommit=local"
make integration-run RUN_ID=<выданный-id>
```

Для ручной отладки pytest после запуска сервиса:

```sh
make integration-seed RUN_ID=<выданный-id>
PYTEST_CONFIG=<напечатанный-путь-pytest-host.yaml> make test-auth-service
make integration-down RUN_ID=<выданный-id>
```

`TEST_MODE=host` выбирает pytest на хосте для общего прогона. По умолчанию тесты запускаются
в контейнере; нативный Linux-сервис доступен им через сеть хоста.
Вывод нативного сервиса остаётся в IDE. Docker-логи доступны через
`make integration-logs RUN_ID=...`.
Полный локальный успех удаляет окружение; ошибка сохраняет контейнеры и `.logs/<id>/run.log`.
В GitHub Actions вывод остаётся в журнале задания; попытка уборки выполняется при любом исходе.

### Загрузка данных без общего скрипта запуска

После подготовки схемы самим сервисом используйте golang-migrate **v4.19.1**:

```sh
PYTEST_CONFIG=/absolute/path/pytest-host.yaml make test-data-auth-service-up
# Для отдельно установленного бинарника закреплённой версии:
MIGRATE_BIN=/absolute/path/migrate PYTEST_CONFIG=/absolute/path/pytest-host.yaml make test-data-auth-service-up
```

Команда загрузки не требует psql или Docker socket. SQL находятся в `testdata/auth-service`.
Таблица `testdata_schema_migrations` ведёт историю отдельно от миграций приложения.
Повторный up без новых версий сообщает `no change`. Ошибки SQL и состояние dirty
останавливают прогон; автоматические force и откат не выполняются.
Подробнее: [контракт пайплайна](specs/autotests/pipeline.md).

### Пул сетей и обновление

Если маршруты VPN мешают автоматическому выделению Docker-подсетей, передайте свободный
частный диапазон через `TESTKIT_SUBNET_POOL`. Пример: `172.30.0.0/16`, только если он
не занят локальными или удалёнными ресурсами. Каждый прогон получает отдельную /24;
настройки демона Docker не меняются.
Для локально собранного сервиса укажите неизменяемый ID:
`AUTH_IMAGE=$(docker image inspect <tag> --format '{{.Id}}')`.

Обновляйте testkit только на опубликованный совместимый коммит:
`git -C testkit fetch origin`, `git -C testkit checkout <commit>`, затем `git add testkit`.
[Порядок выпуска и отката](testkit/README.md) описывает обновление всех трёх репозиториев.
До переключения CI сервиса образ pytests должен содержать migrate v4.19.1 и прямую
команду загрузки данных. Образ сервиса должен содержать непустые метаданные сборки;
ранее проверенный latest требует исправленного выпуска.
Задание auth-service в Actions независимо от существующего задания webserver.
Для доступа CI к приватному testkit используется `CI_GITHUB_TOKEN` либо уже настроенный
`GH_TOKEN`. Это токен доступа к репозиторию, а не содержимое тестовой конфигурации.

## Где смотреть результат pytest

В GitHub Actions откройте запуск → Summary: там находится блок «pytest: auth-service»
с настоящей строкой результата, например `86 passed in 2.20s`, и общим статусом прогона.
Полный вывод каждого теста — в задании, шаг «Выполнить полный прогон тестов auth-service».
Подготовка, логи контейнеров и уборка свёрнуты в отдельные группы; pytest выведен открыто.
В конце шага сводка повторяется после служебных логов. Если pytest не запускался,
это указано явно. Ошибка уборки означает неуспех прогона даже при успешных тестах.
Ранее завершённые запуски сохраняют прежний вид логов.

## Как Make-команды находят реализацию

В auth-service и pytests `make integration-seed RUN_ID=...` вызывает
`make -C ./testkit integration-seed RUN_ID=...`. Флаг `-C` выбирает другой каталог:
вложенный make читает `testkit/Makefile`. Переменная `$@` означает запрошенную цель,
а `$(MAKE)` — используемую программу make. Префикс `@` скрывает текст команды,
но не её вывод. Параметры командной строки передаются вложенному make автоматически.

В `testkit/Makefile` выражение `$(patsubst integration-%,%,$@)` превращает
`integration-seed` в `seed`, после чего выполняется `python3 scripts/integration.py seed`.
Метод `Runner.seed()` ждёт готовности сервиса и запускает загрузку тестовых данных.
Остальные integration-команды делегируются тем же способом; вся оркестрация остаётся в testkit.
