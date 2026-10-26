#!/usr/bin/env bash
# Runs ON the Lapi VM: backend (pytest) and frontend (unit + typecheck) suites in
# throwaway containers against the checked-out branch. Prints a short summary;
# full logs go to /opt/lapi/test-logs/.
#   bash lapi_deploy/lapi_oci/vm_test.sh [backend|frontend|all] [pytest args...]
set -uo pipefail
APP=/opt/lapi/app; LOGS=/opt/lapi/test-logs; mkdir -p "$LOGS"
WHAT="${1:-all}"; shift || true
cd "$APP" && git pull -q --ff-only || true
COMMIT=$(git rev-parse --short HEAD)

backend() {
  docker build -q -t lapi-tests-backend -f - . >/dev/null <<'D'
FROM python:3.12-slim
WORKDIR /src
COPY lapi_backend/requirements*.txt lapi_backend/
COPY lapi_testing/backend/requirements.txt lapi_testing/backend/
RUN pip install --no-cache-dir -r lapi_testing/backend/requirements.txt
D
  docker run --rm -v "$APP":/src:ro -w /src lapi-tests-backend \
    python -B lapi_testing/run_backend_tests.py -p no:randomly "$@" > "$LOGS/backend.log" 2>&1
  local rc=$?
  echo "BACKEND $COMMIT exit=$rc"; grep -E "^(FAILED|ERROR) " "$LOGS/backend.log" | cut -c1-150 | head -25; tail -n 2 "$LOGS/backend.log"
}

frontend() {
  docker run --rm -v "$APP":/src:ro node:22-bookworm-slim bash -c '
    mkdir /w && cd /src && tar --exclude=node_modules --exclude=.git -cf - . | (cd /w && tar -xf -)
    cd /w/lapi_frontend && npm ci --no-audit --no-fund >/dev/null 2>&1 || { echo "npm ci failed"; exit 2; }
    npm run test:unit 2>&1 | tail -n 25; u=${PIPESTATUS[0]}
    npm run typecheck 2>&1 | tail -n 15; t=${PIPESTATUS[0]}
    echo "UNIT=$u TYPECHECK=$t"; [ $u -eq 0 ] && [ $t -eq 0 ]' > "$LOGS/frontend.log" 2>&1
  local rc=$?
  echo "FRONTEND $COMMIT exit=$rc"; grep -E "^# (pass|fail)|not ok|error TS|UNIT=|npm ci failed" "$LOGS/frontend.log" | cut -c1-150 | head -25
}

case "$WHAT" in
  backend) backend "$@" ;;
  frontend) frontend ;;
  *) backend "$@"; frontend ;;
esac
