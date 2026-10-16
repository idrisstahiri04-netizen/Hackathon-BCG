#!/usr/bin/env bash
# signals -> train (all countries pooled) -> export, for the given countries.
#   pipeline/run_all.sh ZWE KEN MWI ZMB
#   FORCE_SIGNALS=1 pipeline/run_all.sh ZWE      # re-extract signals even if the parquet exists
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-/home/looooo/bcg/.venv/bin/python}"
[ $# -ge 1 ] || set -- ZWE KEN MWI ZMB
declare -A ADM=([ZWE]=2 [KEN]=1 [MWI]=2 [ZMB]=2)

have=()
for c in "$@"; do
  c="${c^^}"
  f="$HERE/data/signals_${c}.parquet"
  if [ ! -f "$f" ] || [ "${FORCE_SIGNALS:-0}" = 1 ]; then
    echo "== signals $c (ADM${ADM[$c]:-2})"
    "$PY" "$HERE/extract_signals.py" --iso3 "$c" --adm "${ADM[$c]:-2}" --start 2001 --end 2024 \
      || { echo "!! signals failed for $c, skipping"; continue; }
  fi
  [ -f "$f" ] && have+=("$c")
done
[ ${#have[@]} -ge 1 ] || { echo "no signals available"; exit 1; }

echo "== train (pooled: ${have[*]})"
cd "$HERE"
"$PY" train.py --iso3 "${have[@]}"
echo "== export"
"$PY" export_risk.py --iso3 "${have[@]}"
