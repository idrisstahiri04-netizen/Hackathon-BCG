# Run pipeline training / experiments on Kaggle

Rule: **all model training, experiments and TimesFM runs go to Kaggle, not the laptop.**
These scripts push the data and code to two PRIVATE Kaggle datasets, run one command in a
PRIVATE script kernel, and bring the outputs back.

Kaggle objects (all private, account `omarserghini`):

| object | kind | contents |
| --- | --- | --- |
| `omarserghini/drought-signals` | dataset | `pipeline/data/{signals_*,units_*,pop_*,ipc_*,seasonal_fc_*}` + `pipeline/out/timesfm_*.parquet` |
| `omarserghini/drought-code` | dataset | `pipeline/*.py`, `requirements.txt`, `run_all.sh`, `pipeline/experiments/*.{py,json,yaml,md,sh}` (< 2 MB; no parquet/csv/log) |
| `omarserghini/drought-train` | script kernel | runs one command; outputs in `/kaggle/working/out/` |

## One-liner (what other helpers should use)

```bash
scripts/kaggle/run.sh "python pipeline/train.py --iso3 ZWE KEN MWI ZMB"          # CPU
scripts/kaggle/run.sh "python pipeline/timesfm_forecast.py --iso3 ZWE" --gpu      # GPU (T4/P100)
scripts/kaggle/run.sh "python pipeline/experiments/run_experiments3.py"            # any script
```

`run.sh "<command>" [--gpu] [--force-data]`:
1. `push_data.sh` – re-uploads the data dataset only when a file changed (sha256 of the staged tree; last hash in `.state/`).
2. `push_code.sh` – same for the code dataset, then pushes the kernel with the command inlined.
3. polls `kaggle kernels status` every 20 s, prints status changes.
4. downloads everything into `pipeline/out/kaggle/<UTC timestamp>/` (`out/` = `/kaggle/working/out`, plus `drought-train.log`, `command.txt`), prints the log tail.
5. exit code = the command's exit code on Kaggle (`out/kaggle_run.json` has `exit_code`, `seconds`, file list). Non-zero on any failure.

Inside the kernel the layout mirrors the repo: cwd has `pipeline/` with the scripts, `pipeline/data/` -> dataset
files (read-only links), `pipeline/out/` -> `/kaggle/working/out`. So commands are written exactly as on the laptop
(`python pipeline/train.py ...`). `$PY` is set to the kernel's python for `run_all.sh`-style scripts.
`lightgbm` is pip-installed if missing (internet is on). Extra pins: `KAGGLE_PIP="scikit-learn==1.9.1" scripts/kaggle/run.sh ...`.
Other env knobs: `KERNEL_SLUG`, `CODE_SLUG`, `DATA_SLUG` (use other Kaggle names), `CODE_SRC=<dir>` (bundle another
checkout of `pipeline/`, e.g. `git archive HEAD pipeline | tar -x -C /tmp/x` to re-run a committed revision).

Auth: `~/.kaggle/access_token` is read into `KAGGLE_API_TOKEN` automatically. Never print it.

## Notes and limits

- Kaggle image (Oct 2026): python 3.13, numpy 2.1.3, pandas 2.3.3, scikit-learn 1.6.1, lightgbm 4.6.0, torch 2.11 (CPU image).
  Laptop venv: numpy 2.5.4, pandas 3.0.6, scikit-learn 1.9.1, lightgbm 4.7.0. Verified 2026-10-16: HEAD `train.py` on Kaggle
  (stock image, no pins) reproduces the laptop's per-event CV/hold-out metrics **bit-identically** (233/233 fields x 4 countries);
  `KAGGLE_PIP` pins are therefore optional.
- CPU kernel: 4 vCPU, ~30 GB RAM (train.py's `Parallel(n_jobs=11)` just runs 4 at a time). Startup overhead 15 s – 5 min.
- Measured: `python pipeline/train.py --iso3 ZWE KEN MWI ZMB` = **99 s** on the Kaggle CPU kernel, ~2 min wall from
  `run.sh` start to outputs on disk when data/code are unchanged (+1–2 min per dataset version uploaded).
- Limits: **12 h max per run** (CPU and GPU), **30 GPU hours / week** (shared across the account), 20 GB output,
  107 GB total private-dataset quota. Datasets keep every version (`kaggle datasets version -d` deletes old ones if quota bites).
- One kernel name = one run at a time. A second `run.sh` while one is running **replaces** the kernel version and
  the first run's output is lost. For parallel runs use another kernel name: `KERNEL_SLUG=drought-train-2 scripts/kaggle/run.sh ...`.
- Dataset upload -> mountable takes ~1–2 min; the scripts wait for `ready` + 30 s. If the kernel log says
  `dataset ... not mounted`, just re-run.
- Datasets mount under `/kaggle/input/datasets/omarserghini/<slug>/` (new layout); the kernel resolves both layouts.
- `experiments/` big artefacts (feat_base.parquet, oof_*.parquet, logs) are **not** uploaded; experiment scripts
  that need them must rebuild them on Kaggle, or add them to `push_data.sh` first.
- Everything here is gitignored except the scripts and this README (`.build/`, `.state/`, `pipeline/out/kaggle/` are local only).

## Kaggle objects created so far

`drought-signals`, `drought-code`, `drought-train` (the defaults) and `drought-code-check`, `drought-train-check`
(a one-off verification run of the committed HEAD code; safe to delete on kaggle.com).

## Files

- `_common.sh` – shared helpers (auth, hashing, create/version dataset, wait-for-ready)
- `push_data.sh [--force]`, `push_code.sh "<cmd>" [--gpu] [--force]`, `run.sh "<cmd>" [--gpu] [--force-data]`
- `kernel_template.py` – the kernel; `__CONFIG_JSON__` is filled by `push_code.sh`
