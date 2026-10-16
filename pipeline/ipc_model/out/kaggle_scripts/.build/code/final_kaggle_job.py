"""One combined Kaggle job for the final model (bundled as *.py so push_code.sh ships it).
  A main model, v1.1 labels (default tag), leads 0-3      B same + SPI-3 label confirmation (tag SPI)
  C/D leads 4-6 models for A and B (tags LONG / LONG_SPI)  E FEWS-proxy p_crisis for live months
    python pipeline/final_kaggle_job.py
"""
import os
import subprocess
import sys

POOL = "MOZ TZA ETH SOM NAM BWA ZAF MDG AGO UGA".split()
C = "ZWE KEN MWI ZMB".split()
T = [sys.executable, "pipeline/train.py", "--iso3", *C, "--pool", *POOL]
JOBS = [("A", T, {}), ("B", T + ["--tag", "SPI"], {"LABEL_SPI_CONFIRM": "1"}),
        ("C", T + ["--train-leads", "4", "5", "6", "--tag", "LONG"], {}),
        ("D", T + ["--train-leads", "4", "5", "6", "--tag", "LONG_SPI"], {"LABEL_SPI_CONFIRM": "1"}),
        ("E", [sys.executable, "pipeline/ipc_model/proxy_live.py", "--iso3", "ZWE", "KEN", "MWI"], {})]
rc = 0
for name, cmd, env in JOBS:
    print(f"== job {name}: {' '.join(cmd)} {env}", flush=True)
    r = subprocess.run(cmd, env={**os.environ, **env})
    print(f"== job {name} exit {r.returncode}", flush=True)
    rc = rc or r.returncode
sys.exit(rc)
