#!/usr/bin/env bash
# usage: launch.sh <kernel_slug> "<cmd>"  -- isolated copy of scripts/kaggle; retries until the kernel actually ran
cd /home/looooo/bcg/Hackathon-BCG
RUN=pipeline/ipc_model/out/kaggle_scripts/run.sh
for i in $(seq 1 30); do
  t0=$(date -u +%Y%m%dT%H%M%SZ)
  KERNEL_SLUG="$1" bash $RUN "$2"; rc=$?
  new=$(ls -d pipeline/out/kaggle/*/ 2>/dev/null | awk -v t="pipeline/out/kaggle/$t0/" '$0 >= t' | tail -1)
  if [ -n "$new" ] && [ -f "$new/out/kaggle_run.json" ]; then echo "LAUNCH_DONE rc=$rc dir=$new"; exit $rc; fi
  echo "LAUNCH_RETRY $i rc=$rc (dir=$new)"; sleep 120
done
echo LAUNCH_GAVE_UP; exit 1
