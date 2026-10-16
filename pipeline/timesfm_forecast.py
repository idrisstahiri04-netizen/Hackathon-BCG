"""Zero-shot TimesFM 2.5 forecasts of monthly VCI (vci_crop, vci_grass) per unit.

Challenger / extra feature for pipeline/train.py. Run in the separate venv:
    /home/looooo/bcg/.venv-timesfm/bin/python pipeline/timesfm_forecast.py --iso3 ZWE --lead 1,2,3

For every unit, signal and origin month O (2015-01 .. 2024-06) we feed only the
history with month <= O and forecast O+1..O+max_lead. Output (long):
    pipeline/out/timesfm_<ISO3>.parquet
    unit_id, origin_month, target_month, lead, signal, forecast, q10, q90
Then evaluates vs persistence and climatology -> pipeline/out/timesfm_report.md

Missing data: leading NaNs are dropped; interior gaps in the context are
linearly interpolated (past-only); trailing NaNs are forward-filled. Series with
< 24 valid months at the origin are skipped (no forecast row = missing).

--synthetic writes and uses a fake signals file (same format) for dev testing.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SIGNALS = ["vci_crop", "vci_grass"]
CKPT = "google/timesfm-2.5-200m-pytorch"  # Apache-2.0 weights (3.0 is non-commercial)
EVENT_THR = 35.0


def make_synthetic(path: Path, n_units: int = 10, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    months = pd.date_range("2001-01-01", "2024-12-01", freq="MS")
    rows = []
    for u in range(n_units):
        phase = rng.uniform(0, 2 * np.pi)
        for sig in SIGNALS:
            ar = np.zeros(len(months))
            for i in range(1, len(months)):
                ar[i] = 0.7 * ar[i - 1] + rng.normal(0, 8)
            seas = 15 * np.sin(2 * np.pi * months.month.to_numpy() / 12 + phase)
            v = np.clip(50 + seas + ar, 0, 100).astype(float)
            v[(months >= "2023-11-01") & (months <= "2024-04-01")] -= 30  # fake drought
            v = np.clip(v, 0, 100)
            v[rng.random(len(v)) < 0.03] = np.nan
            rows.append(pd.DataFrame({"unit_id": f"SYN{u:03d}", "unit_name": f"Syn {u}",
                                      "iso3": "SYN", "month": months, "signal_type": sig, "value": v}))
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(rows).to_parquet(path, index=False)


def load_wide(path: Path) -> dict[str, pd.DataFrame]:
    df = pd.read_parquet(path)
    df = df[df.signal_type.isin(SIGNALS)].copy()
    df["month"] = pd.to_datetime(df["month"]).dt.to_period("M").dt.to_timestamp()
    out = {}
    for sig in SIGNALS:
        w = df[df.signal_type == sig].pivot_table(index="month", columns="unit_id", values="value", aggfunc="mean")
        full = pd.date_range(w.index.min(), w.index.max(), freq="MS")
        out[sig] = w.reindex(full)
    return out


def prep_context(s: np.ndarray, min_len: int = 24) -> np.ndarray | None:
    s = s.astype(float)
    ok = np.flatnonzero(~np.isnan(s))
    if len(ok) < min_len:
        return None
    s = pd.Series(s[ok[0]:]).interpolate(limit_area="inside").ffill().to_numpy()
    return s.astype(np.float32)


def run_forecasts(wide, origins, max_lead, batch_size=256, ctx=256, flip=True):
    import timesfm
    import torch

    import os
    torch.set_num_threads(int(os.environ.get("TFM_THREADS", os.cpu_count() or 4)))
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(CKPT)
    model.compile(timesfm.ForecastConfig(
        max_context=ctx, max_horizon=max(16, max_lead), normalize_inputs=True,
        use_continuous_quantile_head=True, force_flip_invariance=flip,
        infer_is_positive=True, fix_quantile_crossing=True, per_core_batch_size=batch_size))

    jobs, ctxs = [], []
    for sig, w in wide.items():
        for o in origins:
            if o not in w.index:
                continue
            hist = w.loc[:o]
            for u in w.columns:
                c = prep_context(hist[u].to_numpy())
                if c is not None:
                    jobs.append((u, o, sig))
                    ctxs.append(c[-ctx:])
    print(f"{len(ctxs)} series to forecast")
    recs = []
    t0 = time.time()
    for b in range(0, len(ctxs), batch_size):
        point, quant = model.forecast(horizon=max_lead, inputs=ctxs[b:b + batch_size])
        # quant[..., k]: k=0 mean, k=1..9 -> q10..q90
        for j, (u, o, sig) in enumerate(jobs[b:b + batch_size]):
            for L in range(1, max_lead + 1):
                recs.append((u, o, o + pd.DateOffset(months=L), L, sig,
                             float(point[j, L - 1]), float(quant[j, L - 1, 1]), float(quant[j, L - 1, 9])))
        print(f"  {min(b + batch_size, len(ctxs))}/{len(ctxs)}  {time.time() - t0:.0f}s", flush=True)
    out = pd.DataFrame(recs, columns=["unit_id", "origin_month", "target_month", "lead", "signal",
                                      "forecast", "q10", "q90"])
    for c in ["forecast", "q10", "q90"]:
        out[c] = out[c].clip(0, 100)
    return out, time.time() - t0


# ---------------------------------------------------------------- evaluation
def add_baselines(fc: pd.DataFrame, wide) -> pd.DataFrame:
    parts = []
    for sig, w in wide.items():
        f = fc[fc.signal == sig].copy()
        long = w.stack().rename("obs").reset_index()
        long.columns = ["target_month", "unit_id", "obs"]
        f = f.merge(long, on=["target_month", "unit_id"], how="left")
        # persistence: last valid value at or before origin
        last = w.ffill().stack().rename("persist").reset_index()
        last.columns = ["origin_month", "unit_id", "persist"]
        f = f.merge(last, on=["origin_month", "unit_id"], how="left")
        # climatology: mean of same calendar month as target, using months <= origin only
        clim = []
        for (o, tm), g in f.groupby(["origin_month", "target_month"]):
            h = w.loc[:o]
            m = h[h.index.month == tm.month].mean()
            clim.append(pd.DataFrame({"origin_month": o, "target_month": tm,
                                      "unit_id": m.index, "clim": m.values}))
        f = f.merge(pd.concat(clim), on=["origin_month", "target_month", "unit_id"], how="left")
        parts.append(f)
    return pd.concat(parts, ignore_index=True)


def scores(d: pd.DataFrame) -> list[dict]:
    rows = []
    d = d.dropna(subset=["obs", "persist", "clim", "forecast"])
    for (sig, L), g in d.groupby(["signal", "lead"]):
        ev = g.obs < EVENT_THR
        for name in ["forecast", "persist", "clim"]:
            pr = g[name] < EVENT_THR
            tp, fp, fn = int((pr & ev).sum()), int((pr & ~ev).sum()), int((~pr & ev).sum())
            rows.append(dict(signal=sig, lead=L, method={"forecast": "timesfm"}.get(name, name),
                             n=len(g), mae=float((g[name] - g.obs).abs().mean()),
                             events=int(ev.sum()), hits=tp, false_alarms=fp,
                             hit_rate=tp / (tp + fn) if tp + fn else np.nan,
                             far=fp / (tp + fp) if tp + fp else np.nan))
    return rows


def md_table(rows: list[dict]) -> str:
    df = pd.DataFrame(rows)
    hdr = "| signal | lead | method | n | MAE | events | hits | false alarms | hit rate | false-alarm ratio |\n|---|---|---|---|---|---|---|---|---|---|\n"
    body = "".join(
        f"| {r.signal} | {r.lead} | {r.method} | {r.n} | {r.mae:.2f} | {r.events} | {r.hits} | {r.false_alarms} | "
        f"{'' if np.isnan(r.hit_rate) else f'{r.hit_rate:.2f}'} | {'' if np.isnan(r.far) else f'{r.far:.2f}'} |\n"
        for r in df.itertuples())
    return hdr + body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", default="ZWE")
    ap.add_argument("--lead", default="1,2,3")
    ap.add_argument("--start", default="2015-01")
    ap.add_argument("--end", default="2024-06")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--ctx", type=int, default=256, help="max context months (multiple of 32)")
    ap.add_argument("--no-flip", action="store_true", help="disable flip invariance (2x faster)")
    ap.add_argument("--max-units", type=int, default=0, help="dev: limit units")
    a = ap.parse_args()
    leads = sorted(int(x) for x in a.lead.split(","))
    iso = "SYN" if a.synthetic else a.iso3.upper()
    src = HERE / "data" / f"signals_{iso}.parquet"
    if a.synthetic:
        src = HERE / "out" / "_synthetic" / "signals_SYN.parquet"
        make_synthetic(src)
    wide = load_wide(src)
    origins = list(pd.date_range(a.start + "-01", a.end + "-01", freq="MS"))
    if a.max_units:
        wide = {k: v.iloc[:, :a.max_units] for k, v in wide.items()}
    fc, secs = run_forecasts(wide, origins, max(leads), a.batch, a.ctx, not a.no_flip)
    fc = fc[fc.lead.isin(leads)]
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    fc.to_parquet(out / f"timesfm_{iso}.parquet", index=False)
    print(f"wrote {len(fc)} rows, forecast time {secs:.0f}s")

    d = add_baselines(fc, wide)
    hist = d[(d.origin_month >= "2015-01-01") & (d.origin_month <= "2022-12-01")]
    crisis = d[(d.target_month >= "2023-10-01") & (d.target_month <= "2024-04-01")]
    n_units = fc.unit_id.nunique()
    rep = [f"# TimesFM zero-shot VCI forecast report ({iso})\n",
           f"Model: `{CKPT}` (zero-shot, CPU). Input: `{src.relative_to(HERE.parent)}`. "
           f"Units: {n_units}. Origins {a.start}..{a.end}. Leads {leads}. max_context={a.ctx} months, "
           f"flip_invariance={not a.no_flip}, batch={a.batch}. Forecast wall time: {secs:.0f}s.\n",
           "Baselines: persistence = last observed value at origin; climatology = mean of same calendar month "
           "using only months <= origin. Event = VCI < 35 (hit rate = hits/events; false-alarm ratio = "
           "false alarms/(hits+false alarms)). Rows with missing obs or baseline are dropped.\n",
           "Caveat: VCI is scaled with 2001-2020 min/max, so the input itself carries mild look-ahead for "
           "2015-2020 origins (same for all methods).\n",
           "\n## Back-test: origins 2015-01 .. 2022-12\n", md_table(scores(hist)),
           "\n## Crisis: targets 2023-10 .. 2024-04\n", md_table(scores(crisis))]
    (out / ("timesfm_report.md" if not a.synthetic else "timesfm_report_SYN.md")).write_text("\n".join(rep))
    print("\n".join(rep))


if __name__ == "__main__":
    main()
