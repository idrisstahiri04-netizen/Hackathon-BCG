"""End-to-end run: discover -> fetch -> extract -> classify -> dedup -> keep -> export -> report."""
import hashlib
import logging
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import EXTRACTION_MODEL, rules, store
from .adapters import ADAPTERS
from .config import CACHE, load_keywords, load_sources
from .dedup import deduplicate, text_hash
from .export import export_all
from .gazetteer import match_units
from .http import PoliteSession
from .text_extract import SOFT_HYPHEN
from .keywords import KeywordTagger

log = logging.getLogger(__name__)


# Option B: shortage evidence (severity 1-3) + government response + good news.
# Dropped: unrelated, and agricultural news with no shortage / response / reassurance angle.
KEEP_CLASSES = {"shortage_signal", "weak_shortage_mention", "mitigation_only", "reassurance"}


def _sha(s: str, n: int = 12) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:n]


def build_record(doc: dict, ingested_at: str) -> dict:
    """Internal record: classification + places. export.to_document() turns it into the stored
    JSON document; the text itself stays in the local cache only. signal_class is internal:
    it decides what is kept (KEEP_CLASSES) but is not part of the document."""
    pub_year = int(doc["published_at"][:4]) if doc.get("published_at") else None
    # documents stored before the soft-hyphen fix still carry them
    doc = {**doc, "text": SOFT_HYPHEN.sub("", doc["text"]), "title": SOFT_HYPHEN.sub("", doc.get("title") or "") or None}
    title = doc.get("title") or ""
    cls = rules.classify(title, doc["text"], pub_year)
    units = match_units(doc["text"], title) if cls["is_relevant"] else []
    return {
        "ann_id": _sha(doc["url"]),
        "source_id": doc["source_id"],
        "published_at": doc.get("published_at"),
        "date_source": doc.get("date_source"),
        "title": doc.get("title"),
        "url": doc["url"],
        "doc_type": doc["doc_type"],
        "language": rules.detect_language(doc["text"]),
        "is_relevant": cls["is_relevant"],
        "signal_class": cls["signal_class"],
        "severity": cls["severity"] if cls["is_relevant"] else None,
        "affected_crops": cls["affected_crops"],
        "units": [u.__dict__ for u in units],
        "evidence": cls["evidence"],
        "text_hash": text_hash(doc["text"]),
        "extraction_model": EXTRACTION_MODEL,
        "ingested_at": ingested_at,
        "text": doc["text"],
    }


def run(only: list[str] | None, budget: int | None, refresh: bool = False,
        date_from: str | None = None, date_to: str | None = None, full: bool = False,
        fetch_only: bool = False, rebuild: bool = False) -> dict:
    """budget set (test run): isolated, ignores and does not update the incremental state.
    Otherwise incremental: each site is only searched from its newest stored article
    (minus an overlap), new documents are appended to the local store, and the outputs are
    rebuilt from the whole store. full=True ignores the state and re-scrapes the window.
    fetch_only: download + extract + store, no classification / output (a test run stores in .cache/test/).
    rebuild: no network at all, classify the stored documents and rewrite the output."""
    t0 = time.time()
    defaults, sources = load_sources()
    window_from, window_to = date_from or defaults["date_from"], date_to or defaults["date_to"]
    search_terms, tags = load_keywords()
    tagger = KeywordTagger(search_terms, tags)
    ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    selected = sorted([s for s in sources if not only or s["source_id"] in only], key=lambda s: s.get("priority", 9))
    incremental = not budget and not full
    if fetch_only and budget:
        store.use_test_store()
    state = store.load_state()
    if full:  # forget only the re-scraped sites; the others keep their state
        for s in selected:
            state.pop(s["source_id"], None)

    if fetch_only and full:
        store.reset(only=[s["source_id"] for s in selected])
    lock = threading.Lock()

    def save_now(docs):
        """fetch-only: documents are written to the store as each year / issue completes,
        so an interrupted run keeps what it already downloaded."""
        if fetch_only and docs:
            with lock:
                store.append_docs(docs)

    def collect(src):
        """One site, in its own thread with its own polite session (one request at a time, 2 s gap)."""
        sid = src["source_id"]
        since = store.since(state.get(sid), window_from) if incremental else window_from
        ctx = {"date_from": since, "date_to": window_to, "budget": budget, "search_terms": search_terms,
               "tagger": tagger, "stats": Counter(), "on_docs": save_now}
        sess = PoliteSession(defaults, CACHE / "http", refresh=refresh)
        fails = []
        log.info("=== %s (%s adapter) %s..%s%s", sid, src["adapter"], since, window_to,
                 " [incremental]" if since != window_from else "")
        try:
            got = ADAPTERS[src["adapter"]](sess, src, fails, ctx)
        except Exception as e:  # noqa: BLE001 - one broken site must not stop the others
            log.exception("adapter crashed for %s", sid)
            fails.append({"source_id": sid, "url": src["url"], "stage": "adapter", "error": repr(e)[:300]})
            got = []
        log.info("=== %s done: %d documents", sid, len(got))
        return sid, since, got, fails, sess.stats, ctx["stats"]

    new_docs, failures, http_stats, skip_stats, since_by_source = [], [], Counter(), Counter(), {}
    with ThreadPoolExecutor(max_workers=len(selected)) as pool:  # the sites run in parallel
        for sid, since, got, fails, hs, ss in (pool.map(collect, selected) if not rebuild else []):
            new_docs += got
            failures += fails
            http_stats.update(hs)
            skip_stats.update(ss)
            since_by_source[sid] = since

    if fetch_only:  # documents already saved by save_now()
        store.save_state(state, new_docs, [s["source_id"] for s in selected], window_to, ingested_at)
        report = fetch_report(new_docs, failures, selected, http_stats, skip_stats, since_by_source,
                              window_to, budget, round(time.time() - t0, 1), ingested_at)
        (store.DOCS.parent / "fetch_report.md").write_text(report, encoding="utf-8")
        return {"report": report, "new_docs": new_docs, "failures": failures}

    if rebuild:
        docs = store.load_docs()
    elif budget:
        docs = new_docs
    else:
        if full:
            store.reset(only=[s["source_id"] for s in selected])
        store.append_docs(new_docs)
        store.save_state(state, new_docs, [s["source_id"] for s in selected], window_to, ingested_at)
        docs = store.load_docs()  # every source, every run so far

    records = []
    for d in docs:
        if len(d["text"].strip()) < 80:
            failures.append({"source_id": d["source_id"], "url": d["url"], "stage": "extract_text",
                             "error": f"too little text extracted ({len(d['text'].strip())} chars)"})
            continue
        records.append(build_record(d, ingested_at))

    priority = {s["source_id"]: s.get("priority", 9) for s in sources}
    unique, dups = deduplicate(records, priority)

    # what is kept: Option B classes, with an explicit date inside the window
    kept, dropped = [], {"unrelated_or_general": 0, "no_date": 0, "outside_window": 0}
    for r in unique:
        if not r["is_relevant"] or r["signal_class"] not in KEEP_CLASSES:
            dropped["unrelated_or_general"] += 1
        elif not r["published_at"]:
            dropped["no_date"] += 1
        elif not (window_from <= r["published_at"][:10] <= window_to):
            dropped["outside_window"] += 1
        else:
            kept.append(r)

    run_meta = {"run_at": ingested_at, "date_from": window_from, "date_to": window_to,
                "budget_per_source": budget, "sources_run": [s["source_id"] for s in selected],
                "searched_from": since_by_source, "new_documents": len(new_docs),
                "elapsed_s": round(time.time() - t0, 1), "http": dict(http_stats), "pre_filter_skips": dict(skip_stats),
                "extraction_model": EXTRACTION_MODEL,
                "documents_read": len(records), "duplicates_removed": len(dups), "dropped": dropped, "kept": len(kept)}
    report = export_all(kept, unique, dups, failures, selected, run_meta)
    return {"report": report, "kept": kept, "all": unique, "dups": dups, "failures": failures}


def fetch_report(docs, failures, sources, http_stats, skip_stats, since_by_source, window_to, budget, elapsed,
                 run_at) -> str:
    """Summary of a --fetch-only run: what was downloaded per site; nothing is analysed."""
    by = {s["source_id"]: Counter() for s in sources}
    dates_by = {s["source_id"]: [] for s in sources}
    for d in docs:
        c = by[d["source_id"]]
        c["documents"] += 1
        c[d["doc_type"]] += 1
        c["no_date"] += d.get("published_at") is None
        c["short_text"] += len(d["text"].strip()) < 80
        if d.get("published_at"):
            dates_by[d["source_id"]].append(d["published_at"][:10])
    for f in failures:
        by[f["source_id"]]["failures"] += 1
    mode = (f"TEST (at most {budget} candidates per source, stored in .cache/test/)" if budget
            else "Full / incremental fetch, stored in .cache/docs/")
    lines = [
        f"# Fetch report — {run_at}", "",
        f"{mode} · window end {window_to} · elapsed {elapsed} s", "",
        f"HTTP requests {http_stats.get('requests', 0)} (cache hits {http_stats.get('cache_hits', 0)}, "
        f"errors {http_stats.get('errors', 0)}, robots-blocked {http_stats.get('robots_blocked', 0)}) · "
        f"pre-filter skips: {dict(skip_stats) or 'none'}", "",
        "| source | searched from | documents | web articles | PDFs | PDF pages | oldest | newest | no date | short text | failures |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in sources:
        sid, c, ds = s["source_id"], by[s["source_id"]], dates_by[s["source_id"]]
        lines.append(f"| {sid} | {since_by_source.get(sid)} | {c['documents']} | {c['web_article']} | "
                     f"{c['pdf'] + c['docx']} | {c['pdf_page']} | {min(ds) if ds else '-'} | {max(ds) if ds else '-'} | "
                     f"{c['no_date']} | {c['short_text']} | {c['failures']} |")
    if failures:
        lines += ["", f"## Failures ({len(failures)})", "", "| source | stage | url | error |", "|---|---|---|---|"]
        lines += [f"| {f['source_id']} | {f['stage']} | {f['url']} | {f['error'].replace('|', '/')[:200]} |"
                  for f in failures[:200]]
    return "\n".join(lines) + "\n"
