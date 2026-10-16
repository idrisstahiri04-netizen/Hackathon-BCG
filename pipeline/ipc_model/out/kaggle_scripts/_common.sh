#!/usr/bin/env bash
# Shared helpers for scripts/kaggle/*.sh. Source this file; do not run it.
set -euo pipefail

REPO="/home/looooo/bcg/Hackathon-BCG"
KDIR="$REPO/pipeline/ipc_model/out/kaggle_scripts"
BUILD="$KDIR/.build"          # staging dirs (gitignored)
STATE="$KDIR/.state"          # last-pushed hashes (gitignored)
mkdir -p "$BUILD" "$STATE"

KAGGLE="${KAGGLE:-/home/looooo/bcg/.venv/bin/kaggle}"
KUSER="${KUSER:-omarserghini}"
DATA_SLUG="${DATA_SLUG:-drought-signals}"
CODE_SLUG="${CODE_SLUG:-drought-code}"
KERNEL_SLUG="${KERNEL_SLUG:-drought-train}"

# auth: token file, never printed
if [ -z "${KAGGLE_API_TOKEN:-}" ]; then
  [ -f "$HOME/.kaggle/access_token" ] || { echo "!! no ~/.kaggle/access_token and KAGGLE_API_TOKEN unset" >&2; exit 2; }
  export KAGGLE_API_TOKEN="$(cat "$HOME/.kaggle/access_token")"
fi

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }

# sha256 over file names + contents of a staged dir (stable order)
tree_hash() { (cd "$1" && find . -type f -o -type l | LC_ALL=C sort | xargs sha256sum | sha256sum | cut -c1-16); }

dataset_exists() { "$KAGGLE" datasets status "$KUSER/$1" >/dev/null 2>&1; }

# wait until a dataset's latest version is processed (new kernels can only attach a ready dataset)
wait_dataset_ready() {
  local slug="$1" i
  for i in $(seq 1 60); do
    local s; s="$("$KAGGLE" datasets status "$KUSER/$slug" 2>/dev/null || true)"
    case "$s" in *ready*) return 0;; esac
    sleep 5
  done
  log "!! dataset $slug not ready after 5 min (status: $s)"; return 1
}

# create or version a staged dataset dir; skips when the tree hash matches the last push
# usage: push_dataset <slug> <title> <staged_dir> [--force]
push_dataset() {
  local slug="$1" title="$2" dir="$3" force="${4:-}"
  local h; h="$(tree_hash "$dir")"
  local sf="$STATE/$slug.sha"
  if [ "$force" != "--force" ] && [ -f "$sf" ] && [ "$(cat "$sf")" = "$h" ] && dataset_exists "$slug"; then
    log "$slug unchanged ($h), skipping upload"; return 0
  fi
  cat > "$dir/dataset-metadata.json" <<JSON
{"title": "$title", "id": "$KUSER/$slug", "licenses": [{"name": "CC0-1.0"}]}
JSON
  if dataset_exists "$slug"; then
    log "versioning $KUSER/$slug ($h)"
    "$KAGGLE" datasets version -p "$dir" -m "auto $(date -u +%FT%TZ) $h" -t -r tar -q
  else
    log "creating PRIVATE dataset $KUSER/$slug ($h)"
    "$KAGGLE" datasets create -p "$dir" -t -r tar -q     # private is the default (no -u)
  fi
  wait_dataset_ready "$slug"
  sleep 30      # "ready" precedes mountability by a few seconds; a kernel started too early sees no /kaggle/input/<slug>
  echo "$h" > "$sf"
}
