#!/usr/bin/env bash
# Dry-spell feature experiment on Kaggle:
#   KERNEL_SLUG=drought-dry scripts/kaggle/run.sh "bash pipeline/dryspell/kaggle_job.sh 4"
# cwd = repo-like root (/kaggle/working). Artefacts -> pipeline/out/dryspell/ (downloaded by run.sh).
set -uo pipefail
cd "$(dirname "$0")/../.."
PY="${PY:-python}"
export EXP_OUT="${EXP_OUT:-$PWD/pipeline/out/dryspell}"
mkdir -p "$EXP_OUT"
NJ="${1:-4}"
echo "[$(date -u +%H:%M:%S)] exp_dryspell n_jobs=$NJ"
$PY pipeline/dryspell/exp_dryspell.py --n-jobs "$NJ" > "$EXP_OUT/log.txt" 2>&1
rc=$?
# keep the download small: drop the row caches, keep OOF + results + summary + replay csv
rm -f "$EXP_OUT"/rows_*.parquet "$EXP_OUT"/feat_*.parquet "$EXP_OUT"/wide_*.parquet "$EXP_OUT"/extra_um*.parquet
echo "[$(date -u +%H:%M:%S)] rc=$rc"; tail -n 60 "$EXP_OUT/log.txt"
exit $rc
