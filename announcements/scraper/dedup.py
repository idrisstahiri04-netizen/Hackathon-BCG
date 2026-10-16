"""Exact + near-duplicate detection (syndicated KNA stories re-published on GAA, MyGov, etc.).

Three tests, cheapest first:
  1. same canonical URL / same normalised-text hash
  2. 5-word shingle Jaccard >= 0.5          (verbatim copy, small edits)
  3. rewritten syndication: content-word cosine >= 0.75 AND overlap of named entities /
     numbers >= 0.7, published within 21 days. GAA republishes KNA stories as edited
     rewrites (e.g. "The wheat farmer who came back" -> "Wheat farmer returns to crop...":
     shingle Jaccard 0.09 but cosine 0.87, entity overlap 1.00; the closest non-duplicate
     pair in the test run scored cosine 0.65 / entities 0.59).
"""
import bisect
import hashlib
import math
import re
from collections import Counter
from datetime import datetime, timedelta

SHINGLE = 5
COS_MIN, ENT_MIN, MAX_DAYS = 0.75, 0.7, 21
WINDOW_DAYS = 30  # copies are compared only with records published up to 30 days earlier

_STOP = set("""that this with from have were been their there which about would could into they them than then when
what will said also more other such only over after before while where these those under among being upon very most
some many much each just like make made says year years county government""".split())


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()


def shingles(text: str, limit_words: int = 3000) -> set[int]:
    w = normalize(text).split()[:limit_words]
    return {hash(" ".join(w[i:i + SHINGLE])) for i in range(max(0, len(w) - SHINGLE + 1))}


def content_vector(text: str) -> Counter:
    return Counter(w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in _STOP)


def entities(text: str) -> set[str]:
    """Capitalised words (names, places, institutions) and multi-digit numbers."""
    names = set(re.findall(r"\b[A-Z][a-z]{2,}\b", text or ""))
    nums = set(re.findall(r"\b\d[\d,.]*\d\b", text or ""))
    return names | nums


def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    num = sum(v * b[k] for k, v in a.items() if k in b)
    return num / math.sqrt(sum(v * v for v in a.values()) * sum(v * v for v in b.values()))


def canonical_url(url: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", (url or "").strip().lower())
    u = re.sub(r"/index\.php/", "/", u)
    return u.rstrip("/")


def _days_apart(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    try:
        return abs((datetime.fromisoformat(a[:10]) - datetime.fromisoformat(b[:10])).days)
    except ValueError:
        return None


def deduplicate(records: list[dict], priority: dict[str, int]) -> tuple[list[dict], list[dict]]:
    """Return (kept, duplicates). The earliest-published record (then higher-priority source) is canonical."""
    def rank(r):
        return (r.get("published_at") is None, r.get("published_at") or "", priority.get(r["source_id"], 9), r["url"])

    kept, dups, kept_dates = [], [], []
    by_url, by_hash, feats = {}, {}, {}
    for r in sorted(records, key=rank):
        cu, th = canonical_url(r["url"]), r["text_hash"]
        canon, reason = None, None
        if cu in by_url:
            canon, reason = by_url[cu], "same_url"
        elif th in by_hash:
            canon, reason = by_hash[th], "same_text"
        else:
            f = (shingles(r["text"]), content_vector(r["text"]), entities(r["text"]))
            feats[r["ann_id"]] = f
            # records arrive oldest first, so only the tail of `kept` can be within the window;
            # undated records are compared with everything
            pub = r.get("published_at")
            lo = 0
            if pub:
                cutoff = (datetime.fromisoformat(pub[:10]) - timedelta(days=WINDOW_DAYS)).date().isoformat()
                lo = bisect.bisect_left(kept_dates, cutoff)
            for k in kept[lo:]:
                ks, kv, ke = feats[k["ann_id"]]
                s, v, e = f
                if len(s) >= 20 and len(ks) >= 20:
                    inter = len(s & ks)
                    jac = inter / len(s | ks)
                    if jac >= 0.5:
                        canon, reason = k, f"near_duplicate(jaccard={jac:.2f})"
                        break
                    if inter / min(len(s), len(ks)) >= 0.8 and min(len(s), len(ks)) / max(len(s), len(ks)) < 0.5:
                        # one text embeds the other (e.g. a MyGov page containing a KNA story): keep both, link them
                        k.setdefault("overlaps_with", []).append(r["ann_id"])
                        r.setdefault("overlaps_with", []).append(k["ann_id"])
                        continue
                # rewritten syndication: only across sources (one ministry publishes several documents on the
                # same campaign; those are not duplicates) and only between whole articles (a newspaper page
                # mixes several stories)
                if (r["source_id"] == k["source_id"] or "pdf_page" in (r["doc_type"], k["doc_type"])
                        or len(e) < 8 or len(ke) < 8):
                    continue
                days = _days_apart(r.get("published_at"), k.get("published_at"))
                if days is not None and days > MAX_DAYS:
                    continue
                c = cosine(v, kv)
                if c < COS_MIN:
                    continue
                eo = len(e & ke) / min(len(e), len(ke))
                if eo >= ENT_MIN:
                    canon, reason = k, f"syndicated_rewrite(cosine={c:.2f},entities={eo:.2f})"
                    break
        if canon is not None:
            canon.setdefault("duplicate_urls", []).append(r["url"])
            dups.append({"ann_id": r["ann_id"], "url": r["url"], "source_id": r["source_id"],
                         "duplicate_of": canon["ann_id"], "duplicate_of_url": canon["url"], "reason": reason})
            continue
        by_url[cu], by_hash[th] = r, r
        kept.append(r)
        # undated records sort last, so kept_dates stays sorted
        kept_dates.append((r.get("published_at") or "9999")[:10])
    return kept, dups
