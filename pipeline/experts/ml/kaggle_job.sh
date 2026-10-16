#!/usr/bin/env bash
# Runs INSIDE the Kaggle kernel (cwd = repo-like root with pipeline/). Launched by run_kaggle.sh via
#   scripts/kaggle/run.sh "bash pipeline/experiments/xml_kaggle_job.sh [proxy|spatial|all]"
# The ML-expert scripts are staged into pipeline/experiments/ (push_code.sh bundles only that dir).
# Artefacts -> pipeline/out/xml  (= /kaggle/working/out/xml, downloaded by run.sh).
set -uo pipefail
cd "$(dirname "$0")/../.."
PY="${PY:-python}"
WHAT="${1:-all}"
export EXP_OUT="$PWD/pipeline/out/xml"
export XML_NJOBS="${XML_NJOBS:-4}"
mkdir -p "$EXP_OUT/logs"
log() { echo "[$(date -u +%H:%M:%S)] $*"; }
step() { local n="$1"; shift; log "start $n"; if "$@" > "$EXP_OUT/logs/$n.txt" 2>&1; then log "ok $n"; else log "!! $n failed (logs/$n.txt)"; fi; }

case "$WHAT" in
  proxy|all)   step proxy   $PY pipeline/experiments/xml_fews_proxy.py --iso3 ZWE KEN MWI ;;&
  spatial|all) step spatial $PY pipeline/experiments/xml_spatial.py ;;
esac

# keep the download small: drop the rebuilt row caches, keep OOF / hold-out / results
rm -f "$EXP_OUT"/rows_base.parquet "$EXP_OUT"/feat_base.parquet "$EXP_OUT"/wide_base.parquet "$EXP_OUT"/extra_um.parquet \
      "$EXP_OUT"/xml_proxy_rows.parquet 2>/dev/null || true
log "done"
for f in "$EXP_OUT"/logs/*.txt; do echo "=== $(basename "$f")"; grep -v '^\s*$' "$f" | tail -25; done
