#!/usr/bin/env python3
"""Quick value test for the outlook signal (ZWE): how early did FEWS NET text project Crisis /
below-normal rain per district, versus our satellite model's first Watch/Warning and the
2024-04-03 national disaster declaration? Plus false-alarm look at non-drought years.

Leakage rule: a row is usable at issue month r only if publish_month <= r. We use publish_month
(from the page's publicationDate) as the month the signal becomes available.

Outlook alert definition (per unit, per publish month):
    text_watch   : any usable statement with projected_severity >= 1 (Stressed+) for a target month
                   within the season window, OR rain_outlook == below for the unit
    text_crisis  : projected_severity >= 2 (Crisis+), statement_type == projection
Match types considered: district, livelihood_zone, province (sub-national, gazetteer) and, in a
second variant, descriptor_map (reviewed descriptor -> LZ map). National rows are excluded
(they would alert all 91 districts at once).

Output: printed tables + pipeline/outlooks/value_test_ZWE.json (numbers used in report.md).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = HERE.parent / "data"
ISO3 = "ZWE"
DECLARATION = "2024-04"
# season windows: issue months considered, target months that count as "this season"
SEASONS = {
    "2023/24 (El Nino drought)": {"issue": ("2023-06", "2024-06"), "target": ("2023-10", "2024-06")},
    "2015/16 (El Nino drought, declared 2016-02)": {"issue": ("2015-06", "2016-06"), "target": ("2015-10", "2016-06")},
    "2018/19 (dry season, Cyclone Idai Mar-2019)": {"issue": ("2018-06", "2019-06"), "target": ("2018-10", "2019-06")},
    "2020/21 (good rains)": {"issue": ("2020-06", "2021-06"), "target": ("2020-10", "2021-06")},
    "2021/22 (mixed, late start)": {"issue": ("2021-06", "2022-06"), "target": ("2021-10", "2022-06")},
    "2022/23 (good rains)": {"issue": ("2022-06", "2023-06"), "target": ("2022-10", "2023-06")},
}


def load_risk() -> pd.DataFrame:
    s = (ROOT / "data" / "risk" / f"{ISO3}.js").read_text()
    j = json.loads(s[s.index(f'RISK_DATA["{ISO3}"] = ') + len(f'RISK_DATA["{ISO3}"] = '):].rstrip().rstrip(";"))
    y0 = j["meta"]["start_year"]
    rows = []
    for u in j["units"]:
        for p in u["series"]:
            rows.append({"unit_id": u["id"], "unit_name": u["name"],
                         "month": f"{y0 + p['t'] // 12}-{p['t'] % 12 + 1:02d}", "level": p["level"]})
    return pd.DataFrame(rows)


def first_month(df: pd.DataFrame, flag: str, lo: str, hi: str, col="month") -> pd.Series:
    d = df[(df[col] >= lo) & (df[col] <= hi) & df[flag]]
    return d.groupby("unit_id")[col].min()


def outlook_alerts(ol: pd.DataFrame, match_types: list[str], tgt: tuple[str, str]) -> pd.DataFrame:
    d = ol[ol.match_type.isin(match_types) & (ol.target_month >= tgt[0]) & (ol.target_month <= tgt[1])
           & ~ol.area_name.str.lower().str.contains("urban")].copy()
    d["text_watch"] = (d.projected_severity >= 1) | (d.rain_outlook == "below")
    d["text_crisis"] = (d.projected_severity >= 2) & (d.statement_type == "projection")
    d["text_below_rain"] = d.rain_outlook == "below"
    # Crisis projected for the post-harvest months (Apr-Jun) = harvest expected to fail; in a normal
    # year FEWS NET projects improvement to Stressed/Minimal after April, so this is drought-specific
    season_end_year = tgt[1][:4]
    d["text_crisis_postharvest"] = d.text_crisis & d.target_month.isin([f"{season_end_year}-04", f"{season_end_year}-05", f"{season_end_year}-06"])
    g = d.groupby(["unit_id", "publish_month"]).agg(text_watch=("text_watch", "any"),
                                                   text_crisis=("text_crisis", "any"),
                                                   text_below_rain=("text_below_rain", "any"),
                                                   text_crisis_postharvest=("text_crisis_postharvest", "any")).reset_index()
    return g.rename(columns={"publish_month": "month"})


def lead_table(first_a: pd.Series, first_b: pd.Series, units: list[str]) -> dict:
    """months by which A precedes B (positive = A earlier), over units where both exist."""
    both = [u for u in units if u in first_a.index and u in first_b.index]
    if not both:
        return {"n_both": 0}
    lead = [(pd.Period(first_b[u], "M") - pd.Period(first_a[u], "M")).n for u in both]
    s = pd.Series(lead)
    return {"n_both": len(both), "median_lead_months": float(s.median()), "mean_lead_months": round(float(s.mean()), 2),
            "share_a_earlier": round(float((s > 0).mean()), 2), "share_same": round(float((s == 0).mean()), 2)}


def main():
    ol = pd.read_parquet(DATA / f"outlook_{ISO3}.parquet")
    risk = load_risk()
    units = sorted(risk.unit_id.unique())
    risk["watch"] = risk.level >= 1
    risk["warning"] = risk.level >= 2
    out = {"n_units": len(units), "rows_outlook": len(ol),
           "match_type_counts": ol.match_type.value_counts().to_dict(), "seasons": {}}
    variants = {"gazetteer_only": ["district", "livelihood_zone", "province"],
                "gazetteer+descriptor_map": ["district", "livelihood_zone", "province", "descriptor_map"]}
    for season, w in SEASONS.items():
        lo, hi = w["issue"]
        res = {"model_first_watch": first_month(risk, "watch", lo, hi).astype(str).to_dict(),
               "model_first_warning_n": int(first_month(risk, "warning", lo, hi).shape[0])}
        mw, mwar = first_month(risk, "watch", lo, hi), first_month(risk, "warning", lo, hi)
        res["model_units_watch"] = int(mw.shape[0])
        res["model_watch_month_hist"] = mw.value_counts().sort_index().to_dict()
        res["model_warning_month_hist"] = mwar.value_counts().sort_index().to_dict()
        for vname, mts in variants.items():
            al = outlook_alerts(ol, mts, w["target"])
            tw = first_month(al, "text_watch", lo, hi)
            tc = first_month(al, "text_crisis", lo, hi)
            tr = first_month(al, "text_below_rain", lo, hi)
            tp = first_month(al, "text_crisis_postharvest", lo, hi)
            v = {"units_text_crisis_postharvest": int(tp.shape[0]),
                 "text_crisis_postharvest_month_hist": tp.value_counts().sort_index().to_dict(),
                 "lead_text_crisis_postharvest_vs_model_watch": lead_table(tp, mw, units),
                 "units_text_watch": int(tw.shape[0]), "units_text_crisis": int(tc.shape[0]),
                 "units_text_below_rain": int(tr.shape[0]),
                 "text_crisis_month_hist": tc.value_counts().sort_index().to_dict(),
                 "text_below_rain_month_hist": tr.value_counts().sort_index().to_dict(),
                 "text_watch_month_hist": tw.value_counts().sort_index().to_dict(),
                 "lead_text_crisis_vs_model_watch": lead_table(tc, mw, units),
                 "lead_text_crisis_vs_model_warning": lead_table(tc, mwar, units),
                 "lead_text_watch_vs_model_watch": lead_table(tw, mw, units)}
            if season.startswith("2023/24"):
                decl = pd.Period(DECLARATION, "M")
                v["text_crisis_lead_vs_declaration_months"] = {
                    "median": float(pd.Series([(decl - pd.Period(m, "M")).n for m in tc]).median()) if len(tc) else None,
                    "min": int(min((decl - pd.Period(m, "M")).n for m in tc)) if len(tc) else None,
                    "max": int(max((decl - pd.Period(m, "M")).n for m in tc)) if len(tc) else None}
                v["model_watch_lead_vs_declaration_months"] = {
                    "median": float(pd.Series([(decl - pd.Period(m, "M")).n for m in mw]).median()) if len(mw) else None}
            res[vname] = v
        del res["model_first_watch"]
        out["seasons"][season] = res

    (HERE / f"value_test_{ISO3}.json").write_text(json.dumps(out, indent=1, default=str))
    for season, r in out["seasons"].items():
        print(f"\n=== {season}")
        print(f"  model: units with Watch {r['model_units_watch']}/{out['n_units']}, Warning {r['model_first_warning_n']}")
        print(f"  model first-Watch month hist: {r['model_watch_month_hist']}")
        print(f"  model first-Warning month hist: {r['model_warning_month_hist']}")
        for vname in variants:
            v = r[vname]
            print(f"  [{vname}] text Crisis units {v['units_text_crisis']}, below-rain units {v['units_text_below_rain']}, Stressed+ units {v['units_text_watch']}")
            print(f"     text first-Crisis month hist: {v['text_crisis_month_hist']}")
            print(f"     text first-below-rain hist:   {v['text_below_rain_month_hist']}")
            print(f"     post-harvest Crisis units {v['units_text_crisis_postharvest']} hist: {v['text_crisis_postharvest_month_hist']}; lead vs model-Watch {v['lead_text_crisis_postharvest_vs_model_watch']}")
            print(f"     lead text-Crisis vs model-Watch: {v['lead_text_crisis_vs_model_watch']}")
            print(f"     lead text-Crisis vs model-Warning: {v['lead_text_crisis_vs_model_warning']}")
            if "text_crisis_lead_vs_declaration_months" in v:
                print(f"     text-Crisis lead vs declaration: {v['text_crisis_lead_vs_declaration_months']}; "
                      f"model-Watch lead vs declaration: {v['model_watch_lead_vs_declaration_months']}")
    print(f"\nwrote {HERE / f'value_test_{ISO3}.json'}")


if __name__ == "__main__":
    main()
