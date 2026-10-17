"""Per-site discovery + document building.

Each adapter returns Doc dicts:
  source_id, url, title, text, published_at, date_source, date_hint, doc_type,
  raw_ref (online URL of the fetched original), raw_cache_path (local copy),
  fetched_at, discovered_via
and appends failures to `failures` instead of raising.

`ctx` carries: date_from, date_to (ISO dates), search_terms, budget (max candidates
per source, None = no limit).
"""
import html as htmllib
import logging
import math
import re
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from . import dates
from .text_extract import docx_text, html_fragment_to_text, html_page_to_text, links_in_fragment, pdf_pages

log = logging.getLogger(__name__)

DOC_EXT = re.compile(r"\.(pdf|docx)(?:$|\?)", re.I)
# running page headers of the MyGov newspaper, e.g. "NEWSFOCUS | 13 OCTOBER 6, 2026"
MYGOV_HEADER = re.compile(r"NEWSFOCUS|MyGov|Issue No|www\.|^\s*\d+\s*\||\|\s*\d+\s*$|\b20\d\d\s*$", re.I)


def _fail(failures, source_id, url, stage, err):
    log.warning("[%s] %s failed for %s: %s", source_id, stage, url, err)
    failures.append({"source_id": source_id, "url": url, "stage": stage, "error": f"{type(err).__name__}: {err}"[:300]})


def _doc(source_id, url, title, text, *, published_at=None, date_source=None, date_hint=None,
         doc_type="web_article", raw_ref=None, raw_cache_path=None, fetched_at=None, via=None, extra=None):
    d = {
        "source_id": source_id, "url": url, "title": (title or "").strip() or None, "text": text or "",
        "published_at": published_at, "date_source": date_source if published_at else None,
        "date_hint": date_hint, "doc_type": doc_type, "raw_ref": raw_ref or url, "raw_cache_path": raw_cache_path,
        "fetched_at": fetched_at, "discovered_via": via,
    }
    if extra:
        d.update(extra)
    return d


def in_range(ctx, iso: str | None) -> bool:
    return bool(iso) and ctx["date_from"] <= iso[:10] <= ctx["date_to"]


# ------------------------------------------------------------------ documents (PDF / DOCX)
def _title_from_pdf(meta: dict, pages: list[str], url: str) -> str:
    t = (meta.get("title") or "").strip()
    if t and len(t) > 8 and not re.search(r"(microsoft|untitled|\.docx?$|^document\d*$)", t, re.I):
        return t
    for line in (pages[0] if pages else "").splitlines()[:15]:
        line = line.strip()
        if len(line) > 15 and not re.search(r"republic of kenya|ministry of|state department|directorate|^office of|^p\.?o\.? box|tel|email", line, re.I):
            return line[:200]
    return unquote(urlparse(url).path.rsplit("/", 1)[-1]).rsplit(".", 1)[0].replace("-", " ").replace("_", " ")


def fetch_document(sess, source_id, url, failures, via, title_hint=None, split_pages=False, date_override=None):
    try:
        body, meta = sess.get(url, sub=f"{source_id}/docs")
    except Exception as e:  # noqa: BLE001 - recorded as failure
        _fail(failures, source_id, url, "fetch_document", e)
        return []
    ctype = meta.get("content_type", "")
    hint = dates.upload_month_hint(url)
    common = dict(raw_ref=meta["url"], raw_cache_path=meta["raw_path"], fetched_at=meta["fetched_at"], via=via)
    try:
        if url.lower().split("?")[0].endswith(".docx") or "wordprocessingml" in ctype:
            text = docx_text(body)
            title = title_hint or (text.splitlines()[0][:200] if text else None)
            return [_doc(source_id, url, title, text, published_at=dates.find_date_in_text(text),
                         date_source="document_text", date_hint=hint, doc_type="docx", **common)]
        if not body[:5].startswith(b"%PDF"):
            raise ValueError(f"not a PDF (content-type {ctype!r})")
        pages, pmeta = pdf_pages(body)
    except Exception as e:  # noqa: BLE001
        _fail(failures, source_id, url, "parse_document", e)
        return []
    if not any(p.strip() for p in pages):
        _fail(failures, source_id, url, "pdf_text", ValueError(f"no text layer in {len(pages)} pages (scanned PDF; OCR needed)"))
        return []

    pub, dsrc = date_override if date_override else (dates.find_date_in_text("\n".join(pages[:2])), "document_text")

    if split_pages:  # newspaper-style PDFs (MyGov): one record per page
        out = []
        base_title = title_hint or _title_from_pdf(pmeta, pages, url)
        for i, ptxt in enumerate(pages, 1):
            if len(ptxt) < 200:
                continue
            first = next((l.strip() for l in ptxt.splitlines() if len(l.strip()) > 25 and not MYGOV_HEADER.search(l)), "")
            out.append(_doc(source_id, f"{url}#page={i}", f"{base_title} p.{i}: {first[:120]}", ptxt,
                            published_at=pub, date_source=dsrc, date_hint=hint, doc_type="pdf_page",
                            extra={"pdf_page": i, "pdf_pages": len(pages)}, **{**common, "raw_ref": f"{meta['url']}#page={i}"}))
        return out
    return [_doc(source_id, url, title_hint or _title_from_pdf(pmeta, pages, url), "\n\n".join(pages), published_at=pub,
                 date_source=dsrc, date_hint=hint, doc_type="pdf", extra={"pdf_pages": len(pages)}, **common)]


# ------------------------------------------------------------------ WordPress REST
LIGHT_FIELDS = "id,date,link"
FULL_FIELDS = "id,date,modified,link,title,content"


def wp_discover(sess, src, failures, ctx) -> dict[int, dict]:
    """Search every keyword within the date window; return {post_id: {date, link, terms}}.
    Light requests (no content) so many pages are cheap."""
    sid, api = src["source_id"], src["discovery"]["wp_api"]
    terms, budget = src.get("search_terms") or ctx["search_terms"], ctx["budget"]
    fields = LIGHT_FIELDS + (",title,excerpt" if src.get("prefilter_excerpt") else "")
    # test runs: spread a small budget across keywords instead of exhausting the first one
    per_term = max(1, math.ceil(budget / len(terms))) if budget else None
    found: dict[int, dict] = {}
    for term in terms:
        if budget and len(found) >= budget:
            break
        page, n_term = 1, 0
        while True:
            params = {"search": term, "after": f"{ctx['date_from']}T00:00:00", "before": f"{ctx['date_to']}T23:59:59",
                      "per_page": min(100, per_term) if per_term else 100, "page": page, "orderby": "date",
                      "order": "desc", "_fields": fields}
            try:
                items, meta = sess.get_json(api, sub=f"{sid}/api", params=params)
            except Exception as e:  # noqa: BLE001
                _fail(failures, sid, f"{api}?search={term}&page={page}", "wp_search", e)
                break
            if not isinstance(items, list):
                _fail(failures, sid, api, "wp_search", ValueError(f"unexpected payload: {str(items)[:120]}"))
                break
            for it in items:
                rec = found.setdefault(it["id"], {
                    "date": it.get("date"), "link": it.get("link"), "terms": [],
                    "title": (it.get("title") or {}).get("rendered", ""),
                    "excerpt": (it.get("excerpt") or {}).get("rendered", "")})
                rec["terms"].append(term)
                n_term += 1
            total_pages = int(meta.get("wp_total_pages") or 1)
            log.info("[%s] '%s' page %d/%d -> %d unique so far", sid, term, page, total_pages, len(found))
            if per_term or page >= total_pages or not items:
                break
            page += 1
    return found


def _wp_get_batch(sess, sid, api, chunk, failures) -> tuple[list, dict]:
    """Fetch up to 100 posts in one request; if the server chokes (timeout / 5xx on a big
    payload), split the batch in two and retry each half, down to single posts."""
    params = {"include": ",".join(map(str, chunk)), "per_page": len(chunk), "_fields": FULL_FIELDS, "orderby": "include"}
    try:
        return sess.get_json(api, sub=f"{sid}/api", params=params)
    except Exception as e:  # noqa: BLE001
        if len(chunk) == 1:
            _fail(failures, sid, f"{api}/{chunk[0]}", "wp_fetch", e)
            return [], {}
        log.warning("[%s] batch of %d failed (%s); splitting", sid, len(chunk), e)
        half = len(chunk) // 2
        a, ma = _wp_get_batch(sess, sid, api, chunk[:half], failures)
        b, mb = _wp_get_batch(sess, sid, api, chunk[half:], failures)
        return a + b, ma or mb


def wp_fetch(sess, src, failures, found: dict[int, dict], batch: int = 100) -> list[dict]:
    """Download full content for the discovered post ids, `batch` posts per request (WordPress max 100)."""
    sid, api = src["source_id"], src["discovery"]["wp_api"]
    batch = int(src.get("fetch_batch", batch))
    ids = list(found)
    docs = []
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        items, meta = _wp_get_batch(sess, sid, api, chunk, failures)
        for it in items:
            content = (it.get("content") or {}).get("rendered", "")
            link = it.get("link")
            title = htmllib.unescape(BeautifulSoup((it.get("title") or {}).get("rendered", ""), "lxml").get_text())
            text = html_fragment_to_text(content)
            if len(text) < 200 and link:  # page-builder content missing from REST -> fetch the page
                try:
                    body, _ = sess.get(link, sub=f"{sid}/pages")
                    text = html_page_to_text(body.decode("utf-8", "ignore"), link) or text
                except Exception as e:  # noqa: BLE001
                    _fail(failures, sid, link, "fetch_page", e)
            terms = found.get(it["id"], {}).get("terms", [])
            docs.append(_doc(sid, link, title, text, published_at=dates.wp_local_to_iso(it.get("date")),
                             date_source="wp_api.date", raw_ref=f"{api}/{it['id']}", fetched_at=meta.get("fetched_at"),
                             via="search:" + "|".join(terms[:5]), extra={"wp_id": it["id"]}))
            # first PDF attached to the article on the same host
            host = urlparse(link or "").netloc
            for href in links_in_fragment(content):
                if DOC_EXT.search(href) and urlparse(href).netloc in ("", host):
                    docs += fetch_document(sess, sid, urljoin(link, href), failures, via=f"attachment_of:{link}")
                    break
        log.info("[%s] fetched %d/%d posts", sid, min(i + batch, len(ids)), len(ids))
    return docs


# ------------------------------------------------------------------ adapters
def year_windows(date_from: str, date_to: str) -> list[tuple[str, str]]:
    """Calendar-year slices of the window, newest first: 2026-01-01..date_to, 2025, ..., date_from..2021-12-31."""
    out = []
    for y in range(int(date_to[:4]), int(date_from[:4]) - 1, -1):
        out.append((max(date_from, f"{y}-01-01"), min(date_to, f"{y}-12-31")))
    return out


def adapter_wordpress(sess, src, failures, ctx):
    """Year by year, newest first; each year is saved (ctx['on_docs']) as soon as it is fetched,
    so recent data is usable while older years are still running."""
    sid = src["source_id"]
    docs, seen = [], set()
    windows = year_windows(ctx["date_from"], ctx["date_to"]) if not ctx["budget"] else [(ctx["date_from"], ctx["date_to"])]
    for wf, wt in windows:
        found = wp_discover(sess, src, failures, {**ctx, "date_from": wf, "date_to": wt})
        found = {k: v for k, v in found.items() if k not in seen}
        seen.update(found)
        n_found = len(found)
        if src.get("prefilter_excerpt"):
            # title + summary come with the search results; skip the full download when neither holds a keyword
            found = {k: v for k, v in found.items()
                     if ctx["tagger"].has_any(BeautifulSoup(v["title"] + " " + v["excerpt"], "lxml").get_text(" "))}
            ctx["stats"][f"{sid}_skipped_by_summary"] += n_found - len(found)
        log.info("[%s] %s..%s: %d candidates, %d to download", sid, wf, wt, n_found, len(found))
        got = wp_fetch(sess, src, failures, found)
        ctx["on_docs"](got)
        docs += got
        if ctx["budget"] and len(docs) >= ctx["budget"]:
            break
    return docs


def adapter_kilimo(sess, src, failures, ctx):
    sid, disc = src["source_id"], src["discovery"]
    docs = []
    # press-release page: PDF / DOCX downloads; keep those whose upload month is inside the window
    try:
        body, _ = sess.get(disc["press_release_page"], sub=f"{sid}/pages")
        soup = BeautifulSoup(body, "lxml")
        links, seen = [], set()
        for a in soup.find_all("a", href=True):
            href = urljoin(disc["press_release_page"], a["href"])
            if DOC_EXT.search(href) and "/wp-content/uploads/" in href and href not in seen:
                seen.add(href)
                links.append((href, a.get_text(" ", strip=True)))
        links = [(h, t) for h, t in links if (dates.upload_month_hint(h) or "9999") >= ctx["date_from"][:7]]
        links.sort(key=lambda x: dates.upload_month_hint(x[0]) or "", reverse=True)
        if ctx["budget"]:
            links = links[:max(1, ctx["budget"] // 4)]
        log.info("[%s] %d press-release documents in window", sid, len(links))
        for href, txt in links:
            title = txt if txt and txt.upper() != "DOWNLOAD" else None
            docs += fetch_document(sess, sid, href, failures, via="press_release_page", title_hint=title)
        ctx["on_docs"](docs)
    except Exception as e:  # noqa: BLE001
        _fail(failures, sid, disc["press_release_page"], "press_release_page", e)
    docs += adapter_wordpress(sess, src, failures, ctx)
    return docs


# GAA news URLs are title slugs; only fetch articles whose slug looks food / agriculture related
GAA_SLUG_WORDS = re.compile(
    r"drought|famine|hunger|food|maize|wheat|rice|beans|sorghum|millet|cassava|potato|crop|harvest|farm|agri|"
    r"livestock|cattle|pasture|fertili|seed|irrigat|rain|nino|nina|flood|locust|armyworm|price|unga|ncpb|ndma|"
    r"relief|cereal|milk|dairy|fish|water|starv|malnutrition|hsnp|cash-transfer", re.I)
GAA_NOTICE_KEYWORDS = re.compile(r"agricultur|food|drought|fertili|maize|crop|livestock|famine|relief|NDMA|cereal|farm|irrigation|seed|veterinar", re.I)


def adapter_gaa(sess, src, failures, ctx):
    sid, disc = src["source_id"], src["discovery"]
    budget, tagger = ctx["budget"], ctx["tagger"]
    docs = []

    # 1) News: /allnews is newest-first; walk pages until articles are older than date_from
    news_budget = budget // 2 if budget else None
    n_news, page, done = 0, 0, bool(src.get("skip_news"))
    while not done and page < 2000:
        url = disc["news_list"] + (f"?page={page}" if page else "")
        try:
            body, _ = sess.get(url, sub=f"{sid}/pages")
        except Exception as e:  # noqa: BLE001
            _fail(failures, sid, url, "news_list", e)
            break
        soup = BeautifulSoup(body, "lxml")
        slugs = []
        for a in soup.select("a[href]"):
            href = a["href"]
            if re.match(r"^/[a-z0-9-]{25,}$", href) and href not in slugs:
                slugs.append(href)
        if not slugs:
            break
        for href in slugs:
            # skip before downloading: the URL slug is the title, so no keyword there = no fetch
            if not (GAA_SLUG_WORDS.search(href) or tagger.has_any(href.replace("-", " "))):
                ctx["stats"]["gaa_skipped_slug"] += 1
                continue
            link = urljoin("https://gaa.go.ke/", href)
            try:
                body, meta = sess.get(link, sub=f"{sid}/pages")
            except Exception as e:  # noqa: BLE001
                _fail(failures, sid, link, "fetch_page", e)
                continue
            html = body.decode("utf-8", "ignore")
            psoup = BeautifulSoup(html, "lxml")
            created = psoup.select_one(".post-created")
            pub = dates.drupal_created_to_iso(created.get_text()) if created else None
            if pub and pub[:10] < ctx["date_from"]:
                done = True
                break
            h1 = psoup.find("h1")
            text = html_page_to_text(html, link)
            if not tagger.has_any(h1.get_text() if h1 else "", text):
                ctx["stats"]["gaa_skipped_no_keyword"] += 1
                continue
            docs.append(_doc(sid, link, h1.get_text(strip=True) if h1 else None, text,
                             published_at=pub, date_source="page.post-created", raw_ref=meta["url"],
                             raw_cache_path=meta["raw_path"], fetched_at=meta["fetched_at"], via="news"))
            n_news += 1
            if news_budget and n_news >= news_budget:
                done = True
                break
        page += 1

    # 2) MyGov weekly issues (PDF newspapers) -> one record per page; date from the issue name
    issues = []
    for list_url in disc.get("mygov_issue_pages", []):
        try:
            body, _ = sess.get(list_url, sub=f"{sid}/pages")
        except Exception as e:  # noqa: BLE001
            _fail(failures, sid, list_url, "mygov_issues", e)
            continue
        for a in BeautifulSoup(body, "lxml").find_all("a", href=True):
            if a["href"].lower().endswith(".pdf"):
                full = urljoin("https://gaa.go.ke/", a["href"].replace("/index.php/sites/", "/sites/"))
                name = unquote(full.rsplit("/", 1)[-1])
                d = dates.find_date_in_text(name)  # "MyGov October 13, 2026.pdf"
                if full not in [i[0] for i in issues] and in_range(ctx, d):
                    issues.append((full, name, d))
    issues.sort(key=lambda x: x[2], reverse=True)
    if budget:
        issues = issues[:1]
    log.info("[%s] %d MyGov issues in window", sid, len(issues))
    for url, name, d in issues:
        pages = fetch_document(sess, sid, url, failures, via="mygov_issue", title_hint=name.rsplit(".", 1)[0],
                               split_pages=True, date_override=(d, "issue_title"))
        # most MyGov pages are tenders, jobs, ads: drop pages with no keyword before classification
        kept_pages = [p for p in pages if tagger.has_any(p["text"])]
        ctx["stats"]["mygov_pages_skipped_no_keyword"] += len(pages) - len(kept_pages)
        ctx["on_docs"](kept_pages)  # save issue by issue
        docs += kept_pages

    # 3) Public notices (current listing only): PDFs whose link text is agri / food related
    try:
        body, _ = sess.get(disc["public_notices"], sub=f"{sid}/pages")
        picked = []
        for a in BeautifulSoup(body, "lxml").find_all("a", href=True):
            txt = a.get_text(" ", strip=True)
            if a["href"].lower().endswith(".pdf") and GAA_NOTICE_KEYWORDS.search(txt):
                # links are published as /index.php/sites/default/... ; the file lives at /sites/default/...
                picked.append((urljoin("https://gaa.go.ke/", a["href"].replace("/index.php/sites/", "/sites/")), txt))
        notices = []
        for url, txt in picked[: (2 if budget else None)]:
            notices += fetch_document(sess, sid, url, failures, via="public_notice", title_hint=txt)
        ctx["on_docs"](notices)
        docs += notices
    except Exception as e:  # noqa: BLE001
        _fail(failures, sid, disc["public_notices"], "public_notices", e)
    return docs


ADAPTERS = {"wordpress": adapter_wordpress, "kilimo": adapter_kilimo, "gaa": adapter_gaa}
