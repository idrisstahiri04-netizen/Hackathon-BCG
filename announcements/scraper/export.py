"""Write the final outputs: output/announcements.json (one document per announcement, ready
for a NoSQL database) and output/scrape_report.md. Local audit files go to .cache/."""
import json
from collections import Counter, defaultdict

from .config import CACHE, OUTPUT

MIN_PLACE_SCORE = 0.5
GROUP = {"shortage": "shortage", "mitigation": "response", "reassurance": "good_news"}
# "policy"/"bill"/"regulation" words match far too many unrelated texts to be a useful response event
SKIP_EVENTS = {"policy_announcement"}


def _places(units: list[dict]) -> list[str]:
    """County names (dashboard spelling), best match first. A sub-county mention counts for its
    county. Empty list = national, no county named."""
    best: dict[str, float] = {}
    for u in units:
        if u["match_score"] >= MIN_PLACE_SCORE:
            best[u["county"]] = max(best.get(u["county"], 0.0), u["match_score"])
    return sorted(best, key=lambda c: (-best[c], c))


def _events(cls_evidence: list[dict]) -> dict[str, list[dict]]:
    """{shortage|response|good_news: [{type, quote}]}, one entry per event type with its
    best supporting sentence; empty groups are left out. Sentences about another country or a
    past year are ignored; a denied shortage ("no food shortage") becomes good_news/shortage_denied."""
    groups: dict[str, list[dict]] = {}
    seen, used_quotes = set(), set()
    candidates = []
    for e in cls_evidence:  # already sorted: live shortage first, most severe first
        if e["historical"] or e["foreign"] or e["event_type"] in SKIP_EVENTS:
            continue
        if e["polarity"] == "shortage" and e["negated"]:
            g, t = "good_news", "shortage_denied"
        else:
            g, t = GROUP[e["polarity"]], e["event_type"]
        candidates.append((g, t, e))
    # prefer a sentence not already used for another event, so each quote adds information
    for g, t, e in candidates:
        if (g, t) in seen:
            continue
        alt = next((c for gg, tt, c in candidates if (gg, tt) == (g, t) and c["quote"] not in used_quotes), e)
        seen.add((g, t))
        used_quotes.add(alt["quote"])
        groups.setdefault(g, []).append({"type": t, "quote": alt["quote"]})
    return {g: groups[g] for g in ("shortage", "response", "good_news") if g in groups}


def to_document(r: dict) -> dict:
    return {
        "_id": r["ann_id"],
        "source": r["source_id"],
        "published_at": r["published_at"],
        "title": r["title"],
        "url": r["url"],
        "severity": r["severity"],
        "events": _events(r["evidence"]),
        "crops": r["affected_crops"],
        "places": _places(r["units"]),
        "doc_type": r["doc_type"],
        "language": r["language"],
        "date_source": r["date_source"],
        "meta": {"extraction_model": r["extraction_model"], "ingested_at": r["ingested_at"],
                 "text_hash": r["text_hash"]},
    }


def report_md(kept, all_records, dups, failures, sources, run_meta) -> str:
    by = defaultdict(Counter)
    for r in all_records:
        by[r["source_id"]]["read"] += 1
    event_counts = Counter()
    for r in kept:
        c = by[r["source_id"]]
        c["kept"] += 1
        c[f"sev{r['severity']}"] += 1
        for g, evs in _events(r["evidence"]).items():
            c[g] += 1
            event_counts.update(f"{g}/{e['type']}" for e in evs)
    for d in dups:
        by[d["source_id"]]["dups"] += 1
    for f in failures:
        by[f["source_id"]]["failures"] += 1
    h = run_meta["http"]
    lines = [
        f"# Scrape report — {run_meta['run_at']}", "",
        f"Window **{run_meta['date_from']} → {run_meta['date_to']}** · "
        f"{'TEST run, at most ' + str(run_meta['budget_per_source']) + ' candidates per source' if run_meta['budget_per_source'] else 'full / incremental run'} · "
        f"elapsed {run_meta['elapsed_s']} s", "",
        f"Searched from: {run_meta['searched_from']} · new documents this run: {run_meta['new_documents']}", "",
        f"HTTP requests {h.get('requests', 0)} (cache hits {h.get('cache_hits', 0)}, errors {h.get('errors', 0)}, "
        f"robots-blocked {h.get('robots_blocked', 0)}) · pre-filter skips: {run_meta['pre_filter_skips'] or 'none'}", "",
        f"Documents analysed: {run_meta['documents_read']} · duplicates removed: {run_meta['duplicates_removed']} · "
        f"dropped: {run_meta['dropped']} · **kept: {run_meta['kept']}**", "",
        "| source | status | analysed | kept | with shortage | with response | with good_news | sev 0 | sev 1 | sev 2 | sev 3 | dups | failures |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in sources:
        c = by[s["source_id"]]
        status = "FAILED" if not c["read"] else ("PARTIAL" if c["failures"] else "OK")
        lines.append(f"| {s['source_id']} | {status} | {c['read']} | {c['kept']} | {c['shortage']} | {c['response']} | "
                     f"{c['good_news']} | {c['sev0']} | {c['sev1']} | {c['sev2']} | {c['sev3']} | {c['dups']} | {c['failures']} |")
    if event_counts:
        lines += ["", "## Events (kept documents)", "",
                  ", ".join(f"{k} ({n})" for k, n in event_counts.most_common())]
    if failures:
        lines += ["", f"## Failures ({len(failures)})", "", "| source | stage | url | error |", "|---|---|---|---|"]
        lines += [f"| {f['source_id']} | {f['stage']} | {f['url']} | {f['error'].replace('|', '/')[:200]} |" for f in failures[:200]]
    if dups:
        lines += ["", f"## Duplicates removed ({len(dups)})", ""]
        lines += [f"- {d['url']} → {d['duplicate_of_url']} ({d['reason']})" for d in dups[:200]]
    return "\n".join(lines) + "\n"


def export_all(kept, all_records, dups, failures, sources, run_meta) -> str:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    kept = sorted(kept, key=lambda r: r["published_at"], reverse=True)

    (OUTPUT / "announcements.json").write_text(
        json.dumps([to_document(r) for r in kept], ensure_ascii=False, indent=1), encoding="utf-8")
    report = report_md(kept, all_records, dups, failures, sources, run_meta)
    (OUTPUT / "scrape_report.md").write_text(report, encoding="utf-8")

    # local audit only: every analysed document with its verdict, to check what the filter dropped
    with open(CACHE / "candidates_all.jsonl", "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps({k: r.get(k) for k in ("ann_id", "source_id", "url", "title", "published_at", "doc_type",
                                                     "is_relevant", "signal_class", "severity")},
                               ensure_ascii=False) + "\n")
    return report
