"""Incremental re-runs: a local store of every document fetched so far + per-site state.

  .cache/docs/<source_id>.jsonl   one JSON document per line (text + metadata), appended each run
  .cache/state.json               per site: newest published date stored, last run

The next run searches each site only from (newest stored date - OVERLAP_DAYS), so late
edits and same-day posts are not missed; documents already stored are replaced by the
newer copy (same URL). Classification is re-done on the whole store every run, so rule
changes apply to old documents too.
"""
import json
from datetime import date, timedelta

from .config import CACHE

DOCS = CACHE / "docs"
STATE = CACHE / "state.json"
OVERLAP_DAYS = 3


def use_test_store():
    """Test runs write to .cache/test/ so they never mix with the real store."""
    global DOCS, STATE
    DOCS = CACHE / "test" / "docs"
    STATE = CACHE / "test" / "state.json"
    for p in DOCS.glob("*.jsonl") if DOCS.exists() else []:
        p.unlink()  # each test starts empty


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def since(site_state: dict | None, window_from: str) -> str:
    if not site_state or not site_state.get("max_published"):
        return window_from
    s = (date.fromisoformat(site_state["max_published"][:10]) - timedelta(days=OVERLAP_DAYS)).isoformat()
    return max(s, window_from)


def reset(only: list[str]):
    for sid in only:
        (DOCS / f"{sid}.jsonl").unlink(missing_ok=True)


def append_docs(docs: list[dict]):
    DOCS.mkdir(parents=True, exist_ok=True)
    by_source: dict[str, list[dict]] = {}
    for d in docs:
        by_source.setdefault(d["source_id"], []).append(d)
    for sid, ds in by_source.items():
        with open(DOCS / f"{sid}.jsonl", "a", encoding="utf-8") as f:
            for d in ds:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")


def load_docs() -> list[dict]:
    """All stored documents, last copy per URL wins."""
    by_url: dict[str, dict] = {}
    if DOCS.exists():
        for p in sorted(DOCS.glob("*.jsonl")):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # line still being written by a running fetch
                    by_url[d["url"]] = d
    return list(by_url.values())


def save_state(state: dict, new_docs: list[dict], sources_run: list[str], window_to: str, run_at: str):
    for sid in sources_run:
        dated = [d["published_at"][:10] for d in new_docs if d["source_id"] == sid and d.get("published_at")]
        s = state.setdefault(sid, {})
        # only dates up to the window end count (a PDF can print a later deadline date)
        dated = [x for x in dated if x <= window_to]
        if dated:
            s["max_published"] = max([s.get("max_published") or "", *dated])
        s["last_run_at"] = run_at
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
