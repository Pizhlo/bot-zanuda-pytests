#!/usr/bin/env bash
# Контракт общего runner проверяется без Docker; выполняется настоящий run_all.sh.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/bin" "$scratch/project/tools" "$scratch/testkit"
cp "$root/tools/run_all.sh" "$scratch/project/tools/"
export TRACE="$scratch/trace"
cat > "$scratch/bin/docker" <<'MOCK'
#!/usr/bin/env bash
printf 'docker %s\n' "$*" >> "$TRACE"
if [[ "$1" == build && "$CASE" == build-failure ]]; then exit 2; fi
if [[ "$1" == pull && "$CASE" == pull-failure && "$2" == *auth-service* ]]; then exit 2; fi
if [[ "$1" == image ]]; then echo sha256:test-image; fi
MOCK
cat > "$scratch/bin/python3" <<'MOCK'
#!/usr/bin/env bash
set -eu
[[ "$CI/$AUTH_MODE/$WEBSERVER_MODE/$TEST_MODE/$SEED_DATA" == true/container/container/container/true ]]
[[ -z "${PYTEST_CONFIG:-}${TESTDATA_PATH:-}${TESTDATA_DATABASE_URL:-}${COMPOSE_PROJECT_NAME:-}" ]]
[[ "$RUN_ID" == all-*"$INTEGRATION_SERVICE" ]]
[[ "$AUTOTESTS_IMAGE" == sha256:test-image ]]
printf '%s %s\n' "$INTEGRATION_SERVICE" "$2" >> "$TRACE"
if [[ "$CASE" == first-failure && "$INTEGRATION_SERVICE/$2" == auth-service/run ]]; then exit 2; fi
if [[ "$CASE" == second-failure && "$INTEGRATION_SERVICE/$2" == webserver/run ]]; then exit 2; fi
if [[ "$CASE" == cleanup-failure && "$INTEGRATION_SERVICE/$2" == auth-service/down ]]; then exit 2; fi
if [[ "$CASE" == interrupted && "$2" == run ]]; then kill -TERM "$PPID"; fi
MOCK
chmod +x "$scratch/bin/"*
export PATH="$scratch/bin:$PATH"
# Унаследованные настройки IDE должны быть изолированы от общего запуска.
export PYTEST_CONFIG=private.yaml TESTDATA_PATH=private TESTDATA_DATABASE_URL=private
export COMPOSE_PROJECT_NAME=ide AUTH_MODE=host TEST_MODE=host RUN_ID=ide SEED_DATA=false
for CASE in success first-failure second-failure cleanup-failure build-failure pull-failure interrupted; do
    export CASE
    : > "$TRACE"
    code=0
    bash "$scratch/project/tools/run_all.sh" "$scratch/testkit" > "$scratch/output" 2>&1 || code=$?
    if [[ "$CASE" == success ]]; then
        [[ "$code" == 0 ]]
    else
        [[ "$code" != 0 ]]
    fi
    [[ $(grep -c '^docker build ' "$TRACE") == 1 ]]
    if [[ "$CASE" == build-failure ]]; then
        ! grep -q ' run$' "$TRACE"
    elif [[ "$CASE" == interrupted ]]; then
        grep -q '^auth-service down$' "$TRACE"
        ! grep -q '^webserver run$' "$TRACE"
    else
        grep -q '^webserver run$' "$TRACE"
        grep -q '^auth-service down$' "$TRACE"
        grep -q '^webserver down$' "$TRACE"
        grep -q 'Итог всех сервисов:' "$scratch/output"
    fi
    printf '%s: OK\n' "$CASE"
done
