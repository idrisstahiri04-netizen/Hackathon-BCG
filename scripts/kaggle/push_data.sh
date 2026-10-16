#!/usr/bin/env bash
# Create/update the PRIVATE Kaggle dataset omarserghini/drought-signals with the pipeline inputs.
#   scripts/kaggle/push_data.sh [--force]
# Contents (flat): signals_*.parquet, units_*.geojson, pop_*.csv, ipc_*.parquet, seasonal_fc_*.parquet,
# timesfm_*.parquet (from pipeline/out). A new dataset version is made only when a file changed.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ST="$BUILD/data"; rm -rf "$ST"; mkdir -p "$ST"
n=0
for f in "$REPO"/pipeline/data/signals_*.parquet "$REPO"/pipeline/data/units_*.geojson \
         "$REPO"/pipeline/data/pop_*.csv "$REPO"/pipeline/data/ipc_*.parquet \
         "$REPO"/pipeline/data/seasonal_fc_*.parquet "$REPO"/pipeline/out/timesfm_*.parquet; do
  [ -f "$f" ] || continue
  cp -p "$f" "$ST/"; n=$((n+1))
done
[ $n -ge 1 ] || { log "!! nothing to upload"; exit 1; }
log "staged $n files ($(du -sh "$ST" | cut -f1))"
push_dataset "$DATA_SLUG" "drought-signals (pipeline inputs)" "$ST" "${1:-}"
