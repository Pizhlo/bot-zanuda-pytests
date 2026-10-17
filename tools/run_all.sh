#!/usr/bin/env bash
# Оба набора используют один образ текущих тестов и независимые стенды testkit.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
testkit=$(cd "${1:-$root/testkit}" && pwd)
run="all-$(date -u +%Y%m%d%H%M%S)-$(cat /proc/sys/kernel/random/uuid)"
logs="$root/.logs/$run"
mkdir -p "$logs"

# Полный прогон всегда изолирован от конфигов, БД и состояния IDE.
unset PYTEST_CONFIG TESTDATA_PATH TESTDATA_DATABASE_URL COMPOSE_PROJECT_NAME
export CI=true AUTH_MODE=container WEBSERVER_MODE=container TEST_MODE=container SEED_DATA=true
export INTEGRATION_ROOT="$root" PYTESTS_DIR="$root"
export AUTH_IMAGE="${AUTH_IMAGE:-pizhlo/bot-zanuda-auth-service:latest}"
export WEBSERVER_IMAGE="${WEBSERVER_IMAGE:-pizhlo/bot-zanuda-webserver:latest}"
active=''
cleanup() {
    if [[ -n "$active" ]]; then
        python3 "$testkit/scripts/integration.py" down
    fi
}
trap 'exit 130' INT
trap 'exit 143' TERM
trap cleanup EXIT

printf 'Логи общего запуска: %s\n' "$logs"
# ID не меняется при последующей сборке/перетегировании другим процессом.
image_tag="testkit-pytests:$run"
if ! docker build -t "$image_tag" "$root" 2>&1 | tee "$logs/build.log"; then
    printf 'Образ тестов: ошибка сборки; оба набора не запускались.\n'
    exit 1
fi
AUTOTESTS_IMAGE=$(docker image inspect "$image_tag" --format '{{.Id}}')
export AUTOTESTS_IMAGE
status=0
: > "$logs/summary.log"
for service in auth-service webserver; do
    export INTEGRATION_SERVICE="$service" INTEGRATION_CONTEXT="$service" RUN_ID="$run-$service"
    active="$service"
    code=0
    image="$AUTH_IMAGE"
    [[ "$service" != webserver ]] || image="$WEBSERVER_IMAGE"
    if [[ "$image" != sha256:* ]]; then
        docker pull "$image" 2>&1 | tee "$logs/$service.log" || code=$?
    fi
    # CI lifecycle включает сбор логов и уборку при успехе и ошибке.
    if [[ "$code" == 0 ]]; then
        python3 "$testkit/scripts/integration.py" run 2>&1 | tee -a "$logs/$service.log" || code=$?
    fi
    # Повторная адресная уборка также покрывает ранний отказ runner.
    cleanup >> "$logs/$service.log" 2>&1 || code=1
    active=''
    if [[ "$code" == 0 ]]; then
        printf '%s: успешно\n' "$service" >> "$logs/summary.log"
    else
        printf '%s: ошибка (код %s)\n' "$service" "$code" >> "$logs/summary.log"
        status=1
    fi
done
printf '\nИтог всех сервисов:\n'
cat "$logs/summary.log"
exit "$status"
