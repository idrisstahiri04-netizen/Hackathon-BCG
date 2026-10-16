#!/usr/bin/env bash
# Bundle pipeline/*.py (+ requirements.txt, experiments/ scripts) into the PRIVATE dataset
# omarserghini/drought-code, then push the PRIVATE script kernel omarserghini/drought-train.
#   scripts/kaggle/push_code.sh "<command>" [--gpu] [--force]
#   e.g. scripts/kaggle/push_code.sh "python pipeline/train.py --iso3 ZWE KEN MWI ZMB"
# Env: KAGGLE_PIP="pkg==1.2 other" extra pip installs in the kernel; KERNEL_SLUG / CODE_SLUG to use other names;
#      CODE_SRC=<dir> bundle that directory instead of $REPO/pipeline (e.g. a git export of another revision).
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
CMD="${1:?usage: push_code.sh \"<command>\" [--gpu] [--force]}"; shift
GPU=false; FORCE=""
for a in "$@"; do case "$a" in --gpu) GPU=true;; --force) FORCE=--force;; esac; done

# ---- code dataset: scripts only (experiments' big parquet/csv/log artefacts are left out)
SRC="${CODE_SRC:-$REPO/pipeline}"
ST="$BUILD/code"; rm -rf "$ST"; mkdir -p "$ST/experiments"
cp -p "$SRC"/*.py "$ST/"
for f in requirements.txt run_all.sh; do [ -f "$SRC/$f" ] && cp -p "$SRC/$f" "$ST/"; done
[ -d "$SRC/experiments" ] && find "$SRC/experiments" -maxdepth 1 -type f \( -name '*.py' -o -name '*.json' -o -name '*.yaml' -o -name '*.md' -o -name '*.sh' \) \
  -size -2M -exec cp -p {} "$ST/experiments/" \;
log "code bundle: $(find "$ST" -type f | wc -l) files"
push_dataset "$CODE_SLUG" "drought-code (pipeline scripts)" "$ST" "$FORCE"

# ---- kernel: template + inlined config
KD="$BUILD/kernel"; rm -rf "$KD"; mkdir -p "$KD"
python3 - "$KDIR/kernel_template.py" "$KD/kernel.py" "$CMD" "${KAGGLE_PIP:-}" "$KUSER" "$DATA_SLUG" "$CODE_SLUG" <<'PY'
import json, sys
tpl, out, cmd, pip, user, data, code = sys.argv[1:]
cfg = {"cmd": cmd, "pip": pip.split(), "data": f"/kaggle/input/{data}", "code": f"/kaggle/input/{code}",
       "pushed_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds")}
src = open(tpl).read().replace("__CONFIG_JSON__", json.dumps(cfg))
open(out, "w").write(src)
PY
cat > "$KD/kernel-metadata.json" <<JSON
{
  "id": "$KUSER/$KERNEL_SLUG",
  "title": "$KERNEL_SLUG",
  "code_file": "kernel.py",
  "language": "python",
  "kernel_type": "script",
  "is_private": true,
  "enable_gpu": $GPU,
  "enable_tpu": false,
  "enable_internet": true,
  "dataset_sources": ["$KUSER/$DATA_SLUG", "$KUSER/$CODE_SLUG"],
  "competition_sources": [],
  "kernel_sources": [],
  "model_sources": []
}
JSON
log "pushing kernel $KUSER/$KERNEL_SLUG (gpu=$GPU): $CMD"
for i in 1 2 3 4 5 6; do          # 409 Conflict while Kaggle still finalises the previous version -> retry
  if out="$("$KAGGLE" kernels push -p "$KD" 2>&1)"; then echo "$out"; exit 0; fi
  echo "$out" | grep -v -i token >&2
  log "kernel push failed (attempt $i/6), retrying in 30s"; sleep 30
done
log "!! kernel push failed"; exit 1
