"""Targets from satellite signals only (no announcements, no prices -> no leakage of the official story).

Per unit and season instance (seasons found per unit from its own rain climatology, see
common.detect_seasons; bimodal climates get two seasons per year):

  crop_failure : min monthly vci_crop over the crop window (3 wettest months shifted +1) < 35
  no_grass     : min vci_grass over the 3 months after the rainy season < 35
  cant_plant   : in any month of the planting window (first 2 rainy-season months)
                 spi_1m < -1 AND sm1_z < -1

A label is NaN (missing, not 0) if the window has no valid observation of the needed signals.

    python pipeline/labels.py --iso3 ZWE        # prints seasons + label prevalence
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common import (DATA_DIR, EVENTS, WINDOW_LEN, Country, load_country,
                    season_instances, unit_seasons)

VCI_T = 35.0


def window_months(start: pd.Timestamp, n: int) -> list:
    return [start + pd.DateOffset(months=i) for i in range(n)]


def event_outcome(w: pd.DataFrame, event: str, months: list) -> float:
    """w: wide frame for one unit indexed by month. Returns 1.0/0.0/NaN."""
    sub = w.reindex(months)
    if event == "crop_failure":
        v = sub["vci_crop"].dropna()
        return np.nan if v.empty else float(v.min() < VCI_T)
    if event == "no_grass":
        v = sub["vci_grass"].dropna()
        return np.nan if v.empty else float(v.min() < VCI_T)
    if event == "cant_plant":
        both = sub[["spi_1m", "sm1_z"]].dropna()
        return np.nan if both.empty else float(((both.spi_1m < -1) & (both.sm1_z < -1)).any())
    raise ValueError(event)


def build_targets(c: Country, seasons: dict | None = None) -> pd.DataFrame:
    """One row per (unit, season instance, event) with window start W0 and label."""
    seasons = seasons or unit_seasons(c)
    months = c.wide.index.get_level_values("month")
    y0, y1 = months.min().year, months.max().year
    rows = []
    for u, ss in seasons.items():
        w = c.wide.loc[u]
        inst = season_instances(ss, y0, y1)
        for _, r in inst.iterrows():
            for e in EVENTS:
                W0 = r[e]
                wm = window_months(W0, WINDOW_LEN[e])
                if wm[-1] > months.max() or wm[0] < months.min():
                    continue
                rows.append(dict(unit_id=u, iso3=c.iso3, season=int(r.season), anchor=r.anchor,
                                 agyear=int(r.agyear), event=e, W0=W0,
                                 label=event_outcome(w, e, wm)))
    t = pd.DataFrame(rows)
    # previous instance of the same event in the same unit (for the persistence baseline)
    t = t.sort_values(["unit_id", "event", "W0"])
    t["prev_label"] = t.groupby(["unit_id", "event"])["label"].shift(1)
    return t.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", required=True)
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    a = ap.parse_args()
    c = load_country(a.iso3, a.data_dir)
    ss = unit_seasons(c)
    nb = sum(len(v) > 1 for v in ss.values())
    print(f"{a.iso3}: {len(ss)} units, {nb} bimodal")
    first = next(iter(ss.values()))
    for s in first:
        print("  example season", s)
    t = build_targets(c, ss)
    print(t.groupby(["event"]).label.agg(["count", "mean"]))
    print(t[t.agyear >= 2015].groupby(["agyear", "event"]).label.mean().unstack().round(2))


if __name__ == "__main__":
    main()
