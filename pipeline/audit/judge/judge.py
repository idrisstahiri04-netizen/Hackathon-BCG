"""Results judge: story check, false alarms, plausibility and plots from data/risk/<ISO3>.js.

Run: PYTHONPATH=/tmp/judge_libs python pipeline/audit/judge/judge.py [--allow-stub]
Writes pipeline/audit/judge/judge_<ISO3>.json and judge_<ISO3>.png. Read-only on everything else.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DECL = {"ZWE": "2024-04-03", "MWI": "2024-03-23", "ZMB": "2024-02-29", "KEN": "2021-09-08"}
# crisis season window (months, inclusive) per country
CRISIS = {"ZWE": ("2023-10-01", "2024-06-01"), "MWI": ("2023-10-01", "2024-06-01"),
          "ZMB": ("2023-10-01", "2024-06-01"), "KEN": ("2020-10-01", "2021-12-01")}
ALLOW_STUB = "--allow-stub" in sys.argv


def load_risk(iso3):
    p = ROOT / "data/risk" / f"{iso3}.js"
    t = p.read_text()
    if f'RISK_DATA["{iso3}"]' not in t:
        return None
    j = json.loads(t[t.index("= {") + 2:].strip().rstrip(";"))
    return j


def panel(j):
    rows = []
    y0 = j["meta"]["start_year"]
    for u in j["units"]:
        for s in u["series"]:
            m = pd.Timestamp(year=y0 + s["t"] // 12, month=s["t"] % 12 + 1, day=1)
            rows.append(dict(unit_id=u["id"], unit_name=u["name"], month=m, level=s["level"], p=s.get("p"),
                             agreeing=s.get("agreeing"), veg=(s.get("families") or {}).get("vegetation")))
    return pd.DataFrame(rows)


def centroids(iso3):
    g = json.loads((ROOT / "pipeline/data" / f"units_{iso3}.geojson").read_text())
    out, shapes = {}, {}
    for f in g["features"]:
        pr = f["properties"]
        uid = pr.get("shapeID") or pr.get("id")
        geom = f["geometry"]
        geoms = geom["geometries"] if geom["type"] == "GeometryCollection" else [geom]
        polys = []
        for gg in geoms:
            if gg["type"] == "MultiPolygon":
                polys += gg["coordinates"]
            elif gg["type"] == "Polygon":
                polys.append(gg["coordinates"])
        rings = [np.array(p[0])[:, :2] for p in polys]
        allpts = np.vstack(rings)
        out[uid] = (allpts[:, 0].mean(), allpts[:, 1].mean())
        shapes[uid] = rings
    return out, shapes


def seasons_climate(sig):
    """Country-mean Nov-Mar SPI-1 per season (labelled by Oct year)."""
    s = sig[sig.signal_type == "spi_1m"].copy()
    s["month"] = pd.to_datetime(s["month"])
    s = s[s.month.dt.month.isin([11, 12, 1, 2, 3])]
    s["season"] = np.where(s.month.dt.month >= 11, s.month.dt.year, s.month.dt.year - 1)
    return s.groupby("season")["value"].mean()


def lead_weeks(first_month, decl):
    # conservative: a monthly level for month m is issued on the 1st of month m+1
    issue = first_month + pd.offsets.MonthBegin(1)
    return (decl - issue).days / 7.0


def judge(iso3):
    j = load_risk(iso3)
    if j is None:
        return {"iso3": iso3, "status": "no risk data"}
    mv = j["meta"].get("model_version")
    if mv == "STUB" and not ALLOW_STUB:
        return {"iso3": iso3, "status": "STUB"}
    df = panel(j)
    decl = pd.Timestamp(DECL[iso3])
    a, b = map(pd.Timestamp, CRISIS[iso3])
    sig = pd.read_parquet(ROOT / "pipeline/data" / f"signals_{iso3}.parquet")
    cen, shapes = centroids(iso3)
    res = {"iso3": iso3, "model_version": mv, "generated_at": j["meta"].get("generated_at"),
           "n_units": df.unit_id.nunique(), "declaration": str(decl.date()),
           "crisis_window": [str(a.date()), str(b.date())],
           "level_counts_all": df.level.value_counts().sort_index().to_dict()}

    cr = df[(df.month >= a) & (df.month <= b)]
    per = []
    for uid, g in cr.groupby("unit_id"):
        g = g.sort_values("month")
        fw = g[g.level >= 1].month.min()
        fwar = g[g.level >= 2].month.min()
        per.append(dict(unit_id=uid, unit_name=g.unit_name.iloc[0], first_watch=fw, first_warning=fwar,
                        max_level=int(g.level.max()), lon=cen.get(uid, (np.nan, np.nan))[0],
                        lat=cen.get(uid, (np.nan, np.nan))[1]))
    per = pd.DataFrame(per)
    n = len(per)
    for lvl, col in (("watch", "first_watch"), ("warning", "first_warning")):
        issued_before = per[col].notna() & ((per[col] + pd.offsets.MonthBegin(1)) <= decl)
        lw = per.loc[issued_before, col].map(lambda m: lead_weeks(m, decl))
        res[f"{lvl}_share_before_decl"] = round(issued_before.mean(), 3)
        res[f"{lvl}_n_before_decl"] = int(issued_before.sum())
        res[f"{lvl}_share_ever_in_window"] = round(per[col].notna().mean(), 3)
        res[f"{lvl}_median_lead_wk"] = round(float(lw.median()), 1) if len(lw) else None
        res[f"{lvl}_lead_wk_iqr"] = [round(float(lw.quantile(q)), 1) for q in (.25, .75)] if len(lw) else None
        res[f"{lvl}_first_month_hist"] = per[col].dt.strftime("%Y-%m").value_counts().sort_index().to_dict()
    conv = {}
    for name in ("month_start_optimistic", "next_month_1st", "next_month_1st_plus5wk_latency"):
        iss = per.first_warning if name == "month_start_optimistic" else per.first_warning + pd.offsets.MonthBegin(1)
        if name.endswith("latency"):
            iss = iss + pd.Timedelta(weeks=5)
        ok = iss.notna() & (iss <= decl)
        lw = (decl - iss[ok]).dt.days / 7
        conv[name] = dict(n=int(ok.sum()), share=round(float(ok.mean()), 3),
                          median_lead_wk=round(float(lw.median()), 1) if ok.any() else None,
                          n_lead_ge_4wk=int((lw >= 4).sum()))
    res["warning_before_decl_by_issue_convention"] = conv
    res["share_level3_in_window"] = round((per.max_level >= 3).mean(), 3)

    # monthly share of units at each level through the window
    res["monthly_share_warning_plus"] = (cr.assign(w=cr.level >= 2).groupby(cr.month.dt.strftime("%Y-%m"))
                                         .w.mean().round(3).to_dict())

    # false alarms by season (Nov-Apr), classified by country-mean Nov-Mar SPI-1
    clim = seasons_climate(sig)
    fa = {}
    df["season"] = np.where(df.month.dt.month >= 10, df.month.dt.year, df.month.dt.year - 1)
    for y, g in df[df.month.dt.month.isin([11, 12, 1, 2, 3, 4])].groupby("season"):
        if y < 2018:
            continue
        spi = float(clim.get(y, np.nan))
        cls = "wet" if spi > 0.3 else ("dry" if spi < -0.3 else "normal")
        fa[f"{y}/{str(y+1)[2:]}"] = dict(
            mean_spi1_NovMar=round(spi, 2), cls=cls,
            warning_plus_unit_months=int((g.level >= 2).sum()), unit_months=len(g),
            share_units_ever_warning=round(g.groupby("unit_id")["level"].max().ge(2).mean(), 3),
            share_units_ever_watch=round(g.groupby("unit_id")["level"].max().ge(1).mean(), 3))
    res["seasons"] = fa

    # plausibility: hit-hardest = most negative crisis-season signals
    s = sig.copy(); s["month"] = pd.to_datetime(s["month"])
    sw = s[(s.month >= pd.Timestamp("2023-11-01") if iso3 != "KEN" else s.month >= pd.Timestamp("2020-10-01"))
           & (s.month <= (pd.Timestamp("2024-03-01") if iso3 != "KEN" else pd.Timestamp("2021-08-01")))]
    piv = sw[sw.signal_type.isin(["spi_3m", "ndvi_z_crop", "sm1_z"])].pivot_table(
        index="unit_id", columns="signal_type", values="value", aggfunc="mean")
    per = per.merge(piv, left_on="unit_id", right_index=True, how="left")
    wm = cr.groupby("unit_id")["level"].apply(lambda x: (x >= 2).sum()).rename("warning_months")
    per = per.merge(wm, left_on="unit_id", right_index=True)
    cor = {}
    for c in ["spi_3m", "ndvi_z_crop", "sm1_z", "lat", "lon"]:
        if c in per and per[c].notna().sum() > 5:
            cor[c] = round(float(per[["warning_months", c]].corr(method="spearman").iloc[0, 1]), 2)
    res["spearman_warning_months_vs"] = cor
    worst = per.sort_values("spi_3m").head(10) if "spi_3m" in per else per.head(0)
    res["driest10_spi3_units_warning_share"] = round(float((worst.max_level >= 2).mean()), 2) if len(worst) else None
    q = per.lat.quantile([1/3, 2/3]).values
    per["band"] = np.where(per.lat <= q[0], "south", np.where(per.lat <= q[1], "middle", "north"))
    res["warning_share_by_lat_band"] = per.groupby("band").apply(lambda g: round((g.max_level >= 2).mean(), 2)).to_dict()
    res["warning_share_by_lon_band"] = per.assign(lb=pd.qcut(per.lon, 3, labels=["west", "centre", "east"])) \
        .groupby("lb", observed=True).apply(lambda g: round((g.max_level >= 2).mean(), 2)).to_dict()
    per.to_csv(OUT / f"units_{iso3}.csv", index=False)
    plot(iso3, cr, per, shapes, decl, mv)
    return res


def plot(iso3, cr, per, shapes, decl, mv):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Polygon
    cmap = ListedColormap(["#d9d9d9", "#f2c94c", "#eb8a2f", "#c0392b"])
    norm = BoundaryNorm([-.5, .5, 1.5, 2.5, 3.5], 4)
    months = sorted(cr.month.unique())
    mons = [m for m in months if pd.Timestamp(m).month in (11, 12, 1, 2, 3, 4)] or months[:6]
    fig = plt.figure(figsize=(18, 9))
    gs = fig.add_gridspec(2, len(mons) + 0, height_ratios=[1, 1.3])
    lvl = cr.set_index(["unit_id", "month"]).level
    for i, m in enumerate(mons):
        ax = fig.add_subplot(gs[0, i])
        for uid, rings in shapes.items():
            v = lvl.get((uid, m), np.nan)
            col = "white" if pd.isna(v) else cmap(int(v))
            for r in rings:
                ax.add_patch(Polygon(r, closed=True, fc=col, ec="#555", lw=.2))
        ax.autoscale_view(); ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(pd.Timestamp(m).strftime("%b %Y"), fontsize=10)
    ax = fig.add_subplot(gs[1, :])
    order = per.sort_values("lat").unit_id.tolist()
    mat = cr.pivot_table(index="unit_id", columns="month", values="level").reindex(order)
    ax.imshow(mat.values, aspect="auto", cmap=cmap, norm=norm, interpolation="nearest")
    ax.set_xticks(range(mat.shape[1])); ax.set_xticklabels([pd.Timestamp(c).strftime("%b %y") for c in mat.columns])
    ax.set_yticks([]); ax.set_ylabel("units, south (top) to north (bottom)")
    di = [k for k, c in enumerate(mat.columns) if pd.Timestamp(c) <= decl]
    if di:
        x = di[-1] + (decl.day - 1) / 30 - .5
        ax.axvline(x, color="k", lw=1.5, ls="--"); ax.text(x, -1, " declaration", va="bottom")
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=cmap(i), label=l) for i, l in enumerate(["Normal", "Watch", "Warning", "Emergency"])],
               loc="upper right", ncol=4)
    fig.suptitle(f"{iso3} risk level, crisis season (model {mv})", fontsize=13)
    fig.savefig(OUT / f"judge_{iso3}.png", dpi=90, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    allres = {}
    for iso in [a for a in sys.argv[1:] if not a.startswith("--")] or ["ZWE", "MWI", "ZMB", "KEN"]:
        r = judge(iso)
        allres[iso] = r
        (OUT / f"judge_{iso}.json").write_text(json.dumps(r, indent=1, default=str))
        print(json.dumps(r, indent=1, default=str)[:3000])
