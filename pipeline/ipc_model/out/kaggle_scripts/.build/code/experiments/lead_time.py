"""Alert-threshold optimisation on CV out-of-fold predictions: lead time at a fixed false-alarm rate.

    python pipeline/experiments/lead_time.py pipeline/out/oof_ZWE_KEN_MWI_ZMB.parquet [cal_ensemble]

Unit of analysis = one season instance (unit_id, event, W0) with its 3 pre-window months
(leads 3, 2, 1). An alert "fires" at lead L if the condition holds at r = W0 - L.
  hit            instance with label 1 where the alert fires at any lead 1-3
  lead time      largest lead L (months before the window) at which it fires, for hits
  false-alarm    instance with label 0 where the alert fires at any lead  -> FPR = FA / negatives
  FAR            false-alarm ratio = FA / (hits + FA)
Conditions compared:
  p_only   p >= t
  warn     vegetation & (rain | soil) & p >= t        (CONTRACT Warning rule)
  watch    any core family | p >= t                   (Watch rule)
Hysteresis (2 runs up) is applied in export, so an alert that fires at leads 3 and 2 becomes a
Warning level at lead 2: "lead time (hyst)" counts the largest L with fires at L and L+1 (or L=1 and
fires at 1 and 0, where lead 0 exists in the OOF).
Uses CV rows only (the OOF file holds no hold-out rows).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXP_OUT", str(HERE)))   # artefacts (caches, OOF, results); HERE = code + small data
OUT.mkdir(parents=True, exist_ok=True)
EVENTS = ["cant_plant", "crop_failure", "no_grass"]
FPR_BUDGETS = [0.10, 0.20, 0.30]


def instance_table(oof: pd.DataFrame, pcol: str, cond: str, t: float) -> pd.DataFrame:
    d = oof.dropna(subset=["label", pcol]).copy()
    p = d[pcol].values
    if cond == "p_only":
        fire = p >= t
    elif cond == "warn":
        fire = (d["vegetation"] & (d["rain"] | d["soil"])).values & (p >= t)
    elif cond == "watch":
        fire = d[["rain", "vegetation", "soil"]].any(axis=1).values | (p >= t)
    else:
        raise ValueError(cond)
    d["fire"] = fire
    piv = d.pivot_table(index=["unit_id", "event", "W0"], columns="lead", values="fire", aggfunc="max")
    lab = d.groupby(["unit_id", "event", "W0"]).label.first()
    out = pd.DataFrame({"label": lab})
    for L in (0, 1, 2, 3):
        out[f"f{L}"] = piv[L].reindex(out.index).fillna(False).astype(bool).values if L in piv.columns else False
    out["any"] = out[["f1", "f2", "f3"]].any(axis=1)
    lt = np.where(out.f3, 3, np.where(out.f2, 2, np.where(out.f1, 1, 0)))
    out["lead"] = lt
    # hysteresis: 2 consecutive fires; lead-3 alert needs lead 4 which does not exist -> max 2
    h = np.where(out.f3 & out.f2, 2, np.where(out.f2 & out.f1, 1, np.where(out.f1 & out.f0, 0, -1)))
    out["lead_h"] = h
    return out.reset_index()


def summarise(inst: pd.DataFrame) -> dict:
    res = {}
    for ev, g in inst.groupby("event"):
        pos, neg = g[g.label == 1], g[g.label == 0]
        hits = pos["any"].sum()
        fa = neg["any"].sum()
        res[ev] = dict(n_pos=int(len(pos)), n_neg=int(len(neg)), hit_rate=round(hits / max(len(pos), 1), 3),
                       fpr=round(fa / max(len(neg), 1), 3), far=round(fa / max(hits + fa, 1), 3),
                       mean_lead=round(float(pos.loc[pos["any"], "lead"].mean()), 2) if hits else None,
                       mean_lead_h=round(float(pos.loc[pos.lead_h >= 0, "lead_h"].mean()), 2) if (pos.lead_h >= 0).any() else None,
                       hit_rate_h=round(float((pos.lead_h >= 0).mean()), 3),
                       lead3_share=round(float((pos.loc[pos["any"], "lead"] == 3).mean()), 3) if hits else None)
    return res


def sweep(oof: pd.DataFrame, pcol: str, cond: str, grid) -> pd.DataFrame:
    rows = []
    for t in grid:
        s = summarise(instance_table(oof, pcol, cond, t))
        for ev, r in s.items():
            rows.append(dict(cond=cond, t=round(float(t), 3), event=ev, **r))
    return pd.DataFrame(rows)


def pick(sw: pd.DataFrame, budget: float) -> pd.DataFrame:
    """Per event and condition: the lowest threshold whose instance-level FPR <= budget (max hit rate / lead)."""
    out = []
    for (c, ev), g in sw.groupby(["cond", "event"]):
        ok = g[g.fpr <= budget]
        if len(ok):
            r = ok.sort_values("t").iloc[0].to_dict()
            r["budget"] = budget
            out.append(r)
    return pd.DataFrame(out)


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "out" / "oof_ZWE_KEN_MWI_ZMB.parquet"
    pcol = sys.argv[2] if len(sys.argv) > 2 else "cal_ensemble"
    oof = pd.read_parquet(path)
    grid = np.round(np.arange(0.05, 0.96, 0.05), 2)
    sws = pd.concat([sweep(oof, pcol, c, grid) for c in ("p_only", "warn", "watch")], ignore_index=True)
    tag = path.stem
    sws.to_csv(OUT / f"leadtime_sweep_{tag}.csv", index=False)
    picks = pd.concat([pick(sws, b) for b in FPR_BUDGETS], ignore_index=True)
    picks.to_csv(OUT / f"leadtime_picks_{tag}.csv", index=False)
    # current CONTRACT thresholds for reference
    th = json.loads((HERE.parent / "out" / f"thresholds_{tag.replace('oof_', '')}.json").read_text()) \
        if (HERE.parent / "out" / f"thresholds_{tag.replace('oof_', '')}.json").exists() else {"p_warn": 0.5, "p_watch": 0.35}
    cur = summarise(instance_table(oof, pcol, "warn", th["p_warn"]))
    print(f"== {tag} {pcol}: Warning rule at tuned p_warn={th['p_warn']}")
    print(pd.DataFrame(cur).T)
    print("\n== lowest threshold meeting FPR budget (instance level, any of leads 1-3)")
    cols = ["budget", "cond", "event", "t", "hit_rate", "fpr", "far", "mean_lead", "hit_rate_h", "mean_lead_h", "lead3_share"]
    print(picks[cols].to_string(index=False))


if __name__ == "__main__":
    main()
