#!/usr/bin/env bash
# Launch the live signal/paper-trading pipeline, API, and frontend.
set -euo pipefail
# Give each service its own process group, including its subprocesses.
set -m

REPO="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$REPO/.venv/bin/python"

if [[ "${1:-}" == --help ]]; then
  echo "Usage: ./start-live.sh"
  echo "Uses .env / environment configuration. Logs: .live-logs/<run>/"
  echo "Starts the live signal and paper-trading engine, API, and frontend on port 3000."
  echo "Ctrl-C stops all services. Requires installed Python/web dependencies and Alpaca keys."
  exit 0
fi
[[ $# -eq 0 ]] || { echo "Unknown arguments. Use --help." >&2; exit 1; }
cd "$REPO"
[[ -x "$PYTHON" ]] || { echo "Missing .venv/bin/python; follow README setup." >&2; exit 1; }
[[ -d web/node_modules ]] || { echo "Run: cd web && pnpm install" >&2; exit 1; }
for command in pnpm curl lsof; do
  command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }
done

# Read only configuration, without contacting Alpaca or displaying credentials.
API_PORT="$("$PYTHON" -c 'import config; config.validate_live(); print(config.DASHBOARD_PORT)')"
for port in "$API_PORT" 3000; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Stop that server before launching." >&2
    exit 1
  fi
done
[[ "$API_PORT" != 3000 ]] || { echo "DASHBOARD_PORT must differ from frontend port 3000." >&2; exit 1; }
export FLASK_API_URL="http://127.0.0.1:$API_PORT"
mkdir -p "$REPO/.live-logs"
LOGS="$(mktemp -d "$REPO/.live-logs/run.XXXXXX")"
pids=()
names=()

stop_all() {
  local status=$?
  trap - EXIT INT TERM
  echo "Stopping services..."
  for pid in "${pids[@]}"; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  # Bound shutdown even when a service or one of its children hangs.
  for _ in {1..10}; do
    local alive=0
    for pid in "${pids[@]}"; do
      if kill -0 -- "-$pid" 2>/dev/null; then alive=1; fi
    done
    [[ "$alive" == 1 ]] || break
    sleep 1
  done
  for pid in "${pids[@]}"; do
    kill -KILL -- "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  exit "$status"
}
trap stop_all EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start() {
  local name="$1"; shift
  "$@" >"$LOGS/$name.log" 2>&1 &
  pids+=("$!")
  names+=("$name")
  echo "Started $name (pid $!). Log: $LOGS/$name.log"
}

check_services() {
  for i in "${!pids[@]}"; do
    if ! kill -0 "${pids[$i]}" 2>/dev/null; then
      echo "${names[$i]} exited. Check $LOGS/${names[$i]}.log" >&2
      return 1
    fi
  done
}

wait_for() {
  local name="$1" url="$2"
  for _ in {1..60}; do
    check_services || return 1
    if curl --fail --silent --output /dev/null --max-time 2 "$url"; then
      echo "$name is ready: $url"
      return 0
    fi
    sleep 1
  done
  echo "$name startup timed out. Check $LOGS." >&2
  return 1
}

start api "$PYTHON" -u run_dashboard.py
start engine "$PYTHON" -u run_live.py
start web bash -c 'cd web && exec pnpm dev --hostname 127.0.0.1 --port 3000'
wait_for API "$FLASK_API_URL/api/status"
wait_for Dashboard "http://127.0.0.1:3000/"
echo "Engine process running; see engine.log for feed connection and market status."
echo "Open http://127.0.0.1:3000/ — Ctrl-C stops all services."
while true; do
  check_services
  sleep 1
done
