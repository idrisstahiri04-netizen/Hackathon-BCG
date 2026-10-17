#!/usr/bin/env bash
# One-command demo start. Idempotent: re-running it never starts a second copy.
#
#   scripts/start_demo.sh            start backend (:8000) + static site (:8777), seed demo users
#   scripts/start_demo.sh --fresh    same, but wipe backend/demo.db first (clean stage)
#   scripts/start_demo.sh --no-seed  do not create the demo subscribers
#   scripts/start_demo.sh --check    prerequisites only, start nothing
#
# Env overrides: GATEWAY=sim|log|android  BACKEND_PORT=8000  SITE_PORT=8777
#                BACKEND_HOST=127.0.0.1 (use 0.0.0.0 if the Android gateway must reach us)
#                DEMO_ISO3=KEN (seed country)  VENV=/path/to/venv     ENV_FILE=/path/to/.env
# Logs + pids: scripts/.run/   Stop with scripts/stop_demo.sh
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
RUN="$HERE/.run"
mkdir -p "$RUN"

BACKEND_PORT="${BACKEND_PORT:-8000}"
SITE_PORT="${SITE_PORT:-8777}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
GATEWAY_FROM_SHELL="${GATEWAY:-}"   # shell env > .env > sim (decided after .env is located)

FRESH=0; SEED=1; CHECK_ONLY=0
for a in "$@"; do
  case "$a" in
    --fresh) FRESH=1 ;;
    --no-seed) SEED=0 ;;
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n 2,13p "$0"; exit 0 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yel()   { printf '\033[33m%s\033[0m\n' "$*"; }
fail=0
ok()   { green "  [ok]   $*"; }
bad()  { red   "  [FAIL] $*"; fail=1; }
warn() { yel   "  [warn] $*"; }

echo "== prerequisites"

# --- venv -------------------------------------------------------------------
PY=""
for cand in "${VENV:-}" "$REPO/.venv" "$REPO/../.venv"; do
  [ -n "$cand" ] && [ -x "$cand/bin/python" ] && { PY="$cand/bin/python"; break; }
done
if [ -z "$PY" ]; then
  bad "no venv found (looked at \$VENV, $REPO/.venv, $REPO/../.venv). Create one: python3 -m venv ../.venv && ../.venv/bin/pip install fastapi uvicorn anthropic httpx python-dotenv pyyaml"
else
  missing="$("$PY" - <<'EOF'
import importlib.util
mods = ["fastapi", "uvicorn", "anthropic", "httpx", "dotenv", "yaml", "rapidfuzz", "pydantic"]
print(" ".join(m for m in mods if importlib.util.find_spec(m) is None))
EOF
)"
  if [ -n "$missing" ]; then
    bad "venv $PY is missing modules: $missing  (pip install them into the venv)"
  else
    ok "venv $PY ($("$PY" --version 2>&1))"
  fi
fi

# --- .env / API key (never printed) -----------------------------------------
ENVF=""
for cand in "${ENV_FILE:-}" "$REPO/.env" "$REPO/../.env"; do
  [ -n "$cand" ] && [ -f "$cand" ] && { ENVF="$cand"; break; }
done
if [ -z "$ENVF" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  bad "no .env found (\$ENV_FILE, $REPO/.env, $REPO/../.env) and ANTHROPIC_API_KEY not exported"
else
  keylen=0
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    keylen=${#ANTHROPIC_API_KEY}
  else
    keylen=$(grep -E '^[[:space:]]*(export[[:space:]]+)?ANTHROPIC_API_KEY=' "$ENVF" | tail -1 \
             | sed -E 's/^[^=]*=//; s/^["'"'"']//; s/["'"'"'][[:space:]]*$//' | tr -d '\r\n' | wc -c)
  fi
  if [ "$keylen" -lt 20 ]; then
    bad "ANTHROPIC_API_KEY missing or too short in ${ENVF:-environment} (len=$keylen). Router will fall back to keyword parsing."
  else
    ok "ANTHROPIC_API_KEY present in ${ENVF:-environment} (len=$keylen, not shown)"
  fi
  [ -n "$ENVF" ] && export ENV_FILE="$ENVF"
fi

if [ -n "$GATEWAY_FROM_SHELL" ]; then export GATEWAY="$GATEWAY_FROM_SHELL"
elif [ -n "$ENVF" ] && grep -qE '^GATEWAY=' "$ENVF"; then export GATEWAY="$(grep -E '^GATEWAY=' "$ENVF" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
else export GATEWAY=sim; fi
if [ "$GATEWAY" = "android" ]; then
  gw_url="$( [ -n "$ENVF" ] && grep -E '^ANDROID_GW_URL=' "$ENVF" | tail -1 | cut -d= -f2- )"
  [ -n "${ANDROID_GW_URL:-$gw_url}" ] && ok "GATEWAY=android, ANDROID_GW_URL set" || bad "GATEWAY=android but ANDROID_GW_URL not set in .env"
else
  ok "GATEWAY=$GATEWAY (no real SMS; Phone tab shows replies)"
fi

# --- files -------------------------------------------------------------------
[ -f "$REPO/backend/app.py" ] && ok "backend/app.py present" || bad "backend/app.py missing"
[ -f "$REPO/js/live.js" ] && ok "js/live.js present" || warn "js/live.js missing (Alert/Users/Phone tabs will not work)"
[ -f "$REPO/vendor/globe.gl.min.js" ] && ok "vendor/globe.gl.min.js present (offline globe)" || bad "vendor/globe.gl.min.js missing"
for iso in KEN; do
  f="$REPO/data/risk/$iso.js"
  if [ ! -f "$f" ]; then bad "data/risk/$iso.js missing"
  elif grep -q '"model_version":"STUB"' "$f" || grep -q '"model_version": *"STUB"' "$f"; then
    warn "data/risk/$iso.js is a STUB: globe shows DATA IN PROGRESS and /alerts/run refuses it"
  else ok "data/risk/$iso.js has real model output"; fi
done

# --- ports -------------------------------------------------------------------
port_pid() { ss -ltnpH "sport = :$1" 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2; }
pidfile_alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

BE_PID_F="$RUN/backend.pid"; SITE_PID_F="$RUN/site.pid"
be_busy="$(port_pid "$BACKEND_PORT")"; site_busy="$(port_pid "$SITE_PORT")"
be_ours=0; site_ours=0
if [ -n "$be_busy" ]; then
  if pidfile_alive "$BE_PID_F" && [ "$(cat "$BE_PID_F")" = "$be_busy" ]; then be_ours=1; ok "backend already running on :$BACKEND_PORT (pid $be_busy)"
  elif tr '\0' ' ' < "/proc/$be_busy/cmdline" 2>/dev/null | grep -q 'backend.app'; then be_ours=1; echo "$be_busy" > "$BE_PID_F"; ok "backend already running on :$BACKEND_PORT (pid $be_busy, adopted)"
  else bad "port :$BACKEND_PORT is used by another process (pid $be_busy): $(tr '\0' ' ' < "/proc/$be_busy/cmdline" 2>/dev/null | cut -c1-80)"; fi
else ok "port :$BACKEND_PORT free"; fi
if [ -n "$site_busy" ]; then
  if pidfile_alive "$SITE_PID_F" && [ "$(cat "$SITE_PID_F")" = "$site_busy" ]; then site_ours=1; ok "static server already running on :$SITE_PORT (pid $site_busy)"
  elif tr '\0' ' ' < "/proc/$site_busy/cmdline" 2>/dev/null | grep -q 'http.server'; then site_ours=1; echo "$site_busy" > "$SITE_PID_F"; ok "static server already running on :$SITE_PORT (pid $site_busy, adopted)"
  else bad "port :$SITE_PORT is used by another process (pid $site_busy)"; fi
else ok "port :$SITE_PORT free"; fi

if [ "$fail" = 1 ]; then red "prerequisites failed; fix the [FAIL] lines above."; exit 1; fi
[ "$CHECK_ONLY" = 1 ] && { green "check only: all good."; exit 0; }

# --- fresh db -----------------------------------------------------------------
if [ "$FRESH" = 1 ]; then
  if [ "$be_ours" = 1 ]; then
    yel "  --fresh: stopping running backend to wipe the db"
    kill "$(cat "$BE_PID_F")" 2>/dev/null; sleep 1; be_ours=0
  fi
  rm -f "$REPO/backend/demo.db" "$REPO/backend/demo.db-wal" "$REPO/backend/demo.db-shm"
  ok "removed backend/demo.db"
fi

echo "== starting"
cd "$REPO" || exit 1

if [ "$be_ours" = 0 ]; then
  nohup "$PY" -m uvicorn backend.app:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
      --log-level info >> "$RUN/backend.log" 2>&1 &
  echo $! > "$BE_PID_F"
  ok "backend starting (pid $!, log $RUN/backend.log)"
fi
if [ "$site_ours" = 0 ]; then
  nohup "$PY" -m http.server "$SITE_PORT" --bind 127.0.0.1 --directory "$REPO" >> "$RUN/site.log" 2>&1 &
  echo $! > "$SITE_PID_F"
  ok "static server starting (pid $!, log $RUN/site.log)"
fi

# wait for health
BE="http://127.0.0.1:$BACKEND_PORT"
up=0
for i in $(seq 1 40); do
  if curl -fsS -m 2 "$BE/health" >/dev/null 2>&1; then up=1; break; fi
  sleep 0.5
done
if [ "$up" = 1 ]; then ok "backend healthy: $(curl -fsS -m 2 "$BE/health")"
else bad "backend did not answer /health in 20 s. Last log lines:"; tail -n 15 "$RUN/backend.log"; exit 1; fi
curl -fsS -m 3 -o /dev/null "http://127.0.0.1:$SITE_PORT/index.html" && ok "static site serving index.html" || bad "static site not answering"

# --- warm-up + UI token: the backend now warms the Claude client itself at startup (backend/llm.py
# warm_up), so no throw-away SMS is needed. Write js/config.local.js (gitignored) so the UI sends X-API-Key.
"$PY" "$REPO/backend/make_ui_config.py" --api "$BE" >/dev/null \
  && ok "UI config written (js/config.local.js, token not shown)" \
  || warn "could not write js/config.local.js (UI operator actions will get 401)"

# --- seed demo users (idempotent: phones are UNIQUE, JOIN is a keyword fast-path) --
if [ "$SEED" = 1 ]; then
  echo "== seeding demo users"
  # team seeder (backend/seed_demo.py): writes straight to the same SQLite db, keyed on phone -> idempotent
  "$PY" -m backend.seed_demo --iso3 "${DEMO_ISO3:-KEN}" 2>&1 | sed 's/^/  /'; rc=${PIPESTATUS[0]}
  [ "$rc" = 0 ] && ok "demo users seeded" || warn "seeding failed rc=$rc (demo still works; users can join live)"
fi

echo
green "== ready"
echo "  Globe + tabs : http://localhost:$SITE_PORT/"
echo "  Stage deep link: http://localhost:$SITE_PORT/?country=Kenya&t=92"
echo "  Backend       : $BE/health   docs: $BE/docs"
echo "  Gateway mode  : $GATEWAY"
echo "  Logs          : $RUN/backend.log  $RUN/site.log"
echo "  Stop          : scripts/stop_demo.sh"
exit 0
