#!/usr/bin/env bash
# Full experiment suite on Kaggle via: scripts/kaggle/run.sh "bash pipeline/experiments/kaggle_job.sh 4"
# Runs from the repo root (cwd = /kaggle/working on Kaggle). Artefacts go to pipeline/out/experiments/
# (pipeline/out is the kernel output the runner downloads). Locally: EXP_OUT defaults to the same place.
set -uo pipefail
cd "$(dirname "$0")/../.."
PY="${PY:-python}"
EXP=pipeline/experiments
export EXP_OUT="${EXP_OUT:-$PWD/pipeline/out/experiments}"
mkdir -p "$EXP_OUT/logs"
NJ="${1:-4}"; shift || true
EXP_GROUPS="${*:-enso sfc pooled labels combos pooled2 longlead season model}"   # which experiment groups to run
want() { case " $EXP_GROUPS " in *" $1 "*) return 0;; *) return 1;; esac; }
sed -i "s/^N_JOBS = .*/N_JOBS = ${NJ}/" "$EXP/harness.py"
log() { echo "[$(date -u +%H:%M:%S)] $*"; }
step() { local n="$1"; shift; log "$n"; "$@" > "$EXP_OUT/logs/$n.txt" 2>&1 || log "!! $n failed (logs/$n.txt)"; }
run() { local g="$1"; shift; want "$g" || return 0; step "exp_$g" $PY "$EXP/run_experiments3.py" "$@"; }

step build     $PY "$EXP/harness.py" build
step baseline  $PY "$EXP/harness.py" baseline
step labels    $PY "$EXP/labels_alt.py"
step expand    $PY "$EXP/expand.py"
run enso       oni_south_only oni_lr_only oni_both oni_south_lr_only nino34_lr_only oni_dmi_lr_only oni_dmi_both oni_lag0_lr_only nino34_both
run sfc        sfc_both sfc_lr_only sfc_m13_both combo_oni_sfc combo_oni_sfc_lr
run pooled     pool_base pool_oni_lr_only pool_oni_sfc
run labels     lab_mean35 lab_mean35_oni lab_q20 lab_q20_oni lab_mean_q20 lab_mean_q20_oni lab_min20
run combos     combo_oni_lr_cum combo_oni_sfc_cum combo_oni_dmi_lr_cum combo_oni_lr_cum_mono
run pooled2    pool_oni_lr_cum pool_lab_mean35_oni
run longlead   long_base long_oni_lr_only long_oni_both long_oni_sfc
run season     cum_rain dry_spell cum_dry_gated ndvi_slope phase_x
run model      mono lr_C1 ens_w_lr70
step calibration $PY "$EXP/calibration.py" "$EXP_OUT/oof_baseline.parquet" ensemble
step leadtime_base $PY "$EXP/lead_time.py" "$EXP_OUT/oof_baseline.parquet" cal_ensemble
[ -f "$EXP_OUT/oof_oni_south_only.parquet" ] && step leadtime_oni $PY "$EXP/lead_time.py" "$EXP_OUT/oof_oni_south_only.parquet" cal_ensemble
# once-only hold-out for the CV-chosen configuration among a shortlist declared BEFORE seeing hold-out
PICK=$($PY - <<'PY'
import json, os
from pathlib import Path
best, bp = None, -1
for l in (Path(os.environ["EXP_OUT"]) / "results.jsonl").read_text().splitlines():
    r = json.loads(l)
    if r["name"] in ("oni_south_only", "oni_lr_only", "oni_both", "combo_oni_lr_cum", "pool_oni_lr_only", "pool_oni_lr_cum",
                     "sfc_both", "combo_oni_sfc", "combo_oni_sfc_cum", "pool_oni_sfc") \
       and r["label"] == "label" and r["ensemble"]["mean2_pr_auc"] > bp:
        best, bp = r["name"], r["ensemble"]["mean2_pr_auc"]
print(best or "")
PY
)
[ -n "$PICK" ] && step holdout_once $PY "$EXP/holdout_once.py" "$PICK"
# keep the download small
find "$EXP_OUT" -maxdepth 1 -name 'oof_*.parquet' ! -name 'oof_baseline.parquet' ! -name 'oof_oni_south_only.parquet' \
     ! -name "oof_${PICK:-none}.parquet" -delete 2>/dev/null || true
rm -f "$EXP_OUT"/rows_*.parquet "$EXP_OUT"/feat_base.parquet "$EXP_OUT"/wide_*.parquet "$EXP_OUT"/extra_um*.parquet "$EXP_OUT"/holdout_*.parquet
log "done"; for f in "$EXP_OUT"/logs/*.txt; do echo "=== $(basename $f)"; grep -v '^\s*$' "$f" | grep -v Traceback | tail -40; done
