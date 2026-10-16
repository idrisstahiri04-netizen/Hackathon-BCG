"""Spec-mode evaluation of candidate early WATCH inputs (no model, no refits).

Unit of analysis: one (unit, crop_failure season window W0) in CV years (agyear 2001-2022, main season).
Label v1.1 = >= 2 of the 3 crop-window months with vci_crop < 35 (same rule as labels.py v1.1).
For each candidate input we ask: at issue month r = W0 - L (L = 2..6), does the input fire?
  enso       ONI (trimester ending r-1) >= 0.5 for units south of 8S / <= -0.5 north of it (El Nino dry south,
             La Nina dry east Africa); also ONI >= 1.0 (strong)
  nmme_m13   NMME MME3 P(below-normal) for next 3 months >= thr, issued in month r
  nmme_m46   same for months 4-6 (the window itself when L = 4..6)
  outlook    FEWS NET rain_outlook == 'below' for the unit in a document published in r-2..r (ZWE 2015+ only);
             'gaz' = district/province/livelihood-zone match only, 'all' = also descriptor_map
  families   CONTRACT Warning condition at r (vegetation & (rain|soil)) - what spec mode fires on
Reported per input and lead: hit rate, FPR (share of non-event unit-seasons that fire), FAR, n.
    python pipeline/experiments/watch_inputs.py
"""
import os, sys, json
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXP_OUT", str(HERE)))
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import extra_features as X

rows = pd.read_parquet(OUT / "rows_base.parquet")
w = pd.read_parquet(OUT / "wide_base.parquet"); w["month"] = pd.to_datetime(w["month"])
inst = rows[(rows.event == "crop_failure") & (rows.lead == 1) & ~rows.test & rows.agyear.between(2001, 2022)][
    ["unit_id", "iso3", "W0", "agyear", "season"]].drop_duplicates()
# v1.1 label
parts = [inst.assign(month=inst.W0 + pd.DateOffset(months=k)) for k in range(3)]
ex = pd.concat(parts).merge(w[["unit_id", "month", "vci_crop"]], on=["unit_id", "month"], how="left")
agg = ex.groupby(["unit_id", "W0"]).vci_crop.agg(nvalid="count", nlow=lambda v: (v < 35).sum()).reset_index()
inst = inst.merge(agg, on=["unit_id", "W0"])
inst["y"] = np.where(inst.nvalid >= 2, (inst.nlow >= 2).astype(float), np.nan)
inst = inst.dropna(subset=["y"])
cen = pd.read_parquet(OUT / "unit_centroids.parquet").set_index("unit_id")["lat"]
inst["south"] = inst.unit_id.map(cen) < -8
oni = X.load_oni()["oni"]
# NMME
sfc = pd.concat([pd.read_parquet(HERE.parent / "data" / f"seasonal_fc_{i}.parquet") for i in ["ZWE", "KEN", "MWI", "ZMB"]])
sfc = sfc[sfc["product"] == "NMME/MME3"]; sfc["issue_month"] = pd.to_datetime(sfc.issue_month)
pbn = sfc.pivot_table(index=["unit_id", "issue_month"], columns="target_window", values="p_below_normal")
# outlook (ZWE, gazetteer vs all)
olf = HERE.parent / "data" / "outlook_ZWE.parquet"
ol = pd.read_parquet(olf) if olf.exists() else pd.DataFrame(columns=["unit_id", "publish_month", "rain_outlook", "match_type"])
ol["pm"] = pd.to_datetime(ol.publish_month.astype(str) + "-01") if len(ol) else pd.Series(dtype="datetime64[ns]")
below_gaz = set(zip(ol[(ol.rain_outlook == "below") & ol.match_type.isin(["district", "province", "livelihood_zone"])].unit_id,
                    ol[(ol.rain_outlook == "below") & ol.match_type.isin(["district", "province", "livelihood_zone"])].pm))
below_all = set(zip(ol[ol.rain_outlook == "below"].unit_id, ol[ol.rain_outlook == "below"].pm))
fam = rows[(rows.event == "crop_failure") & ~rows.test][["unit_id", "W0", "lead", "rain", "vegetation", "soil"]]
fam["warn"] = fam.vegetation & (fam.rain | fam.soil); fam["anyfam"] = fam[["rain", "vegetation", "soil"]].any(axis=1)
famp = fam.pivot_table(index=["unit_id", "W0"], columns="lead", values=["warn", "anyfam"], aggfunc="max")

def rate(d, fire, name, L):
    y = d.y.values.astype(bool); f = np.asarray(fire, bool)
    hits, fa = (f & y).sum(), (f & ~y).sum()
    return dict(input=name, lead=L, n=len(d), base=round(y.mean(), 3), hit_rate=round(hits / max(y.sum(), 1), 3),
                fpr=round(fa / max((~y).sum(), 1), 3), far=round(fa / max(hits + fa, 1), 3), fires=int(f.sum()))

res = []
for L in [2, 3, 4, 5, 6]:
    d = inst.copy(); d["r"] = d.W0 - pd.DateOffset(months=L)
    o = oni.reindex(d.r - pd.DateOffset(months=1)).values
    d["o_signed"] = np.where(d.south, o, -o)
    for thr in (0.5, 1.0):
        res.append(rate(d, d.o_signed >= thr, f"enso_oni>={thr}", L))
        res.append(rate(d[d.iso3 == "ZWE"], d[d.iso3 == "ZWE"].o_signed >= thr, f"enso_oni>={thr} [ZWE]", L))
    p = pbn.reindex(pd.MultiIndex.from_arrays([d.unit_id, d.r]))
    for win in ["m1-3", "m4-6"]:
        for thr in (0.5, 0.6):
            v = p[win].values
            res.append(rate(d[~np.isnan(v)], v[~np.isnan(v)] >= thr, f"nmme_{win}_pbn>={thr}", L))
    z = d[(d.iso3 == "ZWE") & (d.agyear >= 2015)].copy()
    for name, S in ((("outlook_below_gaz", below_gaz), ("outlook_below_all", below_all)) if len(ol) else ()):
        f = [any((u, r - pd.DateOffset(months=k)) in S for k in range(3)) for u, r in zip(z.unit_id, z.r)]
        res.append(rate(z, f, f"{name} [ZWE 2015+]", L))
    if L <= 3:
        for k in ("warn", "anyfam"):
            v = famp[(k, float(L))].reindex(pd.MultiIndex.from_arrays([d.unit_id, d.W0])).fillna(False).values
            res.append(rate(d, v, f"families_{k}", L))
R = pd.DataFrame(res); R.to_csv(OUT / "watch_inputs.csv", index=False)
pd.set_option("display.width", 200)
print("label v1.1 crop_failure, CV unit-seasons:", len(inst), "base", round(inst.y.mean(), 3))
print(R.sort_values(["input", "lead"]).to_string(index=False))
