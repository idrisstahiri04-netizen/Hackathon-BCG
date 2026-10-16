#!/usr/bin/env bash
# Stop what scripts/start_demo.sh started. Idempotent: safe to run twice.
#   scripts/stop_demo.sh           stop backend (:8000) and static server (:8777)
#   scripts/stop_demo.sh --fresh   also delete backend/demo.db
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
RUN="$HERE/.run"
BACKEND_PORT="${BACKEND_PORT:-8000}"
SITE_PORT="${SITE_PORT:-8777}"

stop_pid() {  # $1 pid  $2 label
  local pid="$1"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null
    for i in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; sleep 0.3; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
    echo "  stopped $2 (pid $pid)"
  fi
}

for pair in "backend:$BACKEND_PORT:backend.app" "site:$SITE_PORT:http.server"; do
  IFS=: read -r name port needle <<<"$pair"
  pf="$RUN/$name.pid"
  if [ -f "$pf" ]; then
    stop_pid "$(cat "$pf")" "$name"; rm -f "$pf"
  fi
  # anything else of ours still holding the port (e.g. started by hand)
  for pid in $(ss -ltnpH "sport = :$port" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u); do
    if tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "$needle"; then
      stop_pid "$pid" "$name (port :$port)"
    else
      echo "  port :$port still used by pid $pid (not ours, left alone)"
    fi
  done
done

if [ "${1:-}" = "--fresh" ]; then
  rm -f "$REPO/backend/demo.db" "$REPO/backend/demo.db-wal" "$REPO/backend/demo.db-shm"
  echo "  removed backend/demo.db"
fi
echo "demo stopped."
