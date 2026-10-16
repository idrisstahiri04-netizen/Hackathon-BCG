#!/usr/bin/env python3
"""Download FEWS NET country outlooks (Food Security Outlook, Outlook Update, Key Message Update)
as raw HTML + cleaned text, with the real publication date taken from the page's dataLayer.

Why: expert outlooks state FUTURE conditions ("Crisis (IPC Phase 3) outcomes likely through
March", "below-average rainfall expected") months before satellite signals confirm them.

Route: FEWS NET has no public text API (JSON:API is 404, report-search is bot-challenged), so
we enumerate the documented URL pattern
    https://fews.net/<region>/<country>/<report-type>/<month>-<year>
and keep pages that return HTTP 200 *and* whose dataLayer entityBundle is a report (the site
returns a real 404 for missing months, but we check the bundle anyway: soft-404 guard).

Output (gitignored):
    pipeline/data/raw_outlooks/<ISO3>/<slug>/page.html      untouched download
    pipeline/data/raw_outlooks/<ISO3>/<slug>/text.txt       cleaned body text (paragraph per line)
    pipeline/data/raw_outlooks/<ISO3>/<slug>/_meta.json     url, fetched_at, sha256, publication_date, ...
    pipeline/data/raw_outlooks/manifest.csv                 one row per URL tried (status incl. 404)

Idempotent: URLs already in the manifest are skipped (pass --refetch to retry 404s/errors).
Polite: 4 workers, ~0.3 s between requests per worker, custom UA, obeys robots.txt (checked
manually 2026-10-16: /southern-africa/* and /east-africa/* are not disallowed).

Usage:
    python pipeline/outlooks/fetch.py --iso3 ZWE                 # 2015-06..2024-06
    python pipeline/outlooks/fetch.py --iso3 ZWE MWI ZMB KEN --start 2015-06 --end 2024-06
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html as htmllib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "data" / "raw_outlooks"
MANIFEST = RAW / "manifest.csv"
UA = "Mozilla/5.0 (X11; Linux x86_64) drought-early-warning-hackathon (research; contact via repo)"

COUNTRY_PATH = {
    "ZWE": "southern-africa/zimbabwe",
    "MWI": "southern-africa/malawi",
    "ZMB": "southern-africa/zambia",
    "KEN": "east-africa/kenya",
}
REPORT_TYPES = [
    "food-security-outlook",
    "food-security-outlook-update",
    "key-message-update",
    "remote-monitoring-report",  # remote-monitoring countries (e.g. Zambia) used this
]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
MANIFEST_COLS = ["iso3", "report_type", "month", "url", "status", "publication_date",
                 "page_date_start", "page_date_end", "title", "sha256", "fetched_at", "text_chars"]


class _Text(HTMLParser):
    """Collect visible text, one line per block element, skipping script/style/nav/footer."""
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "svg", "template"}
    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div", "tr", "br", "td", "th",
             "section", "article", "blockquote", "figcaption", "fews-anchor-nav-link"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in raw.split("\n")]
        out, prev_blank = [], True
        for ln in lines:
            if ln:
                out.append(ln)
                prev_blank = False
            elif not prev_blank:
                out.append("")
                prev_blank = True
        return "\n".join(out).strip()


def data_layer(page: str) -> dict:
    """Parse the Drupal dataLayer.push({...}) object (title, publicationDate, report type)."""
    m = re.search(r"window\.dataLayer\.push\((\{.*?\})\);", page, flags=re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def clean_text(page: str, title: str) -> str:
    p = _Text()
    p.feed(page)
    t = p.text()
    # The report body starts at the SECOND "Key Messages" (the first is the anchor nav);
    # fall back to the first occurrence, then to the title.
    idx = [m.start() for m in re.finditer(r"^Key Messages$", t, flags=re.M)]
    start = idx[1] if len(idx) > 1 else (idx[0] if idx else t.find(title) if title else 0)
    t = t[max(start, 0):]
    # Trailing site chrome
    for marker in ("\nRelated Analysis Listing\n", "\nRelated Reports\n", "\nSubscribe to",
                   "\nRecommended Citation\n", "\nAbout FEWS NET\n", "\nGet the latest food security updates"):
        j = t.find(marker)
        if j > 2000:
            t = t[:j]
    return htmllib.unescape(t).strip()


def month_iter(start: str, end: str):
    for m in pd.period_range(start, end, freq="M"):
        yield m.strftime("%Y-%m"), f"{MONTHS[m.month - 1]}-{m.year}"


def fetch_one(sess: requests.Session, iso3: str, rtype: str, month: str, slug: str) -> dict:
    url = f"https://fews.net/{COUNTRY_PATH[iso3]}/{rtype}/{slug}"
    row = dict.fromkeys(MANIFEST_COLS, "")
    row.update(iso3=iso3, report_type=rtype, month=month, url=url,
               fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    try:
        r = sess.get(url, timeout=60, headers={"User-Agent": UA}, allow_redirects=True)
    except requests.RequestException as e:
        row["status"] = f"error:{type(e).__name__}"
        return row
    row["status"] = str(r.status_code)
    if r.status_code != 200:
        return row
    page = r.text
    dl = data_layer(page)
    bundle = dl.get("entityBundle", "")
    if dl.get("entityTitle") == "Page Not Found" or bundle in ("landing_page", ""):
        row["status"] = "soft404"
        return row
    title = dl.get("entityTitle", "")
    pub = (dl.get("publicationDate") or {}).get("value") or []
    pub_date = pub[0]["value"] if pub and isinstance(pub[0], dict) else ""
    pd_range = ((dl.get("pageDate") or {}).get("value") or "").strip("|").split("|")
    text = clean_text(page, title)
    d = RAW / iso3 / f"{rtype}__{slug}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "page.html").write_text(page, encoding="utf-8")
    (d / "text.txt").write_text(text, encoding="utf-8")
    sha = hashlib.sha256(page.encode("utf-8")).hexdigest()
    meta = {"url": url, "final_url": r.url, "fetched_at": row["fetched_at"], "sha256": sha,
            "licence": "FEWS NET / USAID public report; attribute FEWS NET",
            "iso3": iso3, "report_type": rtype, "month": month, "title": title,
            "publication_date": pub_date,
            "page_date_start": pd_range[0] if pd_range else "",
            "page_date_end": pd_range[-1] if len(pd_range) > 1 else "",
            "entity_bundle": bundle, "text_chars": len(text)}
    (d / "_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    row.update(publication_date=pub_date, page_date_start=meta["page_date_start"],
               page_date_end=meta["page_date_end"], title=title, sha256=sha, text_chars=len(text))
    return row


def load_manifest() -> pd.DataFrame:
    if MANIFEST.exists():
        return pd.read_csv(MANIFEST, dtype=str).fillna("")
    return pd.DataFrame(columns=MANIFEST_COLS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", default=["ZWE"], choices=sorted(COUNTRY_PATH))
    ap.add_argument("--start", default="2015-06")
    ap.add_argument("--end", default="2024-06")
    ap.add_argument("--types", nargs="+", default=REPORT_TYPES)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--refetch", action="store_true", help="retry URLs whose status is not 200")
    a = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    man = load_manifest()
    done = set(man.loc[man.status == "200", "url"]) if a.refetch else set(man.url)
    todo = [(iso3, rt, m, slug) for iso3 in a.iso3 for rt in a.types
            for m, slug in month_iter(a.start, a.end)]
    todo = [t for t in todo if f"https://fews.net/{COUNTRY_PATH[t[0]]}/{t[1]}/{t[3]}" not in done]
    print(f"{len(todo)} URLs to try ({len(done)} already in manifest)", file=sys.stderr)

    sess = requests.Session()
    rows = []
    t0 = time.time()

    def job(t):
        time.sleep(0.3)
        return fetch_one(sess, *t)

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(job, t) for t in todo]
        for i, f in enumerate(as_completed(futs), 1):
            rows.append(f.result())
            if i % 50 == 0 or i == len(futs):
                hits = sum(r["status"] == "200" for r in rows)
                print(f"  {i}/{len(futs)} tried, {hits} reports, {time.time() - t0:.0f}s", file=sys.stderr)
                # checkpoint
                pd.concat([man, pd.DataFrame(rows, columns=MANIFEST_COLS)]) \
                    .drop_duplicates("url", keep="last").sort_values(["iso3", "month", "report_type"]) \
                    .to_csv(MANIFEST, index=False, quoting=csv.QUOTE_MINIMAL)

    man = pd.concat([man, pd.DataFrame(rows, columns=MANIFEST_COLS)]) \
        .drop_duplicates("url", keep="last").sort_values(["iso3", "month", "report_type"])
    man.to_csv(MANIFEST, index=False, quoting=csv.QUOTE_MINIMAL)
    ok = man[man.status == "200"]
    print(ok.groupby(["iso3", "report_type"]).size().to_string(), file=sys.stderr)
    print(f"manifest: {MANIFEST} ({len(man)} rows, {len(ok)} reports)", file=sys.stderr)


if __name__ == "__main__":
    main()
