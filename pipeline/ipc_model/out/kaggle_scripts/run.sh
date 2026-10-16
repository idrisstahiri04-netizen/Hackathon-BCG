#!/usr/bin/env bash
# Run one pipeline command on Kaggle end to end:
#   scripts/kaggle/run.sh "<command>" [--gpu] [--force-data]
#   e.g. scripts/kaggle/run.sh "python pipeline/train.py --iso3 ZWE KEN MWI ZMB"
#        scripts/kaggle/run.sh "python pipeline/timesfm_forecast.py --iso3 ZWE" --gpu
# Steps: push data (if changed) -> push code (+kernel) -> poll until complete/error ->
# download /kaggle/working/out + log into pipeline/out/kaggle/<timestamp>/ -> tail log. Exit 1 on failure.
# The command runs with cwd = repo-like root containing pipeline/ (so "python pipeline/train.py" works).
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
CMD="${1:?usage: run.sh \"<command>\" [--gpu] [--force-data]}"; shift
GPU=""; FD=""
for a in "$@"; do case "$a" in --gpu) GPU=--gpu;; --force-data) FD=--force;; esac; done

"$KDIR/push_data.sh" $FD
"$KDIR/push_code.sh" "$CMD" $GPU

TS="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$REPO/pipeline/out/kaggle/$TS"; mkdir -p "$DEST"
echo "*" > "$REPO/pipeline/out/kaggle/.gitignore"   # downloads never enter git
echo "$CMD" > "$DEST/command.txt"
log "polling $KUSER/$KERNEL_SLUG (output -> pipeline/out/kaggle/$TS)"
sleep 15
status=""; last=""; t0=$(date +%s)
while :; do
  status="$("$KAGGLE" kernels status "$KUSER/$KERNEL_SLUG" 2>&1 | tr -d '\r' || true)"
  # e.g.  omarserghini/drought-train has status "KernelWorkerStatus.RUNNING"
  st="$(echo "$status" | grep -oiE 'queued|running|complete|error|cancel[a-z]*' | head -1 | tr 'A-Z' 'a-z' || true)"
  el=$(( $(date +%s) - t0 ))
  if [ "$st" != "$last" ]; then log "status: ${st:-?} (+${el}s)"; last="$st"; fi
  case "$st" in
    complete|error|cancelacknowledged|cancelrequested) break;;
    "") [ $el -gt 120 ] && { log "!! cannot read status: $status"; break; };;
  esac
  [ $el -gt $((13*3600)) ] && { log "!! timeout after 13h"; break; }
  sleep 20
done

log "downloading output"
"$KAGGLE" kernels output "$KUSER/$KERNEL_SLUG" -p "$DEST" -o -q || log "!! output download failed"
LOGF="$(ls "$DEST"/*.log 2>/dev/null | head -1 || true)"
if [ -n "$LOGF" ]; then
  echo "----- log tail ($(basename "$LOGF")) -----"
  # Kaggle logs are JSON arrays of {time,data,stream_name}; print the readable text if so
  python3 - "$LOGF" <<'PY' | tail -n 40
import json, sys
raw = open(sys.argv[1]).read()
try:
    for e in json.loads(raw):
        sys.stdout.write(e.get("data", ""))
except Exception:
    sys.stdout.write(raw)
PY
  echo "----- end log -----"
fi
rc=0
if [ -f "$DEST/out/kaggle_run.json" ]; then
  rc="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['exit_code'])" "$DEST/out/kaggle_run.json")"
  log "kernel command exit_code=$rc, seconds=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['seconds'])" "$DEST/out/kaggle_run.json")"
else
  log "!! no kaggle_run.json in output (kernel crashed before/while running)"; rc=1
fi
[ "$st" = "complete" ] || { log "!! kernel status: $st"; rc=1; }
log "outputs in $DEST"; ls -la "$DEST" >&2
exit "$rc"
