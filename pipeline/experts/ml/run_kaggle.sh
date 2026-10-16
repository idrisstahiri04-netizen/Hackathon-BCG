#!/usr/bin/env bash
# Laptop launcher for the ML-expert experiments (ALL training on Kaggle).
#   pipeline/experts/ml/run_kaggle.sh [proxy|spatial|all]
# Stages a copy of pipeline/ with pipeline/experts/ml/* placed into experiments/ (push_code.sh only bundles
# pipeline/*.py, experiments/, dryspell/, ipc_model/), uses its OWN code dataset and kernel so other helpers'
# running kernels are not replaced:  CODE_SLUG=drought-code-xml  KERNEL_SLUG=drought-xml  (data dataset shared).
# Retries the whole run.sh on a 409 (kernel slot busy: 3 concurrent kernels per account).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
WHAT="${1:-all}"
STAGE="$(mktemp -d /tmp/xml_code.XXXX)"
cp -r "$REPO/pipeline" "$STAGE/pipeline"
rm -rf "$STAGE/pipeline/out" "$STAGE/pipeline/cache" "$STAGE/pipeline/data" "$STAGE/pipeline/__pycache__"
cp -p "$HERE"/xml_*.py "$HERE"/xml_neighbours.json "$STAGE/pipeline/experiments/"
cp -p "$HERE/kaggle_job.sh" "$STAGE/pipeline/experiments/xml_kaggle_job.sh"
echo "[xml] staged $(find "$STAGE/pipeline" -name 'xml_*' | wc -l) expert files into $STAGE/pipeline/experiments"

export CODE_SRC="$STAGE/pipeline" CODE_SLUG="${CODE_SLUG:-drought-code-xml}" KERNEL_SLUG="${KERNEL_SLUG:-drought-xml}"
CMD="${XML_ENV:-} bash pipeline/experiments/xml_kaggle_job.sh $WHAT"
for i in 1 2 3 4 5 6 7 8; do
  if "$REPO/scripts/kaggle/run.sh" "$CMD" 2>&1 | tee "$HERE/.last_run.log"; then
    echo "[xml] run finished OK"; rm -rf "$STAGE"; exit 0
  fi
  if grep -qiE '409|conflict|too many|maximum.*kernels|limit' "$HERE/.last_run.log"; then
    echo "[xml] kernel slot busy (attempt $i/8), retrying in 120 s"; sleep 120; continue
  fi
  echo "[xml] run failed (not a slot conflict); see $HERE/.last_run.log"; rm -rf "$STAGE"; exit 1
done
rm -rf "$STAGE"; exit 1
